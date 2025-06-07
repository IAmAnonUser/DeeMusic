"""
Folder structure settings dialog for DeeMusic.
Provides a UI for configuring folder organization preferences.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QCheckBox, QLabel, QLineEdit, QPushButton,
    QFormLayout, QWidget
)
from PyQt6.QtCore import Qt, pyqtSignal
import re
from pathvalidate import sanitize_filename

class FolderSettingsDialog(QDialog):
    """Dialog for configuring folder structure settings."""
    
    settings_changed = pyqtSignal(dict)

    def __init__(self, settings: dict, parent=None):
        """
        Initialize the folder settings dialog.
        
        Args:
            settings: Current folder structure settings
            parent: Parent widget
        """
        super().__init__(parent)
        self.settings = settings
        self.setup_ui()

    def setup_ui(self):
        """Set up the dialog's user interface."""
        self.setWindowTitle("Folder Structure Settings")
        self.setMinimumWidth(500)

        layout = QVBoxLayout()
        
        # Folder Creation Options
        folder_group = QGroupBox("Folder Creation")
        folder_layout = QVBoxLayout()
        
        self.playlist_checkbox = QCheckBox("Create folder for playlists")
        self.artist_checkbox = QCheckBox("Create folder for artist")
        self.album_checkbox = QCheckBox("Create folder for album")
        self.cd_checkbox = QCheckBox("Create folder for CDs")
        self.playlist_structure_checkbox = QCheckBox("Create folder structure for playlists")
        self.singles_structure_checkbox = QCheckBox("Create folder structure for singles")

        # Load current settings
        self.playlist_checkbox.setChecked(self.settings.get('create_playlist_folders', True))
        self.artist_checkbox.setChecked(self.settings.get('create_artist_folders', True))
        self.album_checkbox.setChecked(self.settings.get('create_album_folders', True))
        self.cd_checkbox.setChecked(self.settings.get('create_cd_folders', True))
        self.playlist_structure_checkbox.setChecked(self.settings.get('create_playlist_structure', False))
        self.singles_structure_checkbox.setChecked(self.settings.get('create_singles_structure', True))

        folder_layout.addWidget(self.playlist_checkbox)
        folder_layout.addWidget(self.artist_checkbox)
        folder_layout.addWidget(self.album_checkbox)
        folder_layout.addWidget(self.cd_checkbox)
        folder_layout.addWidget(self.playlist_structure_checkbox)
        folder_layout.addWidget(self.singles_structure_checkbox)
        folder_group.setLayout(folder_layout)
        
        # Template Settings
        template_group = QGroupBox("Folder Name Templates")
        template_layout = QFormLayout()
        
        self.playlist_template = QLineEdit(self.settings.get('templates', {}).get('playlist', '%playlist%'))
        self.artist_template = QLineEdit(self.settings.get('templates', {}).get('artist', '%artist%'))
        self.album_template = QLineEdit(self.settings.get('templates', {}).get('album', '%album%'))
        self.cd_template = QLineEdit(self.settings.get('templates', {}).get('cd', 'CD %disc_number%'))

        template_layout.addRow("Playlist folder template:", self.playlist_template)
        template_layout.addRow("Artist folder template:", self.artist_template)
        template_layout.addRow("Album folder template:", self.album_template)
        template_layout.addRow("CD folder template:", self.cd_template)
        
        # Add help text
        help_text = QLabel(
            "Available placeholders:\n"
            "%playlist% - Playlist name\n"
            "%artist% - Artist name\n"
            "%album% - Album name\n"
            "%disc_number% - Disc number\n"
            "%year% - Release year"
        )
        help_text.setStyleSheet("color: gray;")
        template_layout.addRow(help_text)
        
        template_group.setLayout(template_layout)

        # Preview section
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout()
        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet("color: gray;")
        preview_layout.addWidget(self.preview_label)
        preview_group.setLayout(preview_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        save_button = QPushButton("Save")
        cancel_button = QPushButton("Cancel")
        
        save_button.clicked.connect(self.save_settings)
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        
        # Add all components to main layout
        layout.addWidget(folder_group)
        layout.addWidget(template_group)
        layout.addWidget(preview_group)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # Connect signals for live preview
        self.playlist_template.textChanged.connect(self.update_preview)
        self.artist_template.textChanged.connect(self.update_preview)
        self.album_template.textChanged.connect(self.update_preview)
        self.cd_template.textChanged.connect(self.update_preview)
        
        # Initial preview update
        self.update_preview()

    def update_preview(self):
        """Update the preview text with current settings."""
        example_metadata = {
            'playlist': 'My Favorite Songs',
            'artist': 'Example Artist',
            'album': 'Greatest Hits',
            'disc_number': 1,
            'year': 2024
        }
        
        preview_parts = []
        
        if self.playlist_checkbox.isChecked():
            preview_parts.append(self._apply_template(self.playlist_template.text(), example_metadata))
        
        if self.artist_checkbox.isChecked():
            preview_parts.append(self._apply_template(self.artist_template.text(), example_metadata))
            
        if self.album_checkbox.isChecked():
            preview_parts.append(self._apply_template(self.album_template.text(), example_metadata))
            
        if self.cd_checkbox.isChecked():
            preview_parts.append(self._apply_template(self.cd_template.text(), example_metadata))
        
        preview_path = " → ".join(preview_parts)
        self.preview_label.setText(f"Example path:\n{preview_path}")

    def _apply_template(self, template: str, metadata: dict) -> str:
        """
        Apply metadata to template string for preview.
        Validates and sanitizes the resulting path.
        """
        result = template
        for key, value in metadata.items():
            placeholder = f"%{key}%"
            if placeholder in result:
                result = result.replace(placeholder, str(value))
        
        # Sanitize the result
        result = sanitize_filename(result)
        
        # Replace remaining problematic characters with underscore
        result = re.sub(r'[<>:"/\\|?*]', '_', result)
        
        # Remove or replace other problematic characters
        result = result.strip('. ')  # Remove leading/trailing dots and spaces
        
        return result

    def save_settings(self):
        """Save the current settings and emit the settings_changed signal."""
        settings = {
            'create_playlist_folders': self.playlist_checkbox.isChecked(),
            'create_artist_folders': self.artist_checkbox.isChecked(),
            'create_album_folders': self.album_checkbox.isChecked(),
            'create_cd_folders': self.cd_checkbox.isChecked(),
            'create_playlist_structure': self.playlist_structure_checkbox.isChecked(),
            'create_singles_structure': self.singles_structure_checkbox.isChecked(),
            'templates': {
                'playlist': self.playlist_template.text(),
                'artist': self.artist_template.text(),
                'album': self.album_template.text(),
                'cd': self.cd_template.text()
            }
        }
        
        self.settings_changed.emit(settings)
        self.accept() 