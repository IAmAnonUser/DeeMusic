"""
Widget to display a single item in the download queue.
"""
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QProgressBar, QFrame, 
    QPushButton, QMessageBox, QToolTip
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
import logging

logger = logging.getLogger(__name__)

class DownloadItemWidget(QFrame):
    """
    Represents a single item in the download queue, showing its name and progress.
    """
    retry_requested = pyqtSignal(str)  # Emits track_id when retry is requested
    
    def __init__(self, item_id: str, item_title: str, artist_name: str, album_name: str, item_type: str, parent=None):
        super().__init__(parent)
        self.item_id = item_id
        self.item_title = item_title
        self.artist_name = artist_name
        self.album_name = album_name # Store album name
        self.item_type = item_type
        self.status = "pending" # ADDED: Initialize status
        self.error_message = None  # Store the error message for failed downloads

        self.setObjectName("DownloadItemWidget")
        self.setFrameShape(QFrame.Shape.StyledPanel) # Add a bit of styling
        # self.setFrameShadow(QFrame.Shadow.Raised)

        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(3)

        # Top row: Title and Error/Retry buttons
        top_layout = QHBoxLayout()
        
        # Display artist, title, and album
        title_parts = []
        if self.artist_name and self.artist_name != "Unknown Artist":
            title_parts.append(self.artist_name)
        
        if self.item_title and self.item_title != "Unknown Title":
            title_parts.append(self.item_title)
        elif not title_parts: # If no artist and no title, use a generic placeholder
            title_parts.append("Unknown Track")

        display_title = " - ".join(title_parts)

        if self.album_name and self.album_name != "Unknown Album":
            display_title += f" ({self.album_name})"
        
        # Optionally add item_type if it's not obvious or for debugging
        # type_display = self.item_type.replace('_', ' ').title()
        # display_title += f" [{type_display}]"

        self.title_label = QLabel(display_title)
        self.title_label.setObjectName("DownloadItemTitle")
        self.title_label.setWordWrap(True) # In case title is very long
        
        # Error icon button (initially hidden)
        self.error_button = QPushButton()
        self.error_button.setObjectName("ErrorButton")
        self.error_button.setFixedSize(24, 24)
        self.error_button.setToolTip("Click to view error details")
        self.error_button.clicked.connect(self._show_error_dialog)
        self.error_button.hide()  # Hidden by default
        
        # Create error icon programmatically
        self._create_error_icon()
        
        # Retry button (initially hidden)
        self.retry_button = QPushButton("⟲")
        self.retry_button.setObjectName("RetryButton")
        self.retry_button.setFixedSize(24, 24)
        self.retry_button.setToolTip("Retry download")
        self.retry_button.clicked.connect(self._request_retry)
        self.retry_button.hide()  # Hidden by default
        
        top_layout.addWidget(self.title_label, 1)  # Title takes most space
        top_layout.addWidget(self.error_button)
        top_layout.addWidget(self.retry_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("DownloadItemProgressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True) # Show percentage

        main_layout.addLayout(top_layout)
        main_layout.addWidget(self.progress_bar)

        # logger.debug(f"DownloadItemWidget created for {self.item_id} - {self.item_title}")

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

    def _show_error_dialog(self):
        """Show a dialog with the full error message."""
        if self.error_message:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Download Error Details")
            msg_box.setIcon(QMessageBox.Icon.Critical)
            msg_box.setText(f"Download failed for:\n{self.item_title}")
            msg_box.setDetailedText(f"Error Details:\n{self.error_message}")
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.exec()

    def _request_retry(self):
        """Emit signal to request retry of this download."""
        self.retry_requested.emit(self.item_id)

    def set_progress(self, percentage: int):
        """Updates the progress bar value."""
        self.progress_bar.setValue(percentage)

    def set_failed(self, error_message: str):
        """Mark this download as failed and show error UI elements."""
        self.status = "failed"
        self.error_message = error_message
        
        # Update UI to show failed state
        self.title_label.setText(f"{self.title_label.text()} - Failed")
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"Error: {error_message[:30]}...")
        self.setStyleSheet("background-color: #552222; border-radius: 3px;")
        
        # Show error and retry buttons
        self.error_button.show()
        self.retry_button.show()

    def get_item_id(self) -> str:
        return self.item_id

if __name__ == '__main__':
    from PyQt6.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    logging.basicConfig(level=logging.DEBUG)

    # Example usage
    item1 = DownloadItemWidget(item_id="track_123", item_title="Amazing Song Title That Is Quite Long Indeed", artist_name="Awesome Artist", album_name="Fantastic Album", item_type="track")
    item1.set_progress(50)
    item1.show()
    item1.resize(280, item1.sizeHint().height())

    item2 = DownloadItemWidget(item_id="album_456", item_title="Epic Album Name", artist_name="Various Artists", album_name="Greatest Hits Collection", item_type="album")
    item2.set_progress(25)
    # item2.show() # Show separately or add to a layout

    # Example failed item
    item3 = DownloadItemWidget(item_id="track_789", item_title="Failed Song", artist_name="Test Artist", album_name="Test Album", item_type="track")
    item3.set_failed("Network timeout: Connection to server failed after 30 seconds")

    # Example of how they might look in a list
    container = QWidget()
    container_layout = QVBoxLayout(container)
    container_layout.addWidget(item1)
    container_layout.addWidget(item2)
    container_layout.addWidget(item3)
    container.show()
    container.setWindowTitle("Download Item Test")

    sys.exit(app.exec()) 