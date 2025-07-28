"""
Queue Import Dialog - UI for importing selected albums to DeeMusic
"""

import logging
from typing import List, Dict, Any
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTextEdit, QCheckBox, QScrollArea, QWidget, QFrame,
    QMessageBox, QProgressBar, QGroupBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

from ..core.data_models import MissingAlbum
from ..utils.queue_integration import QueueIntegration

logger = logging.getLogger(__name__)

class ImportWorker(QThread):
    """Worker thread for importing albums to DeeMusic queue."""
    
    progress_updated = pyqtSignal(int, str)  # progress, message
    import_completed = pyqtSignal(bool, str)  # success, message
    
    def __init__(self, queue_integration: QueueIntegration, selected_albums: List[Dict[str, Any]]):
        super().__init__()
        self.queue_integration = queue_integration
        self.selected_albums = selected_albums
    
    def run(self):
        """Run the import process."""
        try:
            self.progress_updated.emit(10, "Checking DeeMusic queue accessibility...")
            
            if not self.queue_integration.is_deemusic_queue_accessible():
                self.import_completed.emit(False, "DeeMusic download queue is not accessible. Please ensure DeeMusic has been run at least once.")
                return
            
            self.progress_updated.emit(30, "Saving selected albums...")
            
            # Save selected albums first
            if not self.queue_integration.save_selected_albums([]):  # We'll pass the dict data directly
                self.import_completed.emit(False, "Failed to save selected albums.")
                return
            
            self.progress_updated.emit(60, "Importing to DeeMusic queue...")
            
            # Import to DeeMusic queue
            if self.queue_integration.import_to_deemusic_queue(self.selected_albums):
                self.progress_updated.emit(100, "Import completed successfully!")
                self.import_completed.emit(True, f"Successfully imported {len(self.selected_albums)} albums to DeeMusic download queue.")
            else:
                self.import_completed.emit(False, "Failed to import albums to DeeMusic queue.")
                
        except Exception as e:
            logger.error(f"Error in import worker: {e}")
            self.import_completed.emit(False, f"Import failed: {str(e)}")

class AlbumSelectionWidget(QWidget):
    """Widget for selecting individual albums."""
    
    def __init__(self, missing_album: MissingAlbum, parent=None):
        super().__init__(parent)
        self.missing_album = missing_album
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the UI for album selection."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Checkbox for selection
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)  # Default to selected
        layout.addWidget(self.checkbox)
        
        # Album info
        info_layout = QVBoxLayout()
        
        # Title and artist
        title_label = QLabel(f"{self.missing_album.deezer_album.title}")
        title_font = QFont()
        title_font.setBold(True)
        title_label.setFont(title_font)
        info_layout.addWidget(title_label)
        
        artist_label = QLabel(f"by {self.missing_album.deezer_album.artist}")
        artist_label.setStyleSheet("color: #666;")
        info_layout.addWidget(artist_label)
        
        # Details
        details = []
        if self.missing_album.deezer_album.year:
            details.append(f"Year: {self.missing_album.deezer_album.year}")
        details.append(f"Tracks: {self.missing_album.deezer_album.track_count}")
        details.append(f"Missing: {len(self.missing_album.missing_tracks)}")
        
        details_label = QLabel(" • ".join(details))
        details_label.setStyleSheet("color: #888; font-size: 11px;")
        info_layout.addWidget(details_label)
        
        layout.addLayout(info_layout, 1)
        
        # Add separator line
        self.setStyleSheet("""
            AlbumSelectionWidget {
                border-bottom: 1px solid #ddd;
                padding: 5px;
            }
            AlbumSelectionWidget:hover {
                background-color: #f5f5f5;
            }
        """)
    
    def is_selected(self) -> bool:
        """Check if this album is selected."""
        return self.checkbox.isChecked()
    
    def set_selected(self, selected: bool):
        """Set selection state."""
        self.checkbox.setChecked(selected)

class QueueImportDialog(QDialog):
    """Dialog for importing selected albums to DeeMusic's download queue."""
    
    def __init__(self, missing_albums: List[MissingAlbum], parent=None):
        super().__init__(parent)
        self.missing_albums = missing_albums
        self.album_widgets = []
        self.queue_integration = QueueIntegration()
        
        self.setWindowTitle("Import Albums to DeeMusic")
        self.setModal(True)
        self.resize(600, 500)
        
        self.setup_ui()
        self.check_deemusic_accessibility()
    
    def setup_ui(self):
        """Setup the dialog UI."""
        layout = QVBoxLayout(self)
        
        # Title
        title_label = QLabel("Import Albums to DeeMusic Download Queue")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Description
        desc_label = QLabel(
            "Select the albums you want to add to DeeMusic's download queue. "
            "These albums will be available for download when you open DeeMusic."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; margin: 10px 0;")
        layout.addWidget(desc_label)
        
        # Status group
        self.status_group = QGroupBox("Queue Status")
        status_layout = QVBoxLayout(self.status_group)
        self.status_label = QLabel("Checking DeeMusic queue accessibility...")
        status_layout.addWidget(self.status_label)
        layout.addWidget(self.status_group)
        
        # Selection controls
        selection_layout = QHBoxLayout()
        
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all)
        selection_layout.addWidget(self.select_all_btn)
        
        self.select_none_btn = QPushButton("Select None")
        self.select_none_btn.clicked.connect(self.select_none)
        selection_layout.addWidget(self.select_none_btn)
        
        selection_layout.addStretch()
        
        self.selected_count_label = QLabel()
        selection_layout.addWidget(self.selected_count_label)
        
        layout.addLayout(selection_layout)
        
        # Album list
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMaximumHeight(250)
        
        scroll_widget = QWidget()
        self.albums_layout = QVBoxLayout(scroll_widget)
        self.albums_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # Add album selection widgets
        for missing_album in self.missing_albums:
            album_widget = AlbumSelectionWidget(missing_album)
            album_widget.checkbox.toggled.connect(self.update_selection_count)
            self.album_widgets.append(album_widget)
            self.albums_layout.addWidget(album_widget)
        
        self.scroll_area.setWidget(scroll_widget)
        layout.addWidget(self.scroll_area)
        
        # Progress bar (initially hidden)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        self.progress_label = QLabel()
        self.progress_label.setVisible(False)
        layout.addWidget(self.progress_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.preview_btn = QPushButton("Preview Import")
        self.preview_btn.clicked.connect(self.preview_import)
        button_layout.addWidget(self.preview_btn)
        
        button_layout.addStretch()
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        self.import_btn = QPushButton("Import to DeeMusic")
        self.import_btn.setDefault(True)
        self.import_btn.clicked.connect(self.start_import)
        button_layout.addWidget(self.import_btn)
        
        layout.addLayout(button_layout)
        
        # Update initial count
        self.update_selection_count()
    
    def check_deemusic_accessibility(self):
        """Check if DeeMusic queue is accessible and update status."""
        try:
            status = self.queue_integration.get_queue_status()
            
            if status["deemusic_accessible"]:
                self.status_label.setText(
                    f"✅ DeeMusic queue accessible\n"
                    f"📁 Queue location: {status['deemusic_queue_path']}\n"
                    f"📊 Current queue: {status['deemusic_pending_count']} pending, "
                    f"{status['deemusic_completed_count']} completed, "
                    f"{status['deemusic_failed_count']} failed"
                )
                self.status_label.setStyleSheet("color: green;")
                self.import_btn.setEnabled(True)
            else:
                self.status_label.setText(
                    f"❌ DeeMusic queue not accessible\n"
                    f"💡 Please run DeeMusic at least once to create the queue directory\n"
                    f"📁 Expected location: {status['deemusic_queue_path']}"
                )
                self.status_label.setStyleSheet("color: red;")
                self.import_btn.setEnabled(False)
                
        except Exception as e:
            logger.error(f"Error checking DeeMusic accessibility: {e}")
            self.status_label.setText(f"❌ Error checking DeeMusic queue: {str(e)}")
            self.status_label.setStyleSheet("color: red;")
            self.import_btn.setEnabled(False)
    
    def select_all(self):
        """Select all albums."""
        for widget in self.album_widgets:
            widget.set_selected(True)
        self.update_selection_count()
    
    def select_none(self):
        """Deselect all albums."""
        for widget in self.album_widgets:
            widget.set_selected(False)
        self.update_selection_count()
    
    def update_selection_count(self):
        """Update the selection count label."""
        selected_count = sum(1 for widget in self.album_widgets if widget.is_selected())
        total_count = len(self.album_widgets)
        
        self.selected_count_label.setText(f"Selected: {selected_count} of {total_count}")
        
        # Enable/disable import button based on selection
        self.import_btn.setEnabled(selected_count > 0 and self.queue_integration.is_deemusic_queue_accessible())
    
    def get_selected_albums(self) -> List[Dict[str, Any]]:
        """Get the selected albums as dictionary data."""
        selected_albums = []
        
        for widget in self.album_widgets:
            if widget.is_selected():
                missing_album = widget.missing_album
                album_data = {
                    "deezer_id": missing_album.deezer_album.id,
                    "title": missing_album.deezer_album.title,
                    "artist": missing_album.deezer_album.artist,
                    "year": missing_album.deezer_album.year,
                    "track_count": missing_album.deezer_album.track_count,
                    "url": f"https://www.deezer.com/album/{missing_album.deezer_album.id}",
                    "local_album_path": str(missing_album.local_album.path) if missing_album.local_album else None,
                    "missing_tracks_count": len(missing_album.missing_tracks),
                    "selection_reason": "user_selected"
                }
                selected_albums.append(album_data)
        
        return selected_albums
    
    def preview_import(self):
        """Show a preview of what will be imported."""
        selected_albums = self.get_selected_albums()
        
        if not selected_albums:
            QMessageBox.information(self, "No Selection", "Please select at least one album to preview.")
            return
        
        summary = self.queue_integration.create_import_summary(selected_albums)
        
        # Create preview dialog
        preview_dialog = QDialog(self)
        preview_dialog.setWindowTitle("Import Preview")
        preview_dialog.setModal(True)
        preview_dialog.resize(500, 400)
        
        layout = QVBoxLayout(preview_dialog)
        
        text_edit = QTextEdit()
        text_edit.setPlainText(summary)
        text_edit.setReadOnly(True)
        text_edit.setFont(QFont("Consolas", 9))
        layout.addWidget(text_edit)
        
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(preview_dialog.accept)
        button_layout.addWidget(close_btn)
        
        layout.addLayout(button_layout)
        
        preview_dialog.exec()
    
    def start_import(self):
        """Start the import process."""
        selected_albums = self.get_selected_albums()
        
        if not selected_albums:
            QMessageBox.information(self, "No Selection", "Please select at least one album to import.")
            return
        
        # Confirm import
        reply = QMessageBox.question(
            self, 
            "Confirm Import",
            f"Import {len(selected_albums)} selected albums to DeeMusic's download queue?\n\n"
            "These albums will be available for download when you open DeeMusic.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Disable UI during import
        self.import_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.preview_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        
        # Start import worker
        self.import_worker = ImportWorker(self.queue_integration, selected_albums)
        self.import_worker.progress_updated.connect(self.update_progress)
        self.import_worker.import_completed.connect(self.import_finished)
        self.import_worker.start()
    
    def update_progress(self, progress: int, message: str):
        """Update progress bar and message."""
        self.progress_bar.setValue(progress)
        self.progress_label.setText(message)
    
    def import_finished(self, success: bool, message: str):
        """Handle import completion."""
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        
        if success:
            QMessageBox.information(self, "Import Successful", message)
            self.accept()  # Close dialog on success
        else:
            QMessageBox.critical(self, "Import Failed", message)
            
            # Re-enable UI for retry
            self.import_btn.setEnabled(True)
            self.cancel_btn.setEnabled(True)
            self.preview_btn.setEnabled(True)