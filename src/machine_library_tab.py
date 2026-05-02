"""WIP: Machine library — Hanwha UPD .mdb preview (PART_Det via mdbtools)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Set

from PySide6 import QtCore, QtWidgets

from hanwha_mdb_edit.gui import open_hanwha_mdb_editor

from machine_library.hanwha_mdbtools import (
    HanwhaMdbToolsError,
    list_mdb_tables,
    load_part_det_from_mdb,
    part_det_rows_to_dataframe,
)
from qt_models import SortableTableModel


class MachineLibraryTab(QtWidgets.QWidget):
    """Browse Hanwha-style UPD .mdb; show PART_Det (machine part names)."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._mdb_path: str = ""
        self._table_model = SortableTableModel(part_det_rows_to_dataframe([]))

        layout = QtWidgets.QVBoxLayout(self)
        hint = QtWidgets.QLabel(
            "Hanwha/Samsung UPD library (.mdb): requires <b>mdbtools</b> "
            "(<code>mdb-tables</code>, <code>mdb-export</code>) on PATH. "
            "Machine component names are in table <b>PART_Det</b> → column <b>PARTNAME</b>."
        )
        hint.setWordWrap(True)
        hint.setTextFormat(QtCore.Qt.TextFormat.RichText)
        layout.addWidget(hint)

        row = QtWidgets.QHBoxLayout()
        self._path_label = QtWidgets.QLabel("<no .mdb loaded>")
        self._path_label.setWordWrap(True)
        row.addWidget(self._path_label, 1)
        browse = QtWidgets.QPushButton("Open .mdb…")
        browse.clicked.connect(self._browse_mdb)
        row.addWidget(browse)
        reload_btn = QtWidgets.QPushButton("Reload PART_Det")
        reload_btn.clicked.connect(self._reload_part_det)
        row.addWidget(reload_btn)
        edit_btn = QtWidgets.QPushButton("EDIT HANWHA MDB")
        edit_btn.setToolTip("Edit PART_Det in a separate window (Hanwha UPD library)")
        edit_btn.clicked.connect(self._open_hanwha_editor)
        row.addWidget(edit_btn)
        layout.addLayout(row)

        self._hanwha_editor_window: Optional[QtWidgets.QMainWindow] = None

        self._tables_label = QtWidgets.QLabel("")
        self._tables_label.setWordWrap(True)
        layout.addWidget(self._tables_label)

        self._table = QtWidgets.QTableView()
        self._table.setAlternatingRowColors(True)
        self._table.setModel(self._table_model)
        layout.addWidget(self._table, 1)

    def loaded_mdb_path(self) -> str:
        """Absolute path of the library opened on this tab, or empty."""
        return self._mdb_path or ""

    def hanwha_partname_set(self) -> Set[str]:
        """PARTNAME values from the current PART_Det preview (for Clean BOM «From Hanwha MDB»)."""
        df = self._table_model.get_dataframe()
        if df is None or df.empty or "PARTNAME" not in df.columns:
            return set()
        out: Set[str] = set()
        for x in df["PARTNAME"].tolist():
            t = str(x).strip()
            if t:
                out.add(t)
        return out

    def _browse_mdb(self) -> None:
        start = os.path.expanduser("~")
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Hanwha UPD library (.mdb)",
            start,
            "Access database (*.mdb *.MDB);;All (*.*)",
        )
        if path:
            self._mdb_path = path
            self._path_label.setText(path)
            self._reload_tables_and_parts()

    def _reload_tables_and_parts(self) -> None:
        if not self._mdb_path:
            return
        p = Path(self._mdb_path)
        try:
            tables = list_mdb_tables(p)
        except HanwhaMdbToolsError as e:
            self._tables_label.setText(f"mdb-tables: {e}")
            return
        preview = ", ".join(tables[:12])
        if len(tables) > 12:
            preview += f" … (+{len(tables) - 12} more)"
        self._tables_label.setText(f"{len(tables)} tables: {preview}")
        self._reload_part_det()

    def _reload_part_det(self) -> None:
        if not self._mdb_path:
            QtWidgets.QMessageBox.information(self, "Machine library", "Select an .mdb file first.")
            return
        try:
            rows = load_part_det_from_mdb(self._mdb_path)
        except HanwhaMdbToolsError as e:
            QtWidgets.QMessageBox.warning(self, "Machine library", str(e))
            return
        df = part_det_rows_to_dataframe(rows)
        self._table_model.update_dataframe(df)

    def _open_hanwha_editor(self) -> None:
        def _sync_path_chosen(p: str) -> None:
            self._mdb_path = p
            self._path_label.setText(p)
            self._reload_tables_and_parts()

        win = open_hanwha_mdb_editor(
            self,
            self._mdb_path or None,
            on_saved=self._reload_part_det,
            on_path_chosen=_sync_path_chosen,
        )
        if win is not None:
            self._hanwha_editor_window = win
