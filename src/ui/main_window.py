"""
Main window for DeeMusic application.
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFrame,
    QTableWidget, QTableWidgetItem, QProgressBar,
    QSlider, QSpacerItem, QSizePolicy, QStackedWidget,
    QTabWidget, QGroupBox, QFormLayout, QCheckBox,
    QComboBox, QSpinBox, QFileDialog, QMenuBar, QMenu,
    QMessageBox, QDialog, QScrollArea, QStatusBar, QSplashScreen
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QIcon, QAction, QPixmap
# Component imports
from .components.toggle_switch import ToggleSwitch # Added import
# Use absolute imports from src.deemusic
from .theme_manager import ThemeManager
from .home_page import HomePage
# from .settings_page import SettingsPage # File does not exist, SettingsDialog is used directly
# from .explore_page import ExplorePage # File does not exist
from .search_widget import SearchWidget
from .settings_dialog import SettingsDialog # This is used for the settings modal
from .folder_settings_dialog import FolderSettingsDialog
from .playlist_detail_page import PlaylistDetailPage # Added import
from .album_detail_page import AlbumDetailPage # Import AlbumDetailPage
from .artist_detail_page import ArtistDetailPage # Import ArtistDetailPage
from .download_queue_widget import DownloadQueueWidget # ADDED: Import DownloadQueueWidget
from config_manager import ConfigManager
from services.deezer_api import DeezerAPI
from services.download_manager import DownloadManager
from services.music_player import MusicPlayer, DummyMusicPlayer
from services.queue_manager import QueueManager, Track, DummyQueueManager
import logging
import os
import asyncio 

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    """Main window of the DeeMusic application."""

    # Signal for status updates
    status_update = pyqtSignal(str)

    # Remove loop argument
    def __init__(self, config: ConfigManager = None, parent=None):
        """Initialize the main window.
        
        Args:
            config (ConfigManager, optional): Configuration manager instance.
        """
        super().__init__(parent)
        self.config = config if config is not None else ConfigManager()
        self.theme_manager = ThemeManager()
        # Ensure loop is not stored
        # self.loop = loop 
        
        # Initialize managers to None initially
        self.deezer_api = None
        self.download_manager = None
        # Initialize player and queue manager WITH DUMMY IMPLEMENTATIONS
        self.music_player = DummyMusicPlayer() # MODIFIED
        self.queue_manager = DummyQueueManager(self.music_player)  # MODIFIED
        
        self.setWindowTitle("DeeMusic")
        self.setMinimumSize(1400, 900) # MODIFIED: Increased width and height to show more content
        self.resize(1450, 950) # Set initial window size to be wider and taller
        
        # Set up asset paths - Corrected
        self.asset_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')
        logger.info(f"Asset directory set to: {self.asset_dir}")
        
        self.view_history = [] # MOVED EARLIER
        
        # Call the synchronous UI setup first
        self.setup_ui() 

        # Defer async initialization (called from run.py)
        self.current_playlist_load_task = None
        self.current_album_load_task = None 
        self.current_artist_load_task = None 

    async def initialize_services(self):
        """Initialize asynchronous services like DeezerAPI."""
        logger.info("[Initialize Services] Starting...")
        logger.info("[Initialize Services] Initializing DeezerAPI...")
        self.deezer_api = DeezerAPI(self.config, loop=asyncio.get_running_loop())
        initialized = await self.deezer_api.initialize()
        if not initialized:
            logger.error("[Initialize Services] Failed to initialize DeezerAPI.")
        else:
            logger.info("[Initialize Services] DeezerAPI initialized successfully.")
            
        logger.info("[Initialize Services] Initializing DownloadManager...")
        self.download_manager = DownloadManager(self.config, self.deezer_api) 
        logger.info("[Initialize Services] DownloadManager initialized.")

        # Pass initialized managers to the page instances
        if self.home_page:
            self.home_page.deezer_api = self.deezer_api
            self.home_page.download_manager = self.download_manager
            logger.info("[Initialize Services] Updated HomePage with DeezerAPI and DownloadManager.")

        if self.search_widget_page:
            self.search_widget_page.deezer_api = self.deezer_api
            # self.search_widget_page.download_manager is already set in its constructor in setup_content_area
            # BUT it would have received None if self.download_manager wasn't ready then.
            # Let's ensure it gets the proper one.
            self.search_widget_page.download_manager = self.download_manager 
            logger.info("[Initialize Services] Updated SearchWidget with DeezerAPI and DownloadManager.")

        if self.playlist_detail_page:
            self.playlist_detail_page.deezer_api = self.deezer_api
            self.playlist_detail_page.download_manager = self.download_manager
            logger.info("[Initialize Services] Updated PlaylistDetailPage with DeezerAPI and DownloadManager.")

        if self.album_detail_page:
            self.album_detail_page.deezer_api = self.deezer_api
            self.album_detail_page.download_manager = self.download_manager
            logger.info("[Initialize Services] Updated AlbumDetailPage with DeezerAPI and DownloadManager.")

        if self.artist_detail_page:
            self.artist_detail_page.deezer_api = self.deezer_api
            self.artist_detail_page.download_manager = self.download_manager
            logger.info("[Initialize Services] Updated ArtistDetailPage with DeezerAPI and DownloadManager.")

        if hasattr(self, 'download_queue_widget') and self.download_queue_widget:
            logger.info("[Initialize Services] Setting DownloadManager for DownloadQueueWidget.")
            self.download_queue_widget.set_download_manager(self.download_manager)
            # Load previous download queue state (failed downloads) if any
            try:
                self.download_queue_widget.load_queue_state()
                logger.info("[Initialize Services] Download queue state loaded.")
            except Exception as e:
                logger.error(f"[Initialize Services] Failed to load download queue state: {e}")
        else:
            logger.warning("[Initialize Services] DownloadQueueWidget not found to set DownloadManager.")

        logger.info("[Initialize Services] Setting up content area...")
        # self.setup_content_area() is now called from within self.setup_ui for page initialization
        # but components needing deezer_api are initialized here or passed API later
        # if self.playlist_detail_page: # REMOVED, API passed in constructor
            # self.playlist_detail_page.set_deezer_api(self.deezer_api) # REMOVED
        # if self.album_detail_page: # REMOVED, API passed in constructor
            # self.album_detail_page.set_deezer_api(self.deezer_api) # REMOVED
        # if self.artist_detail_page: # REMOVED, API passed in constructor
            # self.artist_detail_page.set_deezer_api(self.deezer_api) # REMOVED

        logger.info("[Initialize Services] Content area set up and API passed to pages.")

        if self.home_page and self.deezer_api and self.deezer_api.initialized:
            logger.info("[Initialize Services] Triggering HomePage content loading...")
            asyncio.create_task(self.home_page.load_content())
        else:
            logger.warning("[Initialize Services] HomePage or DeezerAPI not ready for content load.")

        logger.info("[Initialize Services] Connecting signals...")
        self.connect_signals()
        if self.home_page:
            if not hasattr(self.home_page, '_signals_connected_mw') or not self.home_page._signals_connected_mw:
                logger.info("[Initialize Services] Connecting HomePage signals in initialize_services...")
                print(f"[PRINT DEBUG] MainWindow: Connecting home_page.artist_selected to show_artist_detail")
                self.home_page.album_selected.connect(self.show_album_detail)
                self.home_page.playlist_selected.connect(self.show_playlist_detail)
                self.home_page.artist_selected.connect(self.show_artist_detail)
                print(f"[PRINT DEBUG] MainWindow: home_page.artist_selected.connect(self.show_artist_detail) completed")
                self.home_page.view_all_requested.connect(self.display_view_all_results_from_home)
                self.home_page.home_item_selected.connect(self._handle_home_page_item_navigation)
                self.home_page.home_item_download_requested.connect(self._handle_home_item_download) # Ensure this is connected
                self.home_page._signals_connected_mw = True # Mark as connected
                logger.info("[Initialize Services] Connected HomePage navigation and download signals.")
            else:
                logger.info("[Initialize Services] HomePage signals already connected.")
                print(f"[PRINT DEBUG] MainWindow: HomePage signals already connected (skipping)")
        else:
            logger.warning("[Initialize Services] HomePage not available to connect signals.")
            
        logger.info("[Initialize Services] Signals connected via connect_signals method call next...")
        self.connect_signals() # This call can remain if it handles other signals or if above is moved into it
        logger.info("[Initialize Services] Finished full initialization and signal setup.")

    def connect_signals(self):
        """Connect signals for various UI components."""
        logger.info("MainWindow: Connecting signals...")

        # Home Page Signals - These are now primarily connected in initialize_services to ensure API is ready.
        # If self.home_page:
        # self.home_page.home_item_download_requested.connect(self._handle_home_item_download) # This was the duplicate

        # Search Widget Signals
        if self.search_widget_page:
            self.search_widget_page.album_selected.connect(self.show_album_detail)
            self.search_widget_page.artist_selected.connect(self.show_artist_detail)
            self.search_widget_page.playlist_selected.connect(self.show_playlist_detail)
            # NEW: Connect artist and album name clicks from tracks to navigation
            self.search_widget_page.artist_name_clicked_from_track.connect(self.show_artist_detail)
            self.search_widget_page.album_name_clicked_from_track.connect(self.show_album_detail)
            self.search_widget_page.back_button_pressed.connect(self._handle_back_navigation) # Connect back button
            # Connections for download requests from search results (if SearchResultCard emits directly to SearchWidget)
            # Example: self.search_widget_page.track_download_requested.connect(self._handle_track_download_request)
            # self.search_widget_page.album_download_requested.connect(self._handle_album_download_request) # etc.

        # Playlist Detail Page Signals
        if self.playlist_detail_page:
            self.playlist_detail_page.back_requested.connect(self._handle_back_navigation)
            self.playlist_detail_page.track_selected_for_download.connect(self._handle_track_download_request)
            self.playlist_detail_page.request_full_playlist_download.connect(self._handle_playlist_download_request)  # NEW: Connect playlist download
            # NEW: Connect artist and album name clicks from tracks to navigation
            self.playlist_detail_page.artist_name_clicked_from_track.connect(self.show_artist_detail)
            self.playlist_detail_page.album_name_clicked_from_track.connect(self.show_album_detail)
            # TODO: Connect self.playlist_detail_page.track_selected_for_playback to the music player/queue manager
            # self.playlist_detail_page.track_selected_for_playback.connect(self.queue_manager.play_track_from_data) # Example

        # Album Detail Page Signals
        if self.album_detail_page:
            self.album_detail_page.back_requested.connect(self._handle_back_navigation)
            self.album_detail_page.track_selected_for_download.connect(self._handle_track_download_request)
            self.album_detail_page.album_selected_from_track.connect(self.show_album_detail) # Already connected in show_artist_detail, but good to have if direct
            self.album_detail_page.artist_selected_from_track.connect(self.show_artist_detail)
            # NEW: Connect artist and album name clicks from tracks to navigation
            self.album_detail_page.artist_name_clicked_from_track.connect(self.show_artist_detail)
            self.album_detail_page.album_name_clicked_from_track.connect(self.show_album_detail)
            self.album_detail_page.request_full_album_download.connect(self._handle_album_download_request) # ADDED: Connect to existing handler
            # self.album_detail_page.track_selected_for_playback.connect(self.queue_manager.play_track_from_data) # Connect to actual player

        # Artist Detail Page Signals - Connect them here ONLY, not in other methods
        if self.artist_detail_page:
            # Clean up any existing connections first
            try:
                self.artist_detail_page.playlist_selected.disconnect()
            except TypeError:
                pass
            try:
                self.artist_detail_page.album_selected.disconnect()
            except TypeError:
                pass
            try:
                self.artist_detail_page.back_requested.disconnect()
            except TypeError:
                pass
            try:
                self.artist_detail_page.track_selected_for_download.disconnect()
            except TypeError:
                pass
            try:
                self.artist_detail_page.album_selected_for_download.disconnect()
            except TypeError:
                pass
            try:
                self.artist_detail_page.playlist_selected_for_download.disconnect()
            except TypeError:
                pass
            
            # Now connect them
            self.artist_detail_page.playlist_selected.connect(self.show_playlist_detail)
            self.artist_detail_page.album_selected.connect(self.show_album_detail)
            # NEW: Connect artist and album name clicks from tracks to navigation
            self.artist_detail_page.artist_name_clicked_from_track.connect(self.show_artist_detail)
            self.artist_detail_page.album_name_clicked_from_track.connect(self.show_album_detail)
            self.artist_detail_page.back_requested.connect(self._handle_back_navigation)
            self.artist_detail_page.track_selected_for_download.connect(self._handle_track_download_request)
            self.artist_detail_page.album_selected_for_download.connect(self._handle_album_download_request)
            self.artist_detail_page.playlist_selected_for_download.connect(self._handle_playlist_download_request)
            logger.info("MainWindow: Connected all artist detail page signals")

        # DownloadQueueWidget Signals (if it emits signals MainWindow needs to handle beyond what DM does)
        if self.download_queue_widget:
            # Example: self.download_queue_widget.item_action_requested.connect(self._handle_download_queue_action)
            # Make sure DownloadManager signals are connected to DownloadQueueWidget
            if self.download_manager and hasattr(self.download_queue_widget, 'set_download_manager') and not self.download_queue_widget.download_manager:
                logger.info("Connecting DownloadManager to DownloadQueueWidget in connect_signals as it was missing.")
                self.download_queue_widget.set_download_manager(self.download_manager)
            pass
        
        # MusicPlayer and QueueManager signals (if UI needs to react to player state)
        # if self.music_player and not isinstance(self.music_player, DummyMusicPlayer): 
        #     self.music_player.position_changed.connect(self.update_playback_slider)
        #     self.music_player.duration_changed.connect(self.update_total_time_label)
        #     self.music_player.state_changed.connect(self.update_play_pause_button_icon)
        # if self.queue_manager and not isinstance(self.queue_manager, DummyQueueManager):
        #     self.queue_manager.current_track_changed.connect(self.update_now_playing_info)

        logger.info("MainWindow: Signals connected.")

    def get_asset_path(self, filename: str) -> str:
        """Get the full path to an asset file."""
        return os.path.join(self.asset_dir, filename)

    def setup_content_area(self):
        """Sets up the main content area with a QStackedWidget for different views."""
        logger.debug("Setting up content area (called from setup_ui).")
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("content")

        # Initialize pages here, but pass deezer_api during initialize_services
        self.home_page = HomePage(deezer_api=None, download_manager=None, parent=self) # API/DM set later
        self.search_widget_page = SearchWidget(deezer_api=None, download_manager=self.download_manager, config_manager=self.config, parent=self)
        
        # Detail Pages (API and DM passed later or on creation if safe)
        self.playlist_detail_page = PlaylistDetailPage(deezer_api=None, download_manager=self.download_manager, parent=self)
        self.album_detail_page = AlbumDetailPage(deezer_api=None, download_manager=self.download_manager, parent=self)
        self.artist_detail_page = ArtistDetailPage(deezer_api=None, download_manager=self.download_manager, parent=self)
        
        self.content_stack.addWidget(self.home_page)            # Index 0
        self.content_stack.addWidget(self.search_widget_page)   # Index 1
        self.content_stack.addWidget(self.playlist_detail_page) # Index 2
        self.content_stack.addWidget(self.album_detail_page)    # Index 3
        self.content_stack.addWidget(self.artist_detail_page)   # Index 4

        # Set default view to Home
        self.content_stack.setCurrentWidget(self.home_page)
        self.view_history.append(self.content_stack.currentIndex()) # Start history with home
        logger.info(f"Content stack initialized. Current widget: {self.content_stack.currentWidget().__class__.__name__}")

    def handle_nav_click(self, name: str):
        """Handles navigation clicks from the (now removed) sidebar."""
        logger.info(f"Navigation click: {name}")
        current_view_index = self.content_stack.currentIndex()
        target_view_index = -1
        
        if name == "home":
            target_view_index = self.content_stack.indexOf(self.home_page)
        elif name == "search": # Assuming search is triggered by search bar now
             target_view_index = self.content_stack.indexOf(self.search_widget_page)
        # elif name == "explore": # Explore page doesn't exist
        #     pass 
        elif name == "settings":
            self.show_settings()
            return # Settings is a dialog, not a stacked widget page

        if target_view_index != -1 and target_view_index != current_view_index:
            self._switch_to_view(target_view_index)
        elif target_view_index == current_view_index:
            logger.debug(f"Already on {name} view.")
        self._update_back_button_visibility()

    def show_settings(self):
        """Show the settings dialog."""
        logger.debug("Showing settings dialog.")
        # Pass current config and theme manager to settings dialog
        dialog = SettingsDialog(config=self.config, theme_manager=self.theme_manager, parent=self)
        dialog.settings_changed.connect(self.handle_settings_changed)
        dialog.exec()

    def handle_settings_changed(self, changes: dict):
        """Handle changes from the settings dialog."""
        logger.info(f"Settings changed: {changes}")
        
        # Apply theme changes
        if 'theme' in changes or 'appearance.theme' in changes: # Check for both possible keys from dialog
            self.load_stylesheet() 
            # Update toggle state if theme was changed through settings
            current_theme = self.config.get_setting('appearance.theme', 'light')
            self.theme_toggle_switch.setOn(current_theme == 'dark')
        
        # Apply Spotify settings changes
        if any(change.startswith('spotify.') for change in changes.keys()):
            if hasattr(self, 'search_widget_page') and self.search_widget_page:
                logger.info("Reinitializing Spotify client due to credential changes")
                self.search_widget_page.reinitialize_spotify_client()
            else:
                logger.warning("Cannot reinitialize Spotify client - search widget not available")
        
        # Apply download manager settings changes
        download_related_changes = [
            'downloads.quality', 'downloads.path', 'downloads.concurrent_downloads'
        ]
        if any(change.startswith('downloads.') for change in changes.keys()):
            if self.download_manager:
                logger.info("Refreshing download manager settings due to configuration changes")
                self.download_manager.refresh_settings()
            else:
                logger.warning("Cannot refresh download manager settings - download manager not available")

    def load_stylesheet(self):
        """Load and apply the QSS stylesheet based on the current theme."""
        theme = self.config.get_setting('appearance.theme', 'light')
        
        # First try to load from styles directory in the project
        styles_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'styles')
        qss_file = os.path.join(styles_dir, f"{theme}.qss")
        
        # If not found, fallback to main.qss
        if not os.path.exists(qss_file):
            qss_file = os.path.join(styles_dir, "main.qss")

        logger.info(f"Attempting to load stylesheet: {qss_file}")
        
        stylesheet_content = ""
        
        # Load main stylesheet
        try:
            if os.path.exists(qss_file):
                with open(qss_file, "r") as f:
                    stylesheet_content = f.read()
                logger.info(f"Stylesheet '{qss_file}' loaded.")
            else:
                logger.warning(f"Stylesheet file not found: {qss_file}. Applying default Qt style.")
        except Exception as e:
            logger.error(f"Error loading main stylesheet: {e}", exc_info=True)
        
        # Also load download_queue.qss
        download_queue_qss = os.path.join(styles_dir, "download_queue.qss")
        try:
            if os.path.exists(download_queue_qss):
                with open(download_queue_qss, "r") as f:
                    stylesheet_content += "\n" + f.read()
                logger.info(f"Download queue stylesheet '{download_queue_qss}' loaded.")
        except Exception as e:
            logger.error(f"Error loading download queue stylesheet: {e}", exc_info=True)
        
        # Apply combined stylesheet
        self.setStyleSheet(stylesheet_content)
        self.theme_manager.current_theme = theme

    def setup_ui(self):
        """Set up the main UI components."""
        logger.info("Setting up UI...")
        self.load_stylesheet() # Load initial theme

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        self.main_layout = QVBoxLayout(central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0) # No margins for the main layout
        self.main_layout.setSpacing(0) # No spacing for the main layout

        # --- Top Bar Layout ---
        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(15, 10, 15, 10) # Add some padding around the top bar
        top_bar_layout.setSpacing(10)

        # Logo
        self.logo_label = QLabel("DEEMUSIC")
        self.logo_label.setObjectName("logo") # For QSS styling
        # self.logo_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #6C2BD9;") # Basic style, refine in QSS
        top_bar_layout.addWidget(self.logo_label)

        # Add a small spacer to push search bar a bit to the right
        top_bar_layout.addSpacing(40) # MODIFIED: Increased spacing

        # Search Bar (moved to top bar)
        self.search_bar = QLineEdit()
        self.search_bar.setObjectName("searchBar") # For QSS styling
        self.search_bar.setPlaceholderText("Artists, Albums, Tracks, Playlists, Spotify Playlist URL...")
        self.search_bar.returnPressed.connect(self._handle_header_search)
        # self.search_bar.setMaximumWidth(400) # Make search bar smaller - REMOVED
        self.search_bar.setMinimumWidth(500) # MODIFIED to make it wider and allow expansion
        self.search_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed) # Allow horizontal expansion
        top_bar_layout.addWidget(self.search_bar, 1) # Add stretch factor to allow it to take more space

        # Top Right Controls (Settings and Theme Toggle)
        top_right_controls_layout = QHBoxLayout()
        top_right_controls_layout.setSpacing(15)

        # Settings Button (recreating or re-parenting if it existed)
        self.settings_button = QPushButton() #QPushButton("⚙️")
        settings_icon_path = self.get_asset_path("settings.svg")
        if os.path.exists(settings_icon_path):
            self.settings_button.setIcon(QIcon(settings_icon_path))
            self.settings_button.setIconSize(QSize(20, 20))
        else:
            self.settings_button.setText("S") # Fallback
            logger.warning(f"Settings icon not found: {settings_icon_path}")
        self.settings_button.setObjectName("TopSettingsButton") # New object name for specific styling
        self.settings_button.setToolTip("Settings")
        self.settings_button.setFixedSize(36,36)
        self.settings_button.clicked.connect(self.show_settings)
        top_right_controls_layout.addWidget(self.settings_button)
        
        # Theme Toggle Switch
        self.theme_toggle_switch = ToggleSwitch(parent=self)
        self.theme_toggle_switch.setObjectName("TopThemeToggle")
        self.theme_toggle_switch.setToolTip("Toggle Dark/Light Mode")
        self.theme_toggle_switch.setOn(self.config.get_setting('appearance.theme', 'light') == 'dark')
        self.theme_toggle_switch.toggled.connect(self.toggle_theme_handler) # Corrected indentation
        top_right_controls_layout.addWidget(self.theme_toggle_switch)

        top_bar_layout.addLayout(top_right_controls_layout)
        self.main_layout.addLayout(top_bar_layout)

        # --- Main Content Area (QStackedWidget) ---
        self.setup_content_area() # Initialize pages and add to content_stack
        self.main_layout.addWidget(self.content_stack, 1) # Content stack takes up remaining space

        # --- Download Queue (Now a separate widget, not part of player bar) ---
        # Create the DownloadQueueWidget instance
        self.download_queue_widget = DownloadQueueWidget(parent=self) # Pass None for DM, will be set later
        self.download_queue_widget.setMinimumWidth(400) # Increased from 300 to 400
        self.download_queue_widget.setMaximumWidth(550) # Increased from 450 to 550

        # Add DownloadQueueWidget to a new layout next to content_stack if desired,
        # or handle its visibility/placement differently (e.g., a toggleable panel).
        # For now, let's put it next to the content_stack in a QHBoxLayout.
        
        content_and_queue_layout = QHBoxLayout()
        content_and_queue_layout.addWidget(self.content_stack, 1) # Content stack takes most space

        # Vertical Separator Line
        separator_line = QFrame()
        separator_line.setFrameShape(QFrame.Shape.VLine)
        separator_line.setFrameShadow(QFrame.Shadow.Sunken)
        separator_line.setObjectName("VerticalSeparatorLine") # For styling
        content_and_queue_layout.addWidget(separator_line)

        content_and_queue_layout.addWidget(self.download_queue_widget)
        
        self.main_layout.addLayout(content_and_queue_layout, 1) # This layout now holds content and queue

        # REMOVED Player Bar setup call
        # self.setup_player_bar()

        # Initial active nav item (Home is default for content_stack)
        # self.update_active_nav_item("home") # Not needed without sidebar

        # Apply theme after all UI elements are created
        current_theme = self.config.get_setting('appearance.theme', 'light')
        self.theme_manager.current_theme = current_theme
        # self.theme_manager.apply_theme_to_icons(self) # Apply icon theme # REMOVED


        
        # Initialize status bar (optional, can be removed if not needed)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_update.connect(self.status_bar.showMessage)
        self.status_update.emit("Welcome to DeeMusic!")

        logger.info("UI setup complete.")
        # No need for update_active_nav_item without the sidebar

    def _handle_track_download_request(self, track_data: dict):
        """Handles a request to download a single track."""
        if not self.download_manager:
            logger.error("DownloadManager not available for track download.")
            return

        track_id = track_data.get('id')
        track_title = track_data.get('title', 'Unknown Track')

        if not track_id:
            logger.error(f"Cannot download track '{track_title}': Missing ID.")
            return
            
        logger.info(f"MainWindow initiating download for track: {track_title} (ID: {track_id})")
        self.download_manager.download_track(track_id) # No asyncio.create_task as download_track is sync
        # self.statusBar().showMessage(f"Downloading {track_title}...", 3000)

    def _handle_album_download_request(self, album_data: dict, track_ids: list[int] | None = None):
        """
        Handles a request to download tracks from an album.
        If track_ids is an empty list [], it signifies a request to download the full album by its ID.
        If track_ids is a non-empty list, it downloads specified tracks from the album.
        If track_ids is None, it also downloads the full album.
        """
        if not self.download_manager:
            logger.error("DownloadManager not available for album download.")
            return

        album_id = album_data.get('id')
        album_title = album_data.get('title', 'Unknown Album')

        if not album_id:
            logger.error(f"Cannot download album '{album_title}': Missing ID.")
            return

        if track_ids == [] or track_ids is None: # Full album download
            logger.info(f"MainWindow initiating download for full album: {album_title} (ID: {album_id})")
            asyncio.create_task(self.download_manager.download_album(album_id=album_id, track_ids=[]))
        elif track_ids: # Non-empty list of specific track IDs
            logger.info(f"MainWindow initiating download for {len(track_ids)} specific tracks from album: {album_title} (ID: {album_id}).")
            asyncio.create_task(self.download_manager.download_album(album_id=album_id, track_ids=track_ids))
        else:
            logger.warning(f"Album download request for {album_title} (ID: {album_id}) has unexpected track_ids: {track_ids}. No action taken.")

    def _handle_playlist_download_request(self, playlist_data: dict, track_ids: list[int] | None = None):
        """
        Handles a request to download tracks from a playlist.
        If track_ids is an empty list [], it signifies a request to download the full playlist by its ID.
        If track_ids is a non-empty list, it downloads specified tracks from the playlist.
        If track_ids is None, it also downloads the full playlist.
        """
        if not self.download_manager:
            logger.error("DownloadManager not available for playlist download.")
            return

        playlist_id = playlist_data.get('id')
        playlist_title = playlist_data.get('title', 'Unknown Playlist')
        
        # Debug: Log what we're receiving
        logger.debug(f"[MainWindow] _handle_playlist_download_request called with playlist_data: {playlist_data}")
        logger.debug(f"[MainWindow] track_ids parameter: {track_ids}")

        if not playlist_id:
            logger.error(f"Cannot download playlist '{playlist_title}': Missing ID.")
            return

        if track_ids == [] or track_ids is None: # Full playlist download
            logger.info(f"MainWindow initiating download for full playlist: {playlist_title} (ID: {playlist_id})")
            logger.debug(f"[MainWindow] Calling download_manager.download_playlist with playlist_id={playlist_id}, playlist_title='{playlist_title}', track_ids=[]")
            asyncio.create_task(self.download_manager.download_playlist(playlist_id=playlist_id, playlist_title=playlist_title, track_ids=[])) # MODIFIED: Added asyncio.create_task
            # self.statusBar().showMessage(f"Downloading full playlist {playlist_title}...", 3000)
        elif track_ids: # Non-empty list of specific track IDs
            logger.info(f"MainWindow initiating download for {len(track_ids)} specific tracks from playlist: {playlist_title} (ID: {playlist_id}).")
            asyncio.create_task(self.download_manager.download_playlist(playlist_id=playlist_id, playlist_title=playlist_title, track_ids=track_ids)) # MODIFIED: Added asyncio.create_task
            # self.statusBar().showMessage(f"Downloading {len(track_ids)} tracks from {playlist_title}...", 3000)
        else:
            logger.warning(f"Playlist download request for {playlist_title} (ID: {playlist_id}) has unexpected track_ids: {track_ids}. No action taken.")

    # Dummy methods for player controls (as player bar is removed)
    def update_playback_slider(self, position: int): pass
    def update_total_time_label(self, duration: int): pass
    def update_play_pause_button_icon(self, state: str): pass
    def update_now_playing_info(self, track_info: dict): pass

    def toggle_theme_handler(self, is_on: bool): # Renamed from _toggle_theme_button_clicked
        """Handles the theme toggle switch action."""
        new_theme = 'dark' if is_on else 'light'
        logger.info(f"Theme toggle switched. New state: {'Dark' if is_on else 'Light'}")
        
        if self.config.get_setting('appearance.theme') != new_theme:
            self.config.set_setting('appearance.theme', new_theme)
            self.config.save_config() # Save the new theme preference
            self.load_stylesheet() # Reload QSS for the new theme
            
            # Update icons based on the new theme
            # self.theme_manager.apply_theme_to_icons(self) # REMOVED

            # Emit signal that theme has changed, if other components need to react
            self.theme_manager.theme_changed.emit(new_theme)
        else:
            logger.debug(f"Theme is already {new_theme}.")

    def show_playlist_detail(self, playlist_id):
        """Show playlist details for the given playlist ID."""
        import traceback
        logger.info(f"MainWindow: show_playlist_detail called with ID: {playlist_id}")
        logger.debug(f"Call stack:\n{''.join(traceback.format_stack())}")
        
        if not playlist_id:
            logger.error("MainWindow: Cannot show playlist detail, playlist_id is None or 0.")
            return

        logger.info(f"Attempting to show playlist detail for ID: {playlist_id}")
        
        # Make sure playlist detail page has API
        if not self.playlist_detail_page.deezer_api and self.deezer_api:
            self.playlist_detail_page.deezer_api = self.deezer_api

        # IMMEDIATE NAVIGATION: Switch to playlist detail page first for responsive UI
        self._switch_to_view(self.content_stack.indexOf(self.playlist_detail_page))
        
        # Show loading state immediately
        self.playlist_detail_page.set_loading_state()

        # Schedule the async method call after navigation
        if hasattr(self, 'current_playlist_load_task') and self.current_playlist_load_task and not self.current_playlist_load_task.done():
            logger.debug(f"Cancelling previous playlist load task: {self.current_playlist_load_task}")
            self.current_playlist_load_task.cancel()
        
        logger.info(f"Creating task to load playlist data for ID: {playlist_id}")
        self.current_playlist_load_task = asyncio.create_task(
            self.playlist_detail_page.load_playlist_details(playlist_id)
        )

    def show_album_detail(self, album_id: int):
        logger.info(f"Attempting to show album detail for ID: {album_id}")
        target_index = self.content_stack.indexOf(self.album_detail_page)
        if target_index != -1:
            # IMMEDIATE NAVIGATION: Switch to album detail page first for responsive UI
            self._switch_to_view(target_index) # USE HELPER
            
            # Show loading state immediately
            self.album_detail_page.set_loading_state()
            
            # Schedule async loading after navigation
            if self.current_album_load_task and not self.current_album_load_task.done():
                self.current_album_load_task.cancel()
            self.current_album_load_task = asyncio.create_task(
                self.album_detail_page.load_album(album_id)
            )
        else:
            logger.error("AlbumDetailPage not found in content_stack.")
        self._update_back_button_visibility()

    def show_artist_detail(self, artist_id: int):
        """Shows artist details page for the given artist ID."""
        print(f"SHOW_ARTIST_DETAIL CALLED WITH ID: {artist_id}")  # Debug print
        logger.info(f"MainWindow: Showing artist detail for ID: {artist_id}")
        
        if not artist_id:
            logger.error("MainWindow: Cannot show artist detail, artist_id is None or 0.")
            return
        
        # Ensure the artist detail page exists and has the necessary services
        if not self.artist_detail_page:
            logger.error("Artist detail page not initialized")
            return
            
        # Make sure the page has the updated services
        if not self.artist_detail_page.deezer_api and self.deezer_api:
            self.artist_detail_page.deezer_api = self.deezer_api
        if not self.artist_detail_page.download_manager and self.download_manager:
            self.artist_detail_page.download_manager = self.download_manager

        # Signals are already connected in connect_signals() method - no need to connect here

        # IMMEDIATE NAVIGATION: Switch to artist detail page first for responsive UI
        self._switch_to_view(self.content_stack.indexOf(self.artist_detail_page))
        
        # Show loading state immediately
        self.artist_detail_page.set_loading_state()

        # Schedule the async method call after navigation
        if self.current_artist_load_task and not self.current_artist_load_task.done():
            logger.debug(f"Cancelling previous artist load task: {self.current_artist_load_task}")
            self.current_artist_load_task.cancel()
        
        logger.info(f"Creating task to load artist data for ID: {artist_id}")
        self.current_artist_load_task = asyncio.create_task(
            self.artist_detail_page.load_artist_data(artist_id)
        )
        # Add a callback to log task completion/errors for debugging
        self.current_artist_load_task.add_done_callback(self._handle_async_task_completion)

    def _handle_home_page_item_navigation(self, item_data: dict, item_type: str):
        """Handles navigation when an item is selected from the HomePage."""
        item_id = item_data.get('id')
        if item_id is None:
            logger.error(f"MainWindow: Cannot navigate from home, item ID missing. Data: {item_data}")
            return

        logger.info(f"[MainWindow] Handling navigation for {item_type} ID {item_id}")
        if item_type == 'album':
            self.show_album_detail(item_id)
        elif item_type == 'playlist':
            self.show_playlist_detail(item_id)
        elif item_type == 'artist':
            self.show_artist_detail(item_id)
        else:
            logger.warning(f"[MainWindow] Unknown item type for home page navigation: {item_type}")

    def _handle_home_item_download(self, item_data: dict):
        """Handles download requests originating from the HomePage."""
        item_type = item_data.get('type')
        item_id = item_data.get('id')
        item_title = item_data.get('title', item_data.get('name', 'Unknown Item'))

        logger.info(f"[MainWindow] Received download request from HomePage for {item_type} '{item_title}' (ID: {item_id}).")

        if not self.download_manager:
            logger.error("[MainWindow] DownloadManager not available. Cannot process download from HomePage.")
            # self.statusBar().showMessage("Download service not ready. Please try again later.", 5000)
            return

        if not item_id:
            logger.error(f"[MainWindow] Cannot download {item_type} '{item_title}' from HomePage: Missing ID.")
            return

        if item_type == 'track':
            self._handle_track_download_request(item_data)
        elif item_type == 'album':
            self._handle_album_download_request(album_data=item_data, track_ids=[])
        elif item_type == 'playlist':
            self._handle_playlist_download_request(playlist_data=item_data, track_ids=[])
        elif item_type == 'artist':
            logger.info(f"[MainWindow] Downloading all content for artist '{item_title}' (ID: {item_id}) from HomePage. This will include albums, singles, and EPs.")
            asyncio.create_task(self._download_artist_content(artist_id=item_id, artist_name=item_title))
        else:
            logger.warning(f"[MainWindow] Download not implemented for item type '{item_type}' from HomePage.")

    def _handle_async_task_completion(self, task: asyncio.Task):
        """Generic handler for async task completion to log exceptions."""
        try:
            task.result() # Raise exceptions if any occurred in the task
            logger.debug(f"Async task {task.get_name()} completed successfully.")
        except asyncio.CancelledError:
            logger.info(f"Async task {task.get_name()} was cancelled.")
        except Exception as e:
            logger.error(f"Async task {task.get_name()} failed: {e}", exc_info=True)
            # Optionally show an error message to the user via QMessageBox
            # QMessageBox.critical(self, "Error", f"Failed to load content: {e}")

    def display_view_all_results_from_home(self, results: list, category_title: str):
        """Called from HomePage when a 'View All' button is clicked."""
        logger.info(f"MainWindow: Displaying 'View All' for '{category_title}' from HomePage.")
        
        if not hasattr(self, 'search_widget_page') or self.search_widget_page is None:
            logger.error("Search widget not available to display 'View All' results.")
            return

        target_index = self.content_stack.indexOf(self.search_widget_page)
        if target_index != -1:
            self._switch_to_view(target_index) # USE HELPER
            # Now call the method on search_widget_page to display these specific results
            # This method needs to exist on SearchWidget
            self.search_widget_page.display_view_all_category(results, category_title)
        else:
            logger.error("Search widget not found in content stack for 'View All' display.")
        self._update_back_button_visibility()

    def _handle_header_search(self):
        query = self.search_bar.text().strip()
        if not query:
            # Optionally, switch back to home or do nothing if search is cleared
            # For now, just log and return
            logger.info("Header search is empty, no action taken.")
            return

        logger.info(f"Header search initiated for: '{query}'")
        if self.search_widget_page:
            logger.info(f"[MainWindow] self.search_widget_page is type: {type(self.search_widget_page)}") # ADDED
            logger.info(f"[MainWindow] hasattr set_search_query_and_search: {hasattr(self.search_widget_page, 'set_search_query_and_search')}") # ADDED
            
            if self.content_stack.currentWidget() != self.search_widget_page:
                search_page_index = -1
                for i in range(self.content_stack.count()):
                    if self.content_stack.widget(i) == self.search_widget_page: # Comparison by object identity
                        search_page_index = i
                        break
                
                if search_page_index != -1:
                    self._switch_to_view(search_page_index) 
                else:
                    logger.error("[MainWindow] Search page not found in content stack!") # MODIFIED
                    return
            
            logger.info("[MainWindow] Calling self.search_widget_page.set_search_query_and_search(query)") # ADDED
            self.search_widget_page.set_search_query_and_search(query)
            logger.info("[MainWindow] Called self.search_widget_page.set_search_query_and_search(query)") # ADDED
        else:
            logger.error("[MainWindow] Search widget page is not initialized.") # MODIFIED



    def _switch_to_view(self, target_index: int, is_back_navigation: bool = False):
        """Switches the view in the content_stack and manages history."""
        if target_index < 0 or target_index >= self.content_stack.count():
            logger.warning(f"_switch_to_view: Invalid target_index {target_index}")
            return

        current_index = self.content_stack.currentIndex()

        if current_index == target_index:
            logger.debug(f"_switch_to_view: Already on target_index {target_index}")
            self._update_back_button_visibility() # Still update, as context might change history visibility
            return

        if not is_back_navigation:
            if current_index != -1: # Don't add initial invalid index
                # Avoid adding duplicates if rapidly clicking same nav item that leads to same view
                if not self.view_history or self.view_history[-1] != current_index:
                    self.view_history.append(current_index)
                logger.debug(f"Added {current_index} to view history. History: {self.view_history}")
        
        self.content_stack.setCurrentIndex(target_index)
        logger.debug(f"Switched view to index {target_index}. Current history: {self.view_history}")
        self._update_back_button_visibility()

    def _handle_back_navigation(self):
        """Handles the back button press from SearchWidget."""
        logger.debug(f"_handle_back_navigation called. History: {self.view_history}")
        if self.view_history:
            previous_index = self.view_history.pop()
            logger.debug(f"Popped {previous_index} from history. New history: {self.view_history}")
            self._switch_to_view(previous_index, is_back_navigation=True)
        else:
            logger.debug("View history is empty, cannot go back.")
        # Visibility update is handled by _switch_to_view

    def _update_back_button_visibility(self):
        """Updates the visibility of the SearchWidget's back button."""
        if hasattr(self, 'search_widget_page') and self.search_widget_page:
            # Show back button if there's history AND (the search widget is active OR a detail page is active)
            # This logic implies the back button is global, managed by MainWindow, shown on SearchWidget
            current_widget = self.content_stack.currentWidget()
            is_search_active = (current_widget == self.search_widget_page)
            # Add other pages where the global back button (located in search header) should be active
            is_detail_page_active = (
                current_widget == self.playlist_detail_page or 
                current_widget == self.album_detail_page or 
                current_widget == self.artist_detail_page
            )
            
            # The back button is physically on SearchWidget, but its logic is global.
            # For now, let's only show it if SearchWidget itself is active AND there's history.
            # If we want it visible when SearchWidget is *not* active, the button needs to move out of SearchWidget.
            # Based on user request: "move the filters (All, Tracks,...) across to the right so we can fit a back button in" (on search widget)
            # So, it should be visible when search_widget is the current view and there's history.
            visible = bool(self.view_history and is_search_active)
            self.search_widget_page.set_back_button_visibility(visible)
            logger.debug(f"Back button visibility set to: {visible} (History: {bool(self.view_history)}, SearchActive: {is_search_active})")
        else:
            logger.debug("_update_back_button_visibility: Search widget not available.")
        
    def closeEvent(self, event):
        """Handle the main window close event."""
        logger.info("MainWindow close event triggered.")
        
        # Save download queue state before shutdown
        if hasattr(self, 'download_queue_widget') and self.download_queue_widget:
            try:
                self.download_queue_widget.save_queue_state()
                logger.info("Download queue state saved successfully.")
            except Exception as e:
                logger.error(f"Failed to save download queue state: {e}")
        
        # Perform cleanup tasks
        if self.download_manager:
            logger.info("Shutting down DownloadManager...")
            self.download_manager.shutdown() # Gracefully stop all downloads
            logger.info("DownloadManager shutdown complete.")
        else:
            logger.warning("DownloadManager not initialized, skipping shutdown.")

        # Save any settings or state if necessary
        # Example: self.config.save_settings()
        
        # Properly close any open dialogs or child windows if they don't close automatically

        # Cancel all artwork loading to prevent blocking shutdown
        from src.ui.search_widget import SearchResultCard
        SearchResultCard.cancel_all_artwork_loading()

        logger.info("Proceeding with application exit.")
        super().closeEvent(event) # Proceed with closing
        
    async def _download_artist_content(self, artist_id, artist_name):
        """Download all albums, singles, and EPs for an artist."""
        try:
            logger.info(f"[MainWindow] Starting download of all content for artist '{artist_name}' (ID: {artist_id})")
            
            # Fetch all albums for the artist (this includes albums, singles, and EPs)
            albums = await self.deezer_api.get_artist_albums_generic(artist_id, limit=500)
            
            if not albums:
                logger.warning(f"[MainWindow] No albums found for artist '{artist_name}' (ID: {artist_id})")
                return
            
            logger.info(f"[MainWindow] Found {len(albums)} releases for artist '{artist_name}'. Starting downloads...")
            
            # Download each album
            for album in albums:
                album_id = album.get('id')
                album_title = album.get('title', 'Unknown Album')
                album_type = album.get('record_type', 'album')  # Can be 'album', 'single', 'ep'
                
                if album_id:
                    logger.info(f"[MainWindow] Downloading {album_type}: '{album_title}' (ID: {album_id}) by {artist_name}")
                    # Use the existing download_album method which will fetch tracks automatically
                    asyncio.create_task(self.download_manager.download_album(album_id=album_id, track_ids=[]))
                else:
                    logger.warning(f"[MainWindow] Skipping album '{album_title}' - missing ID")
            
            logger.info(f"[MainWindow] Initiated downloads for all {len(albums)} releases by artist '{artist_name}'")
            
        except Exception as e:
            logger.error(f"[MainWindow] Error downloading artist content for '{artist_name}' (ID: {artist_id}): {e}", exc_info=True)
        
    def _debug_show_playlist_detail(self, playlist_id: int):
        """Debug method to show playlist detail."""
        logger.info(f"Debug method called with playlist_id: {playlist_id}")
        self.show_playlist_detail(playlist_id)
        