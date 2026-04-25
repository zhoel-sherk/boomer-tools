"""
Custom QTableView с clickable headers для popup маппинга.
"""

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtCore import Signal


class ClickableHeaderView(QtWidgets.QHeaderView):
    """Кастомный header с поддержкой клика для popup"""
    
   sectionClicked = Signal(int)  # column index
    sectionDoubleClicked = Signal(int)
    
    def __init__(self, orientation: QtCore.Qt.Orientation, parent=None):
        super().__init__(orientation, parent)
        self._section_sizes = {}
        self._click_timer = None
        
    def mousePressEvent(self, event: QtGui.QMouseEvent):
        """Handle mouse press - detect click vs double click"""
        pos = event.pos()
        if self.orientation == QtCore.Qt.Orientation.Horizontal:
            # Find which section was clicked
            for i in range(self.count()):
                size = self.sectionSize(i)
                x = self.sectionPosition(i)
                if x <= pos.x() < x + size:
                    # Single click - emit aftershort delay to distinguish from double
                    self._clicked_section = i
                    self._click_timer = QtCore.QTimer.singleShot(300, lambda: self._emit_click(i))
                    break
        super().mousePressEvent(event)
    
    def _emit_click(self, section):
        """Emit single click signal"""
        self.sectionClicked.emit(section)
    
    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent):
        """Handle double click - cancel single click timer"""
        if self._click_timer:
            self._click_timer.stop()
            self._click_timer = None
        
        pos = event.pos()
        if self.orientation == QtCore.Qt.Orientation.Horizontal:
            for i in range(self.count()):
                size = self.sectionSize(i)
                x = self.sectionPosition(i)
                if x <= pos.x() < x + size:
                    self.sectionDoubleClicked.emit(i)
                    break
        super().mouseDoubleClickEvent(event)


class MappingPopup(QtWidgets.QDialog):
    """Popup для выбора маппинга колонки"""
    
    def __init__(self, column_name: str, column_options: list, current_mapping: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Map column: {column_name}")
        self.setModal(True)
        
        layout = QtWidgets.QFormLayout(self)
        
        # Current column
        layout.addRow("Column:", QtWidgets.QLabel(column_name))
        
        # Mapping dropdown
        self.mapping_combo = QtWidgets.QComboBox()
        self.mapping_combo.addItems(["-"] + column_options)  # "-" = skip
        
        if current_mapping and current_mapping in column_options:
            self.mapping_combo.setCurrentText(current_mapping)
        elif not current_mapping or current_mapping == "?":
            self.mapping_combo.setCurrentText("-")
        
        layout.addRow("Map to:", self.mapping_combo)
        
        # Buttons
        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)
        
        self.resize(250, 120)
    
    def get_mapping(self) -> str:
        return self.mapping_combo.currentText()


class TableViewWithMapper(QtWidgets.QTableView):
    """TableView с поддержкой маппинга колонок по клику"""
    
    headerDoubleClicked = Signal(int)  # column index
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Enable sorting by clicking header
        self.setSortingEnabled(True)
    
    def set_clickable_header(self, header_widget_class=None):
        """Set up clickable header"""
        if header_widget_class:
            header = header_widget_class(QtCore.Qt.Orientation.Horizontal, self)
            header.sectionDoubleClicked.connect(self._on_header_double_click)
            self.setHeader(header)
    
    def _on_header_double_click(self, section: int):
        """Handle header double click"""
        self.headerDoubleClicked.emit(section)
    
    def show_mapping_popup(self, column_index: int, column_name: str, 
                         column_options: list, current_mapping: str) -> str:
        """Показать popup для маппинга"""
        popup = MappingPopup(column_name, column_options, current_mapping, self)
        if popup.exec() == QtWidgets.QDialog.Accepted:
            return popup.get_mapping()
        return current_mapping


# Convenience factory
def create_table_with_mapper(parent=None) -> TableViewWithMapper:
    """Создать TableView с маппером"""
    view = TableViewWithMapper(parent)
    view.set_clickable_header(ClickableHeaderView)
    return view