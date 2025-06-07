"""
Widgets to display grouped download items (albums/playlists) in the download queue.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QFrame,
    QPushButton, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
import logging

logger = logging.getLogger(__name__)

class BaseGroupItemWidget(QFrame):
    """Base class for common functionality between album and playlist group items."""
    request_cancel_group = pyqtSignal(str) # Emits group_id (album_id or playlist_id)
    retry_failed_tracks = pyqtSignal(str, list)  # Emits group_id, list of failed track_ids

    def __init__(self, group_id: str, group_title: str, total_tracks: int, item_type_display: str, parent=None):
        super().__init__(parent)
        self.group_id = group_id
        self.group_title = group_title
        self.total_tracks = total_tracks
        self.item_type_display = item_type_display # e.g., "Album", "Playlist"

        self.tracks = {}  # track_id: {'title': str, 'progress': int, 'status': str ('pending', 'downloading', 'completed', 'failed'), 'error': str}
        self.completed_tracks_count = 0
        self.failed_tracks_count = 0
        self.overall_status = "Pending" # Overall status of the group

        self.setObjectName(f"{item_type_display}GroupItemWidget_{group_id}")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(5)

        header_layout = QHBoxLayout()
        self.title_label = QLabel(f"{self.item_type_display}: {self.group_title}")
        self.title_label.setObjectName(f"{self.item_type_display}GroupTitle")
        self.title_label.setWordWrap(True)
        header_layout.addWidget(self.title_label, 1) # Title takes most space

        self.status_label = QLabel(f"(0/{self.total_tracks} tracks)")
        self.status_label.setObjectName(f"{self.item_type_display}GroupStatusLabel")
        header_layout.addWidget(self.status_label)
        
        # Error button for showing failed tracks (initially hidden)
        self.error_button = QPushButton()
        self.error_button.setObjectName("GroupErrorButton")
        self.error_button.setFixedSize(24, 24)
        self.error_button.setToolTip("Click to view failed tracks")
        self.error_button.clicked.connect(self._show_failed_tracks_dialog)
        self.error_button.hide()  # Hidden by default
        
        # Create error icon programmatically
        self._create_error_icon()
        
        # Retry failed tracks button (initially hidden)
        self.retry_failed_button = QPushButton("⟲")
        self.retry_failed_button.setObjectName("GroupRetryButton")
        self.retry_failed_button.setFixedSize(24, 24)
        self.retry_failed_button.setToolTip("Retry failed tracks")
        self.retry_failed_button.clicked.connect(self._request_retry_failed)
        self.retry_failed_button.hide()  # Hidden by default
        
        header_layout.addWidget(self.error_button)
        header_layout.addWidget(self.retry_failed_button)
        
        # TODO: Add Cancel button for the group
        # self.cancel_button = QPushButton("Cancel All")
        # self.cancel_button.clicked.connect(lambda: self.request_cancel_group.emit(self.group_id))
        # header_layout.addWidget(self.cancel_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName(f"{self.item_type_display}GroupProgressBar")
        self.progress_bar.setRange(0, 100) # Percentage based
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Pending...")

        main_layout.addLayout(header_layout)
        main_layout.addWidget(self.progress_bar)
        
        # Placeholder for individual track statuses if we want to expand/show them later
        # self.tracks_details_label = QLabel("Individual track progress hidden.")
        # main_layout.addWidget(self.tracks_details_label)

    def _create_error_icon(self):
        """Create a simple error icon programmatically."""
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw red circle
        painter.setBrush(QColor(239, 84, 102))  # #EF5466 red
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, 16, 16)
        
        # Draw white exclamation mark
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(painter.font())
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(12)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "!")
        
        painter.end()
        
        icon = QIcon(pixmap)
        self.error_button.setIcon(icon)

    def _show_failed_tracks_dialog(self):
        """Show a dialog with details of all failed tracks."""
        failed_tracks = [(track_id, track_info) for track_id, track_info in self.tracks.items() 
                        if track_info.get('status') == 'failed']
        
        if not failed_tracks:
            return
            
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(f"Failed Tracks in {self.item_type_display}")
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setText(f"Failed tracks in {self.group_title}:")
        
        # Create detailed text with all failed tracks and their errors
        details = []
        for track_id, track_info in failed_tracks:
            track_title = track_info.get('title', f'Track {track_id}')
            error = track_info.get('error', 'Unknown error')
            details.append(f"• {track_title}\n  Error: {error}")
        
        msg_box.setDetailedText("\n\n".join(details))
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        
        # Make the dialog bigger and more readable
        msg_box.setMinimumSize(500, 300)  # Set minimum width and height
        msg_box.resize(600, 400)  # Set preferred size
        
        # Improve text formatting in the main text area
        main_text = f"Failed tracks in {self.group_title}:\n\n"
        for track_id, track_info in failed_tracks:
            track_title = track_info.get('title', f'Track {track_id}')
            error = track_info.get('error', 'Unknown error')
            main_text += f"• {track_title}\n  Error: {error}\n\n"
        
        msg_box.setText(main_text.strip())
        msg_box.setDetailedText("")  # Clear detailed text since we're using main text
        
        msg_box.exec()

    def _request_retry_failed(self):
        """Emit signal to request retry of all failed tracks."""
        failed_track_ids = [track_id for track_id, track_info in self.tracks.items() 
                           if track_info.get('status') == 'failed']
        if failed_track_ids:
            self.retry_failed_tracks.emit(self.group_id, failed_track_ids)

    def add_track(self, track_id: str, track_title: str):
        if track_id not in self.tracks:
            self.tracks[track_id] = {'title': track_title, 'progress': 0, 'status': 'pending', 'error': None}
            logger.debug(f"[{self.item_type_display}Group:{self.group_id}] Added track {track_id} ('{track_title}'). Total tracks known: {len(self.tracks)}/{self.total_tracks}")
            self._update_overall_progress_display() # Update display with new track count if needed

    def update_track_progress(self, track_id: str, progress: int):
        if track_id in self.tracks:
            self.tracks[track_id]['progress'] = progress
            if self.tracks[track_id]['status'] == 'pending':
                 self.tracks[track_id]['status'] = 'downloading'
            self._update_overall_progress_display()
        else:
            logger.warning(f"[{self.item_type_display}Group:{self.group_id}] Progress update for unknown track_id: {track_id}")

    def handle_track_finished(self, track_id: str):
        if track_id in self.tracks:
            if self.tracks[track_id]['status'] != 'completed': # Avoid double counting
                self.tracks[track_id]['status'] = 'completed'
                self.tracks[track_id]['progress'] = 100
                self.completed_tracks_count += 1
            self._update_overall_progress_display()
        else:
            logger.warning(f"[{self.item_type_display}Group:{self.group_id}] Finished event for unknown track_id: {track_id}")

    def handle_track_failed(self, track_id: str, error: str):
        if track_id in self.tracks:
            if self.tracks[track_id]['status'] != 'failed': # Avoid double counting
                self.tracks[track_id]['status'] = 'failed'
                self.tracks[track_id]['error'] = error
                self.failed_tracks_count += 1
            self._update_overall_progress_display()
        else:
            logger.warning(f"[{self.item_type_display}Group:{self.group_id}] Failed event for unknown track_id: {track_id}")
            
    def get_managed_track_ids(self) -> list:
        return list(self.tracks.keys())

    def reset_group(self):
        """Reset the group to allow retry of downloads."""
        self.completed_tracks_count = 0
        self.failed_tracks_count = 0
        self.overall_status = "Pending"
        
        # Reset all tracks to pending status
        for track_info in self.tracks.values():
            track_info['status'] = 'pending'
            track_info['progress'] = 0
            track_info['error'] = None
        
        self._update_overall_progress_display()

    def get_failed_track_ids(self) -> list:
        """Get list of failed track IDs."""
        return [track_id for track_id, track_info in self.tracks.items() 
                if track_info.get('status') == 'failed']

    def _update_overall_progress_display(self):
        if self.total_tracks == 0:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("No tracks")
            self.status_label.setText("(0/0 tracks)")
            return

        # Calculate overall progress based on completed tracks
        # A more fine-grained progress would be average of individual track progresses
        
        # Option 1: Progress based on completed tracks count
        # overall_percentage = int((self.completed_tracks_count / self.total_tracks) * 100)
        
        # Option 2: Progress based on average of individual progresses
        current_total_progress = sum(track['progress'] for track in self.tracks.values())
        # If not all tracks have emitted 'started' yet, len(self.tracks) might be less than self.total_tracks
        # To avoid division by zero or misleading progress if only some tracks started,
        # we use self.total_tracks as the denominator for the average.
        overall_percentage = int(current_total_progress / self.total_tracks) if self.total_tracks > 0 else 0


        self.progress_bar.setValue(overall_percentage)
        
        status_text = f"({self.completed_tracks_count}/{len(self.tracks)} of {self.total_tracks} started tracks complete"
        if self.failed_tracks_count > 0:
            status_text += f", {self.failed_tracks_count} failed"
        status_text += ")"
        self.status_label.setText(status_text)

        # Show/hide error and retry buttons based on failed tracks count
        if self.failed_tracks_count > 0:
            self.error_button.show()
            self.retry_failed_button.show()
        else:
            self.error_button.hide()
            self.retry_failed_button.hide()

        # Update progress bar format
        if self.failed_tracks_count > 0 and (self.completed_tracks_count + self.failed_tracks_count == self.total_tracks):
            self.overall_status = "Completed with errors"
            self.progress_bar.setFormat(f"{self.overall_status} - {overall_percentage}%")
            self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: orange; }")
        elif self.completed_tracks_count == self.total_tracks:
            self.overall_status = "Completed"
            self.progress_bar.setFormat(f"{self.overall_status} - 100%")
            self.progress_bar.setStyleSheet("QProgressBar::chunk { background-color: green; }") # Green for success
        elif self.failed_tracks_count > 0:
            self.overall_status = f"Downloading ({self.failed_tracks_count} failed)"
            self.progress_bar.setFormat(f"{self.overall_status} - {overall_percentage}%")
        else:
            self.overall_status = "Downloading"
            self.progress_bar.setFormat(f"{self.overall_status} - {overall_percentage}%")
            self.progress_bar.setStyleSheet("") # Reset to default stylesheet for progress bar chunk

        # Update main title label if needed based on status
        self.title_label.setText(f"{self.item_type_display}: {self.group_title} [{self.overall_status}]")


class AlbumGroupItemWidget(BaseGroupItemWidget):
    def __init__(self, album_id: str, album_title: str, artist_name: str, total_tracks: int, parent=None):
        super().__init__(group_id=str(album_id), group_title=f"{artist_name} - {album_title}", total_tracks=total_tracks, item_type_display="Album", parent=parent)
        self.album_id = album_id
        self.album_title = album_title
        self.artist_name = artist_name
        # Specific setup for Album if any
        logger.info(f"AlbumGroupItemWidget created for ID: {self.group_id}, Title: {self.group_title}, Tracks: {self.total_tracks}")

class PlaylistGroupItemWidget(BaseGroupItemWidget):
    def __init__(self, playlist_id: str, playlist_title: str, total_tracks: int, parent=None):
        super().__init__(group_id=str(playlist_id), group_title=playlist_title, total_tracks=total_tracks, item_type_display="Playlist", parent=parent)
        self.playlist_id = playlist_id
        self.playlist_title = playlist_title
        # Specific setup for Playlist if any
        logger.info(f"PlaylistGroupItemWidget created for ID: {self.group_id}, Title: {self.group_title}, Tracks: {self.total_tracks}") 