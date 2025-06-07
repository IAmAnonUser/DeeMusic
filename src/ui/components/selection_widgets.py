from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem,
    QCheckBox, QScrollArea, QFrame, QLineEdit,
    QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from typing import List, Dict

class TrackSelectionWidget(QWidget):
    """Widget for selecting multiple tracks for batch download."""
    
    selection_changed = pyqtSignal(list)  # List of selected track IDs
    download_requested = pyqtSignal(str, list)  # batch_id, list of track IDs
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tracks: Dict[str, Dict] = {}  # track_id -> track info
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # Search box
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholder("Search tracks...")
        self.search_input.textChanged.connect(self._filter_tracks)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)
        
        # Track list
        self.track_list = QListWidget()
        self.track_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.track_list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.track_list)
        
        # Selection controls
        controls = QHBoxLayout()
        
        self.select_all = QPushButton("Select All")
        self.select_all.clicked.connect(self._select_all)
        controls.addWidget(self.select_all)
        
        self.clear_selection = QPushButton("Clear Selection")
        self.clear_selection.clicked.connect(self._clear_selection)
        controls.addWidget(self.clear_selection)
        
        layout.addLayout(controls)
        
        # Download button
        self.download_button = QPushButton("Download Selected")
        self.download_button.clicked.connect(self._start_download)
        self.download_button.setEnabled(False)
        layout.addWidget(self.download_button)
        
    def add_tracks(self, tracks: List[Dict]):
        """Add tracks to the selection list."""
        self.tracks.clear()
        self.track_list.clear()
        
        for track in tracks:
            track_id = track['id']
            self.tracks[track_id] = track
            
            item = QListWidgetItem(
                f"{track['artist']} - {track['title']}"
            )
            item.setData(Qt.ItemDataRole.UserRole, track_id)
            self.track_list.addItem(item)
            
    def _filter_tracks(self, text: str):
        """Filter tracks based on search text."""
        for i in range(self.track_list.count()):
            item = self.track_list.item(i)
            track_id = item.data(Qt.ItemDataRole.UserRole)
            track = self.tracks[track_id]
            
            match = (
                text.lower() in track['title'].lower() or
                text.lower() in track['artist'].lower()
            )
            item.setHidden(not match)
            
    def _on_selection_changed(self):
        """Handle selection changes."""
        selected = self._get_selected_tracks()
        self.selection_changed.emit(selected)
        self.download_button.setEnabled(bool(selected))
        
    def _get_selected_tracks(self) -> List[str]:
        """Get list of selected track IDs."""
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self.track_list.selectedItems()
        ]
        
    def _select_all(self):
        """Select all visible tracks."""
        for i in range(self.track_list.count()):
            item = self.track_list.item(i)
            if not item.isHidden():
                item.setSelected(True)
                
    def _clear_selection(self):
        """Clear all selections."""
        self.track_list.clearSelection()
        
    def _start_download(self):
        """Start downloading selected tracks."""
        selected = self._get_selected_tracks()
        if not selected:
            return
            
        # Generate batch ID from timestamp
        from datetime import datetime
        batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        self.download_requested.emit(batch_id, selected)

class PlaylistSelectionWidget(QWidget):
    """Widget for selecting and downloading playlists."""
    
    playlist_selected = pyqtSignal(str)  # playlist_id
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.playlists: Dict[str, Dict] = {}
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # Search box
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholder("Search playlists...")
        self.search_input.textChanged.connect(self._filter_playlists)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)
        
        # Playlist list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        content = QWidget()
        self.playlist_layout = QVBoxLayout(content)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        
    def add_playlists(self, playlists: List[Dict]):
        """Add playlists to the selection list."""
        # Clear existing playlists
        for i in reversed(range(self.playlist_layout.count())):
            widget = self.playlist_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        self.playlists.clear()
        
        # Add new playlists
        for playlist in playlists:
            playlist_id = playlist['id']
            self.playlists[playlist_id] = playlist
            
            # Create playlist item widget
            item = PlaylistItemWidget(playlist)
            item.download_clicked.connect(
                lambda pid=playlist_id: self.playlist_selected.emit(pid)
            )
            self.playlist_layout.addWidget(item)
            
        self.playlist_layout.addStretch()
        
    def _filter_playlists(self, text: str):
        """Filter playlists based on search text."""
        for i in range(self.playlist_layout.count()):
            widget = self.playlist_layout.itemAt(i).widget()
            if isinstance(widget, PlaylistItemWidget):
                match = text.lower() in widget.title.lower()
                widget.setVisible(match)

class PlaylistItemWidget(QWidget):
    """Widget for displaying a single playlist with download button."""
    
    download_clicked = pyqtSignal()
    
    def __init__(self, playlist: Dict, parent=None):
        super().__init__(parent)
        self.playlist = playlist
        self.title = playlist['title']
        self._init_ui()
        
    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Playlist info
        info = QVBoxLayout()
        
        title = QLabel(self.playlist['title'])
        title.setStyleSheet("font-weight: bold;")
        info.addWidget(title)
        
        details = QLabel(f"{self.playlist['nb_tracks']} tracks")
        details.setStyleSheet("color: #666;")
        info.addWidget(details)
        
        layout.addLayout(info)
        
        # Download button
        download = QPushButton("Download")
        download.clicked.connect(self.download_clicked)
        layout.addWidget(download)
        
        # Add separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line) 