"""
Settings dialog for DeeMusic application.
"""

from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTabWidget, QLabel, QGroupBox,
    QFormLayout, QLineEdit, QCheckBox, QComboBox,
    QSpinBox, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from ui.folder_settings_dialog import FolderSettingsDialog
from config_manager import ConfigManager
from .theme_manager import ThemeManager
import logging
from typing import Dict, Any
import requests
import time

logger = logging.getLogger(__name__)

class SettingsDialog(QDialog):
    """Settings dialog for DeeMusic application."""
    
    settings_changed = pyqtSignal(dict)  # Signal emitted when settings are changed

    def __init__(self, config: ConfigManager, theme_manager: ThemeManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.theme_manager = theme_manager
        self.setWindowTitle("Settings")
        self.setMinimumSize(600, 400)
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        """Set up the settings dialog UI."""
        layout = QVBoxLayout(self)

        # Create tab widget
        tabs = QTabWidget()
        
        # Account tab
        account_tab = QWidget()
        account_layout = QVBoxLayout(account_tab)
        
        # Account settings
        account_group = QGroupBox("Deezer Account")
        account_form = QFormLayout()
        
        # Status label
        self.status_label = QLabel("Not logged in")
        account_form.addRow("Status:", self.status_label)
        
        # Update status based on current ARL token
        arl = self.config.get_setting("deezer.arl", "")
        if arl:
            self.status_label.setText("ARL token saved")
        
        # ARL explanation
        explanation = QLabel(
            "An ARL token is required to access your Deezer account and download music. "
            "This token is stored locally and is used only to authenticate with Deezer."
        )
        explanation.setWordWrap(True)
        account_form.addRow(explanation)
        
        # How to get ARL link
        how_to_link = QLabel("<a href='https://github.com/RemixDev/deemix-py/wiki/FAQ#how-do-i-get-my-arl-token'>How to get your ARL token</a>")
        how_to_link.setOpenExternalLinks(True)
        account_form.addRow(how_to_link)
        
        # Deezer ARL token
        self.arl_input = QLineEdit()
        self.arl_input.setPlaceholderText("Enter your Deezer ARL token")
        self.arl_input.setEchoMode(QLineEdit.EchoMode.Password)
        
        # Show password toggle
        self.show_arl = QCheckBox("Show token")
        self.show_arl.toggled.connect(self.toggle_arl_visibility)
        
        account_form.addRow("ARL Token:", self.arl_input)
        account_form.addRow("", self.show_arl)
        
        account_group.setLayout(account_form)
        account_layout.addWidget(account_group)
        account_layout.addStretch()
        
        # Add account tab
        tabs.addTab(account_tab, "Account")
        
        # Downloads tab
        downloads_tab = QWidget()
        downloads_layout = QVBoxLayout(downloads_tab)
        
        # Download settings
        download_group = QGroupBox("Download Settings")
        download_form = QFormLayout()
        
        # Download path field
        self.download_path = QLineEdit()
        download_path_layout = QHBoxLayout()
        download_path_layout.addWidget(self.download_path)
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self.browse_download_path)
        download_path_layout.addWidget(browse_button)
        download_form.addRow("Download Location:", download_path_layout)
        
        self.quality_combo = QComboBox()
        # Add items with both display text and internal data value
        self.quality_combo.addItem("FLAC", "FLAC") 
        self.quality_combo.addItem("MP3 (320 kbps)", "MP3_320") # Use user-friendly text
        self.quality_combo.addItem("MP3 (128 kbps)", "MP3_128") # Use user-friendly text
        download_form.addRow("Audio Quality:", self.quality_combo)
        
        self.concurrent_downloads = QSpinBox()
        self.concurrent_downloads.setRange(1, 5)
        self.concurrent_downloads.setValue(3)
        download_form.addRow("Concurrent Downloads:", self.concurrent_downloads)
        
        self.overwrite_existing = QCheckBox("Overwrite existing files")
        download_form.addRow(self.overwrite_existing)
        
        self.skip_existing = QCheckBox("Skip existing files")
        download_form.addRow(self.skip_existing)
        
        self.create_playlist_m3u = QCheckBox("Create M3U playlist files")
        download_form.addRow(self.create_playlist_m3u)
        
        download_group.setLayout(download_form)
        downloads_layout.addWidget(download_group)
        
        # Artwork settings
        artwork_group = QGroupBox("Artwork Settings")
        artwork_form = QFormLayout()
        
        # Save artwork options
        self.save_artwork = QCheckBox("Save separate artwork files")
        artwork_form.addRow(self.save_artwork)
        
        self.embed_artwork = QCheckBox("Embed artwork in audio files")
        artwork_form.addRow(self.embed_artwork)
        
        # Album artwork settings
        album_artwork_label = QLabel("Album Artwork Settings:")
        album_artwork_label.setStyleSheet("font-weight: bold;")
        artwork_form.addRow(album_artwork_label)
        
        self.album_artwork_size = QSpinBox()
        self.album_artwork_size.setRange(300, 3000)
        self.album_artwork_size.setSingleStep(100)
        self.album_artwork_size.setSuffix(" px")
        artwork_form.addRow("Album Artwork Size:", self.album_artwork_size)
        
        self.album_image_template = QLineEdit()
        artwork_form.addRow("Album Image Name:", self.album_image_template)
        
        self.album_image_format = QComboBox()
        self.album_image_format.addItems(["jpg", "png", "webp"])
        artwork_form.addRow("Album Image Format:", self.album_image_format)
        
        # Artist artwork settings
        artist_artwork_label = QLabel("Artist Artwork Settings:")
        artist_artwork_label.setStyleSheet("font-weight: bold;")
        artwork_form.addRow(artist_artwork_label)
        
        self.artist_artwork_size = QSpinBox()
        self.artist_artwork_size.setRange(300, 3000)
        self.artist_artwork_size.setSingleStep(100)
        self.artist_artwork_size.setSuffix(" px")
        artwork_form.addRow("Artist Artwork Size:", self.artist_artwork_size)
        
        self.artist_image_template = QLineEdit()
        artwork_form.addRow("Artist Image Name:", self.artist_image_template)
        
        self.artist_image_format = QComboBox()
        self.artist_image_format.addItems(["jpg", "png", "webp"])
        artwork_form.addRow("Artist Image Format:", self.artist_image_format)
        
        # Embedded artwork settings
        embedded_artwork_label = QLabel("Embedded Artwork Settings:")
        embedded_artwork_label.setStyleSheet("font-weight: bold;")
        artwork_form.addRow(embedded_artwork_label)
        
        self.embedded_artwork_size = QSpinBox()
        self.embedded_artwork_size.setRange(300, 3000)
        self.embedded_artwork_size.setSingleStep(100)
        self.embedded_artwork_size.setSuffix(" px")
        artwork_form.addRow("Embedded Artwork Size:", self.embedded_artwork_size)
        
        artwork_group.setLayout(artwork_form)
        downloads_layout.addWidget(artwork_group)
        
        # Add downloads tab
        tabs.addTab(downloads_tab, "Downloads")
        
        # Network tab
        network_tab = QWidget()
        network_layout = QVBoxLayout(network_tab)
        
        # Proxy settings
        proxy_group = QGroupBox("Proxy Settings")
        proxy_layout = QVBoxLayout(proxy_group)
        
        # Proxy description
        proxy_desc = QLabel(
            "Configure proxy settings to bypass geo-restrictions. "
            "This will route Deezer API requests through the specified proxy server."
        )
        proxy_desc.setWordWrap(True)
        proxy_desc.setStyleSheet("color: #666; margin-bottom: 10px;")
        proxy_layout.addWidget(proxy_desc)
        
        # Enable proxy checkbox
        self.enable_proxy = QCheckBox("Enable Proxy")
        proxy_layout.addWidget(self.enable_proxy)
        
        # Proxy configuration form
        proxy_form = QFormLayout()
        
        # Proxy type
        self.proxy_type = QComboBox()
        self.proxy_type.addItems(["http", "https", "socks4", "socks5"])
        proxy_form.addRow("Type:", self.proxy_type)
        
        # Host and port
        host_port_layout = QHBoxLayout()
        self.proxy_host = QLineEdit()
        self.proxy_host.setPlaceholderText("proxy.example.com")
        self.proxy_port = QLineEdit()
        self.proxy_port.setPlaceholderText("8080")
        self.proxy_port.setMaximumWidth(80)
        host_port_layout.addWidget(self.proxy_host)
        host_port_layout.addWidget(QLabel(":"))
        host_port_layout.addWidget(self.proxy_port)
        host_port_layout.addStretch()
        proxy_form.addRow("Host:Port:", host_port_layout)
        
        # Username and password (optional)
        self.proxy_username = QLineEdit()
        self.proxy_username.setPlaceholderText("Optional")
        proxy_form.addRow("Username:", self.proxy_username)
        
        self.proxy_password = QLineEdit()
        self.proxy_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.proxy_password.setPlaceholderText("Optional")
        proxy_form.addRow("Password:", self.proxy_password)
        
        proxy_layout.addLayout(proxy_form)
        
        # Usage options
        self.use_for_api = QCheckBox("Use for API requests (recommended for geo-restrictions)")
        self.use_for_api.setChecked(True)
        self.use_for_downloads = QCheckBox("Use for file downloads")
        self.use_for_downloads.setChecked(True)
        
        proxy_layout.addWidget(self.use_for_api)
        proxy_layout.addWidget(self.use_for_downloads)
        
        # Test proxy button
        self.test_proxy_button = QPushButton("Test Proxy Connection")
        self.test_proxy_button.clicked.connect(self.test_proxy_connection)
        proxy_layout.addWidget(self.test_proxy_button)
        
        # Proxy recommendations
        recommendations_group = QGroupBox("Recommended Proxy Services")
        recommendations_layout = QVBoxLayout(recommendations_group)
        
        recommendations_text = QLabel(
            "<b>Free Options:</b><br>"
            "• ProxyScrape (proxy-daily.com)<br>"
            "• FreeProxy.cz<br>"
            "• Free-Proxy-List.net<br><br>"
            "<b>Paid Services (More Reliable):</b><br>"
            "• Bright Data (premium, $500+/month)<br>"
            "• Oxylabs ($15+/month)<br>"
            "• Smartproxy ($12.5+/month)<br>"
            "• ProxyMesh ($20/month unlimited)<br><br>"
            "<b>Note:</b> Paid services are more reliable for consistent geo-restriction bypass."
        )
        recommendations_text.setWordWrap(True)
        recommendations_text.setStyleSheet("font-size: 11px; color: #555;")
        recommendations_layout.addWidget(recommendations_text)
        
        network_layout.addWidget(proxy_group)
        network_layout.addWidget(recommendations_group)
        network_layout.addStretch()
        
        # Connect proxy enable/disable
        self.enable_proxy.toggled.connect(self.on_proxy_enabled_changed)
        
        # Add network tab
        tabs.addTab(network_tab, "Network")
        
        # Lyrics tab
        lyrics_tab = QWidget()
        lyrics_layout = QVBoxLayout(lyrics_tab)
        
        # Lyrics settings
        lyrics_group = QGroupBox("Lyrics Settings")
        lyrics_form = QFormLayout()
        
        self.lrc_enabled = QCheckBox("Enable LRC (synchronized lyrics)")
        lyrics_form.addRow(self.lrc_enabled)
        
        self.txt_enabled = QCheckBox("Enable plain text lyrics")
        lyrics_form.addRow(self.txt_enabled)
        
        self.embed_sync_lyrics = QCheckBox("Embed synchronized lyrics in audio files")
        lyrics_form.addRow(self.embed_sync_lyrics)
        
        self.embed_plain_lyrics = QCheckBox("Embed plain text lyrics as fallback (USLT/LYRICS)")
        lyrics_form.addRow(self.embed_plain_lyrics)
        
        self.lyrics_language = QComboBox()
        self.lyrics_language.addItems(["Original", "English", "Romanized"])
        lyrics_form.addRow("Preferred Language:", self.lyrics_language)
        
        self.lyrics_location = QComboBox()
        self.lyrics_location.addItems(["With Audio Files", "Separate Folder"])
        lyrics_form.addRow("Lyrics Location:", self.lyrics_location)
        
        self.lyrics_path = QLineEdit()
        self.lyrics_path_button = QPushButton("Browse...")
        lyrics_path_layout = QHBoxLayout()
        lyrics_path_layout.addWidget(self.lyrics_path)
        lyrics_path_layout.addWidget(self.lyrics_path_button)
        lyrics_form.addRow("Custom Lyrics Path:", lyrics_path_layout)
        
        self.lyrics_path_button.clicked.connect(self.browse_lyrics_path)
        
        # Additional lyrics options
        self.sync_offset = QSpinBox()
        self.sync_offset.setRange(-5000, 5000)
        self.sync_offset.setSingleStep(100)
        self.sync_offset.setSuffix(" ms")
        lyrics_form.addRow("Sync Offset:", self.sync_offset)
        
        self.lyrics_encoding = QComboBox()
        self.lyrics_encoding.addItems(["UTF-8", "UTF-16", "ASCII"])
        lyrics_form.addRow("Lyrics Encoding:", self.lyrics_encoding)
        
        lyrics_group.setLayout(lyrics_form)
        lyrics_layout.addWidget(lyrics_group)
        
        # Add lyrics tab
        tabs.addTab(lyrics_tab, "Lyrics")
        
        # Structure tab (renamed from Appearance, now includes file/folder structure)
        structure_tab = QWidget()
        structure_layout = QVBoxLayout(structure_tab)
        
        # Filename Templates section
        templates_group = QGroupBox("Filename Templates")
        templates_form = QFormLayout()
        
        # Create template inputs with placeholder buttons
        self.track_template_input = QLineEdit()
        track_template_layout = self._create_template_input_with_button(self.track_template_input)
        templates_form.addRow("Single Track Template:", track_template_layout)

        self.album_track_template_input = QLineEdit()
        album_track_template_layout = self._create_template_input_with_button(self.album_track_template_input)
        templates_form.addRow("Album Track Template:", album_track_template_layout)

        self.playlist_track_template_input = QLineEdit()
        playlist_track_template_layout = self._create_template_input_with_button(self.playlist_track_template_input)
        templates_form.addRow("Playlist Track Template:", playlist_track_template_layout)
        
        # Available placeholders info
        placeholders_help = QLabel(
            "<b>Available Placeholders:</b><br>"
            "• {artist}, {album}, {title}, {album_artist}, {genre}<br>"
            "• {track_number}, {playlist_position}, {disc_number}<br>"
            "• {year}, {playlist_name}, {playlist}, {isrc}<br>"
            "<i>Use :02d for zero-padded numbers (e.g., {track_number:02d})</i>"
        )
        placeholders_help.setWordWrap(True)
        placeholders_help.setStyleSheet("font-size: 10px; color: #666; padding: 5px;")
        templates_form.addRow(placeholders_help)
        
        templates_group.setLayout(templates_form)
        structure_layout.addWidget(templates_group)
        
        # Folder Structure section
        folder_group = QGroupBox("Folder Structure")
        folder_layout = QVBoxLayout()
        folder_button = QPushButton("Configure Folder Structure...")
        folder_button.clicked.connect(self.show_folder_settings)
        folder_layout.addWidget(folder_button)
        folder_group.setLayout(folder_layout)
        structure_layout.addWidget(folder_group)
        
        structure_layout.addStretch()
        
        # Add structure tab
        tabs.addTab(structure_tab, "Structure")
        
        # Add tabs to main layout
        layout.addWidget(tabs)
        
        # Add buttons
        button_layout = QHBoxLayout()
        save_button = QPushButton("Save")
        cancel_button = QPushButton("Cancel")
        reset_button = QPushButton("Reset to Defaults")
        
        save_button.clicked.connect(self.save_settings)
        cancel_button.clicked.connect(self.reject)
        reset_button.clicked.connect(self.reset_settings)
        
        button_layout.addWidget(reset_button)
        button_layout.addStretch()
        button_layout.addWidget(save_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)

    def _create_template_input_with_button(self, line_edit):
        """Create a layout with a line edit and a placeholder button."""
        layout = QHBoxLayout()
        layout.addWidget(line_edit)
        
        placeholder_button = QPushButton("📝")
        placeholder_button.setToolTip("Insert placeholder")
        placeholder_button.setMaximumWidth(30)
        placeholder_button.clicked.connect(lambda: self._show_placeholder_menu(line_edit))
        layout.addWidget(placeholder_button)
        
        return layout
    
    def _show_placeholder_menu(self, line_edit):
        """Show a menu with available placeholders."""
        from PyQt6.QtWidgets import QMenu, QApplication
        from PyQt6.QtCore import QPoint
        
        menu = QMenu(self)
        
        # Define placeholder categories
        placeholders = {
            "Track Info": [
                ("{artist}", "Artist name"),
                ("{album}", "Album title"),
                ("{title}", "Track title"),
                ("{album_artist}", "Album artist"),
                ("{genre}", "Genre"),
                ("{isrc}", "ISRC code")
            ],
            "Numbering": [
                ("{track_number}", "Original track number"),
                ("{track_number:02d}", "Track number (zero-padded)"),
                ("{playlist_position}", "Position in playlist"),
                ("{playlist_position:02d}", "Playlist position (zero-padded)"),
                ("{disc_number}", "Disc number")
            ],
            "Collection Info": [
                ("{playlist_name}", "Playlist name"),
                ("{playlist}", "Playlist name (alternative)"),
                ("{year}", "Release year")
            ]
        }
        
        for category, items in placeholders.items():
            # Add category header
            category_action = menu.addAction(f"═══ {category} ═══")
            category_action.setEnabled(False)
            
            # Add placeholder items
            for placeholder, description in items:
                action = menu.addAction(f"{placeholder} - {description}")
                action.triggered.connect(
                    lambda checked, p=placeholder: self._insert_placeholder(line_edit, p)
                )
            
            menu.addSeparator()
        
        # Show menu at button position
        button = self.sender()
        menu.exec(button.mapToGlobal(QPoint(0, button.height())))
    
    def _insert_placeholder(self, line_edit, placeholder):
        """Insert a placeholder at the current cursor position."""
        cursor_pos = line_edit.cursorPosition()
        current_text = line_edit.text()
        new_text = current_text[:cursor_pos] + placeholder + current_text[cursor_pos:]
        line_edit.setText(new_text)
        line_edit.setCursorPosition(cursor_pos + len(placeholder))
        line_edit.setFocus()

    def toggle_arl_visibility(self, checked):
        """Toggle the visibility of the ARL token."""
        if checked:
            self.arl_input.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.arl_input.setEchoMode(QLineEdit.EchoMode.Password)

    def load_settings(self):
        """Load settings from configuration into the UI."""
        logger.info("Loading settings into SettingsDialog...")
        
        # Load Deezer ARL token
        arl = self.config.get_setting("deezer.arl", "")
        if arl:
            self.arl_input.setText(arl)
            logger.debug("Got setting deezer.arl: " + arl)

        # Load download settings
        self.download_path.setText(self.config.get_setting("downloads.path", "downloads"))
        
        # Set the quality combo box based on the config value
        quality_value = self.config.get_setting("downloads.quality", "MP3_320")
        logger.debug(f"Got setting downloads.quality: {quality_value}")
        
        # Find and set the index for the quality combo
        for i in range(self.quality_combo.count()):
            if self.quality_combo.itemData(i) == quality_value:
                self.quality_combo.setCurrentIndex(i)
                break
        
        self.concurrent_downloads.setValue(self.config.get_setting("downloads.concurrent_downloads", 3))
        self.overwrite_existing.setChecked(self.config.get_setting("downloads.overwrite_existing", False))
        self.skip_existing.setChecked(self.config.get_setting("downloads.skip_existing", True))
        self.create_playlist_m3u.setChecked(self.config.get_setting("downloads.create_playlist_m3u", False))
        
        # Load filename templates
        track_template = self.config.get_setting("downloads.filename_templates.track", "{artist} - {title}")
        logger.info(f"SettingsDialog.load_settings: Loaded track_template: {track_template}")
        self.track_template_input.setText(track_template)
        
        album_track_template = self.config.get_setting("downloads.filename_templates.album_track", "{track_number:02d} - {album_artist} - {title}")
        logger.info(f"SettingsDialog.load_settings: Loaded album_track_template: {album_track_template}")
        self.album_track_template_input.setText(album_track_template)
        
        playlist_track_template = self.config.get_setting("downloads.filename_templates.playlist_track", "{playlist_position:02d} - {artist} - {title}")
        logger.info(f"SettingsDialog.load_settings: Loaded playlist_track_template: {playlist_track_template}")
        self.playlist_track_template_input.setText(playlist_track_template)
        
        # Load artwork settings
        self.save_artwork.setChecked(self.config.get_setting("downloads.saveArtwork", True))
        self.embed_artwork.setChecked(self.config.get_setting("downloads.embedArtwork", True))
        self.album_artwork_size.setValue(self.config.get_setting("downloads.albumArtworkSize", 1000))
        self.album_image_template.setText(self.config.get_setting("downloads.albumImageTemplate", "cover"))
        self.album_image_format.setCurrentText(self.config.get_setting("downloads.albumImageFormat", "jpg"))
        self.artist_artwork_size.setValue(self.config.get_setting("downloads.artistArtworkSize", 1200))
        self.artist_image_template.setText(self.config.get_setting("downloads.artistImageTemplate", "folder"))
        self.artist_image_format.setCurrentText(self.config.get_setting("downloads.artistImageFormat", "jpg"))
        self.embedded_artwork_size.setValue(self.config.get_setting("downloads.embeddedArtworkSize", 1000))
        
        # Load proxy settings
        proxy_config = self.config.get_setting("network.proxy", {})
        self.enable_proxy.setChecked(proxy_config.get('enabled', False))
        self.proxy_type.setCurrentText(proxy_config.get('type', 'http'))
        self.proxy_host.setText(proxy_config.get('host', ''))
        self.proxy_port.setText(str(proxy_config.get('port', '')))
        self.proxy_username.setText(proxy_config.get('username', ''))
        self.proxy_password.setText(proxy_config.get('password', ''))
        self.use_for_api.setChecked(proxy_config.get('use_for_api', True))
        self.use_for_downloads.setChecked(proxy_config.get('use_for_downloads', True))
        
        # Set initial proxy UI state
        self.on_proxy_enabled_changed()
        
        # Load lyrics settings
        self.lrc_enabled.setChecked(self.config.get_setting('lyrics.lrc_enabled', True))
        self.txt_enabled.setChecked(self.config.get_setting('lyrics.txt_enabled', True))
        self.embed_sync_lyrics.setChecked(self.config.get_setting('lyrics.embed_sync_lyrics', True))
        self.embed_plain_lyrics.setChecked(self.config.get_setting('lyrics.embed_plain_lyrics', False))
        self.lyrics_language.setCurrentText(self.config.get_setting('lyrics.language', 'Original'))
        self.lyrics_location.setCurrentText(self.config.get_setting('lyrics.location', 'With Audio Files'))
        self.lyrics_path.setText(self.config.get_setting('lyrics.custom_path', ''))
        self.sync_offset.setValue(self.config.get_setting('lyrics.sync_offset', 0))
        self.lyrics_encoding.setCurrentText(self.config.get_setting('lyrics.encoding', 'UTF-8'))

    def show_folder_settings(self):
        """Show the folder structure settings dialog."""
        current_settings = self.config.get_setting('downloads.folder_structure', {})
        dialog = FolderSettingsDialog(current_settings, self)
        dialog.settings_changed.connect(self.on_folder_settings_changed)
        dialog.exec()

    def on_folder_settings_changed(self, settings):
        """Handle changes to folder structure settings."""
        self.config.set_setting('downloads.folder_structure', settings)

    def browse_lyrics_path(self):
        """Open file dialog to select lyrics folder."""
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Lyrics Folder",
            self.lyrics_path.text(),
            QFileDialog.Option.ShowDirsOnly
        )
        if path:
            self.lyrics_path.setText(path)

    def browse_download_path(self):
        """Open file dialog to select download folder."""
        path = QFileDialog.getExistingDirectory(
            self,
            "Select Download Folder",
            self.download_path.text(),
            QFileDialog.Option.ShowDirsOnly
        )
        if path:
            self.download_path.setText(path)

    def save_settings(self):
        """Save all settings to config manager."""
        logger.info("--- SettingsDialog: save_settings called ---")
        changes: Dict[str, Any] = {}
        
        # Save account settings
        arl = self.arl_input.text().strip()
        old_arl = self.config.get_setting('deezer.arl', '')
        logger.debug(f"ARL: Current UI value = '{arl}', Old config value = '{old_arl}'")
        if arl != old_arl:
            logger.info(f"Saving ARL: {arl}")
            self.config.set_setting('deezer.arl', arl)
            changes['deezer.arl'] = arl
        
        # Save download path
        path = self.download_path.text()
        old_path = self.config.get_setting('downloads.path', '')
        logger.debug(f"Download Path: Current UI value = '{path}', Old config value = '{old_path}'")
        if path != old_path:
            logger.info(f"Saving Download Path: {path}")
            self.config.set_setting('downloads.path', path)
            changes['downloads.path'] = path
        
        # Save download settings
        quality = self.quality_combo.currentData()
        old_quality = self.config.get_setting('downloads.quality', 'FLAC')
        
        # ADDED more detailed logging for quality combo box state
        selected_quality_text_debug = self.quality_combo.currentText()
        logger.debug(f"Quality ComboBox Check: Selected Text='{selected_quality_text_debug}', Retrieved Data='{quality}'")
        
        logger.debug(f"Quality: Current UI Data = '{quality}', Old config value = '{old_quality}'")
        if quality != old_quality:
            logger.info(f"Saving Quality: {quality}")
            self.config.set_setting('downloads.quality', quality)
            changes['downloads.quality'] = quality
        
        concurrent = self.concurrent_downloads.value()
        old_concurrent = self.config.get_setting('downloads.concurrent_downloads', 3)
        if concurrent != old_concurrent:
            self.config.set_setting('downloads.concurrent_downloads', concurrent)
            changes['downloads.concurrent_downloads'] = concurrent
        
        overwrite = self.overwrite_existing.isChecked()
        old_overwrite = self.config.get_setting('downloads.overwrite_existing', False)
        if overwrite != old_overwrite:
            self.config.set_setting('downloads.overwrite_existing', overwrite)
            changes['downloads.overwrite_existing'] = overwrite
        
        skip = self.skip_existing.isChecked()
        old_skip = self.config.get_setting('downloads.skip_existing', True)
        if skip != old_skip:
            self.config.set_setting('downloads.skip_existing', skip)
            changes['downloads.skip_existing'] = skip
        
        create_playlist = self.create_playlist_m3u.isChecked()
        old_create_playlist = self.config.get_setting('downloads.create_playlist_m3u', False)
        if create_playlist != old_create_playlist:
            self.config.set_setting('downloads.create_playlist_m3u', create_playlist)
            changes['downloads.create_playlist_m3u'] = create_playlist
        
        # Save Filename Templates
        track_template_text = self.track_template_input.text()
        old_track_template = self.config.get_setting("downloads.filename_templates.track", "{artist} - {title}")
        logger.info(f"SettingsDialog.save_settings: UI track_template_text: {track_template_text}, Current Config: {old_track_template}")
        if track_template_text != old_track_template:
            logger.info(f"Saving Track Template: {track_template_text}")
            self.config.set_setting("downloads.filename_templates.track", track_template_text)
            changes['downloads.filename_templates.track'] = track_template_text

        album_track_template_text = self.album_track_template_input.text()
        old_album_track_template = self.config.get_setting("downloads.filename_templates.album_track", "{track_number:02d} - {album_artist} - {title}")
        logger.info(f"SettingsDialog.save_settings: UI album_track_template_text: {album_track_template_text}, Current Config: {old_album_track_template}")
        if album_track_template_text != old_album_track_template:
            logger.info(f"Saving Album Track Template: {album_track_template_text}")
            self.config.set_setting("downloads.filename_templates.album_track", album_track_template_text)
            changes['downloads.filename_templates.album_track'] = album_track_template_text

        playlist_track_template_text = self.playlist_track_template_input.text()
        old_playlist_track_template = self.config.get_setting("downloads.filename_templates.playlist_track", "{playlist_position:02d} - {artist} - {title}")
        logger.info(f"SettingsDialog.save_settings: UI playlist_track_template_text: {playlist_track_template_text}, Current Config: {old_playlist_track_template}")
        if playlist_track_template_text != old_playlist_track_template:
            logger.info(f"Saving Playlist Track Template: {playlist_track_template_text}")
            self.config.set_setting("downloads.filename_templates.playlist_track", playlist_track_template_text)
            changes['downloads.filename_templates.playlist_track'] = playlist_track_template_text

        # Save artwork settings
        save_artwork = self.save_artwork.isChecked()
        old_save_artwork = self.config.get_setting('downloads.saveArtwork', True)
        if save_artwork != old_save_artwork:
            self.config.set_setting('downloads.saveArtwork', save_artwork)
            changes['downloads.saveArtwork'] = save_artwork
        
        embed_artwork = self.embed_artwork.isChecked()
        old_embed_artwork = self.config.get_setting('downloads.embedArtwork', True)
        if embed_artwork != old_embed_artwork:
            self.config.set_setting('downloads.embedArtwork', embed_artwork)
            changes['downloads.embedArtwork'] = embed_artwork
        
        album_size = self.album_artwork_size.value()
        old_album_size = self.config.get_setting('downloads.albumArtworkSize', 1000)
        if album_size != old_album_size:
            self.config.set_setting('downloads.albumArtworkSize', album_size)
            changes['downloads.albumArtworkSize'] = album_size
        
        album_template = self.album_image_template.text()
        old_album_template = self.config.get_setting('downloads.albumImageTemplate', 'cover')
        if album_template != old_album_template:
            self.config.set_setting('downloads.albumImageTemplate', album_template)
            changes['downloads.albumImageTemplate'] = album_template
        
        album_format = self.album_image_format.currentText()
        old_album_format = self.config.get_setting('downloads.albumImageFormat', 'jpg')
        if album_format != old_album_format:
            self.config.set_setting('downloads.albumImageFormat', album_format)
            changes['downloads.albumImageFormat'] = album_format
        
        artist_size = self.artist_artwork_size.value()
        old_artist_size = self.config.get_setting('downloads.artistArtworkSize', 1200)
        if artist_size != old_artist_size:
            self.config.set_setting('downloads.artistArtworkSize', artist_size)
            changes['downloads.artistArtworkSize'] = artist_size
        
        artist_template = self.artist_image_template.text()
        old_artist_template = self.config.get_setting('downloads.artistImageTemplate', 'folder')
        if artist_template != old_artist_template:
            self.config.set_setting('downloads.artistImageTemplate', artist_template)
            changes['downloads.artistImageTemplate'] = artist_template
        
        artist_format = self.artist_image_format.currentText()
        old_artist_format = self.config.get_setting('downloads.artistImageFormat', 'jpg')
        if artist_format != old_artist_format:
            self.config.set_setting('downloads.artistImageFormat', artist_format)
            changes['downloads.artistImageFormat'] = artist_format
        
        embedded_size = self.embedded_artwork_size.value()
        old_embedded_size = self.config.get_setting('downloads.embeddedArtworkSize', 1000)
        if embedded_size != old_embedded_size:
            self.config.set_setting('downloads.embeddedArtworkSize', embedded_size)
            changes['downloads.embeddedArtworkSize'] = embedded_size
        
        # Save proxy settings
        proxy_config = {
            'enabled': self.enable_proxy.isChecked(),
            'type': self.proxy_type.currentText(),
            'host': self.proxy_host.text(),
            'port': self.proxy_port.text(),
            'username': self.proxy_username.text(),
            'password': self.proxy_password.text(),
            'use_for_api': self.use_for_api.isChecked(),
            'use_for_downloads': self.use_for_downloads.isChecked()
        }
        old_proxy_config = self.config.get_setting("network.proxy", {})
        if proxy_config != old_proxy_config:
            self.config.set_setting("network.proxy", proxy_config)
            changes['network.proxy'] = proxy_config
        
        # Save lyrics settings
        lrc_enabled = self.lrc_enabled.isChecked()
        if lrc_enabled != self.config.get_setting('lyrics.lrc_enabled'):
            self.config.set_setting('lyrics.lrc_enabled', lrc_enabled)
            changes['lyrics.lrc_enabled'] = lrc_enabled
            
        txt_enabled = self.txt_enabled.isChecked()
        if txt_enabled != self.config.get_setting('lyrics.txt_enabled'):
            self.config.set_setting('lyrics.txt_enabled', txt_enabled)
            changes['lyrics.txt_enabled'] = txt_enabled
            
        embed_sync_lyrics = self.embed_sync_lyrics.isChecked()
        if embed_sync_lyrics != self.config.get_setting('lyrics.embed_sync_lyrics'):
            self.config.set_setting('lyrics.embed_sync_lyrics', embed_sync_lyrics)
            changes['lyrics.embed_sync_lyrics'] = embed_sync_lyrics
            
        embed_plain_lyrics = self.embed_plain_lyrics.isChecked()
        if embed_plain_lyrics != self.config.get_setting('lyrics.embed_plain_lyrics'):
            self.config.set_setting('lyrics.embed_plain_lyrics', embed_plain_lyrics)
            changes['lyrics.embed_plain_lyrics'] = embed_plain_lyrics
            
        language = self.lyrics_language.currentText()
        if language != self.config.get_setting('lyrics.language'):
            self.config.set_setting('lyrics.language', language)
            changes['lyrics.language'] = language
            
        location = self.lyrics_location.currentText()
        if location != self.config.get_setting('lyrics.location'):
            self.config.set_setting('lyrics.location', location)
            changes['lyrics.location'] = location
            
        custom_path = self.lyrics_path.text()
        if custom_path != self.config.get_setting('lyrics.custom_path'):
            self.config.set_setting('lyrics.custom_path', custom_path)
            changes['lyrics.custom_path'] = custom_path
            
        sync_offset = self.sync_offset.value()
        if sync_offset != self.config.get_setting('lyrics.sync_offset'):
            self.config.set_setting('lyrics.sync_offset', sync_offset)
            changes['lyrics.sync_offset'] = sync_offset
            
        encoding = self.lyrics_encoding.currentText()
        if encoding != self.config.get_setting('lyrics.encoding'):
            self.config.set_setting('lyrics.encoding', encoding)
            changes['lyrics.encoding'] = encoding
            
        # Save all settings
        self.config.save_config()
        
        # Emit signal for changed settings
        if changes:
            logger.info(f"SettingsDialog: Emitting settings_changed signal with: {changes}")
            self.settings_changed.emit(changes)
        else:
            logger.info("SettingsDialog: No changes detected to emit.")
            
        logger.info("--- SettingsDialog: save_settings finished, accepting dialog ---")
        self.accept()
        
    def reset_settings(self):
        """Reset all settings to their default values."""
        if QMessageBox.question(
            self,
            "Reset Settings",
            "Are you sure you want to reset all settings to defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self.config.reset_to_defaults()
            self.load_settings()

            # Reset Filename Templates
            self.track_template_input.setText("{artist} - {title}")
            self.album_track_template_input.setText("{track_number:02d} - {album_artist} - {title}")
            self.playlist_track_template_input.setText("{playlist_position:02d} - {artist} - {title}")

            # Reset artwork settings
            self.save_artwork.setChecked(True)
            self.embed_artwork.setChecked(True)
            self.album_artwork_size.setValue(1000)
            self.album_image_template.setText("cover")
            self.album_image_format.setCurrentText("jpg")
            self.artist_artwork_size.setValue(1200)
            self.artist_image_template.setText("folder")
            self.artist_image_format.setCurrentText("jpg")
            self.embedded_artwork_size.setValue(1000)
            
            # Reset proxy settings
            self.enable_proxy.setChecked(False)
            self.proxy_type.setCurrentText("http")
            self.proxy_host.setText("")
            self.proxy_port.setText("")
            self.proxy_username.setText("")
            self.proxy_password.setText("")
            self.use_for_api.setChecked(True)
            self.use_for_downloads.setChecked(True)
            
            # Reset lyrics settings
            self.lrc_enabled.setChecked(True)
            self.txt_enabled.setChecked(True)
            self.embed_sync_lyrics.setChecked(True)
            self.embed_plain_lyrics.setChecked(False)
            self.lyrics_language.setCurrentText("Original")
            self.lyrics_location.setCurrentText("With Audio Files")
            self.lyrics_path.setText("")
            self.sync_offset.setValue(0)
            self.lyrics_encoding.setCurrentText("UTF-8")
            
            # Save all settings
            self.config.save_config()
            
            self.accept()

    def on_proxy_enabled_changed(self):
        """Handle changes to proxy enable/disable state."""
        enabled = self.enable_proxy.isChecked()
        self.proxy_type.setEnabled(enabled)
        self.proxy_host.setEnabled(enabled)
        self.proxy_port.setEnabled(enabled)
        self.proxy_username.setEnabled(enabled)
        self.proxy_password.setEnabled(enabled)
        self.use_for_api.setEnabled(enabled)
        self.use_for_downloads.setEnabled(enabled)
        self.test_proxy_button.setEnabled(enabled)

    def test_proxy_connection(self):
        """Test the proxy connection."""
        if not self.enable_proxy.isChecked():
            QMessageBox.warning(self, "Proxy Disabled", "Please enable proxy first.")
            return
            
        host = self.proxy_host.text().strip()
        port = self.proxy_port.text().strip()
        
        if not host or not port:
            QMessageBox.warning(self, "Invalid Settings", "Please enter both host and port.")
            return
            
        # Simple test - try to connect to httpbin
        proxy_type = self.proxy_type.currentText()
        username = self.proxy_username.text().strip()
        password = self.proxy_password.text().strip()
        
        # Build proxy URL
        if username and password:
            proxy_url = f"{proxy_type}://{username}:{password}@{host}:{port}"
        else:
            proxy_url = f"{proxy_type}://{host}:{port}"
            
        proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
        
        try:
            self.test_proxy_button.setText("Testing...")
            self.test_proxy_button.setEnabled(False)
            
            # Test with a simple HTTP request
            start_time = time.time()
            response = requests.get('http://httpbin.org/ip', proxies=proxies, timeout=10)
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                ip_info = response.json().get('origin', 'Unknown')
                QMessageBox.information(
                    self, 
                    "Connection Success", 
                    f"Proxy connection successful!\n"
                    f"Response time: {elapsed:.2f}s\n"
                    f"Your IP via proxy: {ip_info}"
                )
            else:
                QMessageBox.warning(
                    self, 
                    "Connection Failed", 
                    f"Proxy test failed with status code: {response.status_code}"
                )
                
        except Exception as e:
            QMessageBox.critical(
                self, 
                "Connection Error", 
                f"Failed to connect through proxy:\n{str(e)}"
            )
        finally:
            self.test_proxy_button.setText("Test Proxy Connection")
            self.test_proxy_button.setEnabled(True) 