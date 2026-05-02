"""PySide6 window for editing PART_Det + joined profile/base/speed columns (Hanwha UPD .mdb)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
from PySide6 import QtCore, QtGui, QtWidgets

from hanwha_mdb_edit.core.errors import HanwhaSaveError, HanwhaValidationError
from hanwha_mdb_edit.core.part_bulk import (
    bulk_update_paren_profile,
    bulk_update_speed_feed,
    bulk_update_speed_feed_all_matching_paren,
    bulk_update_speed_overall,
    bulk_update_speed_overall_all_matching_paren,
)
from hanwha_mdb_edit.core.column_labels import build_column_header_metadata, format_column_for_checklist
from hanwha_mdb_edit.core.part_enriched import load_wide_editor_dataframe
from hanwha_mdb_edit.core.save import SaveResult, save_enriched_library
from hanwha_mdb_edit.gui.column_settings_window import (
    HanwhaMdbColumnSettingsWindow,
    column_settings_qsettings_group,
)
from hanwha_mdb_edit.gui.part_detail_window import HanwhaPartDetailWindow
from hanwha_mdb_edit.gui.part_filter_proxy import HanwhaPartLibraryFilterProxy
from machine_library.hanwha_mdbtools import HanwhaMdbToolsError
from qt_models import PandasTableModel
from working_copy import save_snapshot
from working_copy_ui import prompt_recover_snapshot


class HanwhaMdbEditorWindow(QtWidgets.QMainWindow):
    """Editor: PART_Det plus BASE profile (PARENTPROFILE), feeding / overall speed levels."""

    def __init__(
        self,
        mdb_path: str,
        parent: Optional[QtWidgets.QWidget] = None,
        *,
        on_saved: Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent)
        self._mdb_path = Path(mdb_path).resolve()
        self._on_saved = on_saved
        self._source_model = PandasTableModel(pd.DataFrame(), editable=True)
        self._proxy = HanwhaPartLibraryFilterProxy(self)
        self._proxy.setSourceModel(self._source_model)
        self._column_settings_win: HanwhaMdbColumnSettingsWindow | None = None
        self._part_detail_win: HanwhaPartDetailWindow | None = None
        self._column_settings_group = column_settings_qsettings_group(self._mdb_path)

        app_data = QtCore.QStandardPaths.writableLocation(
            QtCore.QStandardPaths.StandardLocation.AppDataLocation
        )
        self._hanwha_autosave_dir = os.path.join(
            app_data or os.path.expanduser("~/.local/share/BoomerTools"),
            "autosave",
            "hanwha_mdb",
        )
        self._hanwha_dirty = False
        self._hanwha_loading = False
        self._hanwha_autosave_timer = QtCore.QTimer(self)
        self._hanwha_autosave_timer.setSingleShot(True)
        self._hanwha_autosave_timer.timeout.connect(self._autosave_hanwha_working_copy)

        self.setWindowTitle(f"Hanwha MDB editor (WIP) — {self._mdb_path.name}")
        self.resize(1100, 620)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        self._path_label = QtWidgets.QLabel(str(self._mdb_path))
        self._path_label.setWordWrap(True)
        self._path_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._path_label)

        legend = QtWidgets.QLabel(
            "<b>WIP — Wide load:</b> merged tables as <code>Table__column</code>. "
            "Column headers use <b>T-OLP–style names</b> (tooltip shows the real MDB field). "
            "<b>Hide standard library (S)</b> only affects the table view — "
            "<code>Save</code> still writes the full library. "
            "Unsaved edits can be recovered after a crash via the same autosave mechanism as BOM/PnP. "
            "<b>Component…</b> edits the selected row with the same labels."
        )
        legend.setWordWrap(True)
        legend.setTextFormat(QtCore.Qt.TextFormat.RichText)
        layout.addWidget(legend)

        toolbar = QtWidgets.QHBoxLayout()
        reload_btn = QtWidgets.QPushButton("Reload")
        reload_btn.setToolTip("Reload from the .mdb file on disk (skip recovered autosave)")
        reload_btn.clicked.connect(lambda: self._reload(force_original=True))
        toolbar.addWidget(reload_btn)
        save_btn = QtWidgets.QPushButton("Save")
        save_btn.clicked.connect(self._save)
        toolbar.addWidget(save_btn)
        cfg_btn = QtWidgets.QPushButton("Config…")
        cfg_btn.setToolTip("Open column visibility (saved per this .mdb file)")
        cfg_btn.clicked.connect(self._open_column_config)
        toolbar.addWidget(cfg_btn)
        comp_btn = QtWidgets.QPushButton("Component…")
        comp_btn.setToolTip("Edit the selected row in a separate window (friendly field names)")
        comp_btn.clicked.connect(self._open_part_detail)
        toolbar.addWidget(comp_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        filt_row = QtWidgets.QHBoxLayout()
        self._chk_hide_standard_s = QtWidgets.QCheckBox(
            "Hide standard library (S) — parts with «__…» name or [STDVER.] in description"
        )
        self._chk_hide_standard_s.setToolTip(
            "Matches T-OLP vendor «S» library rows. Hidden rows are not removed from the file on Save."
        )
        _fs = QtCore.QSettings("Boomer", "HanwhaMdbEdit")
        _fs.beginGroup(self._column_settings_group)
        _hide_val = _fs.value("hide_standard_library_s", True)
        _fs.endGroup()
        self._chk_hide_standard_s.setChecked(_hide_val not in (False, "false", "0", "no"))
        self._chk_hide_standard_s.toggled.connect(self._on_hide_standard_s_toggled)
        filt_row.addWidget(self._chk_hide_standard_s)
        filt_row.addStretch()
        layout.addLayout(filt_row)

        bulk = QtWidgets.QGroupBox("Bulk edit")
        brow = QtWidgets.QHBoxLayout(bulk)
        b1 = QtWidgets.QPushButton("Bulk BASE profile…")
        b1.setToolTip("Set PARENTPROFILE where it matches a value (parent/base template)")
        b1.clicked.connect(self._bulk_base)
        brow.addWidget(b1)
        b2 = QtWidgets.QPushButton("Bulk feeding speed…")
        b2.setToolTip("FEEDINGSPEEDLEVEL for one profile or all rows with same BASE")
        b2.clicked.connect(self._bulk_feed_speed)
        brow.addWidget(b2)
        b3 = QtWidgets.QPushButton("Bulk Q speed…")
        b3.setToolTip("OVERALL_SPEED_LEVEL for one profile or all rows with same BASE")
        b3.clicked.connect(self._bulk_q_speed)
        brow.addWidget(b3)
        layout.addWidget(bulk)

        self._table = QtWidgets.QTableView()
        self._table.setAlternatingRowColors(True)
        self._table.setModel(self._proxy)
        self._table.setSortingEnabled(True)
        layout.addWidget(self._table, 1)

        self._source_model.dataChanged.connect(self._on_hanwha_grid_changed)

        self.statusBar().showMessage("Ready")

        self._reload()

    def _on_hanwha_grid_changed(self, *_args: object) -> None:
        if self._hanwha_loading:
            return
        self._hanwha_dirty = True
        self._hanwha_autosave_timer.start(1500)

    def _autosave_hanwha_working_copy(self) -> None:
        if not self._hanwha_dirty:
            return
        try:
            save_snapshot(
                self._source_model.get_dataframe(),
                str(self._mdb_path),
                "hanwha_mdb",
                self._hanwha_autosave_dir,
                dirty=True,
            )
        except Exception:
            pass

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self._column_settings_win is not None:
            self._column_settings_win.close()
            self._column_settings_win = None
        if self._part_detail_win is not None:
            self._part_detail_win.close()
            self._part_detail_win = None
        super().closeEvent(event)

    def source_model(self) -> PandasTableModel:
        return self._source_model

    def format_column_for_config_list(self, column_name: str) -> str:
        return format_column_for_checklist(column_name)

    def column_names(self) -> list[str]:
        return list(self._source_model.get_dataframe().columns)

    def load_hidden_columns(self) -> set[str]:
        s = QtCore.QSettings("Boomer", "HanwhaMdbEdit")
        s.beginGroup(self._column_settings_group)
        raw = s.value("hidden", [])
        s.endGroup()
        if not raw:
            return set()
        if isinstance(raw, str):
            return {raw} if raw else set()
        return {str(x) for x in raw}

    def apply_column_visibility(self, hidden: set[str], *, persist: bool = True) -> None:
        cols = list(self._source_model.get_dataframe().columns)
        hidden = {c for c in hidden if c in cols}
        for i, col in enumerate(cols):
            self._table.setColumnHidden(i, col in hidden)
        if persist:
            s = QtCore.QSettings("Boomer", "HanwhaMdbEdit")
            s.beginGroup(self._column_settings_group)
            s.setValue("hidden", sorted(hidden))
            s.endGroup()

    def _open_column_config(self) -> None:
        if self._column_settings_win is None:
            self._column_settings_win = HanwhaMdbColumnSettingsWindow(self)
            self._column_settings_win.destroyed.connect(self._on_column_settings_destroyed)
        self._column_settings_win.show()
        self._column_settings_win.raise_()
        self._column_settings_win.activateWindow()
        self._column_settings_win.rebuild_from_editor()

    def _on_column_settings_destroyed(self) -> None:
        self._column_settings_win = None

    def _on_hide_standard_s_toggled(self, checked: bool) -> None:
        self._proxy.set_hide_standard_s(checked)
        s = QtCore.QSettings("Boomer", "HanwhaMdbEdit")
        s.beginGroup(self._column_settings_group)
        s.setValue("hide_standard_library_s", checked)
        s.endGroup()

    def _selected_source_row(self) -> int | None:
        sel = self._table.selectionModel().selectedRows()
        if not sel:
            return None
        src = self._proxy.mapToSource(sel[0])
        if not src.isValid():
            return None
        return src.row()

    def _open_part_detail(self) -> None:
        row = self._selected_source_row()
        if row is None:
            QtWidgets.QMessageBox.information(self, "Component editor", "Select a row in the table.")
            return
        if self._part_detail_win is None:
            self._part_detail_win = HanwhaPartDetailWindow(self)
            self._part_detail_win.destroyed.connect(self._on_part_detail_destroyed)
        self._part_detail_win.rebuild(row)
        self._part_detail_win.show()
        self._part_detail_win.raise_()
        self._part_detail_win.activateWindow()

    def _on_part_detail_destroyed(self) -> None:
        self._part_detail_win = None

    def _reload(self, *, force_original: bool = False) -> None:
        path = str(self._mdb_path)
        recovered = None if force_original else prompt_recover_snapshot(self, path, "hanwha_mdb", self._hanwha_autosave_dir)
        if isinstance(recovered, str) and recovered == "cancel":
            return
        self._hanwha_loading = True
        try:
            if isinstance(recovered, pd.DataFrame):
                df = recovered
                self._hanwha_dirty = True
            else:
                try:
                    df = load_wide_editor_dataframe(self._mdb_path)
                except HanwhaMdbToolsError as e:
                    QtWidgets.QMessageBox.warning(self, "Hanwha MDB editor", str(e))
                    self.statusBar().showMessage("Load failed")
                    return
                except OSError as e:
                    QtWidgets.QMessageBox.warning(self, "Hanwha MDB editor", str(e))
                    self.statusBar().showMessage("Load failed")
                    return
                self._hanwha_dirty = False
            disp, tips = build_column_header_metadata(df.columns)
            self._source_model.update_dataframe(df)
            self._source_model.set_column_header_metadata(disp, tips)
            self._proxy.sync_column_indices(list(df.columns))
            self._proxy.set_hide_standard_s(self._chk_hide_standard_s.isChecked())
            hidden = self.load_hidden_columns()
            hidden = {c for c in hidden if c in df.columns}
            self.apply_column_visibility(hidden, persist=True)
            if self._column_settings_win is not None:
                self._column_settings_win.rebuild_from_editor()
            self.statusBar().showMessage(f"Loaded {len(df)} rows, {len(df.columns)} columns")
        finally:
            self._hanwha_loading = False

    def _save(self) -> None:
        df = self._source_model.get_dataframe()
        try:
            result = save_enriched_library(self._mdb_path, df)
        except HanwhaValidationError as e:
            QtWidgets.QMessageBox.warning(self, "Validation", str(e))
            return
        except HanwhaSaveError as e:
            QtWidgets.QMessageBox.warning(self, "Save", str(e))
            return
        self._notify_saved(result)
        self._hanwha_dirty = False
        try:
            save_snapshot(
                self._source_model.get_dataframe(),
                str(self._mdb_path),
                "hanwha_mdb",
                self._hanwha_autosave_dir,
                dirty=False,
            )
        except Exception:
            pass

    def _notify_saved(self, result: SaveResult) -> None:
        backup = result.backup_path
        paths = "\n".join(str(p) for p in result.exported_paths)
        if result.mode == "mdb_pyodbc":
            msg = "Library tables updated via ODBC (PART + profiles).\n\n" f"Backup:\n{backup}\n\nCSV snapshots:\n{paths}"
        else:
            msg = (
                "Backup created. CSV snapshots written (Linux cannot patch Jet in place via mdb-sql).\n\n"
                f"Backup:\n{backup}\n\nFiles:\n{paths}"
            )
        QtWidgets.QMessageBox.information(self, "Saved", msg)
        self.statusBar().showMessage(f"Saved ({result.mode})")
        if self._on_saved is not None:
            self._on_saved()

    def _df(self) -> pd.DataFrame:
        return self._source_model.get_dataframe()

    def _set_df(self, df: pd.DataFrame) -> None:
        disp, tips = build_column_header_metadata(df.columns)
        self._source_model.update_dataframe(df)
        self._source_model.set_column_header_metadata(disp, tips)
        self._proxy.sync_column_indices(list(df.columns))
        if not self._hanwha_loading:
            self._hanwha_dirty = True
            self._hanwha_autosave_timer.start(1500)

    def _bulk_base(self) -> None:
        df = self._df()
        if df.empty or "PARENTPROFILE" not in df.columns:
            QtWidgets.QMessageBox.information(self, "Bulk BASE", "No PARENTPROFILE column.")
            return
        uniq = sorted({str(x) for x in df["PARENTPROFILE"].dropna().unique()})
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Bulk — BASE profile (PARENTPROFILE)")
        form = QtWidgets.QFormLayout(dlg)
        cb = QtWidgets.QComboBox()
        cb.setEditable(True)
        cb.addItems([""] + uniq)
        form.addRow("Where PARENTPROFILE equals", cb)
        ne = QtWidgets.QLineEdit()
        form.addRow("Set new PARENTPROFILE", ne)
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        form.addRow(bb)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        old_v = cb.currentText().strip()
        new_v = ne.text().strip()
        if not new_v:
            QtWidgets.QMessageBox.warning(self, "Bulk BASE", "Enter new PARENTPROFILE.")
            return
        self._set_df(bulk_update_paren_profile(df, old_v, new_v))
        self.statusBar().showMessage("Bulk BASE applied (not saved yet)")

    def _bulk_feed_speed(self) -> None:
        df = self._df()
        if df.empty:
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Bulk — FEEDINGSPEEDLEVEL")
        v = QtWidgets.QVBoxLayout(dlg)
        mode = QtWidgets.QComboBox()
        mode.addItems(["By PROFILENAME", "All rows with same PARENTPROFILE (BASE)"])
        v.addWidget(mode)
        prof = QtWidgets.QComboBox()
        prof.setEditable(True)
        if "PROFILENAME" in df.columns:
            prof.addItems(sorted({str(x) for x in df["PROFILENAME"].dropna().unique()}))
        v.addWidget(QtWidgets.QLabel("PROFILENAME (mode 1) / ignored in mode 2"))
        v.addWidget(prof)
        paren = QtWidgets.QComboBox()
        paren.setEditable(True)
        if "PARENTPROFILE" in df.columns:
            paren.addItems(sorted({str(x) for x in df["PARENTPROFILE"].dropna().unique()}))
        v.addWidget(QtWidgets.QLabel("PARENTPROFILE filter (mode 2)"))
        v.addWidget(paren)
        sp = QtWidgets.QSpinBox()
        sp.setRange(-999999, 999999)
        sp.setValue(2)
        v.addWidget(QtWidgets.QLabel("New FEEDINGSPEEDLEVEL"))
        v.addWidget(sp)
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        v.addWidget(bb)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        val = int(sp.value())
        if mode.currentIndex() == 0:
            pn = prof.currentText().strip()
            if not pn:
                return
            self._set_df(bulk_update_speed_feed(df, pn, val))
        else:
            bp = paren.currentText().strip()
            self._set_df(bulk_update_speed_feed_all_matching_paren(df, bp, val))
        self.statusBar().showMessage("Bulk feeding speed applied (not saved yet)")

    def _bulk_q_speed(self) -> None:
        df = self._df()
        if df.empty:
            return
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Bulk — OVERALL_SPEED_LEVEL (Q_HANDDATA)")
        v = QtWidgets.QVBoxLayout(dlg)
        mode = QtWidgets.QComboBox()
        mode.addItems(["By PROFILENAME", "All rows with same PARENTPROFILE (BASE)"])
        v.addWidget(mode)
        prof = QtWidgets.QComboBox()
        prof.setEditable(True)
        if "PROFILENAME" in df.columns:
            prof.addItems(sorted({str(x) for x in df["PROFILENAME"].dropna().unique()}))
        v.addWidget(QtWidgets.QLabel("PROFILENAME (mode 1)"))
        v.addWidget(prof)
        paren = QtWidgets.QComboBox()
        paren.setEditable(True)
        if "PARENTPROFILE" in df.columns:
            paren.addItems(sorted({str(x) for x in df["PARENTPROFILE"].dropna().unique()}))
        v.addWidget(QtWidgets.QLabel("PARENTPROFILE filter (mode 2)"))
        v.addWidget(paren)
        sp = QtWidgets.QSpinBox()
        sp.setRange(-999999, 999999)
        sp.setValue(3)
        v.addWidget(QtWidgets.QLabel("New OVERALL_SPEED_LEVEL"))
        v.addWidget(sp)
        bb = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        v.addWidget(bb)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        val = int(sp.value())
        if mode.currentIndex() == 0:
            pn = prof.currentText().strip()
            if not pn:
                return
            self._set_df(bulk_update_speed_overall(df, pn, val))
        else:
            bp = paren.currentText().strip()
            self._set_df(bulk_update_speed_overall_all_matching_paren(df, bp, val))
        self.statusBar().showMessage("Bulk Q speed applied (not saved yet)")


def pick_mdb_path(parent: QtWidgets.QWidget) -> Optional[str]:
    start = os.path.expanduser("~")
    path, _ = QtWidgets.QFileDialog.getOpenFileName(
        parent,
        "Select Hanwha UPD library (.mdb)",
        start,
        "Access database (*.mdb *.MDB);;All (*.*)",
    )
    return path or None


def open_hanwha_mdb_editor(
    parent: QtWidgets.QWidget,
    mdb_path: Optional[str],
    *,
    on_saved: Optional[Callable[[], None]] = None,
    on_path_chosen: Optional[Callable[[str], None]] = None,
) -> Optional[HanwhaMdbEditorWindow]:
    """Open editor window; optionally prompt for path when ``mdb_path`` is empty."""
    path = (mdb_path or "").strip()
    if not path:
        path = pick_mdb_path(parent) or ""
        if not path:
            return None
        if on_path_chosen is not None:
            on_path_chosen(path)
    win = HanwhaMdbEditorWindow(path, parent=None, on_saved=on_saved)
    win.show()
    return win
