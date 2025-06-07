"""Settings dialog for DeeMusic."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QFormLayout,
    QComboBox, QSpinBox, QCheckBox
)
from PyQt6.QtCore import Qt
from pathlib import Path
from ...deemusic.config_manager import ConfigManager

class SettingsDialog(QDialog):
    """Dialog for managing application settings."""
    
    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")
        self.setMinimumWidth(400)
        
        # Create layout
        layout = QVBoxLayout()
        form_layout = QFormLayout()
        
        # Deezer Settings
        self.arl_input = QLineEdit()
        self.arl_input.setEchoMode(QLineEdit.EchoMode.Password)  # Hide the token
        self.arl_input.setText(self.config.get_setting('deezer.arl', ''))
        form_layout.addRow("Deezer ARL Token:", self.arl_input)
        
        # Download Settings
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(['MP3_128', 'MP3_320', 'FLAC'])
        self.quality_combo.setCurrentText(self.config.get_setting('downloads.quality', 'MP3_320'))
        form_layout.addRow("Download Quality:", self.quality_combo)
        
        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 10)
        self.concurrent_spin.setValue(self.config.get_setting('downloads.concurrent_downloads', 3))
        form_layout.addRow("Concurrent Downloads:", self.concurrent_spin)
        
        self.create_m3u = QCheckBox()
        self.create_m3u.setChecked(self.config.get_setting('downloads.create_playlist_m3u', True))
        form_layout.addRow("Create M3U Playlists:", self.create_m3u)
        
        # Add form to main layout
        layout.addLayout(form_layout)
        
        # Add buttons
        button_layout = QHBoxLayout()
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.save_settings)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
    def save_settings(self):
        """Save settings and close dialog."""
        # Save Deezer settings
        self.config.set_setting('deezer.arl', self.arl_input.text())
        
        # Save download settings
        self.config.set_setting('downloads.quality', self.quality_combo.currentText())
        self.config.set_setting('downloads.concurrent_downloads', self.concurrent_spin.value())
        self.config.set_setting('downloads.create_playlist_m3u', self.create_m3u.isChecked())
        
        self.accept() 