from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt

class TrackListHeaderWidget(QWidget):
    def __init__(self, parent=None, show_track_numbers: bool = False):
        super().__init__(parent)
        self.setObjectName("TrackListHeader")
        self.show_track_numbers = show_track_numbers
        
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
        artwork_spacer.setFixedWidth(40) # ADJUSTED: Trying 40px, (was 48px)
        layout.addWidget(artwork_spacer, 0) # No stretch for the spacer itself

        # Add track number column header if showing track numbers
        if self.show_track_numbers:
            self.track_number_label = QLabel("#")
            self.track_number_label.setObjectName("TrackListHeaderLabel")
            self.track_number_label.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self.track_number_label.setFixedWidth(30)  # Match SearchResultCard track number width
            layout.addWidget(self.track_number_label, 0)

        self.track_label = QLabel("TRACK")
        self.track_label.setObjectName("TrackListHeaderLabel")
        layout.addWidget(self.track_label, 5) # Stretch factor 5

        self.artist_label = QLabel("ARTIST")
        self.artist_label.setObjectName("TrackListHeaderLabel")
        layout.addWidget(self.artist_label, 3) # Stretch factor 3

        self.album_label = QLabel("ALBUM")
        self.album_label.setObjectName("TrackListHeaderLabel")
        layout.addWidget(self.album_label, 3) # Stretch factor 3

        self.duration_label = QLabel("DUR.")
        self.duration_label.setObjectName("TrackListHeaderLabel")
        self.duration_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.duration_label.setFixedWidth(45) # CHANGED from setMinimumWidth to setFixedWidth
        layout.addWidget(self.duration_label, 1) # Stretch factor 1 to allow some flexibility but prioritize others

        # Optional: Add a border-bottom to the widget via QSS in main.qss
        # self.setStyleSheet("QWidget#TrackListHeader { border-bottom: 1px solid #E0E0E0; }")
        # QLabel#TrackListHeaderLabel { color: #666666; font-weight: bold; font-size: 10px; text-transform: uppercase; }
        
        self.setFixedHeight(35) # INCREASED height from 30 to 35 