"""
PandasTableModel - мост между pandas DataFrame и PySide6 QTableView.

Наследуется от QAbstractTableModel, корректно работает с NaN/NaT из pandas.
"""

import pandas as pd
import numpy as np
from typing import Optional, Any, Union
from PySide6 import QtCore
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6 import QtGui


class PandasTableModel(QAbstractTableModel):
    """
    Универсальная модель для отображения pandas DataFrame в QTableView.
    
    Usage:
        model = PandasTableModel(df)
        table_view.setModel(model)
        
        # Обновление данных:
        model.update_dataframe(new_df)
    """
    
    def __init__(
        self,
        dataframe: Optional[pd.DataFrame] = None,
        parent: Optional[QtCore.QObject] = None,
        editable: bool = False,
    ):
        super().__init__(parent)
        self._df = dataframe if dataframe is not None else pd.DataFrame()
        self._editable = editable
        self._active_row_range: tuple[int, int] | None = None
    
    # =========================================================================
    # Required Abstract Methods
    # =========================================================================
    
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._df)
    
    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._df.columns)
    
    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        
        row = index.row()
        col = index.column()
        
        if row >= len(self._df) or col >= len(self._df.columns):
            return None
        
        value = self._df.iloc[row, col]
        
        if role == Qt.ItemDataRole.DisplayRole:
            return self._format_value(value)
        
        elif role == Qt.ItemDataRole.EditRole:
            return self._format_value(value, for_edit=True)
        
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        
        elif role == Qt.ItemDataRole.ToolTipRole:
            return self._format_value(value, for_edit=True)
        
        elif role == Qt.ItemDataRole.BackgroundRole:
            return self._get_background(row, col, value)
        
        elif role == Qt.ItemDataRole.ForegroundRole:
            return self._get_foreground(row, col, value)
        
        return None
    
    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if orientation == Qt.Orientation.Horizontal:
            if role != Qt.ItemDataRole.DisplayRole:
                return None
            if section < len(self._df.columns):
                return str(self._df.columns[section])
            return None
        
        elif orientation == Qt.Orientation.Vertical:
            if role == Qt.ItemDataRole.DisplayRole:
                return str(section + 1)
            if role == Qt.ItemDataRole.BackgroundRole and self._active_row_range is not None:
                first, last = self._active_row_range
                row_number = section + 1
                if first <= row_number <= last:
                    return QtGui.QBrush(QtGui.QColor(66, 133, 244))
            if role == Qt.ItemDataRole.ForegroundRole and self._active_row_range is not None:
                first, last = self._active_row_range
                row_number = section + 1
                if first <= row_number <= last:
                    return QtGui.QBrush(QtGui.QColor(255, 255, 255))
            if role == Qt.ItemDataRole.FontRole and self._active_row_range is not None:
                first, last = self._active_row_range
                row_number = section + 1
                if first <= row_number <= last:
                    font = QtGui.QFont()
                    font.setBold(True)
                    return font
        
        return None
    
    # =========================================================================
    # Optional: Flags
    # =========================================================================
    
    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if self._editable:
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(
        self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:
        if not self._editable or role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        row = index.row()
        col = index.column()
        if row >= len(self._df) or col >= len(self._df.columns):
            return False
        self._df.iat[row, col] = value
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])
        return True
    
    # =========================================================================
    # Update Methods
    # =========================================================================
    
    def update_dataframe(self, new_df: Optional[pd.DataFrame]) -> None:
        if new_df is None:
            new_df = pd.DataFrame()
        
        old_rows = len(self._df)
        old_cols = len(self._df.columns)
        
        self.beginResetModel()
        self._df = new_df
        self.endResetModel()
        
        if old_rows != len(new_df) or old_cols != len(new_df.columns):
            pass
    
    def get_dataframe(self) -> pd.DataFrame:
        return self._df

    def set_active_row_range(self, first: int | None, last: int | None) -> None:
        if first is None or last is None or first < 1 or last < first:
            self._active_row_range = None
        else:
            self._active_row_range = (first, last)
        if self.rowCount() > 0:
            self.headerDataChanged.emit(
                Qt.Orientation.Vertical, 0, self.rowCount() - 1
            )
    
    def get_column_value(self, column_name: str) -> pd.Series:
        if column_name in self._df.columns:
            return self._df[column_name]
        return pd.Series()
    
    def get_row_values(self, row: int) -> dict:
        if row < len(self._df):
            return self._df.iloc[row].to_dict()
        return {}
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _format_value(self, value: Any, for_edit: bool = False) -> str:
        if value is None or pd.isna(value):
            return ""
        
        if isinstance(value, (bool, np.bool_)):
            return "Yes" if value else "No"
        
        if isinstance(value, (int, float, np.integer, np.floating)):
            if for_edit:
                return str(value)
            if isinstance(value, float):
                return f"{value:g}"
            return str(value)
        
        try:
            if isinstance(value, pd.Timestamp):
                return value.strftime("%Y-%m-%d %H:%M:%S")
        except:
            pass
        
        return str(value).strip()
    
    def _get_background(self, row: int, col: int, value: Any) -> Optional[QtGui.QBrush]:
        # Simple alternate row colors using RGB
        if row % 2 == 1:
            return QtGui.QBrush(QtGui.QColor(240, 240, 240))
        return None
    
    def _get_foreground(self, row: int, col: int, value: Any) -> Optional[QtGui.QBrush]:
        return None


class ReadOnlyTableModel(PandasTableModel):
    """Read-only модель без редактирования"""
    pass


class SortableTableModel(PandasTableModel):
    """Сортируемая модель (клик по заголовку)"""
    
    def __init__(
        self,
        dataframe: Optional[pd.DataFrame] = None,
        parent: Optional[QtCore.QObject] = None,
        editable: bool = False,
    ):
        super().__init__(dataframe, parent, editable=editable)
        self._sort_column = -1
        self._sort_order = Qt.SortOrder.AscendingOrder
    
    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        if column < 0 or column >= len(self._df.columns):
            return
        
        self.beginResetModel()
        self._sort_column = column
        self._sort_order = order
        
        col_name = self._df.columns[column]
        ascending = (order == Qt.SortOrder.AscendingOrder)
        
        try:
            self._df = self._df.sort_values(by=col_name, ascending=ascending)
        except Exception:
            pass
        
        self.endResetModel()
    
    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        result = super().headerData(section, orientation, role)
        
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            if section == self._sort_column:
                arrow = "▲" if self._sort_order == Qt.SortOrder.AscendingOrder else "▼"
                return f"{result} {arrow}"
        
        return result


def create_table_model(df: Optional[pd.DataFrame] = None, 
                   sortable: bool = False,
                   readonly: bool = True) -> PandasTableModel:
    if sortable:
        return SortableTableModel(df, editable=not readonly)
    elif readonly:
        return ReadOnlyTableModel(df)
    else:
        return PandasTableModel(df)