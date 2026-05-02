"""Separate tool window: show/hide Hanwha MDB editor table columns (persisted via QSettings)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtWidgets

if TYPE_CHECKING:
    from hanwha_mdb_edit.gui.editor_window import HanwhaMdbEditorWindow


def column_settings_qsettings_group(mdb_path: str | Path) -> str:
    """Stable QSettings subgroup for one library file (path hash, not full path in keys)."""
    p = str(Path(mdb_path).resolve())
    h = hashlib.sha256(p.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"columns/{h}"


class HanwhaMdbColumnSettingsWindow(QtWidgets.QWidget):
    """Non-modal column visibility for the Hanwha MDB editor (checklist + filter)."""

    def __init__(self, editor: HanwhaMdbEditorWindow, *, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self._editor = editor
        self.setWindowTitle("Hanwha MDB edit — column config (WIP)")
        self.setWindowFlag(QtCore.Qt.WindowType.Window, True)
        self.setWindowFlag(QtCore.Qt.WindowType.Tool, True)
        self.resize(420, 520)

        root = QtWidgets.QVBoxLayout(self)
        hint = QtWidgets.QLabel(
            "Checked = visible. Settings are saved per library file. "
            "Merged columns from extra tables use the <code>Table__column</code> name."
        )
        hint.setWordWrap(True)
        hint.setTextFormat(QtCore.Qt.TextFormat.RichText)
        root.addWidget(hint)

        self._filter = QtWidgets.QLineEdit()
        self._filter.setPlaceholderText("Filter by column name…")
        self._filter.textChanged.connect(self._apply_filter)
        root.addWidget(self._filter)

        self._list = QtWidgets.QListWidget()
        self._list.setAlternatingRowColors(True)
        root.addWidget(self._list, 1)

        row1 = QtWidgets.QHBoxLayout()
        b_show = QtWidgets.QPushButton("Show all")
        b_show.clicked.connect(self._check_all_visible)
        row1.addWidget(b_show)
        b_hide_merged = QtWidgets.QPushButton("Hide merged (…__)")
        b_hide_merged.setToolTip("Uncheck columns whose names contain '__' (joined extra tables).")
        b_hide_merged.clicked.connect(self._uncheck_merged_prefixed)
        row1.addWidget(b_hide_merged)
        root.addLayout(row1)

        row2 = QtWidgets.QHBoxLayout()
        b_refresh = QtWidgets.QPushButton("Refresh list")
        b_refresh.clicked.connect(self.rebuild_from_editor)
        row2.addWidget(b_refresh)
        b_apply = QtWidgets.QPushButton("Apply")
        b_apply.setDefault(True)
        b_apply.clicked.connect(self._apply_to_editor)
        row2.addWidget(b_apply)
        row2.addStretch()
        root.addLayout(row2)

        self.rebuild_from_editor()

    def rebuild_from_editor(self) -> None:
        self._list.clear()
        cols = self._editor.column_names()
        hidden = self._editor.load_hidden_columns()
        for col in cols:
            it = QtWidgets.QListWidgetItem(self._editor.format_column_for_config_list(col))
            it.setData(QtCore.Qt.ItemDataRole.UserRole, col)
            it.setFlags(
                it.flags()
                | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                | QtCore.Qt.ItemFlag.ItemIsEnabled
            )
            it.setCheckState(
                QtCore.Qt.CheckState.Unchecked if col in hidden else QtCore.Qt.CheckState.Checked
            )
            self._list.addItem(it)
        self._apply_filter(self._filter.text())

    def _apply_filter(self, text: str) -> None:
        t = (text or "").strip().lower()
        for i in range(self._list.count()):
            it = self._list.item(i)
            it.setHidden(bool(t) and t not in it.text().lower())

    def _check_all_visible(self) -> None:
        for i in range(self._list.count()):
            it = self._list.item(i)
            if not it.isHidden():
                it.setCheckState(QtCore.Qt.CheckState.Checked)

    def _uncheck_merged_prefixed(self) -> None:
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it.isHidden():
                continue
            key = it.data(QtCore.Qt.ItemDataRole.UserRole)
            col_key = str(key) if key else it.text()
            if "__" in col_key:
                it.setCheckState(QtCore.Qt.CheckState.Unchecked)

    def _apply_to_editor(self) -> None:
        hidden: set[str] = set()
        for i in range(self._list.count()):
            it = self._list.item(i)
            key = it.data(QtCore.Qt.ItemDataRole.UserRole)
            col_key = str(key) if key else it.text()
            if it.checkState() != QtCore.Qt.CheckState.Checked:
                hidden.add(col_key)
        self._editor.apply_column_visibility(hidden, persist=True)
