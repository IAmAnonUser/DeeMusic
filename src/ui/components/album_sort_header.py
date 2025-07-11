"""
Album sort header component for DeeMusic.
Provides sorting options for album grids (Albums, Singles, EPs, Featured In).
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
import logging

logger = logging.getLogger(__name__)

class AlbumSortHeader(QWidget):
    """Header widget with sorting options for album grids."""
    
    # Signal emitted when sort criteria changes
    sort_requested = pyqtSignal(str, bool)  # sort_by, ascending
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_sort_by = "release_date"  # Default sort by release date
        self.current_ascending = False  # Default to newest first
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Setup the sorting header UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(10)
        
        # Sort label
        sort_label = QLabel("Sort by:")
        sort_label.setObjectName("album_sort_label")
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        sort_label.setFont(font)
        layout.addWidget(sort_label)
        
        # Sort dropdown
        self.sort_combo = QComboBox()
        self.sort_combo.setObjectName("album_sort_combo")
        self.sort_combo.addItem("Release Date", "release_date")
        self.sort_combo.addItem("Alphabetical", "title")
        self.sort_combo.setCurrentText("Release Date")
        self.sort_combo.currentTextChanged.connect(self._on_sort_changed)
        layout.addWidget(self.sort_combo)
        
        # Sort order button
        self.order_button = QPushButton("Newest First")
        self.order_button.setObjectName("album_sort_order_button")
        self.order_button.clicked.connect(self._toggle_sort_order)
        layout.addWidget(self.order_button)
        
        # Add stretch to push everything to the left
        layout.addStretch(1)
        
        # Set fixed height
        self.setFixedHeight(45)
        
    def _on_sort_changed(self):
        """Handle sort criteria change."""
        current_data = self.sort_combo.currentData()
        if current_data:
            self.current_sort_by = current_data
            self._update_order_button_text()
            self.sort_requested.emit(self.current_sort_by, self.current_ascending)
            
    def _toggle_sort_order(self):
        """Toggle sort order between ascending and descending."""
        self.current_ascending = not self.current_ascending
        self._update_order_button_text()
        self.sort_requested.emit(self.current_sort_by, self.current_ascending)
        
    def _update_order_button_text(self):
        """Update the order button text based on current sort criteria."""
        if self.current_sort_by == "release_date":
            self.order_button.setText("Newest First" if not self.current_ascending else "Oldest First")
        else:  # title/alphabetical
            self.order_button.setText("A-Z" if self.current_ascending else "Z-A")
            
    def reset_sort(self):
        """Reset to default sort (release date, newest first)."""
        self.current_sort_by = "release_date"
        self.current_ascending = False
        self.sort_combo.setCurrentText("Release Date")
        self._update_order_button_text()
        
    def get_current_sort(self):
        """Get current sort criteria."""
        return self.current_sort_by, self.current_ascending 