import logging
from typing import Optional
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui import QIcon

class NotificationManager(QObject):
    """Manages system notifications for downloads."""
    
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.logger = logging.getLogger(__name__)
        
        # Create system tray icon
        self.tray_icon = QSystemTrayIcon(self.app)
        self.tray_icon.setIcon(QIcon(":/icons/app.ico"))
        self.tray_icon.setToolTip("DeeMusic Downloader")
        
        # Create tray menu
        self.tray_menu = QMenu()
        self.tray_icon.setContextMenu(self.tray_menu)
        
        # Show tray icon
        self.tray_icon.show()
        
    def notify(
        self,
        title: str,
        message: str,
        icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Information,
        duration: int = 5000
    ):
        """Show a system notification."""
        try:
            if self.tray_icon.supportsMessages():
                self.tray_icon.showMessage(
                    title,
                    message,
                    icon,
                    duration
                )
            else:
                self.logger.warning("System tray notifications not supported")
        except Exception as e:
            self.logger.error(f"Error showing notification: {str(e)}")
            
    def notify_download_started(self, title: str, is_playlist: bool = False):
        """Show download started notification."""
        item_type = "playlist" if is_playlist else "track"
        self.notify(
            "Download Started",
            f"Started downloading {item_type}: {title}"
        )
        
    def notify_download_complete(self, title: str, is_playlist: bool = False):
        """Show download complete notification."""
        item_type = "playlist" if is_playlist else "track"
        self.notify(
            "Download Complete",
            f"Successfully downloaded {item_type}: {title}",
            QSystemTrayIcon.MessageIcon.Information
        )
        
    def notify_download_error(self, title: str, error: str, is_playlist: bool = False):
        """Show download error notification."""
        item_type = "playlist" if is_playlist else "track"
        self.notify(
            "Download Error",
            f"Error downloading {item_type}: {title}\nError: {error}",
            QSystemTrayIcon.MessageIcon.Critical
        )
        
    def notify_batch_progress(self, batch_id: str, progress: float):
        """Show batch download progress notification."""
        self.notify(
            "Batch Download Progress",
            f"Batch {batch_id}: {progress * 100:.1f}% complete",
            duration=2000
        )
        
    def notify_batch_complete(self, batch_id: str, total: int, failed: int):
        """Show batch download complete notification."""
        if failed == 0:
            self.notify(
                "Batch Download Complete",
                f"Successfully downloaded all {total} tracks in batch {batch_id}"
            )
        else:
            self.notify(
                "Batch Download Complete",
                f"Downloaded {total - failed} of {total} tracks in batch {batch_id}\n{failed} tracks failed",
                QSystemTrayIcon.MessageIcon.Warning
            ) 