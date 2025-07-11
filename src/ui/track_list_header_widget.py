from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QCursor

class TrackListHeaderWidget(QWidget):
    # Signals for sorting
    sort_requested = pyqtSignal(str, bool)  # column_name, ascending
    
    def __init__(self, parent=None, show_track_numbers: bool = False):
        super().__init__(parent)
        self.setObjectName("TrackListHeader")
        self.show_track_numbers = show_track_numbers
        self.current_sort_column = None
        self.current_sort_ascending = True
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8) # Match SearchResultCard track_details_layout spacing

        # Spacer for track artwork in SearchResultCard
        # SearchResultCard.TRACK_ARTWORK_SIZE is 48. track_details_layout spacing is 8.
        # The artwork_container is added directly to the track_details_layout.
        # The 10px left margin of track_details_layout applies before artwork.
        # The 10px left margin of this header's layout also applies.
        # So, the spacer just needs to be the artwork width.
        artwork_spacer = QWidget()
        artwork_spacer.setFixedWidth(48) # FIXED: Changed from 40px back to 48px to match TRACK_ARTWORK_SIZE
        layout.addWidget(artwork_spacer, 0) # No stretch for the spacer itself

        # Add track number column header if showing track numbers
        if self.show_track_numbers:
            self.track_number_label = QLabel("#")
            self.track_number_label.setObjectName("TrackListHeaderLabel")
            self.track_number_label.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self.track_number_label.setFixedWidth(30)  # Match SearchResultCard track number width
            layout.addWidget(self.track_number_label, 0)

        # Create sortable column headers
        self.track_header = self._create_sortable_header("TRACK", "title")
        layout.addWidget(self.track_header, 5) # Stretch factor 5

        self.artist_header = self._create_sortable_header("ARTIST", "artist")
        layout.addWidget(self.artist_header, 3) # Stretch factor 3

        self.album_header = self._create_sortable_header("ALBUM", "album")
        layout.addWidget(self.album_header, 3) # Stretch factor 3

        self.duration_header = self._create_sortable_header("DUR.", "duration")
        self.duration_header.setFixedWidth(45) # CHANGED from setMinimumWidth to setFixedWidth
        layout.addWidget(self.duration_header, 1) # Stretch factor 1

        # Optional: Add a border-bottom to the widget via QSS in main.qss
        # self.setStyleSheet("QWidget#TrackListHeader { border-bottom: 1px solid #E0E0E0; }")
        # QLabel#TrackListHeaderLabel { color: #666666; font-weight: bold; font-size: 10px; text-transform: uppercase; }
        
        self.setFixedHeight(35) # INCREASED height from 30 to 35 
        
    def _create_sortable_header(self, text: str, column_name: str) -> QPushButton:
        """Create a sortable header button."""
        header_btn = QPushButton(text)
        header_btn.setObjectName("TrackListHeaderButton")
        header_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        header_btn.setFlat(True)
        
        # Set alignment based on column type
        if column_name == "duration":
            header_btn.setStyleSheet("text-align: right; padding-right: 5px;")
        else:
            header_btn.setStyleSheet("text-align: left; padding-left: 5px;")
        
        # Connect to sorting function
        header_btn.clicked.connect(lambda: self._handle_sort_request(column_name))
        
        return header_btn
        
    def _handle_sort_request(self, column_name: str):
        """Handle sorting request for a column."""
        # Toggle sort order if clicking the same column
        if self.current_sort_column == column_name:
            self.current_sort_ascending = not self.current_sort_ascending
        else:
            self.current_sort_column = column_name
            self.current_sort_ascending = True
            
        # Update header button text to show sort direction
        self._update_sort_indicators()
        
        # Emit sort signal
        self.sort_requested.emit(column_name, self.current_sort_ascending)
        
    def _update_sort_indicators(self):
        """Update header buttons to show current sort state."""
        headers = {
            "title": (self.track_header, "TRACK"),
            "artist": (self.artist_header, "ARTIST"), 
            "album": (self.album_header, "ALBUM"),
            "duration": (self.duration_header, "DUR.")
        }
        
        for column, (header_btn, base_text) in headers.items():
            if column == self.current_sort_column:
                arrow = " ↑" if self.current_sort_ascending else " ↓"
                header_btn.setText(base_text + arrow)
            else:
                header_btn.setText(base_text)
                
    def reset_sort(self):
        """Reset sorting to default state."""
        self.current_sort_column = None
        self.current_sort_ascending = True
        self._update_sort_indicators() 