"""
Flow Layout for PyQt6
Based on the Qt6 FlowLayout examples from the documentation
"""

from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtWidgets import QLayout, QSizePolicy, QStyle


class FlowLayout(QLayout):
    """FlowLayout implementation for PyQt6."""
    
    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
            
        self.setSpacing(spacing)
        self._item_list = []
        
    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)
            
    def addItem(self, item):
        self._item_list.append(item)
        
    def count(self):
        return len(self._item_list)
        
    def itemAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None
        
    def takeAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None
        
    def expandingDirections(self):
        return Qt.Orientation(0)
        
    def hasHeightForWidth(self):
        return True
        
    def heightForWidth(self, width):
        height = self._do_layout(QRect(0, 0, width, 0), True)
        return height
        
    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)
        
    def sizeHint(self):
        return self.minimumSize()
        
    def minimumSize(self):
        size = QSize()
        
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
            
        margin = self.contentsMargins()
        size += QSize(2 * margin.left(), 2 * margin.top())
        return size
        
    def _do_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self.spacing()
        
        for item in self._item_list:
            widget = item.widget()
            if widget:
                style = widget.style()
                layout_spacing_x = style.layoutSpacing(
                    QSizePolicy.ControlType.PushButton, 
                    QSizePolicy.ControlType.PushButton,
                    Qt.Orientation.Horizontal
                )
                layout_spacing_y = style.layoutSpacing(
                    QSizePolicy.ControlType.PushButton, 
                    QSizePolicy.ControlType.PushButton,
                    Qt.Orientation.Vertical
                )
                space_x = spacing + layout_spacing_x
                space_y = spacing + layout_spacing_y
                
                next_x = x + item.sizeHint().width() + space_x
                if next_x - space_x > rect.right() and line_height > 0:
                    x = rect.x()
                    y = y + line_height + space_y
                    next_x = x + item.sizeHint().width() + space_x
                    line_height = 0
                    
                if not test_only:
                    item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
                    
                x = next_x
                line_height = max(line_height, item.sizeHint().height())
                
        return y + line_height - rect.y() 