from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSlot
from services.download_manager import DownloadManager, DownloadStatus, DownloadTask

class DownloadItem(QWidget):
    def __init__(self, task: DownloadTask, parent=None):
        super().__init__(parent)
        self.task = task
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        
        # Title and artist
        info_layout = QHBoxLayout()
        title_label = QLabel(f"{self.task.title}")
        title_label.setObjectName("download-title")
        artist_label = QLabel(f"by {self.task.artist}")
        artist_label.setObjectName("download-artist")
        
        info_layout.addWidget(title_label)
        info_layout.addWidget(artist_label)
        info_layout.addStretch()
        
        # Progress bar and status
        progress_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(int(self.task.progress * 100))
        self.progress_bar.setTextVisible(True)
        
        self.status_label = QLabel(self.task.status.value)
        self.status_label.setObjectName("download-status")
        
        self.speed_label = QLabel("0 B/s")
        self.speed_label.setObjectName("download-speed")
        
        self.time_label = QLabel("calculating...")
        self.time_label.setObjectName("download-time")
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("cancel-button")
        self.cancel_button.setVisible(
            self.task.status in [DownloadStatus.QUEUED, DownloadStatus.DOWNLOADING]
        )
        
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.speed_label)
        progress_layout.addWidget(self.time_label)
        progress_layout.addWidget(self.status_label)
        progress_layout.addWidget(self.cancel_button)
        
        layout.addLayout(info_layout)
        layout.addLayout(progress_layout)
        
        if self.task.error:
            error_label = QLabel(f"Error: {self.task.error}")
            error_label.setObjectName("download-error")
            layout.addWidget(error_label)
        
        self.setLayout(layout)
        
    def update_progress(self, progress: float):
        self.progress_bar.setValue(int(progress * 100))
        
    def update_speed(self, speed: str):
        self.speed_label.setText(speed)
        
    def update_time(self, time_remaining: str):
        self.time_label.setText(time_remaining)
        
    def update_status(self, status: DownloadStatus):
        self.status_label.setText(status.value)
        self.cancel_button.setVisible(
            status in [DownloadStatus.QUEUED, DownloadStatus.DOWNLOADING]
        )

class DownloadQueue(QWidget):
    def __init__(self, download_manager: DownloadManager, parent=None):
        super().__init__(parent)
        self.download_manager = download_manager
        self.download_items = {}
        self.setup_ui()
        self.connect_signals()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header
        header = QWidget()
        header.setObjectName("download-queue-header")
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(16, 8, 16, 8)
        
        title = QLabel("Download Queue")
        title.setObjectName("download-queue-title")
        clear_button = QPushButton("Clear Completed")
        clear_button.setObjectName("clear-button")
        clear_button.clicked.connect(self.clear_completed)
        
        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(clear_button)
        header.setLayout(header_layout)
        
        # Scroll area for downloads
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.downloads_container = QWidget()
        self.downloads_layout = QVBoxLayout()
        self.downloads_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.downloads_container.setLayout(self.downloads_layout)
        
        scroll.setWidget(self.downloads_container)
        
        layout.addWidget(header)
        layout.addWidget(scroll)
        self.setLayout(layout)
        
    def connect_signals(self):
        self.download_manager.download_progress.connect(self.update_progress)
        self.download_manager.download_complete.connect(self.mark_complete)
        self.download_manager.download_error.connect(self.mark_error)
        self.download_manager.download_cancelled.connect(self.mark_cancelled)
        self.download_manager.download_speed_update.connect(self.update_speed)
        self.download_manager.download_time_update.connect(self.update_time)
        
    @pyqtSlot(str, float)
    def update_progress(self, track_id: str, progress: float):
        if track_id in self.download_items:
            self.download_items[track_id].update_progress(progress)
            
    @pyqtSlot(str, str)
    def update_speed(self, track_id: str, speed: str):
        if track_id in self.download_items:
            self.download_items[track_id].update_speed(speed)
            
    @pyqtSlot(str, str)
    def update_time(self, track_id: str, time_remaining: str):
        if track_id in self.download_items:
            self.download_items[track_id].update_time(time_remaining)
            
    @pyqtSlot(str)
    def mark_complete(self, track_id: str):
        if track_id in self.download_items:
            self.download_items[track_id].update_status(DownloadStatus.COMPLETED)
            
    @pyqtSlot(str, str)
    def mark_error(self, track_id: str, error: str):
        if track_id in self.download_items:
            self.download_items[track_id].update_status(DownloadStatus.FAILED)
            
    @pyqtSlot(str)
    def mark_cancelled(self, track_id: str):
        if track_id in self.download_items:
            self.download_items[track_id].update_status(DownloadStatus.CANCELLED)
            
    def add_download(self, task: DownloadTask):
        """Add a new download to the queue UI."""
        download_item = DownloadItem(task)
        self.download_items[task.track_id] = download_item
        self.downloads_layout.addWidget(download_item)
        
    def clear_completed(self):
        """Remove completed downloads from the UI."""
        completed = []
        for track_id, item in self.download_items.items():
            if item.task.status in [DownloadStatus.COMPLETED, DownloadStatus.CANCELLED]:
                item.deleteLater()
                completed.append(track_id)
                
        for track_id in completed:
            del self.download_items[track_id] 