"""Single-row editor with T-OLP–style labels; writes back to the main grid model."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
from PySide6 import QtCore, QtWidgets

from hanwha_mdb_edit.core.column_labels import label_and_tooltip_for_column

if TYPE_CHECKING:
    from hanwha_mdb_edit.gui.editor_window import HanwhaMdbEditorWindow

_DETAIL_FIRST = (
    "PARTNAME",
    "PROFILENAME",
    "PARTDESC",
    "PARENTPROFILE",
    "UPDPARTGROUPID",
    "FEEDINGSPEEDLEVEL",
    "OVERALL_SPEED_LEVEL",
    "CONFIDENCE_LEVEL",
    "USED_MACHINE_SET",
    "VENDORID",
)


class HanwhaPartDetailWindow(QtWidgets.QWidget):
    def __init__(self, editor: HanwhaMdbEditorWindow, *, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._editor = editor
        self._row = -1
        self._edits: dict[str, QtWidgets.QLineEdit] = {}
        self.setWindowTitle("Hanwha MDB edit — component (WIP)")
        self.setWindowFlag(QtCore.Qt.WindowType.Window, True)
        self.setWindowFlag(QtCore.Qt.WindowType.Tool, True)
        self.resize(520, 640)

        root = QtWidgets.QVBoxLayout(self)
        self._subtitle = QtWidgets.QLabel()
        self._subtitle.setWordWrap(True)
        root.addWidget(self._subtitle)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QtWidgets.QWidget()
        self._form = QtWidgets.QFormLayout(inner)
        self._form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        row_btn = QtWidgets.QHBoxLayout()
        apply_btn = QtWidgets.QPushButton("Apply to grid")
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self._apply)
        row_btn.addWidget(apply_btn)
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        row_btn.addWidget(close_btn)
        row_btn.addStretch()
        root.addLayout(row_btn)

    def rebuild(self, source_row: int) -> None:
        self._row = source_row
        while self._form.rowCount():
            self._form.removeRow(0)
        self._edits.clear()

        m = self._editor.source_model()
        df = m.get_dataframe()
        if source_row < 0 or source_row >= len(df):
            self._subtitle.setText("No row.")
            return

        row = df.iloc[source_row]
        pn = row.get("PARTNAME", "")
        self._subtitle.setText(
            f"Editing source row {source_row + 1}. Values here are the same cells as in the main table."
        )
        self.setWindowTitle(f"Component (WIP) — {pn}")

        cols = list(df.columns)
        ordered: list[str] = []
        for c in _DETAIL_FIRST:
            if c in cols:
                ordered.append(c)
        rest = [c for c in cols if c not in ordered]
        rest.sort(key=lambda c: label_and_tooltip_for_column(str(c))[0].lower())
        ordered.extend(rest)

        for col in ordered:
            label_text, tip = label_and_tooltip_for_column(str(col))
            le = QtWidgets.QLineEdit()
            v = row[col]
            if pd.isna(v):
                le.setText("")
            else:
                le.setText(str(v))
            le.setToolTip(tip)
            lbl = QtWidgets.QLabel(label_text)
            lbl.setToolTip(tip)
            self._form.addRow(lbl, le)
            self._edits[str(col)] = le

    def _apply(self) -> None:
        if self._row < 0:
            return
        patch = {k: w.text() for k, w in self._edits.items()}
        ok = self._editor.source_model().apply_row_patch(self._row, patch)
        if not ok:
            QtWidgets.QMessageBox.warning(self, "Component editor", "Could not apply values (check number formats).")
