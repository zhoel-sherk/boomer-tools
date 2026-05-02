"""
PySide6 desktop GUI for Boomer Tools (BOM / PnP workflows).

(c) 2023-2026 Mariusz Midor
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional, Any
from urllib.parse import quote

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtCore import QSettings, QUrl, Signal
from PySide6.QtGui import QDesktopServices
import pandas as pd

from qt_material import apply_stylesheet

from settings_paths import path_settings_hash
from smt_processor import (
    SMTDataProcessor,
    ColumnConfig,
    ProcessorConfig,
    read_file,
    read_text_whitespace_sp,
    _clean_empty_rows,
    SMTProcessorError,
    SMTEmptyDataError,
)
from qt_models import SortableTableModel
from report_html import (
    html_document_from_fragment,
    result_dataframe_plain_text,
    result_dataframe_to_html,
)

from clean_component import CleanConfig, clean_bom_dataframe, clean_preview
from component_library import append_component, default_components_path
from pn_original import normalize_mpn_bare
from working_copy import save_snapshot
from working_copy_ui import prompt_recover_snapshot

from pcb_preview_tab import PcbPreviewTab
from machine_library_tab import MachineLibraryTab
from ui_i18n import UiI18n

import pnp_coord

import logger

APP_NAME = "Boomer Tools"
APP_VERSION = "0.1.0"
VERSION_DISPLAY = "ALPHA v0.1.0"

SETTINGS_ORG = "Boomer"
SETTINGS_APP = "BoomerTools"

PROFILE_STATE_VERSION = 1
PROFILE_NAMES_KEY = "profiles/names"
PROFILE_LAST_ACTIVE_KEY = "profiles/last_active"

# Hidden from UI: False = treat loaded grids as «no dedicated header row» for core mapping (matches
# full-row preview: «spaces» loader does not promote a row into column names).
HIDDEN_TABLE_HAS_HEADER_ROW = False

LIGHT_THEME = "light_blue.xml"
DARK_THEME = "dark_blue.xml"

# Preview table: numeric column headers only; thin horizontal header under mapping combos.
_PREVIEW_TABLE_HDR_HEIGHT = 22
_MAPPING_COMBO_MAX_HEIGHT = 26

# Cap table column auto-width so BOM/PnP load does not force a multi-screen-wide window.
_TABLE_COL_MAX_WIDTH = 400

# Tab order for i18n (must match addTab sequence in _setup_ui).
_TAB_ORDER_KEYS = (
    "project",
    "bom",
    "pnp",
    "clean_bom",
    "merge",
    "report",
    "pcb_preview",
    "machine_lib",
)


class CrossCheckThread(QtCore.QThread):
    """Runs SMTDataProcessor.cross_check() off the GUI thread."""

    result_ready = QtCore.Signal(object, str)  # DataFrame or None, error message (empty if ok)

    def __init__(self, proc: SMTDataProcessor, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self._proc = proc

    def run(self) -> None:
        try:
            r = self._proc.cross_check()
        except SMTProcessorError as e:
            self.result_ready.emit(None, str(e))
        except Exception as e:
            self.result_ready.emit(None, str(e))
        else:
            self.result_ready.emit(r, "")


class MainWindow(QtWidgets.QMainWindow):
    """Main application window."""

    log_message = QtCore.Signal(str, str)  # message, level

    def __init__(self):
        super().__init__()
        self.resize(1400, 900)
        
        # Data processor
        self.processor = SMTDataProcessor(ProcessorConfig())
        
        # Current data
        self._bom_df: Optional[pd.DataFrame] = None
        self._pnp_df: Optional[pd.DataFrame] = None
        self._result_df: Optional[pd.DataFrame] = None
        
        # Recent files (up to 10)
        self._recent_bom: list[str] = []
        self._recent_pnp: list[str] = []
        self._last_report_html: str = ""
        self._last_merge_df: Optional[pd.DataFrame] = None
        self._restoring_settings: bool = False
        self._settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        app_data = QtCore.QStandardPaths.writableLocation(
            QtCore.QStandardPaths.StandardLocation.AppDataLocation
        )
        self._autosave_dir = os.path.join(
            app_data or os.path.expanduser("~/.local/share/BoomerTools"), "autosave"
        )
        self._current_theme = LIGHT_THEME
        self._cc_thread: Optional[CrossCheckThread] = None
        self._bom_source_path: str = ""
        self._pnp_source_path: str = ""
        self._bom_dirty: bool = False
        self._pnp_dirty: bool = False
        self._loading_working_copy: bool = False
        self._autosave_timer = QtCore.QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.timeout.connect(self._autosave_dirty_working_copies)
        self._bom_ui_restoring = False
        self._pnp_ui_restoring = False
        self._bom_tab_settings_timer = QtCore.QTimer(self)
        self._bom_tab_settings_timer.setSingleShot(True)
        self._bom_tab_settings_timer.timeout.connect(self._save_bom_tab_settings_to_disk)
        self._pnp_tab_settings_timer = QtCore.QTimer(self)
        self._pnp_tab_settings_timer.setSingleShot(True)
        self._pnp_tab_settings_timer.timeout.connect(self._save_pnp_tab_settings_to_disk)

        self._profile_restore_bom_mappings: Optional[list[str]] = None
        self._profile_restore_pnp_mappings: Optional[list[str]] = None

        _raw_lang = self._settings.value("ui/language", "en")
        _lang = str(_raw_lang) if _raw_lang is not None else "en"
        self._i18n = UiI18n(_lang if _lang in ("en", "ru") else "en")
        self.setWindowTitle(self.ui_tr("app.window_title"))

        self._setup_ui()
        self._load_settings()
        self._log(self.ui_tr("msg.app_ready"), "info")

    def ui_tr(self, key: str, **kwargs: Any) -> str:
        """UI string from current language catalog."""
        return self._i18n.tr(key, **kwargs)

    def _setup_ui(self):
        """Build main UI."""
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        main_layout = QtWidgets.QVBoxLayout(central)

        self._wip_banner = QtWidgets.QLabel(self.ui_tr("wip.banner"))
        self._wip_banner.setWordWrap(True)
        self._wip_banner.setStyleSheet(
            "padding: 8px; background-color: #fff3cd; color: #664d03; border-radius: 4px;"
        )
        main_layout.addWidget(self._wip_banner)

        self.tabs = QtWidgets.QTabWidget()
        main_layout.addWidget(self.tabs)

        # Tabs (titles filled via ui_tr inside each _create_* or here — set after add)
        self._create_project_tab()
        self._create_bom_tab()
        self._create_pnp_tab()
        self._create_clean_tab()
        self._create_merge_tab()
        self._create_report_tab()
        self._create_pcb_preview_tab()
        self._create_machine_library_tab()

        self._sync_tab_titles_i18n()

        self.statusBar().showMessage(self.ui_tr("status.ready"))

    def _sync_tab_titles_i18n(self) -> None:
        for i, key in enumerate(_TAB_ORDER_KEYS):
            if i < self.tabs.count():
                self.tabs.setTabText(i, self.ui_tr(f"tab.{key}"))

    def _refresh_static_ui_texts(self) -> None:
        """Re-apply translated strings (after language change)."""
        self.setWindowTitle(self.ui_tr("app.window_title"))
        self._wip_banner.setText(self.ui_tr("wip.banner"))
        self.statusBar().showMessage(self.ui_tr("status.ready"))
        self._sync_tab_titles_i18n()
        self._refresh_project_tab_static_texts()
        if hasattr(self, "_theme_button"):
            dark = self._theme_button.isChecked()
            self._theme_button.setText(self.ui_tr("theme.dark" if dark else "theme.light"))
            self._theme_button.setToolTip(self.ui_tr("theme.tooltip"))

    def _refresh_project_tab_static_texts(self) -> None:
        if not hasattr(self, "project_bom_group"):
            return
        self.project_bom_group.setTitle(self.ui_tr("project.bom_file"))
        self.project_pnp_group.setTitle(self.ui_tr("project.pnp_file"))
        self.project_settings_group.setTitle(self.ui_tr("project.settings"))
        self.project_console_group.setTitle(self.ui_tr("project.console"))
        self.btn_browse_bom.setText(self.ui_tr("project.browse"))
        self.btn_browse_pnp.setText(self.ui_tr("project.browse"))
        self.profile_label.setText(self.ui_tr("project.profile"))
        self.btn_profile_clone.setText(self.ui_tr("project.profile_clone"))
        self.btn_profile_delete.setText(self.ui_tr("project.profile_delete"))
        self.chk_colorful.setText(self.ui_tr("project.colorful_logs"))
        self.lang_label.setText(self.ui_tr("project.language"))
        self.theme_label.setText(self.ui_tr("project.theme"))
        if self._bom_source_path:
            self.bom_path_label.setText(self._bom_source_path)
        else:
            self.bom_path_label.setText(self.ui_tr("project.no_file"))
        if self._pnp_source_path:
            self.pnp_path_label.setText(self._pnp_source_path)
        else:
            self.pnp_path_label.setText(self.ui_tr("project.no_file"))

    def _on_ui_language_changed(self) -> None:
        if getattr(self, "_restoring_settings", False):
            return
        lang = self.lang_combo.currentData()
        if not lang:
            return
        lang_s = str(lang)
        if lang_s not in ("en", "ru"):
            return
        self._apply_ui_language(lang_s, save=True)

    def _apply_ui_language(self, lang: str, *, save: bool = True) -> None:
        if lang not in ("en", "ru"):
            lang = "en"
        self._i18n.set_locale(lang)
        if save:
            self._settings.setValue("ui/language", lang)
        self.lang_combo.blockSignals(True)
        idx = self.lang_combo.findData(lang)
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.blockSignals(False)
        self._refresh_static_ui_texts()

    def _create_project_tab(self):
        """Project tab — file selection, settings (profile, theme, language), console."""
        tab = QtWidgets.QWidget()
        self.tabs.addTab(tab, self.ui_tr("tab.project"))

        layout = QtWidgets.QVBoxLayout(tab)

        self.project_bom_group = QtWidgets.QGroupBox(self.ui_tr("project.bom_file"))
        group_layout = QtWidgets.QHBoxLayout(self.project_bom_group)

        self.bom_path_label = QtWidgets.QLabel(self.ui_tr("project.no_file"))
        group_layout.addWidget(self.bom_path_label, 1)

        self.btn_browse_bom = QtWidgets.QPushButton(self.ui_tr("project.browse"))
        self.btn_browse_bom.clicked.connect(self._browse_bom)
        group_layout.addWidget(self.btn_browse_bom)

        layout.addWidget(self.project_bom_group)

        self.project_pnp_group = QtWidgets.QGroupBox(self.ui_tr("project.pnp_file"))
        group_layout = QtWidgets.QHBoxLayout(self.project_pnp_group)

        self.pnp_path_label = QtWidgets.QLabel(self.ui_tr("project.no_file"))
        group_layout.addWidget(self.pnp_path_label, 1)

        self.btn_browse_pnp = QtWidgets.QPushButton(self.ui_tr("project.browse"))
        self.btn_browse_pnp.clicked.connect(self._browse_pnp)
        group_layout.addWidget(self.btn_browse_pnp)

        layout.addWidget(self.project_pnp_group)

        self.project_settings_group = QtWidgets.QGroupBox(self.ui_tr("project.settings"))
        settings_layout = QtWidgets.QVBoxLayout(self.project_settings_group)

        row_prof = QtWidgets.QHBoxLayout()
        self.profile_label = QtWidgets.QLabel(self.ui_tr("project.profile"))
        row_prof.addWidget(self.profile_label)
        self.profile_combo = QtWidgets.QComboBox()
        self.profile_combo.addItems(["default"])
        row_prof.addWidget(self.profile_combo)
        self.btn_profile_clone = QtWidgets.QPushButton(self.ui_tr("project.profile_clone"))
        row_prof.addWidget(self.btn_profile_clone)
        self.btn_profile_delete = QtWidgets.QPushButton(self.ui_tr("project.profile_delete"))
        row_prof.addWidget(self.btn_profile_delete)
        row_prof.addStretch(1)
        settings_layout.addLayout(row_prof)
        self.profile_combo.currentTextChanged.connect(self._on_profile_combo_changed)
        self.btn_profile_clone.clicked.connect(self._on_profile_clone_clicked)
        self.btn_profile_delete.clicked.connect(self._on_profile_delete_clicked)

        row_ui = QtWidgets.QHBoxLayout()
        self.theme_label = QtWidgets.QLabel(self.ui_tr("project.theme"))
        row_ui.addWidget(self.theme_label)
        self._theme_button = QtWidgets.QPushButton(self.ui_tr("theme.light"))
        self._theme_button.setCheckable(True)
        self._theme_button.setToolTip(self.ui_tr("theme.tooltip"))
        self._theme_button.clicked.connect(self._toggle_theme)
        row_ui.addWidget(self._theme_button)

        row_ui.addSpacing(24)
        self.lang_label = QtWidgets.QLabel(self.ui_tr("project.language"))
        row_ui.addWidget(self.lang_label)
        self.lang_combo = QtWidgets.QComboBox()
        self.lang_combo.addItem("English", "en")
        self.lang_combo.addItem("Русский", "ru")
        li = self.lang_combo.findData(self._i18n.locale)
        self.lang_combo.setCurrentIndex(li if li >= 0 else 0)
        self.lang_combo.currentIndexChanged.connect(lambda *_: self._on_ui_language_changed())
        row_ui.addWidget(self.lang_combo)
        row_ui.addStretch(1)
        settings_layout.addLayout(row_ui)

        layout.addWidget(self.project_settings_group)

        self.project_console_group = QtWidgets.QGroupBox(self.ui_tr("project.console"))
        group_layout = QtWidgets.QVBoxLayout(self.project_console_group)

        self.console = QtWidgets.QTextEdit()
        self.console.setFont(QtGui.QFont("Consolas", 10))
        self.console.setReadOnly(True)
        group_layout.addWidget(self.console)

        self.chk_colorful = QtWidgets.QCheckBox(self.ui_tr("project.colorful_logs"))
        group_layout.addWidget(self.chk_colorful)
        self.chk_colorful.toggled.connect(self._on_colorful_logs_toggled)

        layout.addWidget(self.project_console_group, 1)

        self.log_message.connect(self._on_log_message)
    
    def _build_mapping_row_widgets(
        self,
    ) -> tuple[QtWidgets.QWidget, QtWidgets.QWidget, QtWidgets.QHBoxLayout]:
        """Spacer (row-number column) + plain widget with combo row. No QScrollArea — it hid combos on some styles."""
        spacer = QtWidgets.QWidget()
        inner = QtWidgets.QWidget()
        inner.setMinimumHeight(26)
        inner.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Fixed
        )
        lay = QtWidgets.QHBoxLayout(inner)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        return spacer, inner, lay

    def _wrap_mapping_row(self, spacer: QtWidgets.QWidget, inner: QtWidgets.QWidget) -> QtWidgets.QWidget:
        row = QtWidgets.QWidget()
        row.setMinimumHeight(28)
        h = QtWidgets.QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(spacer)
        h.addWidget(inner, 0, QtCore.Qt.AlignmentFlag.AlignLeft)
        return row

    def _apply_compact_preview_chrome(self, table: QtWidgets.QTableView) -> None:
        """Short horizontal header (labels are only 0,1,… in preview); mapping row sits flush above."""
        hh = table.horizontalHeader()
        hh.setFixedHeight(_PREVIEW_TABLE_HDR_HEIGHT)

    def _style_mapping_combo(self, combo: QtWidgets.QComboBox) -> None:
        combo.setMaximumHeight(_MAPPING_COMBO_MAX_HEIGHT)

    def _connect_mapping_table_signals(self, table: QtWidgets.QTableView, which: str) -> None:
        vh = table.verticalHeader()
        vh.sectionResized.connect(lambda *args, w=which: self._update_mapping_margins(w))
        vh.geometriesChanged.connect(lambda w=which: self._update_mapping_margins(w))

    def _update_mapping_margins(self, which: Optional[str] = None) -> None:
        if which in (None, "_bom") and hasattr(self, "bom_combo_vheader_spacer"):
            self.bom_combo_vheader_spacer.setFixedWidth(self.bom_table.verticalHeader().width())
            self._refresh_bom_mapping_strip()
        if which in (None, "_pnp") and hasattr(self, "pnp_combo_vheader_spacer"):
            self.pnp_combo_vheader_spacer.setFixedWidth(self.pnp_table.verticalHeader().width())
            self._refresh_pnp_mapping_strip()

    def _strip_column_width(self, table: QtWidgets.QTableView, col: int) -> int:
        """Column width for mapping strip. columnWidth is often 0 before first layout; use size hint."""
        w = table.columnWidth(col)
        if w <= 0:
            w = table.sizeHintForColumn(col)
        return min(max(50, w), _TABLE_COL_MAX_WIDTH)

    def _refresh_pnp_mapping_strip(self) -> None:
        if not hasattr(self, "pnp_col_combos") or not self.pnp_col_combos or not hasattr(
            self, "pnp_combo_inner"
        ):
            return
        n = self.pnp_model.columnCount()
        if n <= 0:
            return
        total = sum(self._strip_column_width(self.pnp_table, i) for i in range(n))
        self.pnp_combo_inner.setFixedWidth(
            max(total, len(self.pnp_col_combos) * 50)
        )

    def _refresh_bom_mapping_strip(self) -> None:
        if not hasattr(self, "bom_col_combos") or not self.bom_col_combos or not hasattr(
            self, "bom_combo_inner"
        ):
            return
        n = self.bom_model.columnCount()
        if n <= 0:
            return
        total = sum(self._strip_column_width(self.bom_table, i) for i in range(n))
        self.bom_combo_inner.setFixedWidth(
            max(total, len(self.bom_col_combos) * 60)
        )

    def _on_bom_section_resized(self, idx: int, old: int, new: int) -> None:
        self._sync_bom_combo_width(idx, new)
        self._refresh_bom_mapping_strip()

    def _on_pnp_section_resized(self, idx: int, old: int, new: int) -> None:
        self._sync_pnp_combo_width(idx, new)
        self._refresh_pnp_mapping_strip()

    def _autoresize_bom_columns(self) -> None:
        if not hasattr(self, "bom_table") or self.bom_model.columnCount() <= 0:
            return
        for c in range(self.bom_model.columnCount()):
            self.bom_table.resizeColumnToContents(c)
            w = self.bom_table.columnWidth(c)
            self.bom_table.setColumnWidth(c, min(max(w, 48), _TABLE_COL_MAX_WIDTH))
        self._sync_bom_all_combos_width()

    def _autoresize_pnp_columns(self) -> None:
        if not hasattr(self, "pnp_table") or self.pnp_model.columnCount() <= 0:
            return
        for c in range(self.pnp_model.columnCount()):
            self.pnp_table.resizeColumnToContents(c)
            w = self.pnp_table.columnWidth(c)
            self.pnp_table.setColumnWidth(c, min(max(w, 48), _TABLE_COL_MAX_WIDTH))
        self._sync_pnp_all_combos_width()
    
    def _create_bom_tab(self):
        """BOM tab — table view and column mapping."""
        tab = QtWidgets.QWidget()
        self.tabs.addTab(tab, self.ui_tr("tab.bom"))
        
        layout = QtWidgets.QVBoxLayout(tab)
        
        self.bom_preview_stack = QtWidgets.QWidget()
        bom_pv = QtWidgets.QVBoxLayout(self.bom_preview_stack)
        bom_pv.setContentsMargins(0, 0, 0, 0)
        bom_pv.setSpacing(0)

        self.bom_combo_vheader_spacer, self.bom_combo_inner, self.bom_combos_layout = self._build_mapping_row_widgets()
        bom_pv.addWidget(self._wrap_mapping_row(self.bom_combo_vheader_spacer, self.bom_combo_inner))
        
        self.bom_table = QtWidgets.QTableView()
        self.bom_table.setAlternatingRowColors(True)
        self.bom_model = SortableTableModel(pd.DataFrame(), editable=True)
        self.bom_table.setModel(self.bom_model)
        self.bom_table.horizontalHeader().setMinimumSectionSize(48)
        self._apply_compact_preview_chrome(self.bom_table)
        self.bom_table.horizontalHeader().sectionResized.connect(self._on_bom_section_resized)
        self.bom_model.dataChanged.connect(lambda *args: self._mark_working_dirty("bom"))
        self._connect_mapping_table_signals(self.bom_table, "_bom")
        bom_pv.addWidget(self.bom_table, 1)
        layout.addWidget(self.bom_preview_stack, 1)
        
        # Bottom config row
        config = QtWidgets.QFrame()
        config_layout = QtWidgets.QHBoxLayout(config)

        config_layout.addWidget(QtWidgets.QLabel("Separator:"))
        self.bom_separator = QtWidgets.QComboBox()
        self.bom_separator.addItems(["auto", ",", ";", "\\t", "space"])
        self.bom_separator.setCurrentText("auto")
        self.bom_separator.setMinimumWidth(70)
        config_layout.addWidget(self.bom_separator)

        lbl_first = QtWidgets.QLabel("First row:")
        lbl_first.setToolTip(
            "First line from file to load (1-based). Also defines the highlighted active row range in the table."
        )
        config_layout.addWidget(lbl_first)
        self.bom_first_row = QtWidgets.QLineEdit("1")
        self.bom_first_row.setMaximumWidth(52)
        self.bom_first_row.setToolTip(
            "1 = first line of the file after decode. Empty defaults to 1 when loading."
        )
        config_layout.addWidget(self.bom_first_row)

        lbl_last = QtWidgets.QLabel("Last row:")
        lbl_last.setToolTip(
            "Last line to include when loading (1-based, inclusive with First row). Leave empty to read through the end."
        )
        config_layout.addWidget(lbl_last)
        self.bom_last_row = QtWidgets.QLineEdit("")
        self.bom_last_row.setMaximumWidth(52)
        self.bom_last_row.setToolTip(
            "Last line included in the load range (1-based, inclusive with First row). Empty = through end."
        )
        config_layout.addWidget(self.bom_last_row)
        
        config_layout.addStretch()
        btn_find = QtWidgets.QPushButton("Find / Replace...")
        btn_find.clicked.connect(lambda: self._find_replace_table("bom"))
        config_layout.addWidget(btn_find)
        
        btn = QtWidgets.QPushButton("Reload")
        btn.clicked.connect(self._reload_bom)
        config_layout.addWidget(btn)

        btn_clear_bom = QtWidgets.QPushButton(self.ui_tr("bom.clear_workspace"))
        btn_clear_bom.setToolTip(self.ui_tr("bom.clear_workspace_tip"))
        btn_clear_bom.clicked.connect(self._clear_bom_workspace)
        config_layout.addWidget(btn_clear_bom)

        layout.addWidget(config)

        self.bom_separator.currentTextChanged.connect(lambda *_: self._schedule_save_bom_tab_settings())
        self.bom_first_row.textChanged.connect(self._on_bom_first_last_row_changed)
        self.bom_last_row.textChanged.connect(self._on_bom_first_last_row_changed)
    
    def _create_pnp_tab(self):
        """PnP tab."""
        tab = QtWidgets.QWidget()
        self.tabs.addTab(tab, self.ui_tr("tab.pnp"))
        
        layout = QtWidgets.QVBoxLayout(tab)
        
        self.pnp_preview_stack = QtWidgets.QWidget()
        pnp_pv = QtWidgets.QVBoxLayout(self.pnp_preview_stack)
        pnp_pv.setContentsMargins(0, 0, 0, 0)
        pnp_pv.setSpacing(0)

        self.pnp_combo_vheader_spacer, self.pnp_combo_inner, self.pnp_combos_layout = self._build_mapping_row_widgets()
        pnp_pv.addWidget(self._wrap_mapping_row(self.pnp_combo_vheader_spacer, self.pnp_combo_inner))
        
        self.pnp_table = QtWidgets.QTableView()
        self.pnp_table.setAlternatingRowColors(True)
        self.pnp_model = SortableTableModel(pd.DataFrame(), editable=True)
        self.pnp_table.setModel(self.pnp_model)
        self.pnp_table.horizontalHeader().setMinimumSectionSize(48)
        self._apply_compact_preview_chrome(self.pnp_table)
        self.pnp_table.horizontalHeader().sectionResized.connect(self._on_pnp_section_resized)
        self.pnp_model.dataChanged.connect(lambda *args: self._mark_working_dirty("pnp"))
        self._connect_mapping_table_signals(self.pnp_table, "_pnp")
        pnp_pv.addWidget(self.pnp_table, 1)
        layout.addWidget(self.pnp_preview_stack, 1)

        coord_row = QtWidgets.QHBoxLayout()
        btn_clean_xyr = QtWidgets.QPushButton("Clean X/Y/R")
        btn_clean_xyr.setToolTip(
            "Strip junk from mapped X, Y, and Rotation columns — keeps digits and decimal separators "
            "(`.` `,` `-`); does not remove dots inside numbers."
        )
        btn_clean_xyr.clicked.connect(self._pnp_clean_xy_rot_columns)
        coord_row.addWidget(btn_clean_xyr)
        btn_mm_mil = QtWidgets.QPushButton("MM→MIL")
        btn_mm_mil.setToolTip(
            "Convert mapped X and Y from millimeters to mils (explicit edit); four fractional digits."
        )
        btn_mm_mil.clicked.connect(self._pnp_convert_xy_mm_to_mil)
        coord_row.addWidget(btn_mm_mil)
        btn_mil_mm = QtWidgets.QPushButton("MIL→MM")
        btn_mil_mm.setToolTip(
            "Convert mapped X and Y from mils to millimeters (explicit edit); four fractional digits."
        )
        btn_mil_mm.clicked.connect(self._pnp_convert_xy_mil_to_mm)
        coord_row.addWidget(btn_mil_mm)
        coord_row.addStretch()
        layout.addLayout(coord_row)

        # Bottom config row
        config = QtWidgets.QFrame()
        config_layout = QtWidgets.QHBoxLayout(config)
        
        config_layout.addWidget(QtWidgets.QLabel("Separator:"))
        self.pnp_separator = QtWidgets.QComboBox()
        self.pnp_separator.addItems(
            ["auto", ",", ";", "\\t", "space", "spaces", "2+sp", "fixed"]
        )
        self.pnp_separator.setCurrentText("auto")
        self.pnp_separator.setMinimumWidth(70)
        self.pnp_separator.setToolTip(
            "space = one ASCII space field; "
            "spaces = classic SPACES (any whitespace) like original Boomer; "
            "2+sp = Eagle/cmp: split on 2+ spaces. "
            "First row = first data row to keep (1-based), same as CSV/Excel; "
            "rows above are skipped and no row is removed as column headers in spaces mode."
        )
        config_layout.addWidget(self.pnp_separator)

        lbl_pfirst = QtWidgets.QLabel("First row:")
        lbl_pfirst.setToolTip(
            "First row from file (1-based): first row kept after load (rows above skipped); "
            "preview shows the full kept grid (column names stay 0,1,2… in spaces mode); "
            "highlighted range uses these fields."
        )
        config_layout.addWidget(lbl_pfirst)
        self.pnp_first_row = QtWidgets.QLineEdit("1")
        self.pnp_first_row.setMaximumWidth(52)
        self.pnp_first_row.setToolTip("1-based index into the file/grid before trimming.")
        config_layout.addWidget(self.pnp_first_row)

        lbl_plast = QtWidgets.QLabel("Last row:")
        lbl_plast.setToolTip(
            "Last row to include when loading (1-based, inclusive with First row). Empty = through end."
        )
        config_layout.addWidget(lbl_plast)
        self.pnp_last_row = QtWidgets.QLineEdit("")
        self.pnp_last_row.setMaximumWidth(52)
        self.pnp_last_row.setToolTip(
            "Last line included in the load range (1-based, inclusive with First row). Empty = through end."
        )
        config_layout.addWidget(self.pnp_last_row)

        config_layout.addWidget(QtWidgets.QLabel("Overlap / PCB preview:"))
        self.pnp_units_mm = QtWidgets.QRadioButton("mm")
        self.pnp_units_mils = QtWidgets.QRadioButton("mils")
        self.pnp_units_mm.setChecked(True)
        self.pnp_units_mm.setToolTip(
            "PnP X/Y numbers are treated as millimeters when comparing overlap distance on the Report tab "
            "and when scaling placements for PCB Preview."
        )
        self.pnp_units_mils.setToolTip(
            "PnP X/Y numbers are treated as mils for overlap distance only (×0.0254 vs threshold in mm) "
            "and for PCB Preview; merge/export/cross-check tables keep raw values."
        )
        self.pnp_units_mm.toggled.connect(self._on_pnp_units_changed)
        self.pnp_units_mils.toggled.connect(self._on_pnp_units_changed)
        config_layout.addWidget(self.pnp_units_mm)
        config_layout.addWidget(self.pnp_units_mils)

        config_layout.addStretch()
        btn_find = QtWidgets.QPushButton("Find / Replace...")
        btn_find.clicked.connect(lambda: self._find_replace_table("pnp"))
        config_layout.addWidget(btn_find)
        
        btn = QtWidgets.QPushButton("Reload")
        btn.clicked.connect(self._reload_pnp)
        config_layout.addWidget(btn)

        btn_clear_pnp = QtWidgets.QPushButton(self.ui_tr("pnp.clear_workspace"))
        btn_clear_pnp.setToolTip(self.ui_tr("pnp.clear_workspace_tip"))
        btn_clear_pnp.clicked.connect(self._clear_pnp_workspace)
        config_layout.addWidget(btn_clear_pnp)

        layout.addWidget(config)

        self.pnp_separator.currentTextChanged.connect(lambda *_: self._schedule_save_pnp_tab_settings())
        self.pnp_first_row.textChanged.connect(self._on_pnp_first_last_row_changed)
        self.pnp_last_row.textChanged.connect(self._on_pnp_first_last_row_changed)

    def _create_clean_tab(self):
        """Clean BOM tab — normalization via clean_component and optional pn_original."""
        tab = QtWidgets.QWidget()
        self.tabs.addTab(tab, self.ui_tr("tab.clean_bom"))
        layout = QtWidgets.QVBoxLayout(tab)

        clean_intro = QtWidgets.QLabel(
            "Uses the BOM column mapped to «Comment» on the BOM tab. "
            "Import fills the table with raw Comment; Convert! runs classifiers and regex; "
            "Apply adds _cleaned / clean_* columns. "
            "Global settings: From DB, From Hanwha MDB (PARTNAME from Machine lib .mdb), Part numbers (vendor MPN)."
        )
        clean_intro.setToolTip(
            "External hand-made BOMs may prefix THT parts with «DIP_» to mean off-line or "
            "through-hole; that is not the same as this tab’s cleaned Comment from PnP."
        )
        layout.addWidget(clean_intro)

        options = QtWidgets.QFrame()
        grid = QtWidgets.QGridLayout(options)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        group_global = QtWidgets.QGroupBox("Global settings")
        glb_outer = QtWidgets.QVBoxLayout(group_global)
        row_sp = QtWidgets.QHBoxLayout()
        row_sp.addWidget(QtWidgets.QLabel("Spacer (join segments):"))
        self.clean_spacer_combo = QtWidgets.QComboBox()
        self.clean_spacer_combo.setSizeAdjustPolicy(
            QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.clean_spacer_combo.setMinimumContentsLength(16)
        self.clean_spacer_combo.addItem('Underscore "_"', "_")
        self.clean_spacer_combo.addItem('Hyphen "-"', "-")
        self.clean_spacer_combo.addItem("Space", " ")
        self.clean_spacer_combo.addItem("Custom…", "cust")
        self.clean_spacer_cust = QtWidgets.QLineEdit()
        self.clean_spacer_cust.setPlaceholderText("Custom separator (any string)")
        self.clean_spacer_cust.setEnabled(False)
        self.clean_spacer_cust.setMaximumWidth(220)
        row_sp.addWidget(self.clean_spacer_combo, 0)
        row_sp.addWidget(self.clean_spacer_cust, 1)
        self.clean_prefix_use_separator = QtWidgets.QCheckBox("Use spacer after Prefix")
        self.clean_prefix_use_separator.setChecked(True)
        self.clean_prefix_use_separator.setToolTip(
            "On: Prefix C + spacer '-' + 0402-12PF -> C-0402-12PF. "
            "Off: C0402-12PF."
        )
        row_sp.addWidget(self.clean_prefix_use_separator)
        row_sp.addStretch(1)
        glb_outer.addLayout(row_sp)

        row_lib = QtWidgets.QHBoxLayout()
        self.clean_from_db = QtWidgets.QCheckBox("From DB")
        self.clean_from_db.setChecked(True)
        self.clean_from_db.setToolTip(
            "On: use components.txt learned components. Off: skip components.txt lookup."
        )
        row_lib.addWidget(self.clean_from_db)
        self.clean_from_hanwha_mdb = QtWidgets.QCheckBox("From Hanwha MDB")
        self.clean_from_hanwha_mdb.setChecked(False)
        self.clean_from_hanwha_mdb.setToolTip(
            "Match BOM text to PARTNAME from the .mdb loaded on the Machine lib tab "
            "(longest substring wins). Load PART_Det first; no match falls through to other rules."
        )
        row_lib.addWidget(self.clean_from_hanwha_mdb)
        row_lib.addStretch(1)
        glb_outer.addLayout(row_lib)

        self.gb_clean_pn = QtWidgets.QGroupBox("Part numbers (vendor MPN)")
        self.gb_clean_pn.setCheckable(True)
        self.gb_clean_pn.setChecked(True)
        self.gb_clean_pn.setToolTip(
            "Off: no pn_original MPN decoders (TAI RM/WR, Yageo, Murata, …); only regex. "
            "On: decoders run first, then fall back to regex. "
            "The inner checkbox only changes Source: «vendor» vs «pn»."
        )
        gl_pn = QtWidgets.QHBoxLayout(self.gb_clean_pn)
        self.clean_use_vendor = QtWidgets.QCheckBox("Label as «vendor» in Source (not «pn»)")
        self.clean_use_vendor.setToolTip(
            "When Part numbers is on, MPN decoders (pn_original) always run first. "
            "This only controls the Source column: «vendor» vs «pn» for decoded lines."
        )
        self.clean_use_vendor.setChecked(False)
        gl_pn.addWidget(self.clean_use_vendor)
        gl_pn.addStretch(1)
        glb_outer.addWidget(self.gb_clean_pn)

        grid.addWidget(group_global, 0, 0, 1, 3)

        self.gb_clean_res = QtWidgets.QGroupBox("Resistor")
        self.gb_clean_res.setCheckable(True)
        self.gb_clean_res.setChecked(True)
        self.gb_clean_res.setToolTip(
            "Off: resistor regex is disabled (row stays original after classification)."
        )
        gl = QtWidgets.QHBoxLayout(self.gb_clean_res)
        gl.setContentsMargins(6, 4, 6, 4)
        gl.setSpacing(6)
        gl.addWidget(QtWidgets.QLabel("Template:"))
        self.clean_res_template_combos: list[QtWidgets.QComboBox] = []
        res_options = [
            ("nom", "nom"),
            ("pack", "pack"),
            ("watt", "watt"),
            ("%", "%"),
            ("none", "none"),
        ]
        for i, default in enumerate(("nom", "pack", "watt", "%")):
            gl.addWidget(QtWidgets.QLabel(str(i + 1)))
            combo = QtWidgets.QComboBox()
            for label, data in res_options:
                combo.addItem(label, data)
            combo.setCurrentIndex(combo.findData(default))
            combo.setMaximumWidth(86)
            self.clean_res_template_combos.append(combo)
            gl.addWidget(combo)
        gl.addWidget(QtWidgets.QLabel("Prefix:"))
        self.clean_res_prefix = QtWidgets.QLineEdit()
        self.clean_res_prefix.setPlaceholderText("R")
        self.clean_res_prefix.setMaximumWidth(54)
        gl.addWidget(self.clean_res_prefix)
        gl.addStretch(1)
        grid.addWidget(self.gb_clean_res, 1, 0)

        self.gb_clean_cap = QtWidgets.QGroupBox("Capacitor")
        self.gb_clean_cap.setCheckable(True)
        self.gb_clean_cap.setChecked(True)
        self.gb_clean_cap.setToolTip(
            "Off: capacitor regex/MLCC helper is disabled (row stays original when typed as cap)."
        )
        cgrid = QtWidgets.QHBoxLayout(self.gb_clean_cap)
        cgrid.setContentsMargins(6, 4, 6, 4)
        cgrid.setSpacing(6)
        cgrid.addWidget(QtWidgets.QLabel("Template:"))
        self.clean_cap_template_combos: list[QtWidgets.QComboBox] = []
        cap_options = [
            ("nom", "nom"),
            ("pack", "pack"),
            ("film", "film"),
            ("%", "%"),
            ("W", "W"),
            ("none", "none"),
        ]
        for i, default in enumerate(("nom", "pack", "film", "%", "W")):
            cgrid.addWidget(QtWidgets.QLabel(str(i + 1)))
            combo = QtWidgets.QComboBox()
            for label, data in cap_options:
                combo.addItem(label, data)
            combo.setCurrentIndex(combo.findData(default))
            combo.setMaximumWidth(82)
            self.clean_cap_template_combos.append(combo)
            cgrid.addWidget(combo)
        self.clean_cap_nf = QtWidgets.QCheckBox("Convert nF → µF (simple)")
        self.clean_cap_nf.setChecked(False)
        cgrid.addWidget(self.clean_cap_nf)
        cgrid.addWidget(QtWidgets.QLabel("Prefix:"))
        self.clean_cap_prefix = QtWidgets.QLineEdit()
        self.clean_cap_prefix.setPlaceholderText("C")
        self.clean_cap_prefix.setMaximumWidth(54)
        cgrid.addWidget(self.clean_cap_prefix)
        cgrid.addStretch(1)
        grid.addWidget(self.gb_clean_cap, 1, 1)

        self.gb_clean_ind = QtWidgets.QGroupBox("Inductor")
        self.gb_clean_ind.setCheckable(True)
        self.gb_clean_ind.setChecked(True)
        self.gb_clean_ind.setToolTip(
            "Off: inductor-specific regex is disabled; classified inductor lines use the same path as "
            "OTHER (vendor MPN for passives, From DB, From Hanwha MDB, then general OTHER regex)."
        )
        ind_row = QtWidgets.QHBoxLayout(self.gb_clean_ind)
        ind_row.setContentsMargins(6, 4, 6, 4)
        ind_row.setSpacing(6)
        ind_row.addWidget(QtWidgets.QLabel("Template:"))
        self.clean_ind_template_combos: list[QtWidgets.QComboBox] = []
        ind_options = [
            ("pack", "pack"),
            ("nom", "nom"),
            ("%", "%"),
            ("Imax", "Imax"),
            ("DCR", "DCR"),
            ("none", "none"),
        ]
        for i, default in enumerate(("pack", "nom", "%", "Imax", "DCR")):
            ind_row.addWidget(QtWidgets.QLabel(str(i + 1)))
            combo = QtWidgets.QComboBox()
            for label, data in ind_options:
                combo.addItem(label, data)
            combo.setCurrentIndex(combo.findData(default))
            combo.setMaximumWidth(82)
            self.clean_ind_template_combos.append(combo)
            ind_row.addWidget(combo)
        ind_row.addWidget(QtWidgets.QLabel("Prefix:"))
        self.clean_ind_prefix = QtWidgets.QLineEdit()
        self.clean_ind_prefix.setPlaceholderText("L")
        self.clean_ind_prefix.setMaximumWidth(54)
        ind_row.addWidget(self.clean_ind_prefix)
        ind_row.addStretch(1)
        grid.addWidget(self.gb_clean_ind, 1, 2)

        group_mpn_www = QtWidgets.QGroupBox("MPN web lookup")
        mpn_w = QtWidgets.QHBoxLayout(group_mpn_www)
        mpn_w.addWidget(QtWidgets.QLabel("Search:"))
        self.clean_mpn_search_provider = QtWidgets.QComboBox()
        self.clean_mpn_search_provider.addItem("Digi-Key", "digikey")
        self.clean_mpn_search_provider.addItem("Mouser", "mouser")
        self.clean_mpn_search_provider.addItem("Octopart (search page)", "octopart")
        mpn_w.addWidget(self.clean_mpn_search_provider)
        mpn_w.addWidget(QtWidgets.QLabel("API key (optional, reserved):"))
        self.clean_octopart_api_key = QtWidgets.QLineEdit()
        self.clean_octopart_api_key.setEchoMode(
            QtWidgets.QLineEdit.EchoMode.PasswordEchoOnEdit
        )
        self.clean_octopart_api_key.setPlaceholderText("Octopart / Nexar — not used in UI yet")
        self.clean_octopart_api_key.setMaximumWidth(280)
        mpn_w.addWidget(self.clean_octopart_api_key, 0)
        self.btn_mpn_open_search = QtWidgets.QPushButton("Open search for selected row")
        self.btn_mpn_open_search.setToolTip(
            "Uses «Original» from the table below (VENDOR/MPN normalized to bare MPN). "
            "Select a cell in the Clean BOM preview, then click."
        )
        self.btn_mpn_open_search.clicked.connect(self._open_mpn_search_browser)
        mpn_w.addWidget(self.btn_mpn_open_search)
        mpn_w.addStretch(1)
        grid.addWidget(group_mpn_www, 3, 0, 1, 3)

        layout.addWidget(options)

        for w in (*self.clean_res_template_combos, *self.clean_cap_template_combos, *self.clean_ind_template_combos):
            w.currentIndexChanged.connect(self._save_clean_settings)
        for w in (
            self.clean_cap_nf,
            self.clean_use_vendor,
            self.clean_from_db,
            self.clean_from_hanwha_mdb,
        ):
            w.stateChanged.connect(self._save_clean_settings)
        self.gb_clean_res.toggled.connect(self._on_gb_clean_res_toggled)
        self.gb_clean_cap.toggled.connect(self._on_gb_clean_cap_toggled)
        self.gb_clean_ind.toggled.connect(self._on_gb_clean_ind_toggled)
        self.gb_clean_pn.toggled.connect(self._on_gb_clean_pn_toggled)
        self._on_gb_clean_res_toggled(self.gb_clean_res.isChecked())
        self._on_gb_clean_cap_toggled(self.gb_clean_cap.isChecked())
        self._on_gb_clean_ind_toggled(self.gb_clean_ind.isChecked())
        self._on_gb_clean_pn_toggled(self.gb_clean_pn.isChecked())
        self.clean_spacer_combo.currentIndexChanged.connect(self._on_clean_spacer_changed)
        self.clean_spacer_cust.textChanged.connect(self._save_clean_settings)
        self.clean_prefix_use_separator.stateChanged.connect(self._save_clean_settings)
        self.clean_res_prefix.textChanged.connect(self._save_clean_settings)
        self.clean_cap_prefix.textChanged.connect(self._save_clean_settings)
        self.clean_ind_prefix.textChanged.connect(self._save_clean_settings)
        self.clean_mpn_search_provider.currentIndexChanged.connect(
            self._save_clean_mpn_lookup_settings
        )
        self.clean_octopart_api_key.editingFinished.connect(
            self._save_clean_mpn_lookup_settings
        )

        buttons = QtWidgets.QHBoxLayout()
        self.btn_clean_import = QtWidgets.QPushButton("Import from BOM")
        self.btn_clean_import.setToolTip(
            "Reads the BOM column mapped to «Comment»; fills the preview with raw values."
        )
        self.btn_clean_import.clicked.connect(self._clean_import)
        self.btn_clean_convert = QtWidgets.QPushButton("Convert!")
        self.btn_clean_convert.setToolTip(
            "Runs classifiers, clean_component regex, and optional vendor MPN (pn_original)."
        )
        self.btn_clean_convert.setEnabled(False)
        self.btn_clean_convert.clicked.connect(self._run_clean_preview)
        self.btn_clean_apply = QtWidgets.QPushButton("Apply to BOM (add columns)")
        self.btn_clean_apply.setToolTip(
            "Adds Comment_cleaned, clean_type, clean_part_code, clean_vendor (drops prior clean_* if re-run)"
        )
        self.btn_clean_apply.setEnabled(False)
        self.btn_clean_apply.clicked.connect(self._clean_apply)
        self.clean_apply_replace = QtWidgets.QCheckBox("Replace source column")
        self.clean_apply_replace.setToolTip(
            "On: write Cleaned back into the source Comment column. "
            "Off: update/add the *_cleaned and clean_* columns."
        )
        self.clean_apply_replace.stateChanged.connect(self._save_clean_settings)
        self.btn_clean_learn_other = QtWidgets.QPushButton("Learn selected OTHER")
        self.btn_clean_learn_other.setToolTip(
            "Approve and append the selected OTHER row to components.txt for future imports."
        )
        self.btn_clean_learn_other.setEnabled(False)
        self.btn_clean_learn_other.clicked.connect(self._learn_selected_other)
        self.btn_clean_save = QtWidgets.QPushButton("Save Excel…")
        self.btn_clean_save.clicked.connect(self._clean_save_excel)
        for b in (
            self.btn_clean_import,
            self.btn_clean_convert,
            self.btn_clean_apply,
            self.btn_clean_learn_other,
            self.btn_clean_save,
        ):
            buttons.addWidget(b)
        buttons.addWidget(self.clean_apply_replace)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.lbl_clean_source = QtWidgets.QLabel(
            "Set BOM column mapping to «Comment», then Import from BOM to list raw Comment values below. "
            "Then use Convert!."
        )
        self.lbl_clean_source.setWordWrap(True)
        layout.addWidget(self.lbl_clean_source)

        self._clean_imported_comments: list[str] = []
        self._clean_last_preview: list = []
        self._clean_source_column: Optional[str] = None
        self._clean_source_indices: list[int] = []

        self.clean_preview_table = QtWidgets.QTableView()
        self.clean_preview_table.setAlternatingRowColors(True)
        self.clean_preview_model = SortableTableModel(
            pd.DataFrame(columns=["#", "Original", "Cleaned", "Type", "Source"])
        )
        self.clean_preview_table.setModel(self.clean_preview_model)
        self.clean_preview_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.clean_preview_table, 1)

    def _get_bom_comment_column_name(self) -> Optional[str]:
        self._sync_bom_df_from_model()
        if self._bom_df is None or self._bom_df.empty:
            return None
        if hasattr(self, "bom_col_combos") and self.bom_col_combos:
            for i, combo in enumerate(self.bom_col_combos):
                if i >= len(self._bom_df.columns):
                    break
                if combo.currentText() == "Comment":
                    return str(self._bom_df.columns[i])
        for col in self._bom_df.columns:
            u = str(col).upper()
            if "COMMENT" in u or u == "VALUE" or "NAME" in u:
                return str(col)
        return str(self._bom_df.columns[0])

    def _sync_bom_df_from_model(self) -> None:
        if not hasattr(self, "bom_model"):
            return
        df = self.bom_model.get_dataframe()
        if df is not None:
            self._bom_df = df

    def _sync_pnp_df_from_model(self) -> None:
        if not hasattr(self, "pnp_model"):
            return
        df = self.pnp_model.get_dataframe()
        if df is not None:
            self._pnp_df = df

    def _active_row_indices(self, total_rows: int, first_widget: QtWidgets.QLineEdit, last_widget: QtWidgets.QLineEdit) -> list[int]:
        if total_rows <= 0:
            return []
        try:
            first = max(0, int(first_widget.text() or "1") - 1)
        except ValueError:
            first = 0
        try:
            last_text = last_widget.text().strip()
            last = int(last_text) - 1 if last_text else total_rows - 1
        except ValueError:
            last = total_rows - 1
        last = min(max(last, first), total_rows - 1)
        if first >= total_rows:
            return []
        return list(range(first, last + 1))

    def _active_row_numbers(
        self,
        total_rows: int,
        first_widget: QtWidgets.QLineEdit,
        last_widget: QtWidgets.QLineEdit,
    ) -> tuple[int | None, int | None]:
        if total_rows <= 0:
            return None, None
        try:
            first = max(1, int(first_widget.text() or "1"))
        except ValueError:
            first = 1
        try:
            last_text = last_widget.text().strip()
            last = int(last_text) if last_text else total_rows
        except ValueError:
            last = total_rows
        if first > total_rows:
            return None, None
        return first, min(max(last, first), total_rows)

    def _refresh_active_row_highlight(self, kind: str) -> None:
        if kind == "bom" and hasattr(self, "bom_model"):
            first, last = self._active_row_numbers(
                self.bom_model.rowCount(), self.bom_first_row, self.bom_last_row
            )
            self.bom_model.set_active_row_range(first, last)
            self.bom_table.verticalHeader().viewport().update()
        elif kind == "pnp" and hasattr(self, "pnp_model"):
            first, last = self._active_row_numbers(
                self.pnp_model.rowCount(), self.pnp_first_row, self.pnp_last_row
            )
            self.pnp_model.set_active_row_range(first, last)
            self.pnp_table.verticalHeader().viewport().update()

    def _mark_working_dirty(self, kind: str, *, autosave: bool = True) -> None:
        if self._loading_working_copy or self._restoring_settings:
            return
        if kind == "bom":
            self._sync_bom_df_from_model()
            self._bom_dirty = True
        elif kind == "pnp":
            self._sync_pnp_df_from_model()
            self._pnp_dirty = True
        else:
            return
        if autosave:
            self._autosave_timer.start(1500)

    def _autosave_dirty_working_copies(self) -> None:
        try:
            if self._bom_dirty and self._bom_source_path and self._bom_df is not None:
                save_snapshot(
                    self._bom_df,
                    self._bom_source_path,
                    "bom",
                    self._autosave_dir,
                    dirty=True,
                )
                self._log("BOM working copy autosaved", "debug")
            if self._pnp_dirty and self._pnp_source_path and self._pnp_df is not None:
                save_snapshot(
                    self._pnp_df,
                    self._pnp_source_path,
                    "pnp",
                    self._autosave_dir,
                    dirty=True,
                )
                self._log("PnP working copy autosaved", "debug")
        except Exception as e:
            self._log(f"Working copy autosave failed: {e}", "warning")
            logger.warning("Working copy autosave failed: %s", e)

    def _clean_output_separator(self) -> str:
        d = self.clean_spacer_combo.currentData()
        if d == "cust":
            return self.clean_spacer_cust.text()
        if isinstance(d, str):
            return d
        return "_"

    def _on_clean_spacer_changed(self) -> None:
        d = self.clean_spacer_combo.currentData()
        if d == "cust":
            self.clean_spacer_cust.setEnabled(True)
        else:
            self.clean_spacer_cust.setEnabled(False)
            self.clean_spacer_cust.clear()
        self._save_clean_settings()

    def _apply_clean_spacer_to_ui(self, sep: str) -> None:
        """Set combo and optional custom line from a saved output_separator string."""
        for i in range(self.clean_spacer_combo.count()):
            data = self.clean_spacer_combo.itemData(i)
            if data == "cust" or data is None:
                continue
            if data == sep:
                self.clean_spacer_combo.setCurrentIndex(i)
                self.clean_spacer_cust.setEnabled(False)
                self.clean_spacer_cust.clear()
                return
        idx = self.clean_spacer_combo.findData("cust")
        if idx < 0:
            return
        self.clean_spacer_combo.setCurrentIndex(idx)
        self.clean_spacer_cust.setText(sep)
        self.clean_spacer_cust.setEnabled(True)

    def _on_gb_clean_res_toggled(self, on: bool) -> None:
        for w in (*self.clean_res_template_combos, self.clean_res_prefix):
            w.setEnabled(on)
        self._save_clean_settings()

    def _on_gb_clean_cap_toggled(self, on: bool) -> None:
        for w in (*self.clean_cap_template_combos, self.clean_cap_nf, self.clean_cap_prefix):
            w.setEnabled(on)
        self._save_clean_settings()

    def _on_gb_clean_ind_toggled(self, on: bool) -> None:
        for w in (*self.clean_ind_template_combos, self.clean_ind_prefix):
            w.setEnabled(on)
        self._save_clean_settings()

    def _on_gb_clean_pn_toggled(self, on: bool) -> None:
        self.clean_use_vendor.setEnabled(on)
        self._save_clean_settings()

    def _save_clean_mpn_lookup_settings(self) -> None:
        if getattr(self, "_restoring_settings", False) or not hasattr(self, "_settings"):
            return
        s = self._settings
        prov = self.clean_mpn_search_provider.currentData()
        s.setValue("clean/mpn_search_provider", prov if prov else "digikey")
        s.setValue("clean/octopart_api_key", self.clean_octopart_api_key.text())

    def _open_mpn_search_browser(self) -> None:
        idx = self.clean_preview_table.currentIndex()
        if not idx.isValid():
            self._log("Clean BOM: select a row in the preview table first", "warning")
            return
        row = idx.row()
        df = self.clean_preview_model.get_dataframe()
        if df is None or df.empty or row < 0 or row >= len(df):
            self._log("Clean BOM: no preview data", "warning")
            return
        if "Original" not in df.columns:
            self._log("Clean BOM: preview has no Original column", "error")
            return
        orig = str(df.iloc[row]["Original"])
        mpn = normalize_mpn_bare(orig)
        if not mpn:
            self._log("Clean BOM: empty MPN after normalize", "warning")
            return
        prov = self.clean_mpn_search_provider.currentData() or "digikey"
        q = quote(mpn, safe="")
        if prov == "digikey":
            url = f"https://www.digikey.com/en/products/result?keywords={q}"
        elif prov == "mouser":
            url = f"https://www.mouser.com/c/?q={q}"
        else:
            url = f"https://octopart.com/search?q={q}"
        if not QDesktopServices.openUrl(QUrl(url)):
            self._log("Could not open default browser for MPN search", "error")
        else:
            self._log(f"MPN search opened for {mpn!r} ({prov})", "info")

    def _template_from_combos(
        self, combos: list[QtWidgets.QComboBox]
    ) -> tuple[str, ...]:
        values: list[str] = []
        for combo in combos:
            data = combo.currentData()
            key = str(data) if data is not None else "none"
            values.append(key)
        return tuple(values)

    def _set_template_combos(
        self, combos: list[QtWidgets.QComboBox], raw: object, default: tuple[str, ...]
    ) -> None:
        if isinstance(raw, str) and raw.strip():
            values = [x.strip() for x in raw.split(",")]
        else:
            values = list(default)
        for i, combo in enumerate(combos):
            key = values[i] if i < len(values) else "none"
            idx = combo.findData(key)
            if idx < 0:
                idx = combo.findData("none")
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def _clean_config_from_ui(self) -> CleanConfig:
        res_template = self._template_from_combos(self.clean_res_template_combos)
        cap_template = self._template_from_combos(self.clean_cap_template_combos)
        ind_template = self._template_from_combos(self.clean_ind_template_combos)
        hanwha_names = None
        if self.clean_from_hanwha_mdb.isChecked() and hasattr(self, "_machine_library_tab"):
            hs = self._machine_library_tab.hanwha_partname_set()
            hanwha_names = hs if hs else None
        return CleanConfig(
            resistor_include_package="pack" in res_template,
            resistor_include_tolerance="%" in res_template,
            cap_include_package="pack" in cap_template,
            cap_include_voltage="W" in cap_template,
            cap_include_dielectric="film" in cap_template,
            cap_include_tolerance="%" in cap_template,
            cap_convert_nf_to_uf=self.clean_cap_nf.isChecked(),
            use_pn_codecs=self.gb_clean_pn.isChecked(),
            use_vendor_pn=self.gb_clean_pn.isChecked() and self.clean_use_vendor.isChecked(),
            parse_resistors=self.gb_clean_res.isChecked(),
            parse_capacitors=self.gb_clean_cap.isChecked(),
            parse_inductors=self.gb_clean_ind.isChecked(),
            output_separator=self._clean_output_separator(),
            resistor_template=res_template,
            cap_template=cap_template,
            inductor_template=ind_template if ind_template else CleanConfig.inductor_template,
            resistor_prefix=self.clean_res_prefix.text().strip(),
            cap_prefix=self.clean_cap_prefix.text().strip(),
            inductor_prefix=self.clean_ind_prefix.text().strip(),
            prefix_use_separator=self.clean_prefix_use_separator.isChecked(),
            use_component_library=self.clean_from_db.isChecked(),
            use_hanwha_mdb=self.clean_from_hanwha_mdb.isChecked(),
            hanwha_partnames=hanwha_names,
        )

    def _save_clean_settings(self) -> None:
        if getattr(self, "_restoring_settings", False) or not hasattr(self, "_settings"):
            return
        s = self._settings
        s.setValue(
            "clean/res_template",
            ",".join(self._template_from_combos(self.clean_res_template_combos)),
        )
        s.setValue(
            "clean/cap_template",
            ",".join(self._template_from_combos(self.clean_cap_template_combos)),
        )
        s.setValue(
            "clean/ind_template",
            ",".join(self._template_from_combos(self.clean_ind_template_combos)),
        )
        s.setValue("clean/cap_nf", self.clean_cap_nf.isChecked())
        s.setValue("clean/use_vendor", self.clean_use_vendor.isChecked())
        s.setValue("clean/group_res", self.gb_clean_res.isChecked())
        s.setValue("clean/group_cap", self.gb_clean_cap.isChecked())
        s.setValue("clean/group_ind", self.gb_clean_ind.isChecked())
        s.setValue("clean/group_pn", self.gb_clean_pn.isChecked())
        s.setValue("clean/output_separator", self._clean_output_separator())
        s.setValue("clean/res_prefix", self.clean_res_prefix.text().strip())
        s.setValue("clean/cap_prefix", self.clean_cap_prefix.text().strip())
        s.setValue("clean/ind_prefix", self.clean_ind_prefix.text().strip())
        s.setValue("clean/prefix_use_separator", self.clean_prefix_use_separator.isChecked())
        if hasattr(self, "clean_from_db"):
            s.setValue("clean/from_db", self.clean_from_db.isChecked())
        if hasattr(self, "clean_from_hanwha_mdb"):
            s.setValue("clean/from_hanwha_mdb", self.clean_from_hanwha_mdb.isChecked())
        if hasattr(self, "clean_apply_replace"):
            s.setValue("clean/apply_replace", self.clean_apply_replace.isChecked())

    def _clean_import(self) -> None:
        self._sync_bom_df_from_model()
        if self._bom_df is None or self._bom_df.empty:
            self._log("Clean BOM: load BOM on BOM tab first", "warning")
            logger.warning("Clean BOM: no BOM loaded")
            return
        col = self._get_bom_comment_column_name()
        if not col or col not in self._bom_df.columns:
            self._log("Clean BOM: map a column to «Comment» on the BOM tab", "warning")
            logger.error("Clean BOM: BOM comment column not configured")
            return
        self._clean_source_column = col
        self._clean_source_indices = self._active_row_indices(
            len(self._bom_df), self.bom_first_row, self.bom_last_row
        )
        if not self._clean_source_indices:
            self._log("Clean BOM: selected BOM row range is empty", "warning")
            return
        self._clean_imported_comments = [
            str(self._bom_df.iloc[i][col]) for i in self._clean_source_indices
        ]
        n = len(self._clean_imported_comments)
        logger.info("Imported %d comments from BOM column %r", n, col)
        self._log(
            f"Clean BOM: imported {n} row(s) from column «{col}» using active BOM range",
            "info",
        )
        for i, c in enumerate(self._clean_imported_comments[:5], start=1):
            one = c.replace("\n", " ")
            if len(one) > 72:
                one = one[:70] + ".."
            self._log(f"  sample row {i}: {one}", "info")
        if n > 5:
            self._log(f"  … plus {n - 5} more rows (see Original column in the table)", "info")
        self.btn_clean_convert.setEnabled(True)
        self.btn_clean_apply.setEnabled(False)
        self.btn_clean_learn_other.setEnabled(False)
        self._clean_last_preview = []
        pending = "\u2014"
        raw_df = pd.DataFrame(
            {
                "#": list(range(1, n + 1)),
                "Original": self._clean_imported_comments,
                "Cleaned": [pending] * n,
                "Type": [pending] * n,
                "Source": [pending] * n,
            }
        )
        self.clean_preview_model.update_dataframe(raw_df)
        self.lbl_clean_source.setText(
            f"Preview: raw values from BOM column «{col}» — {n} row(s). "
            "Click Convert! to run classifiers and cleaning."
        )

    def _run_clean_preview(self) -> None:
        if not self._clean_imported_comments:
            self._log("Clean BOM: run Import from BOM first, then Convert!", "warning")
            logger.error("Clean BOM: no comments imported")
            return
        n = len(self._clean_imported_comments)
        logger.info("Generating clean preview for %d components…", n)
        self._log(f"Clean BOM: generating clean preview for {n} component(s)…", "info")
        cfg = self._clean_config_from_ui()
        try:
            rows = clean_preview(self._clean_imported_comments, cfg)
        except Exception as e:
            self._log(f"Clean BOM: Convert! error: {e}", "error")
            logger.error("Clean BOM clean_preview failed: %s", e)
            return
        self._clean_last_preview = rows
        df = pd.DataFrame(
            rows, columns=["#", "Original", "Cleaned", "Type", "Source"]
        )
        self.clean_preview_model.update_dataframe(df)
        logger.info("Clean preview generated: %d rows", len(rows))
        self._log(
            f"Clean BOM: Convert! done — {len(rows)} row(s) (check Cleaned / Type / Source)",
            "info",
        )
        if self._clean_source_column:
            self.lbl_clean_source.setText(
                f"Last import: column «{self._clean_source_column}»; "
                f"table shows post-Convert! results ({len(rows)} rows)."
            )
        self.btn_clean_apply.setEnabled(bool(rows))
        self.btn_clean_learn_other.setEnabled(bool(rows))

    def _footprint_for_clean_row(self, one_based_row: int) -> str:
        self._sync_bom_df_from_model()
        if self._bom_df is None or self._bom_df.empty:
            return ""
        preview_idx = one_based_row - 1
        if 0 <= preview_idx < len(self._clean_source_indices):
            idx = self._clean_source_indices[preview_idx]
        else:
            idx = preview_idx
        if idx < 0 or idx >= len(self._bom_df):
            return ""
        for col in self._bom_df.columns:
            if "FOOTPRINT" in str(col).upper():
                val = self._bom_df.iloc[idx].get(col, "")
                return "" if pd.isna(val) else str(val).strip()
        return ""

    def _learn_selected_other(self) -> None:
        idx = self.clean_preview_table.currentIndex()
        if not idx.isValid():
            self._log("Clean BOM: select an OTHER row first", "warning")
            return
        df = self.clean_preview_model.get_dataframe()
        if df is None or df.empty or idx.row() >= len(df):
            self._log("Clean BOM: preview table is empty", "warning")
            return
        row = df.iloc[idx.row()]
        typ = str(row.get("Type", "")).upper()
        if typ != "OTHER":
            self._log("Clean BOM: selected row is not OTHER", "warning")
            return
        original = str(row.get("Original", "")).strip()
        cleaned = str(row.get("Cleaned", "")).strip()
        try:
            one_based = int(row.get("#", idx.row() + 1))
        except (TypeError, ValueError):
            one_based = idx.row() + 1
        footprint = self._footprint_for_clean_row(one_based)

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Learn OTHER component")
        form = QtWidgets.QFormLayout(dlg)
        raw_edit = QtWidgets.QLineEdit(original)
        raw_edit.setReadOnly(True)
        clean_edit = QtWidgets.QLineEdit(cleaned or original)
        type_combo = QtWidgets.QComboBox()
        for label in ("OTHER", "CAP", "RES", "IND"):
            type_combo.addItem(label, label)
        fp_edit = QtWidgets.QLineEdit(footprint)
        form.addRow("Original", raw_edit)
        form.addRow("Canonical name", clean_edit)
        form.addRow("Type", type_combo)
        form.addRow("Footprint", fp_edit)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        ok = append_component(
            raw_edit.text(),
            clean_edit.text(),
            type_combo.currentData() or "OTHER",
            fp_edit.text(),
        )
        path = default_components_path()
        if ok:
            self._log(f"Learned component saved to {path}", "info")
        else:
            self._log("Component already exists in user library", "warning")

    def _clean_apply(self) -> None:
        self._sync_bom_df_from_model()
        if self._bom_df is None or self._bom_df.empty:
            logger.warning("Clean BOM apply: no BOM data")
            return
        col = self._clean_source_column or self._get_bom_comment_column_name()
        if not col or col not in self._bom_df.columns:
            self._log("Clean BOM: no Comment column", "warning")
            logger.error("Clean BOM apply: comment column missing")
            return
        if not self._clean_last_preview:
            self._log("Clean BOM: run Convert! before Apply", "warning")
            return

        replace = self.clean_apply_replace.isChecked()
        logger.info(
            "Applying clean preview to BOM (%d preview rows, replace=%s)…",
            len(self._clean_last_preview),
            replace,
        )
        df = self._bom_df.copy()
        target_col = col if replace else f"{col}_cleaned"
        if not replace and target_col not in df.columns:
            df[target_col] = ""
        if not replace:
            for meta_col in ("clean_type", "clean_part_code", "clean_vendor"):
                if meta_col not in df.columns:
                    df[meta_col] = ""

        applied = 0
        for preview_i, row in enumerate(self._clean_last_preview):
            if preview_i < len(self._clean_source_indices):
                df_i = self._clean_source_indices[preview_i]
            else:
                df_i = preview_i
            if df_i < 0 or df_i >= len(df):
                continue
            cleaned, typ, part_code, source = row[2], row[3], "", row[4]
            if len(row) >= 5:
                # clean_preview does not expose part_code; map from visible Type for metadata only.
                part_code = "RES" if typ == "RESISTOR" else "IND" if typ == "INDUCTOR" else typ
            df.at[df.index[df_i], target_col] = cleaned
            if not replace:
                df.at[df.index[df_i], "clean_type"] = typ
                df.at[df.index[df_i], "clean_part_code"] = part_code
                df.at[df.index[df_i], "clean_vendor"] = source
            applied += 1

        self._bom_df = df
        self.bom_model.update_dataframe(self._bom_df)
        self._refresh_active_row_highlight("bom")
        self._fill_bom_combos()
        self._autoresize_bom_columns()
        if replace:
            msg = f"Clean BOM: replaced {applied} value(s) in source column «{col}»"
        else:
            msg = (
                f"Clean BOM: updated {applied} value(s) in «{target_col}» "
                "plus clean_type / clean_part_code / clean_vendor"
            )
        self._log(msg, "info")
        logger.info("Applied clean to BOM: %s", msg)
        self._mark_working_dirty("bom")

    def _clean_save_excel(self) -> None:
        self._sync_bom_df_from_model()
        if self._bom_df is None or self._bom_df.empty:
            self._log("Clean BOM: no BOM to save", "warning")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save cleaned BOM as Excel", "", "Excel (*.xlsx);;All (*.*)"
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            self._bom_df.to_excel(path, index=False)
            self._log(f"Clean BOM: saved {path}", "info")
            logger.info("Clean BOM saved Excel: %s", path)
        except Exception as e:
            self._log(f"Save Excel error: {e}", "error")
            logger.error("Clean BOM save Excel failed: %s", e)
            QtWidgets.QMessageBox.critical(self, "Error", str(e))

    def _create_merge_tab(self):
        """Merge tab — combine BOM and PnP."""
        tab = QtWidgets.QWidget()
        self.tabs.addTab(tab, self.ui_tr("tab.merge"))
        
        layout = QtWidgets.QVBoxLayout(tab)
        
        info = QtWidgets.QLabel("Merge uses column settings from BOM and PnP tabs")
        layout.addWidget(info)

        self.merge_cc_ok_banner = QtWidgets.QFrame()
        self.merge_cc_ok_banner.setObjectName("mergeCcOkBanner")
        self.merge_cc_ok_banner.setVisible(False)
        self.merge_cc_ok_banner.setStyleSheet(
            "QFrame#mergeCcOkBanner { background-color: rgba(46, 125, 50, 0.22); "
            "border: 1px solid #43a047; border-radius: 4px; padding: 6px 8px; }"
        )
        cc_ok_lay = QtWidgets.QHBoxLayout(self.merge_cc_ok_banner)
        cc_ok_lay.setContentsMargins(8, 4, 8, 4)
        self.merge_cc_ok_icon = QtWidgets.QLabel("\u2713")
        self.merge_cc_ok_icon.setStyleSheet(
            "color: #66bb6a; font-size: 22px; font-weight: bold; border: none; background: transparent;"
        )
        self.merge_cc_ok_label = QtWidgets.QLabel("PnP is good, ready for Export!")
        self.merge_cc_ok_label.setStyleSheet(
            "color: #c8e6c9; font-weight: bold; border: none; background: transparent;"
        )
        self.merge_cc_ok_hint = QtWidgets.QLabel(
            "Cross-check reported no issues — run Merge below, then save or export."
        )
        self.merge_cc_ok_hint.setStyleSheet(
            "color: #a5d6a7; border: none; background: transparent;"
        )
        cc_ok_lay.addWidget(self.merge_cc_ok_icon, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
        vtxt = QtWidgets.QVBoxLayout()
        vtxt.setSpacing(0)
        vtxt.addWidget(self.merge_cc_ok_label)
        vtxt.addWidget(self.merge_cc_ok_hint)
        cc_ok_lay.addLayout(vtxt)
        cc_ok_lay.addStretch()
        layout.addWidget(self.merge_cc_ok_banner)

        # TODO(full Merge): import paired TOP + BOT (see examples/example9) and align with
        # Manual_BOM when present; current UI merges a single loaded BOM+PnP only.

        # Options
        options = QtWidgets.QHBoxLayout()
        self.merge_delete_dnp = QtWidgets.QCheckBox("Delete DNP components")
        self.merge_delete_dnp.stateChanged.connect(self._on_merge_settings_changed)
        options.addWidget(self.merge_delete_dnp)
        options.addStretch()
        layout.addLayout(options)

        # Buttons
        buttons = QtWidgets.QHBoxLayout()
        self.btn_merge = QtWidgets.QPushButton("Merge")
        self.btn_merge.clicked.connect(self._run_merge)
        buttons.addWidget(self.btn_merge)

        self.btn_replace_pnp_from_merge = QtWidgets.QPushButton("Replace PNP")
        self.btn_replace_pnp_from_merge.setToolTip(
            "Replace all rows/columns on the PnP tab with the current Merge result."
        )
        self.btn_replace_pnp_from_merge.clicked.connect(self._replace_pnp_from_merge)
        buttons.addWidget(self.btn_replace_pnp_from_merge)

        self.btn_save_merge_csv = QtWidgets.QPushButton("Save CSV")
        self.btn_save_merge_csv.clicked.connect(self._save_merge_csv)
        buttons.addWidget(self.btn_save_merge_csv)

        self.btn_save_merge_excel = QtWidgets.QPushButton("Save Excel")
        self.btn_save_merge_excel.clicked.connect(self._save_merge_excel)
        buttons.addWidget(self.btn_save_merge_excel)

        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.Shape.VLine)
        sep.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        buttons.addWidget(sep)

        self.btn_export_top = QtWidgets.QPushButton("Export Top")
        self.btn_export_top.setToolTip("Export Merge rows whose Layer matches the selected TOP value.")
        self.btn_export_top.clicked.connect(lambda: self._export_merge_layer("top"))
        buttons.addWidget(self.btn_export_top)
        self.merge_top_layer_combo = QtWidgets.QComboBox()
        self.merge_top_layer_combo.setMinimumWidth(90)
        buttons.addWidget(self.merge_top_layer_combo)

        sep2 = QtWidgets.QFrame()
        sep2.setFrameShape(QtWidgets.QFrame.Shape.VLine)
        sep2.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        buttons.addWidget(sep2)

        self.btn_export_bot = QtWidgets.QPushButton("Export Bot")
        self.btn_export_bot.setToolTip("Export Merge rows whose Layer matches the selected BOT/mirror value.")
        self.btn_export_bot.clicked.connect(lambda: self._export_merge_layer("bot"))
        buttons.addWidget(self.btn_export_bot)
        self.merge_bot_layer_combo = QtWidgets.QComboBox()
        self.merge_bot_layer_combo.setMinimumWidth(90)
        buttons.addWidget(self.merge_bot_layer_combo)
        self._update_merge_layer_export_controls()
        buttons.addStretch()
        layout.addLayout(buttons)
        
        # Merge result table
        self.merge_table = QtWidgets.QTableView()
        self.merge_table.setAlternatingRowColors(True)
        self.merge_model = SortableTableModel(pd.DataFrame())
        self.merge_table.setModel(self.merge_model)
        layout.addWidget(self.merge_table, 1)
    
    def _create_report_tab(self):
        """Cross-check report tab."""
        tab = QtWidgets.QWidget()
        self.tabs.addTab(tab, self.ui_tr("tab.report"))
        
        layout = QtWidgets.QVBoxLayout(tab)
        
        # Buttons
        buttons = QtWidgets.QHBoxLayout()
        
        self.btn_cross_check = QtWidgets.QPushButton("Cross-check")
        self.btn_cross_check.clicked.connect(self._run_cross_check)
        buttons.addWidget(self.btn_cross_check)

        self.btn_copy_html = QtWidgets.QPushButton("Copy HTML")
        self.btn_copy_html.setEnabled(False)
        self.btn_copy_html.setToolTip("Copy last cross-check result as HTML")
        self.btn_copy_html.clicked.connect(self._copy_report_html)
        buttons.addWidget(self.btn_copy_html)

        self.btn_save_report_html = QtWidgets.QPushButton("Save HTML report…")
        self.btn_save_report_html.setEnabled(False)
        self.btn_save_report_html.setToolTip(
            "Save last cross-check report as a standalone .html file (same styling as Copy HTML)"
        )
        self.btn_save_report_html.clicked.connect(self._save_report_html)
        buttons.addWidget(self.btn_save_report_html)

        buttons.addStretch()
        
        # Filter checkboxes
        self.chk_critical = QtWidgets.QCheckBox("Critical")
        self.chk_critical.setChecked(True)
        buttons.addWidget(self.chk_critical)
        
        self.chk_warning = QtWidgets.QCheckBox("Warning")
        self.chk_warning.setChecked(True)
        buttons.addWidget(self.chk_warning)
        
        self.chk_info = QtWidgets.QCheckBox("Info")
        self.chk_info.setChecked(True)
        buttons.addWidget(self.chk_info)
        
        layout.addLayout(buttons)
        
        overlap_row = QtWidgets.QHBoxLayout()
        self.chk_overlap = QtWidgets.QCheckBox("Overlap: min center distance (mm)")
        self.chk_overlap.setChecked(False)
        self.chk_overlap.setToolTip(
            "If enabled, report pairs of placements on the same layer when center distance (after scaling "
            "PnP X/Y per the **PnP tab** mm/mils toggle) is below this threshold. Distance limit is always "
            "in millimeters. O(n²) in PnP size — leave off for very dense panels."
        )
        self.spin_overlap_mm = QtWidgets.QDoubleSpinBox()
        self.spin_overlap_mm.setRange(0.1, 999.0)
        self.spin_overlap_mm.setDecimals(2)
        self.spin_overlap_mm.setValue(3.0)
        self.spin_overlap_mm.setEnabled(False)
        self.spin_overlap_mm.setMaximumWidth(100)
        self.chk_overlap.toggled.connect(self.spin_overlap_mm.setEnabled)
        self.chk_overlap.toggled.connect(self._save_report_overlap_settings)
        self.spin_overlap_mm.valueChanged.connect(self._save_report_overlap_settings)
        overlap_row.addWidget(self.chk_overlap)
        overlap_row.addWidget(self.spin_overlap_mm)
        overlap_row.addStretch()
        layout.addLayout(overlap_row)
        
        # Result table
        self.result_table = QtWidgets.QTableView()
        self.result_table.setAlternatingRowColors(True)
        self.result_model = SortableTableModel(pd.DataFrame())
        self.result_table.setModel(self.result_model)
        layout.addWidget(self.result_table, 1)

    def _create_pcb_preview_tab(self) -> None:
        self._pcb_tab = PcbPreviewTab(self)
        self.tabs.addTab(self._pcb_tab, self.ui_tr("tab.pcb_preview"))
        self.tabs.currentChanged.connect(self._on_main_tab_changed)

    def _create_machine_library_tab(self) -> None:
        self._machine_library_tab = MachineLibraryTab(self)
        self.tabs.addTab(self._machine_library_tab, self.ui_tr("tab.machine_lib"))

    def _on_main_tab_changed(self, idx: int) -> None:
        if self.tabs.widget(idx) is getattr(self, "_pcb_tab", None):
            self._refresh_pcb_preview_from_ui()

    def _pcb_preview_bridge_kwargs(self) -> Optional[dict]:
        self._sync_pnp_df_from_model()
        if self._pnp_df is None or not hasattr(self, "pnp_col_combos") or not self.pnp_col_combos:
            return None
        cols = list(self._pnp_df.columns)
        m: dict[str, object] = {}
        for i, combo in enumerate(self.pnp_col_combos):
            label = combo.currentText()
            if label != "-":
                m[label] = cols[i]
        ref = m.get("REF")
        xc = m.get("X")
        yc = m.get("Y")
        if not ref or not xc or not yc:
            return None
        return {
            "designator_col": ref,
            "x_col": xc,
            "y_col": yc,
            "rot_col": m.get("Rotation"),
            "layer_col": m.get("Layer"),
            "footprint_col": m.get("Footprint"),
            "value_col": m.get("Value"),
            "comment_col": m.get("Comment"),
            "coord_unit_mm": not self.pnp_units_mils.isChecked(),
        }

    def _refresh_pcb_preview_from_ui(self) -> None:
        kwargs = self._pcb_preview_bridge_kwargs()
        if kwargs is None:
            return
        self._pcb_tab.set_placements_from_dataframe(self._pnp_df, **kwargs)
    
    # =========================================================================
    # File handling
    # =========================================================================
    
    def _browse_bom(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select BOM file", "",
            "Supported (*.xls *.xlsx *.csv *.ods *.txt *.tab);;All (*.*)"
        )
        if path:
            self._load_bom(path)
    
    def _browse_pnp(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select PnP file", "",
            "Supported (*.xls *.xlsx *.csv *.ods *.txt *.tab);;All (*.*)"
        )
        if path:
            self._load_pnp(path)
    
    def _recover_snapshot_choice(self, path: str, kind: str) -> pd.DataFrame | None | str:
        return prompt_recover_snapshot(self, path, kind, self._autosave_dir)

    def _confirm_reload_original(self, kind: str) -> bool:
        dirty = self._bom_dirty if kind == "bom" else self._pnp_dirty
        if not dirty:
            return True
        res = QtWidgets.QMessageBox.question(
            self,
            "Reload original file?",
            f"Reload {kind.upper()} from original file?\n\n"
            "Unsaved working changes and new columns in this table will be replaced.",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        return res == QtWidgets.QMessageBox.StandardButton.Yes

    def _load_bom(self, path: str, *, force_original: bool = False):
        try:
            recovered = None if force_original else self._recover_snapshot_choice(path, "bom")
            if isinstance(recovered, str) and recovered == "cancel":
                return
            if not isinstance(recovered, pd.DataFrame):
                self._restore_bom_tab_load_params(path)
            sep = self.bom_separator.currentText()
            first = int(self.bom_first_row.text() or 1) - 1  # 0-based
            last_text = self.bom_last_row.text()
            last = int(last_text) - 1 if last_text else -1

            if isinstance(recovered, pd.DataFrame):
                self._bom_df = recovered
                self._bom_dirty = True
                recovered_note = "recovered working copy"
            else:
                self._bom_df = read_file(
                    path,
                    first_row=first,
                    last_row=last,
                    separator=sep,
                    column_headers_from_file=False,
                )
                self._bom_dirty = False
                recovered_note = "original file"
            self._bom_source_path = path
            self.bom_path_label.setText(path)
            self._loading_working_copy = True
            self.bom_model.update_dataframe(self._bom_df)
            self._loading_working_copy = False
            self._refresh_active_row_highlight("bom")
            self._fill_bom_combos()
            self._restore_bom_mappings_after_fill(path)
            QtCore.QTimer.singleShot(0, self._autoresize_bom_columns)
            
            if path not in self._recent_bom:
                self._recent_bom.insert(0, path)
                if len(self._recent_bom) > 10:
                    self._recent_bom.pop()
            
            self._log(
                f"Loaded BOM ({recovered_note}): {len(self._bom_df)} rows, {len(self._bom_df.columns)} cols",
                "info",
            )
            self._log(f"Columns: {list(self._bom_df.columns)}", "debug")
            if force_original:
                save_snapshot(
                    self._bom_df,
                    self._bom_source_path,
                    "bom",
                    self._autosave_dir,
                    dirty=False,
                )
            QtCore.QTimer.singleShot(0, self._save_bom_tab_settings_to_disk)
            self._hide_merge_cross_check_ok_banner()
        except SMTProcessorError as e:
            self._log(f"Error loading BOM: {e}", "error")
            QtWidgets.QMessageBox.critical(self, "Error", str(e))
    
        finally:
            self._loading_working_copy = False

    def _load_pnp(self, path: str, *, force_original: bool = False):
        try:
            recovered = None if force_original else self._recover_snapshot_choice(path, "pnp")
            if isinstance(recovered, str) and recovered == "cancel":
                return
            if not isinstance(recovered, pd.DataFrame):
                self._restore_pnp_tab_load_params(path)
            sep = self.pnp_separator.currentText()
            first = int(self.pnp_first_row.text() or 1) - 1
            last_text = self.pnp_last_row.text()
            last = int(last_text) - 1 if last_text else -1

            if isinstance(recovered, pd.DataFrame):
                self._pnp_df = recovered
                self._pnp_dirty = True
                recovered_note = "recovered working copy"
            else:
                if sep == "spaces":
                    self._pnp_df = read_text_whitespace_sp(path)
                    self._pnp_df = _clean_empty_rows(self._pnp_df)
                    if self._pnp_df.empty:
                        raise SMTEmptyDataError(f"No data rows in {path!r} (spaces mode)")
                    n = len(self._pnp_df)
                    if first >= n:
                        self._pnp_df = self._pnp_df.iloc[0:0].copy()
                    elif last < 0:
                        self._pnp_df = self._pnp_df.iloc[first:].copy().reset_index(drop=True)
                    elif last < first:
                        self._pnp_df = self._pnp_df.iloc[0:0].copy()
                    else:
                        end = min(last + 1, n)
                        self._pnp_df = self._pnp_df.iloc[first:end].copy().reset_index(drop=True)
                    if self._pnp_df.empty:
                        raise SMTEmptyDataError(f"No data after trim in {path!r} (spaces mode)")
                else:
                    self._pnp_df = read_file(
                        path,
                        first_row=first,
                        last_row=last,
                        separator=sep,
                        column_headers_from_file=False,
                    )
                self._pnp_dirty = False
                recovered_note = "original file"
            self._pnp_source_path = path
            self.pnp_path_label.setText(path)
            self._loading_working_copy = True
            self.pnp_model.update_dataframe(self._pnp_df)
            self._loading_working_copy = False
            self._refresh_active_row_highlight("pnp")
            self._fill_pnp_combos()
            self._restore_pnp_mappings_after_fill(path)
            QtCore.QTimer.singleShot(0, self._autoresize_pnp_columns)
            
            if path not in self._recent_pnp:
                self._recent_pnp.insert(0, path)
                if len(self._recent_pnp) > 10:
                    self._recent_pnp.pop()
            
            self._log(
                f"Loaded PnP ({recovered_note}): {len(self._pnp_df)} rows, {len(self._pnp_df.columns)} cols",
                "info",
            )
            self._log(f"Columns: {list(self._pnp_df.columns)}", "debug")
            if force_original:
                save_snapshot(
                    self._pnp_df,
                    self._pnp_source_path,
                    "pnp",
                    self._autosave_dir,
                    dirty=False,
                )
            QtCore.QTimer.singleShot(0, self._save_pnp_tab_settings_to_disk)
            self._hide_merge_cross_check_ok_banner()
        except SMTProcessorError as e:
            self._log(f"Error loading PnP: {e}", "error")
            QtWidgets.QMessageBox.critical(self, "Error", str(e))
        finally:
            self._loading_working_copy = False
    
    def _reload_bom(self):
        path = self.bom_path_label.text()
        if path and os.path.exists(path) and self._confirm_reload_original("bom"):
            self._load_bom(path, force_original=True)
    
    def _reload_pnp(self):
        path = self.pnp_path_label.text()
        if path and os.path.exists(path) and self._confirm_reload_original("pnp"):
            self._load_pnp(path, force_original=True)

    def _apply_theme(self, dark: bool, save: bool = True) -> None:
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        apply_stylesheet(app, theme=DARK_THEME if dark else LIGHT_THEME)
        self._current_theme = DARK_THEME if dark else LIGHT_THEME
        self._theme_button.blockSignals(True)
        self._theme_button.setChecked(dark)
        self._theme_button.setText(
            self.ui_tr("theme.dark" if dark else "theme.light")
        )
        self._theme_button.setToolTip(self.ui_tr("theme.tooltip"))
        self._theme_button.blockSignals(False)
        if save and hasattr(self, "_settings"):
            self._settings.setValue("ui/dark_theme", dark)

    def _toggle_theme(self) -> None:
        self._apply_theme(self._theme_button.isChecked(), save=True)

    def _on_merge_settings_changed(self) -> None:
        if not self._restoring_settings and hasattr(self, "merge_delete_dnp"):
            self._settings.setValue("merge/delete_dnp", self.merge_delete_dnp.isChecked())

    def _on_pnp_units_changed(self) -> None:
        if self._restoring_settings:
            return
        self._settings.setValue("pnp/units", "mils" if self.pnp_units_mils.isChecked() else "mm")

    def _on_colorful_logs_toggled(self, *_args) -> None:
        if self._restoring_settings or not hasattr(self, "_settings"):
            return
        self._settings.setValue("ui/colorful_logs", self.chk_colorful.isChecked())

    @staticmethod
    def _sanitize_profile_id(name: str) -> str:
        t = (name or "").strip().replace(" ", "_")
        if not t:
            return "default"
        out = re.sub(r"[^a-zA-Z0-9_-]", "", t)
        return out[:64] or "default"

    def _current_profile_id(self) -> str:
        return self._sanitize_profile_id(self.profile_combo.currentText())

    def _load_profile_combo_from_storage(self) -> None:
        s = self._settings
        raw = str(s.value(PROFILE_NAMES_KEY, "") or "").strip()
        names: list[str] = ["default"]
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list) and parsed:
                    names = [str(x) for x in parsed]
            except json.JSONDecodeError:
                pass
        names = [self._sanitize_profile_id(x) for x in names]
        if "default" not in names:
            names.insert(0, "default")
        last = self._sanitize_profile_id(str(s.value(PROFILE_LAST_ACTIVE_KEY, "default") or "default"))
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for n in names:
            if self.profile_combo.findText(n) < 0:
                self.profile_combo.addItem(n)
        idx = self.profile_combo.findText(last)
        self.profile_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.profile_combo.blockSignals(False)

    def _gather_clean_prefs_payload(self) -> dict[str, Any]:
        if not hasattr(self, "clean_res_template_combos"):
            return {}
        prov = "digikey"
        if hasattr(self, "clean_mpn_search_provider"):
            prov = self.clean_mpn_search_provider.currentData() or "digikey"
        key = str(prov) if prov is not None else "digikey"
        return {
            "res_template": ",".join(self._template_from_combos(self.clean_res_template_combos)),
            "cap_template": ",".join(self._template_from_combos(self.clean_cap_template_combos)),
            "ind_template": ",".join(self._template_from_combos(self.clean_ind_template_combos)),
            "cap_nf": self.clean_cap_nf.isChecked(),
            "use_vendor": self.clean_use_vendor.isChecked(),
            "from_db": self.clean_from_db.isChecked(),
            "from_hanwha_mdb": self.clean_from_hanwha_mdb.isChecked(),
            "prefix_use_separator": self.clean_prefix_use_separator.isChecked(),
            "res_prefix": self.clean_res_prefix.text(),
            "cap_prefix": self.clean_cap_prefix.text(),
            "ind_prefix": self.clean_ind_prefix.text(),
            "apply_replace": self.clean_apply_replace.isChecked(),
            "group_res": self.gb_clean_res.isChecked(),
            "group_cap": self.gb_clean_cap.isChecked(),
            "group_ind": self.gb_clean_ind.isChecked(),
            "group_pn": self.gb_clean_pn.isChecked(),
            "output_separator": self._clean_output_separator(),
            "mpn_search_provider": key,
            "octopart_api_key": self.clean_octopart_api_key.text()
            if hasattr(self, "clean_octopart_api_key")
            else "",
        }

    def _apply_clean_prefs_dict(self, c: dict[str, Any]) -> None:
        if not hasattr(self, "clean_res_template_combos"):
            return
        if hasattr(self, "gb_clean_res"):
            for gb in (
                self.gb_clean_res,
                self.gb_clean_cap,
                self.gb_clean_ind,
                self.gb_clean_pn,
            ):
                gb.blockSignals(True)
        for w in (
            *self.clean_res_template_combos,
            *self.clean_cap_template_combos,
            *self.clean_ind_template_combos,
            self.clean_cap_nf,
            self.clean_use_vendor,
            self.clean_from_db,
            self.clean_from_hanwha_mdb,
            self.clean_prefix_use_separator,
            self.clean_res_prefix,
            self.clean_cap_prefix,
            self.clean_ind_prefix,
            self.clean_apply_replace,
        ):
            w.blockSignals(True)
        self._set_template_combos(
            self.clean_res_template_combos,
            str(c.get("res_template", "nom,pack,watt,%")),
            ("nom", "pack", "watt", "%"),
        )
        self._set_template_combos(
            self.clean_cap_template_combos,
            str(c.get("cap_template", "nom,pack,film,%,W")),
            ("nom", "pack", "film", "%", "W"),
        )
        self._set_template_combos(
            self.clean_ind_template_combos,
            str(c.get("ind_template", "pack,nom,%,Imax,DCR")),
            ("pack", "nom", "%", "Imax", "DCR"),
        )
        self.clean_cap_nf.setChecked(bool(c.get("cap_nf", False)))
        self.clean_use_vendor.setChecked(bool(c.get("use_vendor", False)))
        self.clean_from_db.setChecked(bool(c.get("from_db", True)))
        self.clean_from_hanwha_mdb.setChecked(bool(c.get("from_hanwha_mdb", False)))
        self.clean_prefix_use_separator.setChecked(bool(c.get("prefix_use_separator", True)))
        self.clean_res_prefix.setText(str(c.get("res_prefix", "")))
        self.clean_cap_prefix.setText(str(c.get("cap_prefix", "")))
        self.clean_ind_prefix.setText(str(c.get("ind_prefix", "")))
        self.clean_apply_replace.setChecked(bool(c.get("apply_replace", False)))
        if hasattr(self, "gb_clean_res"):
            self.gb_clean_res.setChecked(bool(c.get("group_res", True)))
            self.gb_clean_cap.setChecked(bool(c.get("group_cap", True)))
            self.gb_clean_ind.setChecked(bool(c.get("group_ind", True)))
            self.gb_clean_pn.setChecked(bool(c.get("group_pn", True)))
        self.clean_spacer_combo.blockSignals(True)
        self.clean_spacer_cust.blockSignals(True)
        self._apply_clean_spacer_to_ui(str(c.get("output_separator", "_")))
        self.clean_spacer_combo.blockSignals(False)
        self.clean_spacer_cust.blockSignals(False)
        for w in (
            *self.clean_res_template_combos,
            *self.clean_cap_template_combos,
            *self.clean_ind_template_combos,
            self.clean_cap_nf,
            self.clean_use_vendor,
            self.clean_from_db,
            self.clean_from_hanwha_mdb,
            self.clean_prefix_use_separator,
            self.clean_res_prefix,
            self.clean_cap_prefix,
            self.clean_ind_prefix,
            self.clean_apply_replace,
        ):
            w.blockSignals(False)
        if hasattr(self, "clean_mpn_search_provider"):
            self.clean_mpn_search_provider.blockSignals(True)
            self.clean_octopart_api_key.blockSignals(True)
            prov = str(c.get("mpn_search_provider", "digikey"))
            for i in range(self.clean_mpn_search_provider.count()):
                if self.clean_mpn_search_provider.itemData(i) == prov:
                    self.clean_mpn_search_provider.setCurrentIndex(i)
                    break
            self.clean_octopart_api_key.setText(str(c.get("octopart_api_key", "")))
            self.clean_mpn_search_provider.blockSignals(False)
            self.clean_octopart_api_key.blockSignals(False)
        if hasattr(self, "gb_clean_res"):
            for gb in (
                self.gb_clean_res,
                self.gb_clean_cap,
                self.gb_clean_ind,
                self.gb_clean_pn,
            ):
                gb.blockSignals(False)
            self._on_gb_clean_res_toggled(self.gb_clean_res.isChecked())
            self._on_gb_clean_cap_toggled(self.gb_clean_cap.isChecked())
            self._on_gb_clean_ind_toggled(self.gb_clean_ind.isChecked())
            self._on_gb_clean_pn_toggled(self.gb_clean_pn.isChecked())

    def _gather_profile_payload(self) -> dict[str, Any]:
        bom_maps: list[str] = []
        if getattr(self, "bom_col_combos", None):
            bom_maps = [x.currentText() for x in self.bom_col_combos]
        pnp_maps: list[str] = []
        if getattr(self, "pnp_col_combos", None):
            pnp_maps = [x.currentText() for x in self.pnp_col_combos]
        pcb: dict[str, Any] = {}
        if hasattr(self, "_pcb_tab") and hasattr(self._pcb_tab, "export_ui_prefs"):
            pcb = self._pcb_tab.export_ui_prefs()
        lang = "en"
        if hasattr(self, "lang_combo"):
            lang = str(self.lang_combo.currentData() or "en")
        return {
            "v": PROFILE_STATE_VERSION,
            "ui": {
                "language": lang if lang in ("en", "ru") else "en",
                "dark_theme": bool(self._theme_button.isChecked()),
                "colorful_logs": self.chk_colorful.isChecked() if hasattr(self, "chk_colorful") else True,
            },
            "bom": {
                "separator": self.bom_separator.currentText(),
                "first_row": self.bom_first_row.text(),
                "last_row": self.bom_last_row.text(),
                "mappings": bom_maps,
            },
            "pnp": {
                "separator": self.pnp_separator.currentText(),
                "first_row": self.pnp_first_row.text(),
                "last_row": self.pnp_last_row.text(),
                "units": "mils" if self.pnp_units_mils.isChecked() else "mm",
                "mappings": pnp_maps,
            },
            "merge": {"delete_dnp": self.merge_delete_dnp.isChecked()},
            "report": {
                "show_critical": self.chk_critical.isChecked(),
                "show_warning": self.chk_warning.isChecked(),
                "show_info": self.chk_info.isChecked(),
                "overlap": self.chk_overlap.isChecked(),
                "overlap_mm": float(self.spin_overlap_mm.value()),
            },
            "clean": self._gather_clean_prefs_payload(),
            "pcb_preview": pcb,
        }

    def _apply_profile_payload(self, data: dict[str, Any]) -> None:
        ui = data.get("ui") or {}
        lang = str(ui.get("language", "en"))
        if lang not in ("en", "ru"):
            lang = "en"
        self._apply_theme(bool(ui.get("dark_theme", False)), save=False)
        if hasattr(self, "chk_colorful"):
            self.chk_colorful.setChecked(bool(ui.get("colorful_logs", True)))
        bom = data.get("bom") or {}
        bsep = str(bom.get("separator", "auto"))
        if self.bom_separator.findText(bsep) >= 0:
            self.bom_separator.setCurrentText(bsep)
        self.bom_first_row.setText(str(bom.get("first_row", "1")))
        self.bom_last_row.setText(str(bom.get("last_row", "")))
        bm = bom.get("mappings")
        self._profile_restore_bom_mappings = (
            [str(x) for x in bm] if isinstance(bm, list) else None
        )
        pnp = data.get("pnp") or {}
        psep = str(pnp.get("separator", "auto"))
        if self.pnp_separator.findText(psep) >= 0:
            self.pnp_separator.setCurrentText(psep)
        self.pnp_first_row.setText(str(pnp.get("first_row", "1")))
        self.pnp_last_row.setText(str(pnp.get("last_row", "")))
        if str(pnp.get("units", "mm")).lower() == "mils":
            self.pnp_units_mils.setChecked(True)
        else:
            self.pnp_units_mm.setChecked(True)
        pm = pnp.get("mappings")
        self._profile_restore_pnp_mappings = (
            [str(x) for x in pm] if isinstance(pm, list) else None
        )
        merge = data.get("merge") or {}
        self.merge_delete_dnp.setChecked(bool(merge.get("delete_dnp", False)))
        rep = data.get("report") or {}
        self.chk_critical.setChecked(bool(rep.get("show_critical", True)))
        self.chk_warning.setChecked(bool(rep.get("show_warning", True)))
        self.chk_info.setChecked(bool(rep.get("show_info", True)))
        self.chk_overlap.blockSignals(True)
        self.spin_overlap_mm.blockSignals(True)
        self.chk_overlap.setChecked(bool(rep.get("overlap", False)))
        self.spin_overlap_mm.setValue(float(rep.get("overlap_mm", 3.0)))
        self.spin_overlap_mm.setEnabled(self.chk_overlap.isChecked())
        self.spin_overlap_mm.blockSignals(False)
        self.chk_overlap.blockSignals(False)
        clean = data.get("clean")
        if isinstance(clean, dict) and clean:
            self._apply_clean_prefs_dict(clean)
        pcb = data.get("pcb_preview")
        if isinstance(pcb, dict) and hasattr(self, "_pcb_tab"):
            self._pcb_tab.apply_ui_prefs(pcb)
        if hasattr(self, "lang_combo"):
            self.lang_combo.blockSignals(True)
            li = self.lang_combo.findData(lang)
            if li >= 0:
                self.lang_combo.setCurrentIndex(li)
            self.lang_combo.blockSignals(False)
        self._apply_ui_language(lang, save=False)
        self._refresh_active_row_highlight("bom")
        self._refresh_active_row_highlight("pnp")

    def _save_full_profile_snapshot(self) -> None:
        if not hasattr(self, "_settings"):
            return
        self._save_clean_settings()
        if hasattr(self, "_save_clean_mpn_lookup_settings"):
            self._save_clean_mpn_lookup_settings()
        self._save_report_overlap_settings()
        if hasattr(self, "chk_critical"):
            self._settings.setValue("report/show_critical", self.chk_critical.isChecked())
            self._settings.setValue("report/show_warning", self.chk_warning.isChecked())
            self._settings.setValue("report/show_info", self.chk_info.isChecked())
        pid = self._current_profile_id()
        payload = self._gather_profile_payload()
        self._settings.setValue(f"profiles/{pid}/state_json", json.dumps(payload, ensure_ascii=False))
        self._settings.setValue(PROFILE_LAST_ACTIVE_KEY, pid)
        names = [self.profile_combo.itemText(i) for i in range(self.profile_combo.count())]
        self._settings.setValue(PROFILE_NAMES_KEY, json.dumps(names))
        self._settings.remove("files/last_bom")
        self._settings.remove("files/last_pnp")

    def _clear_bom_workspace(self) -> None:
        self._bom_df = None
        self._bom_source_path = ""
        self._bom_dirty = False
        self._loading_working_copy = True
        self.bom_model.update_dataframe(pd.DataFrame())
        self._loading_working_copy = False
        while self.bom_combos_layout.count():
            item = self.bom_combos_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.bom_col_combos = []
        self.bom_path_label.setText(self.ui_tr("project.no_file"))
        self._refresh_active_row_highlight("bom")
        self._hide_merge_cross_check_ok_banner()
        self._profile_restore_bom_mappings = None
        self._log(self.ui_tr("msg.bom_cleared"), "info")

    def _clear_pnp_workspace(self) -> None:
        self._pnp_df = None
        self._pnp_source_path = ""
        self._pnp_dirty = False
        self._loading_working_copy = True
        self.pnp_model.update_dataframe(pd.DataFrame())
        self._loading_working_copy = False
        while self.pnp_combos_layout.count():
            item = self.pnp_combos_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.pnp_col_combos = []
        self.pnp_path_label.setText(self.ui_tr("project.no_file"))
        self._refresh_active_row_highlight("pnp")
        self._hide_merge_cross_check_ok_banner()
        self._profile_restore_pnp_mappings = None
        self._refresh_pcb_preview_from_ui()
        self._log(self.ui_tr("msg.pnp_cleared"), "info")

    def _apply_pending_profile_bom_mappings(self) -> None:
        pm = getattr(self, "_profile_restore_bom_mappings", None)
        if not pm or not getattr(self, "bom_col_combos", None):
            return
        if len(pm) != len(self.bom_col_combos):
            return
        self._bom_ui_restoring = True
        try:
            for i, txt in enumerate(pm):
                if isinstance(txt, str) and self.bom_col_combos[i].findText(txt) >= 0:
                    self.bom_col_combos[i].setCurrentText(txt)
        finally:
            self._bom_ui_restoring = False
        self._profile_restore_bom_mappings = None

    def _apply_pending_profile_pnp_mappings(self) -> None:
        pm = getattr(self, "_profile_restore_pnp_mappings", None)
        if not pm or not getattr(self, "pnp_col_combos", None):
            return
        if len(pm) != len(self.pnp_col_combos):
            return
        self._pnp_ui_restoring = True
        try:
            for i, txt in enumerate(pm):
                if isinstance(txt, str) and self.pnp_col_combos[i].findText(txt) >= 0:
                    self.pnp_col_combos[i].setCurrentText(txt)
        finally:
            self._pnp_ui_restoring = False
        self._profile_restore_pnp_mappings = None

    def _on_profile_combo_changed(self, _text: str) -> None:
        if getattr(self, "_restoring_settings", False):
            return
        pid = self._current_profile_id()
        self._settings.setValue(PROFILE_LAST_ACTIVE_KEY, pid)
        raw = str(self._settings.value(f"profiles/{pid}/state_json", "") or "").strip()
        if not raw:
            self._log(self.ui_tr("msg.profile_empty_kept_ui", name=pid), "info")
            return
        try:
            self._restoring_settings = True
            self._apply_profile_payload(json.loads(raw))
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            self._log(self.ui_tr("msg.profile_load_failed", err=str(e)), "warning")
        finally:
            self._restoring_settings = False

    def _on_profile_clone_clicked(self) -> None:
        name, ok = QtWidgets.QInputDialog.getText(
            self,
            self.ui_tr("project.profile_clone"),
            self.ui_tr("msg.profile_clone_prompt"),
        )
        if not ok:
            return
        pid = self._sanitize_profile_id(name)
        if pid == "default":
            QtWidgets.QMessageBox.warning(
                self,
                self.ui_tr("project.profile_clone"),
                self.ui_tr("msg.profile_reserved_default"),
            )
            return
        if self.profile_combo.findText(pid) >= 0:
            QtWidgets.QMessageBox.warning(
                self,
                self.ui_tr("project.profile_clone"),
                self.ui_tr("msg.profile_exists", name=pid),
            )
            return
        src = self._current_profile_id()
        blob = self._settings.value(f"profiles/{src}/state_json", "")
        self._settings.setValue(f"profiles/{pid}/state_json", blob)
        self.profile_combo.addItem(pid)
        self.profile_combo.setCurrentText(pid)
        self._log(self.ui_tr("msg.profile_cloned", src=src, dst=pid), "info")

    def _on_profile_delete_clicked(self) -> None:
        pid = self._current_profile_id()
        if pid == "default":
            QtWidgets.QMessageBox.information(
                self,
                self.ui_tr("project.profile_delete"),
                self.ui_tr("msg.profile_cannot_delete_default"),
            )
            return
        res = QtWidgets.QMessageBox.question(
            self,
            self.ui_tr("project.profile_delete"),
            self.ui_tr("msg.profile_delete_confirm", name=pid),
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if res != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._settings.remove(f"profiles/{pid}/state_json")
        idx = self.profile_combo.currentIndex()
        self.profile_combo.removeItem(idx)
        self.profile_combo.setCurrentText("default")
        names = [self.profile_combo.itemText(i) for i in range(self.profile_combo.count())]
        self._settings.setValue(PROFILE_NAMES_KEY, json.dumps(names))
        self._log(self.ui_tr("msg.profile_deleted", name=pid), "info")

    def _load_settings(self) -> None:
        self._restoring_settings = True
        s = self._settings
        try:
            self._load_profile_combo_from_storage()
            pid = self._current_profile_id()
            blob = str(s.value(f"profiles/{pid}/state_json", "") or "").strip()
            loaded = False
            if blob:
                try:
                    self._apply_profile_payload(json.loads(blob))
                    loaded = True
                except (json.JSONDecodeError, TypeError, ValueError) as e:
                    logger.warning("Profile state invalid (%s); using legacy flat keys", e)
            if not loaded:
                self._load_legacy_settings_flat(s)
        finally:
            self._restoring_settings = False

    def _load_legacy_settings_flat(self, s: QSettings) -> None:
        dark = s.value("ui/dark_theme", False, type=bool)
        self._apply_theme(dark, save=False)
        if hasattr(self, "chk_colorful"):
            self.chk_colorful.setChecked(s.value("ui/colorful_logs", True, type=bool))
        if hasattr(self, "merge_delete_dnp") and s.contains("merge/delete_dnp"):
            self.merge_delete_dnp.setChecked(s.value("merge/delete_dnp", False, type=bool))
        if hasattr(self, "clean_res_template_combos"):
                if hasattr(self, "gb_clean_res"):
                    for gb in (
                        self.gb_clean_res,
                        self.gb_clean_cap,
                        self.gb_clean_ind,
                        self.gb_clean_pn,
                    ):
                        gb.blockSignals(True)
                for w in (
                    *self.clean_res_template_combos,
                    *self.clean_cap_template_combos,
                    *self.clean_ind_template_combos,
                    self.clean_cap_nf,
                    self.clean_use_vendor,
                    self.clean_from_db,
                    self.clean_from_hanwha_mdb,
                    self.clean_prefix_use_separator,
                    self.clean_res_prefix,
                    self.clean_cap_prefix,
                    self.clean_ind_prefix,
                    self.clean_apply_replace,
                ):
                    w.blockSignals(True)
                res_template = s.value(
                    "clean/res_template", "nom,pack,watt,%", str
                )
                cap_template = s.value(
                    "clean/cap_template", "nom,pack,film,%,W", str
                )
                ind_template = s.value(
                    "clean/ind_template", "pack,nom,%,Imax,DCR", str
                )
                self._set_template_combos(
                    self.clean_res_template_combos,
                    res_template,
                    ("nom", "pack", "watt", "%"),
                )
                self._set_template_combos(
                    self.clean_cap_template_combos,
                    cap_template,
                    ("nom", "pack", "film", "%", "W"),
                )
                self._set_template_combos(
                    self.clean_ind_template_combos,
                    ind_template,
                    ("pack", "nom", "%", "Imax", "DCR"),
                )
                self.clean_cap_nf.setChecked(
                    s.value("clean/cap_nf", False, type=bool)
                )
                self.clean_use_vendor.setChecked(
                    s.value("clean/use_vendor", False, type=bool)
                )
                self.clean_from_db.setChecked(
                    s.value("clean/from_db", True, type=bool)
                )
                self.clean_from_hanwha_mdb.setChecked(
                    s.value("clean/from_hanwha_mdb", False, type=bool)
                )
                self.clean_prefix_use_separator.setChecked(
                    s.value("clean/prefix_use_separator", True, type=bool)
                )
                self.clean_res_prefix.setText(s.value("clean/res_prefix", "", str))
                self.clean_cap_prefix.setText(s.value("clean/cap_prefix", "", str))
                self.clean_ind_prefix.setText(s.value("clean/ind_prefix", "", str))
                self.clean_apply_replace.setChecked(
                    s.value("clean/apply_replace", False, type=bool)
                )
                if hasattr(self, "gb_clean_res"):
                    self.gb_clean_res.setChecked(
                        s.value("clean/group_res", True, type=bool)
                    )
                    self.gb_clean_cap.setChecked(
                        s.value("clean/group_cap", True, type=bool)
                    )
                    self.gb_clean_ind.setChecked(
                        s.value("clean/group_ind", True, type=bool)
                    )
                    self.gb_clean_pn.setChecked(
                        s.value("clean/group_pn", True, type=bool)
                    )
                self.clean_spacer_combo.blockSignals(True)
                self.clean_spacer_cust.blockSignals(True)
                raw_sep = s.value("clean/output_separator", "_")
                if isinstance(raw_sep, str):
                    sep = raw_sep
                elif raw_sep is not None:
                    sep = str(raw_sep)
                else:
                    sep = "_"
                self._apply_clean_spacer_to_ui(sep)
                self.clean_spacer_combo.blockSignals(False)
                self.clean_spacer_cust.blockSignals(False)
                for w in (
                    *self.clean_res_template_combos,
                    *self.clean_cap_template_combos,
                    *self.clean_ind_template_combos,
                    self.clean_cap_nf,
                    self.clean_use_vendor,
                    self.clean_from_db,
                    self.clean_from_hanwha_mdb,
                    self.clean_prefix_use_separator,
                    self.clean_res_prefix,
                    self.clean_cap_prefix,
                    self.clean_ind_prefix,
                    self.clean_apply_replace,
                ):
                    w.blockSignals(False)
                if hasattr(self, "clean_mpn_search_provider"):
                    self.clean_mpn_search_provider.blockSignals(True)
                    self.clean_octopart_api_key.blockSignals(True)
                    prov = s.value("clean/mpn_search_provider", "digikey", str)
                    for i in range(self.clean_mpn_search_provider.count()):
                        if self.clean_mpn_search_provider.itemData(i) == prov:
                            self.clean_mpn_search_provider.setCurrentIndex(i)
                            break
                    self.clean_octopart_api_key.setText(
                        s.value("clean/octopart_api_key", "", str)
                    )
                    self.clean_mpn_search_provider.blockSignals(False)
                    self.clean_octopart_api_key.blockSignals(False)
                if hasattr(self, "gb_clean_res"):
                    for gb in (
                        self.gb_clean_res,
                        self.gb_clean_cap,
                        self.gb_clean_ind,
                        self.gb_clean_pn,
                    ):
                        gb.blockSignals(False)
                    self._on_gb_clean_res_toggled(self.gb_clean_res.isChecked())
                    self._on_gb_clean_cap_toggled(self.gb_clean_cap.isChecked())
                    self._on_gb_clean_ind_toggled(self.gb_clean_ind.isChecked())
                    self._on_gb_clean_pn_toggled(self.gb_clean_pn.isChecked())
        if hasattr(self, "chk_critical"):
            self.chk_critical.setChecked(s.value("report/show_critical", True, type=bool))
            self.chk_warning.setChecked(s.value("report/show_warning", True, type=bool))
            self.chk_info.setChecked(s.value("report/show_info", True, type=bool))
        if hasattr(self, "chk_overlap") and hasattr(self, "spin_overlap_mm"):
            self.chk_overlap.blockSignals(True)
            self.spin_overlap_mm.blockSignals(True)
            self.chk_overlap.setChecked(s.value("report/check_overlap", False, type=bool))
            ov = s.value("report/overlap_mm", 3.0)
            self.spin_overlap_mm.setValue(float(ov) if ov is not None else 3.0)
            self.spin_overlap_mm.setEnabled(self.chk_overlap.isChecked())
            self.spin_overlap_mm.blockSignals(False)
            self.chk_overlap.blockSignals(False)
        units = s.value("pnp/units", "mm", str)
        if units == "mils" and hasattr(self, "pnp_units_mils"):
            self.pnp_units_mils.setChecked(True)
        elif hasattr(self, "pnp_units_mm"):
            self.pnp_units_mm.setChecked(True)
        lang_raw = s.value("ui/language", "en")
        lang = str(lang_raw) if lang_raw is not None else "en"
        if lang not in ("en", "ru"):
            lang = "en"
        if hasattr(self, "lang_combo"):
            self.lang_combo.blockSignals(True)
            li = self.lang_combo.findData(lang)
            if li >= 0:
                self.lang_combo.setCurrentIndex(li)
            self.lang_combo.blockSignals(False)
        self._apply_ui_language(lang, save=False)

    def _save_report_overlap_settings(self) -> None:
        if self._restoring_settings or not hasattr(self, "_settings"):
            return
        s = self._settings
        s.setValue("report/check_overlap", self.chk_overlap.isChecked())
        s.setValue("report/overlap_mm", float(self.spin_overlap_mm.value()))

    def _on_bom_first_last_row_changed(self, *_args) -> None:
        self._refresh_active_row_highlight("bom")
        self._schedule_save_bom_tab_settings()

    def _on_pnp_first_last_row_changed(self, *_args) -> None:
        self._refresh_active_row_highlight("pnp")
        self._schedule_save_pnp_tab_settings()

    def _schedule_save_bom_tab_settings(self) -> None:
        if self._bom_ui_restoring or self._restoring_settings:
            return
        self._bom_tab_settings_timer.start(400)

    def _schedule_save_pnp_tab_settings(self) -> None:
        if self._pnp_ui_restoring or self._restoring_settings:
            return
        self._pnp_tab_settings_timer.start(400)

    @staticmethod
    def _qsettings_bool(value: Any, default: bool = True) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes")
        return bool(value)

    def _save_bom_tab_settings_to_disk(self) -> None:
        if self._bom_ui_restoring or self._restoring_settings:
            return
        path = self._bom_source_path
        if not path or not os.path.isfile(path):
            return
        h = path_settings_hash(path)
        self._settings.beginGroup(f"bom/ui/{h}")
        self._settings.setValue("separator", self.bom_separator.currentText())
        self._settings.setValue("first_row", self.bom_first_row.text())
        self._settings.setValue("last_row", self.bom_last_row.text())
        if hasattr(self, "bom_col_combos") and self.bom_col_combos:
            self._settings.setValue("mappings", [c.currentText() for c in self.bom_col_combos])
        self._settings.endGroup()

    def _save_pnp_tab_settings_to_disk(self) -> None:
        if self._pnp_ui_restoring or self._restoring_settings:
            return
        path = self._pnp_source_path
        if not path or not os.path.isfile(path):
            return
        h = path_settings_hash(path)
        self._settings.beginGroup(f"pnp/ui/{h}")
        self._settings.setValue("separator", self.pnp_separator.currentText())
        self._settings.setValue("first_row", self.pnp_first_row.text())
        self._settings.setValue("last_row", self.pnp_last_row.text())
        if hasattr(self, "pnp_col_combos") and self.pnp_col_combos:
            self._settings.setValue("mappings", [c.currentText() for c in self.pnp_col_combos])
        self._settings.endGroup()

    def _restore_bom_tab_load_params(self, path: str) -> None:
        if not path or not os.path.isfile(path):
            return
        h = path_settings_hash(path)
        self._settings.beginGroup(f"bom/ui/{h}")
        try:
            if not self._settings.contains("separator"):
                return
            self._bom_ui_restoring = True
            sep = self._settings.value("separator", "auto")
            if isinstance(sep, str) and self.bom_separator.findText(sep) >= 0:
                self.bom_separator.setCurrentText(sep)
            elif isinstance(sep, str):
                idx = self.bom_separator.findText(sep)
                if idx >= 0:
                    self.bom_separator.setCurrentIndex(idx)
            self.bom_first_row.setText(str(self._settings.value("first_row", "1")))
            self.bom_last_row.setText(str(self._settings.value("last_row", "")))
        finally:
            self._bom_ui_restoring = False
            self._settings.endGroup()

    def _restore_pnp_tab_load_params(self, path: str) -> None:
        if not path or not os.path.isfile(path):
            return
        h = path_settings_hash(path)
        self._settings.beginGroup(f"pnp/ui/{h}")
        try:
            if not self._settings.contains("separator"):
                return
            self._pnp_ui_restoring = True
            sep = self._settings.value("separator", "auto")
            if isinstance(sep, str) and self.pnp_separator.findText(sep) >= 0:
                self.pnp_separator.setCurrentText(sep)
            self.pnp_first_row.setText(str(self._settings.value("first_row", "1")))
            self.pnp_last_row.setText(str(self._settings.value("last_row", "")))
        finally:
            self._pnp_ui_restoring = False
            self._settings.endGroup()

    def _restore_bom_mappings_after_fill(self, path: str) -> None:
        if not path or not hasattr(self, "bom_col_combos") or not self.bom_col_combos:
            return
        h = path_settings_hash(path)
        self._settings.beginGroup(f"bom/ui/{h}")
        mappings = self._settings.value("mappings", [])
        self._settings.endGroup()
        if not isinstance(mappings, list) or len(mappings) != len(self.bom_col_combos):
            return
        self._bom_ui_restoring = True
        try:
            for i, m in enumerate(mappings):
                txt = str(m)
                if self.bom_col_combos[i].findText(txt) >= 0:
                    self.bom_col_combos[i].setCurrentText(txt)
        finally:
            self._bom_ui_restoring = False

    def _restore_pnp_mappings_after_fill(self, path: str) -> None:
        if not path or not hasattr(self, "pnp_col_combos") or not self.pnp_col_combos:
            return
        h = path_settings_hash(path)
        self._settings.beginGroup(f"pnp/ui/{h}")
        mappings = self._settings.value("mappings", [])
        self._settings.endGroup()
        if not isinstance(mappings, list) or len(mappings) != len(self.pnp_col_combos):
            return
        self._pnp_ui_restoring = True
        try:
            for i, m in enumerate(mappings):
                txt = str(m)
                if self.pnp_col_combos[i].findText(txt) >= 0:
                    self.pnp_col_combos[i].setCurrentText(txt)
        finally:
            self._pnp_ui_restoring = False

    # =========================================================================
    # Column selectors - fill and handlers
    # =========================================================================
    
    def _fill_bom_combos(self):
        """Create per-column role dropdowns above the BOM table."""
        if self._bom_df is None:
            return
        
        # Clear existing combos
        while self.bom_combos_layout.count():
            item = self.bom_combos_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        cols = list(self._bom_df.columns)
        self.bom_col_combos = []
        
        # Mapping options for BOM columns
        bom_options = ["-", "REF", "Comment"]
        
        for i, col_name in enumerate(cols):
            combo = QtWidgets.QComboBox()
            combo.addItems(bom_options)
            combo.setMinimumWidth(60)
            self._style_mapping_combo(combo)
            
            # Auto-detect REF or Comment
            col_name_str = str(col_name) if col_name else ""
            col_upper = col_name_str.upper()
            if "DESIGNATOR" in col_upper or "REF" in col_upper:
                combo.setCurrentText("REF")
            elif "COMMENT" in col_upper or "VALUE" in col_upper or "NAME" in col_upper:
                combo.setCurrentText("Comment")
            else:
                combo.setCurrentText("-")
            
            combo.currentTextChanged.connect(lambda t, idx=i: self._on_bom_col_mapping_changed(idx, t))
            self.bom_col_combos.append(combo)
            self.bom_combos_layout.addWidget(combo)
        
        QtCore.QTimer.singleShot(0, self._update_mapping_margins)
        # Sync widths after table is shown
        QtCore.QTimer.singleShot(50, self._sync_bom_all_combos_width)
        self._apply_pending_profile_bom_mappings()
    
    def _sync_bom_combo_width(self, col_idx, new_width):
        """Match one BOM mapping combo width to its table column."""
        if hasattr(self, "bom_col_combos") and col_idx < len(self.bom_col_combos):
            w = new_width if new_width > 0 else self.bom_table.sizeHintForColumn(col_idx)
            self.bom_col_combos[col_idx].setFixedWidth(max(60, w))
    
    def _sync_bom_all_combos_width(self):
        """Resize all BOM role dropdowns to match column widths."""
        if not hasattr(self, "bom_col_combos"):
            return
        header = self.bom_table.horizontalHeader()
        for i, combo in enumerate(self.bom_col_combos):
            w = self.bom_table.columnWidth(i) if header.count() > i else 60
            if w <= 0:
                w = self.bom_table.sizeHintForColumn(i)
            combo.setFixedWidth(max(60, w))
        self._update_mapping_margins("_bom")
        self._refresh_bom_mapping_strip()
    
    def _fill_pnp_combos(self):
        """Create per-column role dropdowns above the PnP table."""
        if self._pnp_df is None:
            return
        
        # Clear existing combos
        while self.pnp_combos_layout.count():
            item = self.pnp_combos_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        cols = list(self._pnp_df.columns)
        self.pnp_col_combos = []
        
        # Mapping options for PnP columns
        pnp_options = ["-", "REF", "Comment", "Value", "Footprint", "X", "Y", "Rotation", "Layer"]
        
        for i, col_name in enumerate(cols):
            combo = QtWidgets.QComboBox()
            combo.addItems(pnp_options)
            combo.setMinimumWidth(50)
            self._style_mapping_combo(combo)
            
            # Auto-detect
            col_name_str = str(col_name) if col_name else ""
            col_upper = col_name_str.upper()
            compact = col_upper.replace(" ", "")
            if "DESIGNATOR" in col_upper or "REFDES" in compact:
                combo.setCurrentText("REF")
            elif "POS-X" in compact and "MIL" not in col_upper:
                combo.setCurrentText("X")
            elif "POS-Y" in compact and "MIL" not in col_upper:
                combo.setCurrentText("Y")
            elif "MID-X" in col_upper or "MID-Y" in col_upper:
                combo.setCurrentText("-")
            elif "FOOTPRINT" in col_upper or "PATTERN" in col_upper or "PACKAGE" in col_upper:
                combo.setCurrentText("Footprint")
            elif "COMMENT" in col_upper and "VALUE" not in col_name_str:
                combo.setCurrentText("-")
            elif "VALUE" in col_upper and "POS" not in col_upper:
                combo.setCurrentText("-")
            elif "CENTER-X" in col_upper and "MID" not in col_upper:
                combo.setCurrentText("X")
            elif "CENTER-Y" in col_upper and "MID" not in col_upper:
                combo.setCurrentText("Y")
            elif col_upper.strip() == "X" and "MIL" not in col_upper and "PAD" not in col_upper and "MID" not in col_upper:
                combo.setCurrentText("X")
            elif col_upper.strip() == "Y" and "MIL" not in col_upper and "PAD" not in col_upper and "MID" not in col_upper:
                combo.setCurrentText("Y")
            elif "ROTATION" in col_upper:
                combo.setCurrentText("Rotation")
            elif "LAYER" in col_upper or "SIDE" in col_upper or "MIRROR" in col_upper:
                combo.setCurrentText("Layer")
            else:
                combo.setCurrentText("-")
            
            combo.currentTextChanged.connect(lambda t, idx=i: self._on_pnp_col_mapping_changed(idx, t))
            self.pnp_col_combos.append(combo)
            self.pnp_combos_layout.addWidget(combo)
        
        QtCore.QTimer.singleShot(0, lambda: self._update_mapping_margins("_pnp"))
        QtCore.QTimer.singleShot(50, self._sync_pnp_all_combos_width)
        self._apply_pending_profile_pnp_mappings()
    
    def _sync_pnp_combo_width(self, col_idx, new_width):
        """Match one PnP mapping combo width to its table column."""
        if hasattr(self, "pnp_col_combos") and col_idx < len(self.pnp_col_combos):
            w = new_width if new_width > 0 else self.pnp_table.sizeHintForColumn(col_idx)
            self.pnp_col_combos[col_idx].setFixedWidth(max(50, w))
    
    def _sync_pnp_all_combos_width(self):
        """Resize all PnP role dropdowns to match column widths."""
        if not hasattr(self, "pnp_col_combos"):
            return
        header = self.pnp_table.horizontalHeader()
        for i, combo in enumerate(self.pnp_col_combos):
            w = self.pnp_table.columnWidth(i) if header.count() > i else 50
            if w <= 0:
                w = self.pnp_table.sizeHintForColumn(i)
            combo.setFixedWidth(max(50, w))
        self._update_mapping_margins("_pnp")
        self._refresh_pnp_mapping_strip()
    
    def _on_bom_column_changed(self, text):
        """Legacy single-combo BOM column handler (logging only)."""
        self._log(f"BOM cols: REF={self.bom_ref_combo.currentText() if hasattr(self, 'bom_ref_combo') else 'N/A'}, Comment={self.bom_comment_combo.currentText() if hasattr(self, 'bom_comment_combo') else 'N/A'}", "debug")
    
    def _on_pnp_column_changed(self, text):
        """Legacy single-combo PnP column handler (logging only)."""
        self._log(f"PnP cols: REF={self.pnp_ref_combo.currentText() if hasattr(self, 'pnp_ref_combo') else 'N/A'}, Comment={self.pnp_comment_combo.currentText() if hasattr(self, 'pnp_comment_combo') else 'N/A'}", "debug")
    
    def _on_bom_col_mapping_changed(self, col_idx, mapping):
        """Per-column BOM role dropdown changed."""
        self._log(f"BOM col {col_idx} -> {mapping}", "debug")
        self._schedule_save_bom_tab_settings()

    def _on_pnp_col_mapping_changed(self, col_idx, mapping):
        """Per-column PnP role dropdown changed."""
        self._log(f"PnP col {col_idx} -> {mapping}", "debug")
        self._schedule_save_pnp_tab_settings()
    
    # =========================================================================
    # Header click handlers for column mapping
    # =========================================================================
    
    def _on_bom_header_click(self, section: int):
        """Handle click on BOM header - show mapping popup"""
        if self._bom_df is None:
            return
        
        cols = list(self._bom_df.columns)
        if section >= len(cols):
            return
        
        col_name = cols[section]
        options = ["REF", "Comment", "Value", "Description", "Footprint", "-"]
        
        # Show simple input dialog for mapping
        text, ok = QtWidgets.QInputDialog.getItem(
            self, 
            f"Map column: {col_name}", 
            "Select mapping:",
            ["-"] + options,
            0, False
        )
        
        if ok and text != "-":
            self._log(f"BOM column {col_name} -> {text}", "info")
    
    def _on_pnp_header_click(self, section: int):
        """Handle click on PnP header - show mapping popup"""
        if self._pnp_df is None:
            return
        
        cols = list(self._pnp_df.columns)
        if section >= len(cols):
            return
        
        col_name = cols[section]
        options = ["REF", "Comment", "Value", "Footprint", "X", "Y", "Rotation", "Layer", "-"]
        
        text, ok = QtWidgets.QInputDialog.getItem(
            self,
            f"Map column: {col_name}",
            "Select mapping:",
            ["-"] + options,
            0, False
        )
        
        if ok and text != "-":
            self._log(f"PnP column {col_name} -> {text}", "info")
    
    # =========================================================================
    # Cross-check, merge (shared processor config)
    # =========================================================================

    def _pnp_mappings_from_combos(self) -> dict[str, object]:
        self._sync_pnp_df_from_model()
        out: dict[str, object] = {}
        if self._pnp_df is None or not getattr(self, "pnp_col_combos", None):
            return out
        colnames = list(self._pnp_df.columns)
        for i, combo in enumerate(self.pnp_col_combos):
            m = combo.currentText()
            if m != "-" and i < len(colnames):
                out[m] = colnames[i]
        return out

    def _apply_pnp_dataframe(self, df: pd.DataFrame) -> None:
        self._loading_working_copy = True
        self._pnp_df = df
        self.pnp_model.update_dataframe(df)
        self._loading_working_copy = False
        self._refresh_active_row_highlight("pnp")
        self._autoresize_pnp_columns()
        self._mark_working_dirty("pnp")
        self._refresh_pcb_preview_from_ui()

    def _pnp_clean_xy_rot_columns(self) -> None:
        self._sync_pnp_df_from_model()
        if self._pnp_df is None or self._pnp_df.empty:
            QtWidgets.QMessageBox.warning(self, "Clean X/Y/R", "Load a PnP table first.")
            return
        maps = self._pnp_mappings_from_combos()
        xc, yc, rc = maps.get("X"), maps.get("Y"), maps.get("Rotation")
        miss = [n for n, c in (("X", xc), ("Y", yc), ("Rotation", rc)) if not c]
        if miss:
            QtWidgets.QMessageBox.warning(
                self,
                "Clean X/Y/R",
                "Map these PnP columns first: " + ", ".join(miss),
            )
            return
        df = self._pnp_df.copy()
        for col in (xc, yc, rc):
            df[col] = df[col].map(lambda v: pnp_coord.clean_numeric_cell_keep_separators(v))
        self._apply_pnp_dataframe(df)
        self._log("PnP: cleaned X / Y / Rotation cells", "info")

    def _pnp_convert_xy_mm_to_mil(self) -> None:
        self._sync_pnp_df_from_model()
        if self._pnp_df is None or self._pnp_df.empty:
            QtWidgets.QMessageBox.warning(self, "MM→MIL", "Load a PnP table first.")
            return
        maps = self._pnp_mappings_from_combos()
        xc, yc = maps.get("X"), maps.get("Y")
        if not xc or not yc:
            QtWidgets.QMessageBox.warning(self, "MM→MIL", "Map PnP columns X and Y first.")
            return
        df = self._pnp_df.copy()
        n = 0
        for i in df.index:
            xs, ys = pnp_coord.convert_xy_mm_to_mil_row(df.at[i, xc], df.at[i, yc])
            if xs and ys:
                df.at[i, xc] = xs
                df.at[i, yc] = ys
                n += 1
        self._apply_pnp_dataframe(df)
        self._log(f"PnP: MM→MIL on X/Y ({n} rows)", "info")

    def _pnp_convert_xy_mil_to_mm(self) -> None:
        self._sync_pnp_df_from_model()
        if self._pnp_df is None or self._pnp_df.empty:
            QtWidgets.QMessageBox.warning(self, "MIL→MM", "Load a PnP table first.")
            return
        maps = self._pnp_mappings_from_combos()
        xc, yc = maps.get("X"), maps.get("Y")
        if not xc or not yc:
            QtWidgets.QMessageBox.warning(self, "MIL→MM", "Map PnP columns X and Y first.")
            return
        df = self._pnp_df.copy()
        n = 0
        for i in df.index:
            xs, ys = pnp_coord.convert_xy_mil_to_mm_row(df.at[i, xc], df.at[i, yc])
            if xs and ys:
                df.at[i, xc] = xs
                df.at[i, yc] = ys
                n += 1
        self._apply_pnp_dataframe(df)
        self._log(f"PnP: MIL→MM on X/Y ({n} rows)", "info")

    def _configure_processor_from_ui(self) -> Optional[SMTDataProcessor]:
        self._sync_bom_df_from_model()
        self._sync_pnp_df_from_model()
        if self._bom_df is None:
            self._log("BOM not loaded", "warning")
            return None
        if self._pnp_df is None:
            self._log("PnP not loaded", "warning")
            return None
        if not hasattr(self, "pnp_col_combos") or not self.pnp_col_combos:
            self._log("PnP dropdowns not created - reload PnP file", "error")
            return None
        if not hasattr(self, "bom_col_combos") or not self.bom_col_combos:
            self._log("BOM dropdowns not created - reload BOM file", "error")
            return None

        bom_mappings: dict[str, object] = {}
        for i, combo in enumerate(self.bom_col_combos):
            mapping = combo.currentText()
            if mapping != "-":
                bom_mappings[mapping] = list(self._bom_df.columns)[i]

        pnp_mappings: dict[str, object] = {}
        for i, combo in enumerate(self.pnp_col_combos):
            mapping = combo.currentText()
            if mapping != "-":
                pnp_mappings[mapping] = list(self._pnp_df.columns)[i]

        bom_ref = bom_mappings.get("REF")
        bom_comment = bom_mappings.get("Comment")
        if not bom_ref:
            self._log("BOM: using first column as REF", "warning")
            bom_ref = list(self._bom_df.columns)[0]
        bom_comment_col = bom_comment if bom_comment else "_skip_"

        pnp_ref = pnp_mappings.get("REF")
        if not pnp_ref:
            for col in self._pnp_df.columns:
                if "DESIGNATOR" in str(col).upper():
                    pnp_ref = col
                    self._log(f"PnP: auto-detected REF as '{col}'", "debug")
                    break
        if not pnp_ref:
            self._log("PnP: ERROR - cannot find Designator column", "error")
            return None

        pnp_foot = pnp_mappings.get("Footprint")
        if not pnp_foot:
            for col in self._pnp_df.columns:
                if "FOOTPRINT" in str(col).upper():
                    pnp_foot = col
                    break

        pnp_x = pnp_mappings.get("X")
        pnp_y = pnp_mappings.get("Y")
        pnp_rot = pnp_mappings.get("Rotation")
        pnp_layer = pnp_mappings.get("Layer")
        pnp_val = pnp_mappings.get("Comment") or pnp_mappings.get("Value")
        pnp_comment_col = pnp_val if pnp_val else "_skip_"

        bom_cfg = ColumnConfig(
            designator=str(bom_ref),
            comment=str(bom_comment_col),
            has_header=HIDDEN_TABLE_HAS_HEADER_ROW,
        )
        pnp_cfg = ColumnConfig(
            designator=str(pnp_ref),
            comment=str(pnp_comment_col),
            footprint=str(pnp_foot) if pnp_foot else "_skip_",
            coord_x=str(pnp_x) if pnp_x else "_skip_",
            coord_y=str(pnp_y) if pnp_y else "_skip_",
            rotation=str(pnp_rot) if pnp_rot else "_skip_",
            layer=str(pnp_layer) if pnp_layer else "_skip_",
            has_header=HIDDEN_TABLE_HAS_HEADER_ROW,
        )

        use_mils = self.pnp_units_mils.isChecked()
        proc = SMTDataProcessor(
            ProcessorConfig(
                overlap_xy_are_mm=not use_mils,
                min_distance_mm=float(self.spin_overlap_mm.value()),
                check_overlap=self.chk_overlap.isChecked(),
                progress_log=lambda m, l: self.log_message.emit(m, l),
            )
        )
        proc.set_dataframes(self._bom_df, self._pnp_df, bom_cfg, pnp_cfg)
        return proc

    def _hide_merge_cross_check_ok_banner(self) -> None:
        if hasattr(self, "merge_cc_ok_banner"):
            self.merge_cc_ok_banner.setVisible(False)

    def _show_merge_cross_check_ok_banner(self) -> None:
        if hasattr(self, "merge_cc_ok_banner"):
            self.merge_cc_ok_banner.setVisible(True)

    def _run_cross_check(self) -> None:
        t = self._cc_thread
        if t is not None:
            try:
                if t.isRunning():
                    self._log("Cross-check already running", "warning")
                    return
            except RuntimeError:
                self._cc_thread = None
        self._hide_merge_cross_check_ok_banner()
        self._log("Running cross-check...", "info")
        proc = self._configure_processor_from_ui()
        if not proc:
            return
        self.processor = proc
        self.btn_cross_check.setEnabled(False)
        self._cc_thread = CrossCheckThread(proc, self)
        self._cc_thread.result_ready.connect(self._on_cross_check_finished)
        self._cc_thread.finished.connect(self._on_cross_check_thread_finished)
        self._cc_thread.start()

    def _on_cross_check_thread_finished(self) -> None:
        """Clear reference before deleteLater so we never call methods on a deleted QThread."""
        self.btn_cross_check.setEnabled(True)
        t = self._cc_thread
        self._cc_thread = None
        if t is not None:
            t.deleteLater()

    def _on_cross_check_finished(self, result: Any, err: str) -> None:
        if err:
            self._hide_merge_cross_check_ok_banner()
            self._log(f"Cross-check error: {err}", "error")
            self._last_report_html = ""
            self.btn_copy_html.setEnabled(False)
            self.btn_save_report_html.setEnabled(False)
            QtWidgets.QMessageBox.critical(self, "Error", err)
            return
        if result is None:
            self._hide_merge_cross_check_ok_banner()
            return
        cross_check_clean = bool(result.empty)
        try:
            filtered = result
            if not self.chk_critical.isChecked():
                filtered = filtered[filtered["Severity"] != "critical"]
            if not self.chk_warning.isChecked():
                filtered = filtered[filtered["Severity"] != "warning"]
            if not self.chk_info.isChecked():
                filtered = filtered[filtered["Severity"] != "info"]
            self._result_df = filtered
            self.result_model.update_dataframe(filtered)

            critical = int((filtered["Severity"] == "critical").sum()) if not filtered.empty else 0
            warn_n = int((filtered["Severity"] == "warning").sum()) if not filtered.empty else 0
            info_n = int((filtered["Severity"] == "info").sum()) if not filtered.empty else 0

            if cross_check_clean:
                self._show_merge_cross_check_ok_banner()
                self._log(
                    "Cross-check complete: no issues — BOM and PnP are consistent. "
                    "Use the Merge tab to merge and export.",
                    "info",
                )
                QtWidgets.QMessageBox.information(
                    self,
                    "Cross-check",
                    "No issues found. BOM and PnP look consistent.\n\n"
                    "Go to the Merge tab to run Merge and export CSV, Excel, or layer files.",
                )
            else:
                self._hide_merge_cross_check_ok_banner()
                self._log(f"Cross-check complete: {len(filtered)} issue(s) in report view", "info")
                self._log(f"  Critical: {critical}", "info")
                self._log(f"  Warning: {warn_n}", "info")
                self._log(f"  Info: {info_n}", "info")

            bom_p = self.bom_path_label.text()
            pnp_p = self.pnp_path_label.text()
            self._last_report_html = result_dataframe_to_html(
                filtered, bom_p if not bom_p.startswith("<") else "", pnp_p if not pnp_p.startswith("<") else ""
            )
            has_report = bool(self._last_report_html)
            self.btn_copy_html.setEnabled(has_report)
            self.btn_save_report_html.setEnabled(has_report)
        except Exception as e:
            self._hide_merge_cross_check_ok_banner()
            self._log(f"Cross-check result handling error: {e}", "error")
            self._last_report_html = ""
            self.btn_copy_html.setEnabled(False)
            self.btn_save_report_html.setEnabled(False)
            QtWidgets.QMessageBox.critical(self, "Error", str(e))

    def _run_merge(self) -> None:
        self._log("Running merge...", "info")
        try:
            proc = self._configure_processor_from_ui()
            if not proc:
                return
            self.processor = proc
            include_dnp = not self.merge_delete_dnp.isChecked()
            merged = self.processor.merge_bom_pnp(include_dnp=include_dnp)
            self._last_merge_df = merged
            self.merge_model.update_dataframe(merged)
            self._update_merge_layer_export_controls()
            self._log(f"Merge complete: {len(merged)} rows", "info")
        except SMTProcessorError as e:
            self._log(f"Merge error: {e}", "error")
            self._last_merge_df = None
            self._update_merge_layer_export_controls()
            QtWidgets.QMessageBox.critical(self, "Error", str(e))

    def _replace_pnp_from_merge(self) -> None:
        if self._last_merge_df is None or self._last_merge_df.empty:
            self._log("No merge data to replace PnP — run Merge first", "warning")
            QtWidgets.QMessageBox.warning(
                self, "Replace PNP", "Run Merge first; there is no merge result yet."
            )
            return
        res = QtWidgets.QMessageBox.question(
            self,
            "Replace PNP from Merge?",
            "Replace all data on the PnP tab with the current Merge result?\n\n"
            "This changes the working PnP copy; use Reload on the PnP tab to restore the original file.",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if res != QtWidgets.QMessageBox.StandardButton.Yes:
            return

        self._pnp_df = self._last_merge_df.copy()
        self._loading_working_copy = True
        self.pnp_model.update_dataframe(self._pnp_df)
        self._loading_working_copy = False
        self._fill_pnp_combos()
        self._refresh_active_row_highlight("pnp")
        self._autoresize_pnp_columns()
        self._mark_working_dirty("pnp")
        self._log(
            f"PnP replaced from Merge: {len(self._pnp_df)} rows, {len(self._pnp_df.columns)} cols",
            "info",
        )
        self._hide_merge_cross_check_ok_banner()

    def _merge_layer_column(self) -> Optional[str]:
        if self._last_merge_df is None:
            return None
        for col in self._last_merge_df.columns:
            if str(col).strip().lower() == "layer":
                return col
        return None

    @staticmethod
    def _display_layer_value(value: Any) -> str:
        if pd.isna(value):
            return "None"
        text = str(value).strip()
        if not text or text.lower() in ("nan", "none"):
            return "None"
        return text

    @staticmethod
    def _is_bot_layer_value(value: str) -> bool:
        return value.strip().lower() in ("m", "b", "bot", "bottom", "bottomlayer", "mirror")

    @staticmethod
    def _is_top_layer_value(value: str) -> bool:
        return value.strip().lower() in ("t", "top", "toplayer")

    def _merge_layer_values(self) -> list[str]:
        if self._last_merge_df is None or self._last_merge_df.empty:
            return []
        layer_col = self._merge_layer_column()
        if layer_col is None:
            return []
        values: list[str] = []
        for raw in self._last_merge_df[layer_col].tolist():
            val = self._display_layer_value(raw)
            if val not in values:
                values.append(val)
        return values

    def _select_merge_layer_defaults(self, values: list[str]) -> tuple[str | None, str | None]:
        if not values:
            return None, None
        top = next((v for v in values if self._is_top_layer_value(v)), None)
        bot = next((v for v in values if self._is_bot_layer_value(v)), None)
        if top is None and "None" in values:
            top = "None"
        if bot is None:
            bot = next((v for v in values if v != top), None)
        if top is None:
            top = next((v for v in values if v != bot), values[0])
        return top, bot

    def _populate_layer_combo(self, combo: QtWidgets.QComboBox, values: list[str], selected: str | None) -> None:
        combo.blockSignals(True)
        combo.clear()
        for value in values:
            combo.addItem(value, value)
        if selected is not None:
            idx = combo.findData(selected)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    def _update_merge_layer_export_controls(self) -> None:
        if not hasattr(self, "btn_export_top"):
            return
        has_merge = self._last_merge_df is not None and not self._last_merge_df.empty
        values = self._merge_layer_values()
        if not values and has_merge:
            values = ["All"]
        top, bot = self._select_merge_layer_defaults(values)
        self._populate_layer_combo(self.merge_top_layer_combo, values, top)
        self._populate_layer_combo(self.merge_bot_layer_combo, values, bot)
        has_layer_split = len(values) > 1 and values != ["All"]
        self.btn_export_top.setEnabled(has_merge)
        self.merge_top_layer_combo.setEnabled(has_merge and bool(values))
        self.btn_export_bot.setEnabled(has_merge and has_layer_split and bot is not None)
        self.merge_bot_layer_combo.setEnabled(has_merge and has_layer_split and bot is not None)

    def _merge_filtered_by_layer(self, selected: str) -> pd.DataFrame:
        if self._last_merge_df is None:
            return pd.DataFrame()
        if selected == "All":
            return self._last_merge_df.copy()
        layer_col = self._merge_layer_column()
        if layer_col is None:
            return self._last_merge_df.copy()
        mask = self._last_merge_df[layer_col].map(self._display_layer_value) == selected
        return self._last_merge_df.loc[mask].copy()

    def _export_merge_layer(self, side: str) -> None:
        if self._last_merge_df is None or self._last_merge_df.empty:
            self._log("No merge data to export — run Merge first", "warning")
            return
        combo = self.merge_bot_layer_combo if side == "bot" else self.merge_top_layer_combo
        selected = str(combo.currentData() or combo.currentText() or "All")
        out_df = self._merge_filtered_by_layer(selected)
        if out_df.empty:
            self._log(f"Merge {side.upper()} export is empty for Layer={selected}", "warning")
            return
        default_name = f"merge_{side}_{selected.lower().replace(' ', '_')}.csv"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, f"Export {side.upper()} CSV", default_name, "CSV (*.csv);;All (*.*)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            self.processor.export_csv(out_df, path)
            self._log(
                f"Exported {side.upper()} CSV ({selected}): {len(out_df)} rows -> {path}",
                "info",
            )
        except Exception as e:
            self._log(f"Export {side.upper()} CSV error: {e}", "error")
            QtWidgets.QMessageBox.critical(self, "Error", str(e))

    def _save_merge_csv(self) -> None:
        if self._last_merge_df is None or self._last_merge_df.empty:
            self._log("No merge data to save — run Merge first", "warning")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save merged CSV", "", "CSV (*.csv);;All (*.*)"
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            self.processor.export_csv(self._last_merge_df, path)
            self._log(f"Saved CSV: {path}", "info")
        except Exception as e:
            self._log(f"Save CSV error: {e}", "error")
            QtWidgets.QMessageBox.critical(self, "Error", str(e))

    def _save_merge_excel(self) -> None:
        if self._last_merge_df is None or self._last_merge_df.empty:
            self._log("No merge data to save — run Merge first", "warning")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save merged Excel", "", "Excel (*.xlsx);;All (*.*)"
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            self.processor.export_excel(self._last_merge_df, path)
            self._log(f"Saved Excel: {path}", "info")
        except Exception as e:
            self._log(f"Save Excel error: {e}", "error")
            QtWidgets.QMessageBox.critical(self, "Error", str(e))

    def _copy_report_html(self) -> None:
        if not self._last_report_html:
            self._log("No report HTML — run Cross-check first", "warning")
            return
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        clip = app.clipboard()
        mime = QtCore.QMimeData()
        plain = result_dataframe_plain_text(self._result_df) if self._result_df is not None else ""
        mime.setHtml(self._last_report_html)
        mime.setText(plain if plain else self._last_report_html)
        clip.setMimeData(mime)
        self._log("Report copied to clipboard (HTML + text)", "info")

    def _save_report_html(self) -> None:
        if not self._last_report_html:
            self._log("No report HTML — run Cross-check first", "warning")
            QtWidgets.QMessageBox.warning(
                self,
                "Save HTML report",
                "Run Cross-check first; there is no report to save.",
            )
            return
        bom_t = self.bom_path_label.text()
        pnp_t = self.pnp_path_label.text()
        start_dir = os.getcwd()
        suggest = "cross_check_report.html"
        for p in (bom_t, pnp_t):
            if not p or p.startswith("<"):
                continue
            path_obj = Path(p).expanduser()
            try:
                resolved = path_obj.resolve()
            except OSError:
                continue
            parent = resolved.parent
            if parent.is_dir():
                start_dir = str(parent)
            if path_obj.is_file():
                suggest = f"{path_obj.stem}_cross_check_report.html"
                break
            if path_obj.stem:
                suggest = f"{path_obj.stem}_cross_check_report.html"
                break

        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save HTML report",
            os.path.join(start_dir, suggest),
            "HTML files (*.html);;All files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".html"):
            path += ".html"
        try:
            doc = html_document_from_fragment(self._last_report_html)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(doc)
        except OSError as e:
            self._log(f"Save HTML report failed: {e}", "error")
            QtWidgets.QMessageBox.critical(self, "Save HTML report", str(e))
            return
        self._log(f"Saved HTML report: {path}", "info")

    def _find_replace_table(self, kind: str) -> None:
        table = self.bom_table if kind == "bom" else self.pnp_table
        model = self.bom_model if kind == "bom" else self.pnp_model
        df = model.get_dataframe()
        if df is None or df.empty:
            self._log(f"{kind.upper()}: no table data for Find / Replace", "warning")
            return

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(f"{kind.upper()} Find / Replace")
        form = QtWidgets.QFormLayout(dlg)
        find_edit = QtWidgets.QLineEdit()
        replace_edit = QtWidgets.QLineEdit()
        scope_combo = QtWidgets.QComboBox()
        scope_combo.addItem("Selected cells", "selected")
        scope_combo.addItem("Current column", "column")
        scope_combo.addItem("Whole table", "all")
        match_case = QtWidgets.QCheckBox("Match case")
        whole_cell = QtWidgets.QCheckBox("Whole cell")
        form.addRow("Find", find_edit)
        form.addRow("Replace with", replace_edit)
        form.addRow("Scope", scope_combo)
        form.addRow(match_case)
        form.addRow(whole_cell)
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Apply
            | QtWidgets.QDialogButtonBox.StandardButton.Close
        )
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Apply).setText("Replace all")
        form.addRow(buttons)

        def replace_all() -> None:
            needle = find_edit.text()
            if not needle:
                self._log("Find / Replace: empty Find text", "warning")
                return
            repl = replace_edit.text()
            scope = scope_combo.currentData()
            indexes: list[tuple[int, int]] = []
            if scope == "selected":
                indexes = sorted(
                    {(idx.row(), idx.column()) for idx in table.selectionModel().selectedIndexes()}
                )
                if not indexes:
                    self._log("Find / Replace: no selected cells", "warning")
                    return
            elif scope == "column":
                cur = table.currentIndex()
                if not cur.isValid():
                    self._log("Find / Replace: select a current cell/column first", "warning")
                    return
                indexes = [(r, cur.column()) for r in range(len(df))]
            else:
                indexes = [(r, c) for r in range(len(df)) for c in range(len(df.columns))]

            changed = 0
            cmp_needle = needle if match_case.isChecked() else needle.lower()
            new_df = df.copy()
            for row, col in indexes:
                if row >= len(new_df) or col >= len(new_df.columns):
                    continue
                value = new_df.iat[row, col]
                text = "" if pd.isna(value) else str(value)
                cmp_text = text if match_case.isChecked() else text.lower()
                if whole_cell.isChecked():
                    if cmp_text != cmp_needle:
                        continue
                    out = repl
                else:
                    if cmp_needle not in cmp_text:
                        continue
                    if match_case.isChecked():
                        out = text.replace(needle, repl)
                    else:
                        out = re.sub(re.escape(needle), repl, text, flags=re.IGNORECASE)
                if out != text:
                    new_df.iat[row, col] = out
                    changed += 1
            if changed:
                model.update_dataframe(new_df)
                if kind == "bom":
                    self._bom_df = new_df
                    self._mark_working_dirty("bom")
                    self._fill_bom_combos()
                    QtCore.QTimer.singleShot(0, self._autoresize_bom_columns)
                else:
                    self._pnp_df = new_df
                    self._mark_working_dirty("pnp")
                    self._fill_pnp_combos()
                    QtCore.QTimer.singleShot(0, self._autoresize_pnp_columns)
            self._log(f"{kind.upper()} Find / Replace: {changed} cell(s) changed", "info")

        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Apply).clicked.connect(replace_all)
        buttons.rejected.connect(dlg.reject)
        dlg.resize(420, 180)
        dlg.exec()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Persist active profile snapshot (widgets only; no BOM/PnP file paths)."""
        try:
            if hasattr(self, "_save_full_profile_snapshot"):
                self._save_full_profile_snapshot()
            if hasattr(self, "_settings"):
                self._settings.sync()
        finally:
            super().closeEvent(event)

    # =========================================================================
    # Logging
    # =========================================================================
    
    def _log(self, message: str, level: str = "info"):
        self.log_message.emit(message, level)
    
    def _on_log_message(self, message: str, level: str):
        color = {
            "error": "red",
            "warning": "orange", 
            "info": "black",
            "debug": "gray"
        }.get(level, "black")
        
        self.console.append(f'<span style="color:{color}">{message}</span>')
        


# =========================================================================
# App entry point
# =========================================================================

def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(SETTINGS_ORG)
    apply_stylesheet(app, theme=LIGHT_THEME)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()