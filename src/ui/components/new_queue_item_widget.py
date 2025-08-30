"""
Individual queue item widget for the new download system.

This widget displays a single download item (album, playlist, or track)
with progress information and action buttons.
"""

import logging
from typing import Callable, Optional
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, 
                            QPushButton, QProgressBar, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPalette

# Import our new system components
import sys
from pathlib import Path
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from src.models.queue_models import QueueItem, QueueItemState, DownloadState, ItemType

logger = logging.getLogger(__name__)


class QueueItemWidget(QFrame):
    """
    Widget for displaying a single queue item.
    
    Shows:
    - Item information (title, artist, type)
    - Download progress
    - Current state
    - Action buttons (remove, retry, pause, etc.)
    """
    
    def __init__(self, item: QueueItem, state: QueueItemState, 
                 on_remove: Callable[[str], None],
                 on_retry: Callable[[str], None],
                 on_cancel: Callable[[str], None],
                 on_pause: Callable[[str], None],
                 on_resume: Callable[[str], None],
                 parent=None):
        super().__init__(parent)
        
        self.item = item
        self.state = state
        self.on_remove = on_remove
        self.on_retry = on_retry
        self.on_cancel = on_cancel
        self.on_pause = on_pause
        self.on_resume = on_resume
        
        # Setup UI
        self._setup_ui()
        self._update_display()
        
        logger.debug(f"[QueueItemWidget] Created widget for: {item.title}")
    
    def _setup_ui(self):
        """Setup the user interface."""
        # Set frame style
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setLineWidth(1)
        
        # Set fixed height to prevent shrinking when many items are in queue
        self.setFixedHeight(70)  # Increased height for better spacing
        
        # Set size policy to prevent vertical expansion
        from PyQt6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        # Main layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)  # More padding
        layout.setSpacing(10)  # More spacing between sections
        
        # Left side - Item information and progress
        self._create_info_section(layout)
        
        # Right side - Action buttons
        self._create_action_section(layout)
    
    def _create_info_section(self, layout):
        """Create information section with title, artist, and progress."""
        info_layout = QVBoxLayout()
        info_layout.setSpacing(1)
        
        # Title and type
        title_layout = QHBoxLayout()
        title_layout.setSpacing(4)
        
        # Item type icon/label
        type_label = QLabel(self._get_type_display())
        type_label.setObjectName("ItemTypeLabel")
        type_font = QFont()
        type_font.setBold(True)
        type_font.setPointSize(6)
        type_label.setFont(type_font)
        title_layout.addWidget(type_label)
        
        # Title
        self.title_label = QLabel(self.item.title)
        self.title_label.setObjectName("ItemTitleLabel")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(9)  # Slightly larger
        self.title_label.setFont(title_font)
        self.title_label.setWordWrap(True)
        title_layout.addWidget(self.title_label)
        
        title_layout.addStretch()
        info_layout.addLayout(title_layout)
        
        # Artist and track count
        artist_layout = QHBoxLayout()
        
        self.artist_label = QLabel(self.item.artist)
        self.artist_label.setObjectName("ItemArtistLabel")
        artist_layout.addWidget(self.artist_label)
        
        # Track count for albums/playlists
        if self.item.item_type in [ItemType.ALBUM, ItemType.PLAYLIST]:
            track_count_text = f"({self.item.total_tracks} tracks)"
            self.track_count_label = QLabel(track_count_text)
            self.track_count_label.setObjectName("ItemTrackCountLabel")
            artist_layout.addWidget(self.track_count_label)
        
        artist_layout.addStretch()
        info_layout.addLayout(artist_layout)
        
        # Progress section
        progress_layout = QVBoxLayout()
        progress_layout.setSpacing(0)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(int(self.state.progress * 100))
        self.progress_bar.setTextVisible(False)  # Hide text to save space
        self.progress_bar.setFixedHeight(6)  # Slightly thicker for better visibility
        progress_layout.addWidget(self.progress_bar)
        
        # Progress details
        self.progress_label = QLabel()
        self.progress_label.setObjectName("ItemProgressLabel")
        progress_font = QFont()
        progress_font.setPointSize(7)  # Slightly larger
        self.progress_label.setFont(progress_font)
        progress_layout.addWidget(self.progress_label)
        
        info_layout.addLayout(progress_layout)
        
        # Status
        self.status_label = QLabel()
        self.status_label.setObjectName("ItemStatusLabel")
        status_font = QFont()
        status_font.setPointSize(8)  # Slightly larger
        status_font.setItalic(True)
        self.status_label.setFont(status_font)
        info_layout.addWidget(self.status_label)
        
        layout.addLayout(info_layout, 1)  # Take most of the space
    
    def _create_action_section(self, layout):
        """Create action buttons section."""
        button_layout = QHBoxLayout()  # Changed to horizontal layout
        button_layout.setSpacing(4)
        
        # State-specific buttons
        self.action_button = QPushButton()
        self.action_button.setFixedSize(60, 24)  # Larger button
        self.action_button.clicked.connect(self._handle_action_button)
        button_layout.addWidget(self.action_button)
        
        # Remove button (always available)
        self.remove_button = QPushButton("✕")
        self.remove_button.setObjectName("RemoveButton")
        self.remove_button.setFixedSize(24, 24)  # Larger button
        self.remove_button.setToolTip("Remove from queue")
        self.remove_button.clicked.connect(lambda: self.on_remove(self.item.id))
        button_layout.addWidget(self.remove_button)
        
        layout.addLayout(button_layout)
    
    def _get_type_display(self) -> str:
        """Get display text for item type."""
        type_map = {
            ItemType.ALBUM: "🎵 ALBUM",
            ItemType.PLAYLIST: "📋 PLAYLIST", 
            ItemType.TRACK: "🎵 TRACK"
        }
        return type_map.get(self.item.item_type, "UNKNOWN")
    
    def _update_display(self):
        """Update the display based on current state."""
        try:
            # Check if widgets still exist before updating
            if not self.progress_bar or not self.progress_label:
                return
                
            # Update progress
            progress_percent = int(self.state.progress * 100)
            self.progress_bar.setValue(progress_percent)
            
            # Update progress text
            if self.item.item_type in [ItemType.ALBUM, ItemType.PLAYLIST]:
                progress_text = f"{self.state.completed_tracks}/{self.item.total_tracks} tracks"
                if self.state.failed_tracks > 0:
                    progress_text += f" ({self.state.failed_tracks} failed)"
            else:
                progress_text = f"{progress_percent}%"
            
            self.progress_label.setText(progress_text)
            
            # Update status and styling based on state
            self._update_status_display()
            
            # Update action button
            self._update_action_button()
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                logger.debug(f"[QueueItemWidget] Widget deleted during update: {e}")
            else:
                logger.error(f"[QueueItemWidget] Runtime error in _update_display: {e}")
        except Exception as e:
            logger.error(f"[QueueItemWidget] Error in _update_display: {e}")
    
    def _update_status_display(self):
        """Update status display and widget styling."""
        try:
            # Check if widgets still exist before updating
            if not self.status_label:
                return
                
            state_info = {
                DownloadState.QUEUED: ("Queued", "#666666", "normal"),
                DownloadState.DOWNLOADING: ("Downloading...", "#0066CC", "downloading"),
                DownloadState.COMPLETED: ("Completed", "#00AA00", "completed"),
                DownloadState.FAILED: ("Failed", "#CC0000", "failed"),
                DownloadState.CANCELLED: ("Cancelled", "#AA6600", "cancelled"),
                DownloadState.PAUSED: ("Paused", "#AA6600", "paused")
            }
            
            status_text, color, style_class = state_info.get(
                self.state.state, 
                ("Unknown", "#666666", "normal")
            )
            
            # Add error message for failed items
            if self.state.state == DownloadState.FAILED and self.state.error_message:
                status_text += f": {self.state.error_message}"
            
            self.status_label.setText(status_text)
            self.status_label.setStyleSheet(f"color: {color};")
            
            # Update widget style class
            self.setProperty("downloadState", style_class)
            self.style().unpolish(self)
            self.style().polish(self)
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                logger.debug(f"[QueueItemWidget] Widget deleted during status update: {e}")
            else:
                logger.error(f"[QueueItemWidget] Runtime error in _update_status_display: {e}")
        except Exception as e:
            logger.error(f"[QueueItemWidget] Error in _update_status_display: {e}")
    
    def _update_action_button(self):
        """Update action button based on current state."""
        button_config = {
            DownloadState.QUEUED: ("Cancel", "Cancel download"),
            DownloadState.DOWNLOADING: ("Pause", "Pause download"),
            DownloadState.COMPLETED: ("", ""),  # No action needed
            DownloadState.FAILED: ("Retry", "Retry download"),
            DownloadState.CANCELLED: ("Retry", "Retry download"),
            DownloadState.PAUSED: ("Resume", "Resume download")
        }
        
        text, tooltip = button_config.get(self.state.state, ("", ""))
        
        self.action_button.setText(text)
        self.action_button.setToolTip(tooltip)
        self.action_button.setVisible(bool(text))
    
    def _handle_action_button(self):
        """Handle action button click based on current state."""
        try:
            if self.state.state == DownloadState.QUEUED:
                self.on_cancel(self.item.id)
            elif self.state.state == DownloadState.DOWNLOADING:
                self.on_pause(self.item.id)
            elif self.state.state in [DownloadState.FAILED, DownloadState.CANCELLED]:
                self.on_retry(self.item.id)
            elif self.state.state == DownloadState.PAUSED:
                self.on_resume(self.item.id)
                
        except Exception as e:
            logger.error(f"[QueueItemWidget] Error handling action button: {e}")
    
    def update_state(self, new_state: QueueItemState):
        """Update widget with new state."""
        try:
            self.state = new_state
            self._update_display()
            
        except Exception as e:
            logger.error(f"[QueueItemWidget] Error updating state: {e}")
    
    def update_progress(self, progress: float, completed_tracks: int, failed_tracks: int):
        """Update progress information."""
        try:
            # Update state
            self.state.progress = progress
            self.state.completed_tracks = completed_tracks
            self.state.failed_tracks = failed_tracks
            
            # Update display
            self._update_display()
            
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                logger.debug(f"[QueueItemWidget] Widget deleted during progress update: {e}")
            else:
                logger.error(f"[QueueItemWidget] Runtime error updating progress: {e}")
        except Exception as e:
            logger.error(f"[QueueItemWidget] Error updating progress: {e}")
    
    def get_item_id(self) -> str:
        """Get the item ID."""
        return self.item.id
    
    def get_item_title(self) -> str:
        """Get the item title."""
        return self.item.title
    
    def get_download_state(self) -> DownloadState:
        """Get the current download state."""
        return self.state.state
    
    def is_active(self) -> bool:
        """Check if item is currently active (downloading or queued)."""
        return self.state.state in [DownloadState.QUEUED, DownloadState.DOWNLOADING]
    
    def is_finished(self) -> bool:
        """Check if item is in a finished state."""
        return self.state.state in [DownloadState.COMPLETED, DownloadState.FAILED, DownloadState.CANCELLED]


# Example usage and testing
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget
    
    # Import test data
    sys.path.append(str(Path(__file__).parent.parent.parent))
    from src.models.queue_models import QueueItem, QueueItemState, TrackInfo, ItemType, DownloadState
    
    app = QApplication(sys.argv)
    
    # Create test data
    track = TrackInfo(
        track_id=123,
        title="Test Track",
        artist="Test Artist",
        duration=180,
        track_number=1
    )
    
    item = QueueItem.create_album(
        deezer_id=456,
        title="Test Album",
        artist="Test Artist",
        tracks=[track]
    )
    
    state = QueueItemState(
        item_id=item.id,
        state=DownloadState.DOWNLOADING,
        progress=0.5,
        completed_tracks=1,
        failed_tracks=0
    )
    
    # Create test window
    window = QWidget()
    layout = QVBoxLayout(window)
    
    # Mock callbacks
    def mock_callback(item_id):
        print(f"Action called for item: {item_id}")
    
    # Create widget
    widget = QueueItemWidget(
        item=item,
        state=state,
        on_remove=mock_callback,
        on_retry=mock_callback,
        on_cancel=mock_callback,
        on_pause=mock_callback,
        on_resume=mock_callback
    )
    
    layout.addWidget(widget)
    
    window.setWindowTitle("Queue Item Widget Test")
    window.resize(500, 150)
    window.show()
    
    sys.exit(app.exec())