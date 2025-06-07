from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QFrame
)
from PyQt6.QtCore import Qt, pyqtSlot

class BatchDownloadWidget(QWidget):
    """Widget for displaying batch download progress."""
    
    def __init__(self, batch_id: str, total_tracks: int, parent=None):
        super().__init__(parent)
        self.batch_id = batch_id
        self.total_tracks = total_tracks
        self.completed_tracks = 0
        self.failed_tracks = 0
        
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # Header
        header = QHBoxLayout()
        self.title_label = QLabel(f"Batch Download: {self.batch_id}")
        self.title_label.setStyleSheet("font-weight: bold;")
        header.addWidget(self.title_label)
        
        self.status_label = QLabel("0 / 0 completed")
        header.addWidget(self.status_label, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addLayout(header)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Status details
        details = QHBoxLayout()
        self.speed_label = QLabel("Speed: --")
        details.addWidget(self.speed_label)
        
        self.time_label = QLabel("Time remaining: --")
        details.addWidget(self.time_label, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addLayout(details)
        
        # Cancel button
        self.cancel_button = QPushButton("Cancel")
        layout.addWidget(self.cancel_button, alignment=Qt.AlignmentFlag.AlignRight)
        
        # Add separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)
        
    @pyqtSlot(float)
    def update_progress(self, progress: float):
        """Update batch download progress."""
        self.progress_bar.setValue(int(progress * 100))
        
    @pyqtSlot(int, int)
    def update_status(self, completed: int, failed: int):
        """Update completion status."""
        self.completed_tracks = completed
        self.failed_tracks = failed
        self.status_label.setText(
            f"{completed} / {self.total_tracks} completed "
            f"({failed} failed)" if failed > 0 else ""
        )
        
    @pyqtSlot(str)
    def update_speed(self, speed: str):
        """Update download speed."""
        self.speed_label.setText(f"Speed: {speed}")
        
    @pyqtSlot(str)
    def update_time(self, time: str):
        """Update time remaining."""
        self.time_label.setText(f"Time remaining: {time}")

class PlaylistDownloadWidget(QWidget):
    """Widget for displaying playlist download progress."""
    
    def __init__(self, playlist_id: str, title: str, total_tracks: int, parent=None):
        super().__init__(parent)
        self.playlist_id = playlist_id
        self.title = title
        self.total_tracks = total_tracks
        
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # Header
        header = QHBoxLayout()
        self.title_label = QLabel(f"Playlist: {self.title}")
        self.title_label.setStyleSheet("font-weight: bold;")
        header.addWidget(self.title_label)
        
        self.status_label = QLabel(f"0 / {self.total_tracks} tracks")
        header.addWidget(self.status_label, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addLayout(header)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, self.total_tracks)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Current track
        self.current_track_label = QLabel("Preparing download...")
        layout.addWidget(self.current_track_label)
        
        # Status details
        details = QHBoxLayout()
        self.speed_label = QLabel("Speed: --")
        details.addWidget(self.speed_label)
        
        self.time_label = QLabel("Time remaining: --")
        details.addWidget(self.time_label, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addLayout(details)
        
        # Cancel button
        self.cancel_button = QPushButton("Cancel")
        layout.addWidget(self.cancel_button, alignment=Qt.AlignmentFlag.AlignRight)
        
        # Add separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)
        
    @pyqtSlot(int)
    def update_progress(self, completed: int):
        """Update playlist download progress."""
        self.progress_bar.setValue(completed)
        self.status_label.setText(f"{completed} / {self.total_tracks} tracks")
        
    @pyqtSlot(str)
    def update_current_track(self, track_title: str):
        """Update currently downloading track."""
        self.current_track_label.setText(f"Downloading: {track_title}")
        
    @pyqtSlot(str)
    def update_speed(self, speed: str):
        """Update download speed."""
        self.speed_label.setText(f"Speed: {speed}")
        
    @pyqtSlot(str)
    def update_time(self, time: str):
        """Update time remaining."""
        self.time_label.setText(f"Time remaining: {time}") 