"""View-only filter: hide standard-library (S) parts without removing rows from save."""

from __future__ import annotations

from PySide6 import QtCore

from hanwha_mdb_edit.core.part_filters import is_standard_library_s_row


class HanwhaPartLibraryFilterProxy(QtCore.QSortFilterProxyModel):
    """Filters source rows; underlying DataFrame stays complete for CSV/ODBC save."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._hide_standard_s = True
        self._partname_col = -1
        self._partdesc_col = -1

    def set_hide_standard_s(self, hide: bool) -> None:
        self._hide_standard_s = hide
        self.invalidateFilter()

    def hide_standard_s(self) -> bool:
        return self._hide_standard_s

    def sync_column_indices(self, column_names: list[str]) -> None:
        self._partname_col = column_names.index("PARTNAME") if "PARTNAME" in column_names else -1
        self._partdesc_col = column_names.index("PARTDESC") if "PARTDESC" in column_names else -1
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QtCore.QModelIndex) -> bool:
        if not self._hide_standard_s:
            return True
        if self._partname_col < 0:
            return True
        sm = self.sourceModel()
        if sm is None:
            return True
        pn_idx = sm.index(source_row, self._partname_col, source_parent)
        pn = sm.data(pn_idx, QtCore.Qt.ItemDataRole.DisplayRole)
        pd_ = ""
        if self._partdesc_col >= 0:
            pd_idx = sm.index(source_row, self._partdesc_col, source_parent)
            raw = sm.data(pd_idx, QtCore.Qt.ItemDataRole.DisplayRole)
            pd_ = raw if raw is not None else ""
        return not is_standard_library_s_row(pn, pd_)
