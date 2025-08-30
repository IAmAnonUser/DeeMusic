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
            settings: Current folder structure and character replacement settings
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

        # Character Replacement Settings
        char_group = QGroupBox("Character Replacement")
        char_layout = QVBoxLayout()
        
        # Enable/disable character replacement
        self.char_replacement_enabled = QCheckBox("Enable custom character replacement")
        char_layout.addWidget(self.char_replacement_enabled)
        
        # Default replacement character
        default_char_layout = QHBoxLayout()
        default_char_layout.addWidget(QLabel("Default replacement character:"))
        self.default_replacement_char = QLineEdit()
        self.default_replacement_char.setMaxLength(1)
        self.default_replacement_char.setFixedWidth(30)
        default_char_layout.addWidget(self.default_replacement_char)
        default_char_layout.addStretch()
        char_layout.addLayout(default_char_layout)
        
        # Custom character replacements
        custom_char_label = QLabel("Custom character replacements:")
        char_layout.addWidget(custom_char_label)
        
        # Create a form for common illegal characters
        self.char_replacements = {}
        illegal_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        
        char_form_layout = QFormLayout()
        for char in illegal_chars:
            replacement_input = QLineEdit()
            replacement_input.setMaxLength(3)  # Allow up to 3 characters for replacement
            replacement_input.setFixedWidth(50)
            self.char_replacements[char] = replacement_input
            char_form_layout.addRow(f"Replace '{char}' with:", replacement_input)
        
        char_layout.addLayout(char_form_layout)
        
        # Add help text for character replacement
        char_help_text = QLabel(
            "Configure how illegal filename characters are replaced.\n"
            "Leave empty to use the default replacement character.\n"
            "Common illegal characters: < > : \" / \\ | ? *"
        )
        char_help_text.setStyleSheet("color: gray; font-size: 10px;")
        char_layout.addWidget(char_help_text)
        
        char_group.setLayout(char_layout)
        
        # Load character replacement settings after widgets are created
        char_settings = self.settings.get('character_replacement', {})
        self.char_replacement_enabled.setChecked(char_settings.get('enabled', True))
        self.default_replacement_char.setText(char_settings.get('replacement_char', '_'))
        
        # Load custom replacements
        custom_replacements = char_settings.get('custom_replacements', {})
        for char, input_widget in self.char_replacements.items():
            input_widget.setText(custom_replacements.get(char, ''))

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
        layout.addWidget(char_group)
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
        # Collect custom character replacements
        custom_replacements = {}
        for char, input_widget in self.char_replacements.items():
            replacement = input_widget.text().strip()
            if replacement:  # Only add non-empty replacements
                custom_replacements[char] = replacement
        
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
            },
            'character_replacement': {
                'enabled': self.char_replacement_enabled.isChecked(),
                'replacement_char': self.default_replacement_char.text() or '_',
                'custom_replacements': custom_replacements
            }
        }
        
        self.settings_changed.emit(settings)
        self.accept() 