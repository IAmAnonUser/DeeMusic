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
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTimer
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
# Legacy download queue widget moved to backup
# from .download_queue_widget import DownloadQueueWidget
from .components.new_queue_widget import NewQueueWidget # NEW: Import new queue widget
from .library_scanner_widget_minimal import LibraryScannerWidget # ADDED: Import LibraryScannerWidget
from src.config_manager import ConfigManager
from src.services.deezer_api import DeezerAPI
from src.services.download_service import DownloadService
# Legacy import moved to backup - using new system only
# from src.services.download_manager import DownloadManager
from src.services.music_player import MusicPlayer, DummyMusicPlayer
# Legacy queue manager moved to backup
# from src.services.queue_manager import QueueManager, Track
import logging
import os
import asyncio 

logger = logging.getLogger(__name__)

# Add this helper function near the top of the file (after imports)
def trackinfo_to_dict(track):
    return {
        "file_path": getattr(track, "file_path", ""),
        "title": getattr(track, "title", ""),
        "artist": getattr(track, "artist", ""),
        "album": getattr(track, "album", ""),
        "album_artist": getattr(track, "album_artist", ""),
        "track_number": getattr(track, "track_number", 0),
        "disc_number": getattr(track, "disc_number", 1),
        "year": getattr(track, "year", 0),
        "duration": getattr(track, "duration", 0),
        "genre": getattr(track, "genre", ""),
        "file_size": getattr(track, "file_size", 0),
        "file_format": getattr(track, "file_format", ""),
        "bitrate": getattr(track, "bitrate", 0),
        "sample_rate": getattr(track, "sample_rate", 0)
    }

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
        
        # Initialize performance monitoring (disabled for stability)
        self.performance_monitor = None 
        
        # Initialize managers to None initially
        self.deezer_api = None
        self.download_service = None  # New download service
        # Initialize player and queue manager
        self.music_player = DummyMusicPlayer() # MODIFIED
        # Legacy queue manager removed - using new download service queue management
        
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

    def showEvent(self, event):
        """Called when the window is shown. Initialize services here."""
        super().showEvent(event)
        if not hasattr(self, '_services_initialized') or not self._services_initialized:
            self._services_initialized = True
            logger.info("[ShowEvent] Scheduling service initialization...")
            # Schedule the async initialization using QTimer
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(100, lambda: asyncio.create_task(self.initialize_services()))
        else:
            logger.info("[ShowEvent] Services already initialized, skipping")


    
    def _check_and_migrate_queue_data(self):
        """Check if queue data migration is needed and perform it."""
        try:
            from pathlib import Path
            import sys
            
            # Add tools to path for migration script
            tools_path = Path(__file__).parent.parent.parent / "tools"
            if str(tools_path) not in sys.path:
                sys.path.insert(0, str(tools_path))
            
            from migrate_queue_data import QueueMigrator
            
            # Get app data directory
            app_data_dir = Path(self.config.config_dir)
            old_queue_file = app_data_dir / "download_queue_state.json"
            new_queue_file = app_data_dir / "new_queue_state.json"
            
            # Check if migration is needed
            if old_queue_file.exists() and not new_queue_file.exists():
                logger.info("[Migration] Old queue data found, performing migration...")
                
                migrator = QueueMigrator(app_data_dir)
                success = migrator.migrate()
                
                if success and migrator.verify_migration():
                    logger.info("[Migration] Queue data migration completed successfully")
                else:
                    logger.error("[Migration] Queue data migration failed")
            else:
                logger.info("[Migration] No migration needed")
                
        except Exception as e:
            logger.error(f"[Migration] Error during queue data migration: {e}")
    
    def _setup_queue_widget(self):
        """Set up the proper queue widget after services are initialized."""
        try:
            # Check feature flag
            use_new_queue_system = self.config.get_setting('experimental.new_queue_system', False)  # Default to False for safety
            
            logger.info(f"[Queue Widget Setup] Feature flag 'experimental.new_queue_system': {use_new_queue_system}")
            logger.info(f"[Queue Widget Setup] Has download_service: {hasattr(self, 'download_service')}")
            logger.info(f"[Queue Widget Setup] Download service exists: {self.download_service is not None if hasattr(self, 'download_service') else 'N/A'}")
            
            if use_new_queue_system and hasattr(self, 'download_service') and self.download_service:
                logger.info("[Queue Widget Setup] Creating new queue widget")
                
                # Find the splitter first
                splitter = None
                for i in range(self.main_layout.count()):
                    item = self.main_layout.itemAt(i)
                    if hasattr(item, 'widget') and item.widget():
                        widget = item.widget()
                        if hasattr(widget, 'addWidget') and hasattr(widget, 'count'):
                            splitter = widget
                            break
                
                if splitter and hasattr(self, 'download_queue_widget') and self.download_queue_widget:
                    # Remove old widget from splitter (not layout)
                    old_widget = self.download_queue_widget
                    old_widget.setParent(None)  # Remove from splitter
                    old_widget.deleteLater()
                    
                    # Create new queue widget
                    self.download_queue_widget = NewQueueWidget(self.download_service, parent=self)
                    self.download_queue_widget.setMinimumWidth(450)
                    self.download_queue_widget.setMaximumWidth(600)
                    
                    # Set size policy to expand vertically
                    self.download_queue_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
                    
                    # Add new widget to splitter
                    splitter.addWidget(self.download_queue_widget)
                    
                    # Reset splitter proportions
                    splitter.setSizes([800, 500])
                    splitter.setStretchFactor(0, 1)  # Content stretches
                    splitter.setStretchFactor(1, 0)  # Queue doesn't stretch
                    
                    logger.info("[Queue Widget Setup] Successfully replaced queue widget in splitter")
                else:
                    logger.error("[Queue Widget Setup] Could not find splitter or old widget to replace")
                
                logger.info("[Queue Widget Setup] New queue widget created and added to layout")
            else:
                logger.info("[Queue Widget Setup] Using legacy queue widget (feature flag disabled or service unavailable)")
                
        except Exception as e:
            logger.error(f"[Queue Widget Setup] Error setting up queue widget: {e}")
    
    async def initialize_services(self):
        """Initialize asynchronous services like DeezerAPI."""
        # Guard against multiple initializations
        if hasattr(self, '_initialization_in_progress') and self._initialization_in_progress:
            logger.warning("[Initialize Services] Initialization already in progress, skipping")
            return
        
        if hasattr(self, '_services_fully_initialized') and self._services_fully_initialized:
            logger.warning("[Initialize Services] Services already fully initialized, skipping")
            return
        
        self._initialization_in_progress = True
        logger.info("[Initialize Services] Starting...")
        
        try:
            # Deezer API init
            logger.info("[Initialize Services] Initializing DeezerAPI...")
            self.deezer_api = DeezerAPI(self.config, loop=asyncio.get_running_loop())
            
            # No need to reset CSRF state with simplified approach
            logger.info("[Initialize Services] DeezerAPI initialized with simplified CSRF handling")
            
            # Test ARL token validity
            if self.deezer_api.test_arl_validity():
                logger.info("[Initialize Services] ARL token validation successful")
            else:
                logger.error("[Initialize Services] ARL token validation failed - token may be expired or invalid")
            
            # Test token refresh functionality
            if self.deezer_api.force_token_refresh_test():
                logger.info("[Initialize Services] Token refresh test successful")
            else:
                logger.error("[Initialize Services] Token refresh test failed")
            
            # Set up periodic token refresh to prevent CSRF errors
            self._setup_periodic_token_refresh()
            
            initialized = await self.deezer_api.initialize()
            if not initialized:
                logger.error("[Initialize Services] Failed to initialize DeezerAPI.")
            else:
                logger.info("[Initialize Services] DeezerAPI initialized successfully.")
            
            # Check ARL token status and authenticate if available
            arl_token = self.config.get_setting('deezer.arl', '')
            if not arl_token:
                logger.warning("[Initialize Services] No ARL token configured - home page content will not load")
                logger.warning("[Initialize Services] Please configure your ARL token in Settings > Account")
            else:
                logger.info(f"[Initialize Services] ARL token configured (length: {len(arl_token)})")
                # Set ARL token but defer authentication to avoid blocking startup
                self.deezer_api.arl = arl_token
                self.config.set_setting('deezer.arl', arl_token)

                logger.info("[Initialize Services] ARL token set, authentication will happen on demand")
            
            # Check feature flag to determine which system to use
            use_new_queue_system = self.config.get_setting('experimental.new_queue_system', False)
            logger.info(f"[Initialize Services] Feature flag 'experimental.new_queue_system': {use_new_queue_system}")
            
            # Check if migration is needed
            self._check_and_migrate_queue_data()
            
            if use_new_queue_system:
                # Initialize new download service
                logger.info("[Initialize Services] Initializing new DownloadService...")
                try:
                    self.download_service = DownloadService(self.config, self.deezer_api)
                    self.download_service.start()
                    logger.info("[Initialize Services] New DownloadService initialized and started.")
                except Exception as e:
                    logger.error(f"[Initialize Services] Failed to initialize new DownloadService: {e}")
                    logger.info("[Initialize Services] Falling back to legacy DownloadManager...")
                    use_new_queue_system = False
            
            # Now that services are initialized, create the proper queue widget
            logger.info("[Initialize Services] About to setup queue widget...")
            self._setup_queue_widget()
            logger.info("[Initialize Services] Queue widget setup completed")
            
            # Pass initialized managers to the page instances
            if self.home_page:
                self.home_page.deezer_api = self.deezer_api
                logger.info("[Initialize Services] Updated HomePage with DeezerAPI.")
            
            if self.search_widget_page:
                self.search_widget_page.deezer_api = self.deezer_api
                self.search_widget_page.download_service = self.download_service
                logger.info("[Initialize Services] Updated SearchWidget with DeezerAPI and DownloadService.")
            
            if self.playlist_detail_page:
                self.playlist_detail_page.deezer_api = self.deezer_api
                logger.info("[Initialize Services] Updated PlaylistDetailPage with DeezerAPI.")
            
            if self.album_detail_page:
                self.album_detail_page.deezer_api = self.deezer_api
                logger.info("[Initialize Services] Updated AlbumDetailPage with DeezerAPI.")
            
            if self.artist_detail_page:
                self.artist_detail_page.deezer_api = self.deezer_api
                logger.info("[Initialize Services] Updated ArtistDetailPage with DeezerAPI.")
            
            if hasattr(self, 'download_queue_widget') and self.download_queue_widget:
                if isinstance(self.download_queue_widget, NewQueueWidget):
                    logger.info("[Initialize Services] New queue widget already initialized with DownloadService")
                logger.info("[Initialize Services] Queue loading deferred for better startup performance.")
            else:
                logger.warning("[Initialize Services] DownloadQueueWidget not found to set DownloadManager.")
            
            logger.info("[Initialize Services] Setting up content area...")
            
            # Performance monitor disabled for stability
            self._connect_performance_monitor()
            
            # Initialize Library Scanner
            if hasattr(self, 'library_scanner_widget') and self.library_scanner_widget:
                logger.info("[Initialize Services] Library Scanner initialized and ready.")
            else:
                logger.warning("[Initialize Services] Library Scanner not available.")
            
            # Queue processing will be started manually when needed
            logger.info("[Initialize Services] Queue processing ready (will start on demand)")
            
            logger.info("[Initialize Services] Content area set up and API passed to pages.")
            
            # Critical debug info
            try:
                logger.critical(f"[Initialize Services] CRITICAL DEBUG: home_page={self.home_page is not None}, deezer_api={self.deezer_api is not None}")
                if self.home_page:
                    logger.critical(f"[Initialize Services] HomePage exists, deezer_api on home_page: {hasattr(self.home_page, 'deezer_api') and self.home_page.deezer_api is not None}")
                if self.deezer_api:
                    logger.critical(f"[Initialize Services] DeezerAPI exists, initialized: {getattr(self.deezer_api, 'initialized', False)}")
            except Exception as e:
                logger.error(f"[Initialize Services] Error in debug logging: {e}", exc_info=True)
            
            # Trigger home page content loading
            if self.home_page and self.deezer_api:
                logger.info("[Initialize Services] Triggering HomePage content loading...")
                # Create a task and store reference to prevent garbage collection
                self._home_content_task = asyncio.create_task(self.home_page.load_content())
                
                # Add a callback to log completion
                def content_loaded(task):
                    try:
                        task.result()
                        logger.info("[Initialize Services] HomePage content loading completed successfully")
                    except Exception as e:
                        logger.error(f"[Initialize Services] Error loading HomePage content: {e}", exc_info=True)
                
                self._home_content_task.add_done_callback(content_loaded)
            else:
                logger.warning(f"[Initialize Services] HomePage or DeezerAPI not available for content load. home_page={self.home_page is not None}, deezer_api={self.deezer_api is not None}")
            

            
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
                    self.home_page.home_item_download_requested.connect(self._handle_home_item_download)
                    self.home_page.content_loaded.connect(self.load_queue_state_deferred)
                    self.home_page._signals_connected_mw = True
                    logger.info("[Initialize Services] Connected HomePage navigation and download signals.")
                else:
                    logger.info("[Initialize Services] HomePage signals already connected.")
                    print(f"[PRINT DEBUG] MainWindow: HomePage signals already connected (skipping)")
            else:
                logger.warning("[Initialize Services] HomePage not available to connect signals.")
                logger.info("[Initialize Services] Signals connected via connect_signals method call next...")
                self.connect_signals()
                logger.info("[Initialize Services] Finished full initialization and signal setup.")
            
            # Mark initialization as complete
            self._services_fully_initialized = True
        except Exception as e:
            logger.error(f"[Initialize Services] Error during initialization: {e}")
            raise
        finally:
            self._initialization_in_progress = False

    def _connect_performance_monitor(self):
        """Connect performance monitor to download service in a deferred manner."""
        try:
            # Legacy performance monitor connection removed - new system handles optimization internally
            pass
        except Exception as e:
            logger.error(f"[Initialize Services] Error connecting performance monitor: {e}")

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

        # DownloadQueueWidget Signals - using new download service
        if self.download_queue_widget:
            # Legacy download manager connections removed - new system handles this automatically
            pass
        
        # MusicPlayer and QueueManager signals (if UI needs to react to player state)
        # if self.music_player and not isinstance(self.music_player, DummyMusicPlayer): 
        #     self.music_player.position_changed.connect(self.update_playback_slider)
        #     self.music_player.duration_changed.connect(self.update_total_time_label)
        #     self.music_player.state_changed.connect(self.update_play_pause_button_icon)
        # if self.queue_manager and not isinstance(self.queue_manager, DummyQueueManager):
        #     self.queue_manager.current_track_changed.connect(self.update_now_playing_info)

        logger.info("MainWindow: Signals connected.")

    def _handle_auto_restart_notification(self, reason: str):
        """Handle automatic restart notification from download manager."""
        try:
            logger.info(f"[AUTO_RESTART_UI] Received auto restart notification: {reason}")
            
            # Show a brief status message
            if hasattr(self, 'statusBar'):
                self.statusBar().showMessage(f"Auto-restarted stalled downloads: {reason}", 5000)
            
            # You could also show a more prominent notification here if desired
            # For now, just log it and show in status bar
            
        except Exception as e:
            logger.error(f"[AUTO_RESTART_UI] Error handling auto restart notification: {e}")

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
        self.search_widget_page = SearchWidget(deezer_api=None, download_service=None, config_manager=self.config, parent=self)
        
        # Detail Pages (API and DM passed later or on creation if safe)
        self.playlist_detail_page = PlaylistDetailPage(deezer_api=None, download_manager=None, parent=self)
        self.album_detail_page = AlbumDetailPage(deezer_api=None, download_manager=None, parent=self)
        self.artist_detail_page = ArtistDetailPage(deezer_api=None, download_manager=None, parent=self)
        
        # Library Scanner Widget
        self.library_scanner_widget = LibraryScannerWidget(config_manager=self.config, parent=self)
        
        self.content_stack.addWidget(self.home_page)            # Index 0
        self.content_stack.addWidget(self.search_widget_page)   # Index 1
        self.content_stack.addWidget(self.playlist_detail_page) # Index 2
        self.content_stack.addWidget(self.album_detail_page)    # Index 3
        self.content_stack.addWidget(self.artist_detail_page)   # Index 4
        self.content_stack.addWidget(self.library_scanner_widget) # Index 5

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
    
    def show_library_scanner(self):
        """Show the Library Scanner widget."""
        logger.info("Showing Library Scanner")
        if self.library_scanner_widget:
            self.content_stack.setCurrentWidget(self.library_scanner_widget)
            self.setWindowTitle("DeeMusic - Library Scanner")
        else:
            logger.error("Library Scanner widget not initialized")
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", "Library Scanner could not be loaded.")

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
            # Legacy download manager refresh removed - new system handles config changes automatically
            pass

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

        # Add small spacing between logo and search bar
        top_bar_layout.addSpacing(15) # Reduced spacing to keep search bar close to logo

        # Search Bar (positioned right next to DEEMUSIC logo)
        self.search_bar = QLineEdit()
        self.search_bar.setObjectName("searchBar") # For QSS styling
        self.search_bar.setPlaceholderText("Artists, Albums, Tracks, Playlists, Spotify Playlist URL...")
        self.search_bar.returnPressed.connect(self._handle_header_search)
        self.search_bar.setMinimumWidth(350) # Set appropriate width for left position
        self.search_bar.setMaximumWidth(450) # Reduced max width since it's on the left
        self.search_bar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        top_bar_layout.addWidget(self.search_bar)
        
        # Add expanding spacer to push Library Scanner and controls to the right
        top_bar_layout.addStretch(1)

        # Library Scanner Button (NEW)
        self.library_scanner_btn = QPushButton("📚 Library Scanner")
        self.library_scanner_btn.setObjectName("LibraryScannerButton")
        self.library_scanner_btn.setToolTip("Open Library Scanner to find missing albums")
        self.library_scanner_btn.clicked.connect(self.show_library_scanner)
        self.library_scanner_btn.setStyleSheet("""
            QPushButton#LibraryScannerButton {
                background-color: #6C2BD9;
                color: #FFFFFF;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
                font-size: 14px;
                margin-left: 10px;
            }
            QPushButton#LibraryScannerButton:hover {
                background-color: #7C3BE9;
            }
            QPushButton#LibraryScannerButton:pressed {
                background-color: #5C1BC9;
            }
        """)
        top_bar_layout.addWidget(self.library_scanner_btn)

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

        # --- Download Queue (Now a separate widget, not part of player bar) ---
        # Create placeholder - will be replaced after services are initialized
        logger.info("[UI Setup] Creating placeholder queue widget (will be replaced after service initialization)")
        # Create placeholder widget - will be replaced with proper queue widget after service initialization
        self.download_queue_widget = QWidget(parent=self)
        placeholder_layout = QVBoxLayout(self.download_queue_widget)
        placeholder_layout.addWidget(QLabel("Download queue loading..."))
        self.download_queue_widget.setMinimumWidth(450)
        self.download_queue_widget.setMaximumWidth(600)
        
        self.download_queue_widget.setMinimumWidth(450) # Increased to accommodate X buttons
        self.download_queue_widget.setMaximumWidth(600) # Increased to give more space

        # Create horizontal splitter for content and queue (full height)
        from PyQt6.QtWidgets import QSplitter
        content_and_queue_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Add content stack to splitter
        content_and_queue_splitter.addWidget(self.content_stack)
        
        # Set size policy for download queue widget to expand vertically
        self.download_queue_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        content_and_queue_splitter.addWidget(self.download_queue_widget)
        
        # Set splitter proportions (content takes most space, queue takes fixed width)
        content_and_queue_splitter.setSizes([800, 500])  # Approximate proportions
        content_and_queue_splitter.setStretchFactor(0, 1)  # Content stretches
        content_and_queue_splitter.setStretchFactor(1, 0)  # Queue doesn't stretch
        
        self.main_layout.addWidget(content_and_queue_splitter, 1) # This splitter now holds content and queue

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
        
        # Legacy download monitor widget removed with legacy system
        # Monitor functionality is now integrated into the new download service
        
        self.status_update.emit("Welcome to DeeMusic!")

        logger.info("UI setup complete.")
        # No need for update_active_nav_item without the sidebar

    def _handle_track_download_request(self, track_data: dict):
        """Handles a request to download a single track."""
        # Try new system first, fallback to legacy
        if hasattr(self, 'download_service') and self.download_service:
            logger.info("Using new DownloadService for track download")
            try:
                track_id = track_data.get('id')
                if track_id:
                    self.download_service.download_track(track_id)
                    return
            except Exception as e:
                logger.error(f"New DownloadService failed for track download: {e}")
                logger.info("Falling back to legacy system...")
        
        # Legacy system removed - only new service available
        logger.error("Track download fallback to legacy system not available - legacy system removed.")
        return

    def _handle_album_download_request(self, album_data: dict, track_ids: list[int] | None = None):
        """
        Handles a request to download tracks from an album.
        If track_ids is an empty list [], it signifies a request to download the full album by its ID.
        If track_ids is a non-empty list, it downloads specified tracks from the album.
        If track_ids is None, it also downloads the full album.
        """
        # Try new system first, fallback to legacy
        if hasattr(self, 'download_service') and self.download_service:
            logger.info("Using new DownloadService for album download")
            try:
                album_id = album_data.get('id')
                if album_id:
                    self.download_service.download_album(album_id)
                    return
            except Exception as e:
                logger.error(f"New DownloadService failed for album download: {e}")
                logger.info("Falling back to legacy system...")
        
        # Legacy system removed - only new service available
        logger.error("Album download fallback to legacy system not available - legacy system removed.")
        return

    def _handle_playlist_download_request(self, playlist_data: dict, track_ids: list[int] | None = None):
        """
        Handles a request to download tracks from a playlist.
        If track_ids is an empty list [], it signifies a request to download the full playlist by its ID.
        If track_ids is a non-empty list, it downloads specified tracks from the playlist.
        If track_ids is None, it also downloads the full playlist.
        """
        if not playlist_data:
            logger.error("[MainWindow] No playlist data provided for download")
            return
            
        playlist_title = playlist_data.get('title', 'Unknown Playlist')
        playlist_id = playlist_data.get('id')
        
        logger.info(f"[MainWindow] Received download request for playlist '{playlist_title}' (ID: {playlist_id}).")
        
        # Use new DownloadService for playlist downloads
        if hasattr(self, 'download_service') and self.download_service:
            logger.info("Using new DownloadService for playlist download")
            # Use async method for playlist downloads to properly fetch tracks
            import asyncio
            asyncio.create_task(self._async_add_playlist_to_queue(playlist_data))
        else:
            logger.error("[MainWindow] DownloadService not available for playlist download")
            return
    
    async def _async_add_playlist_to_queue(self, playlist_data: dict):
        """Async helper to add playlist to queue with proper track fetching."""
        try:
            playlist_id = playlist_data.get('id')
            playlist_title = playlist_data.get('title', 'Unknown Playlist')
            
            if playlist_id and self.deezer_api:
                logger.info(f"[MainWindow] Fetching tracks for playlist {playlist_id}")
                # Fetch full playlist data with tracks
                full_tracks = await self.deezer_api.get_playlist_tracks(playlist_id)
                
                if full_tracks:
                    # Update playlist data with tracks
                    playlist_data['tracks'] = {'data': full_tracks}
                    logger.info(f"[MainWindow] Fetched {len(full_tracks)} tracks for playlist '{playlist_title}'")
                else:
                    logger.warning(f"[MainWindow] Could not fetch tracks for playlist {playlist_id}")
                    return
            
            # Now add to download service with full track data
            self.download_service.add_playlist(playlist_data)
            logger.info(f"[MainWindow] Successfully added playlist '{playlist_title}' to download queue")
            
        except Exception as e:
            logger.error(f"[MainWindow] Error adding playlist to download queue: {e}")

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
        # Legacy download_manager reference removed - using new download service

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

        # Check for new download service
        if not (hasattr(self, 'download_service') and self.download_service):
            logger.error("[MainWindow] DownloadService not available. Cannot process download from HomePage.")
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
        current_widget = self.content_stack.currentWidget()
        target_widget = self.content_stack.widget(target_index)
        
        current_page_name = current_widget.__class__.__name__ if current_widget else "Unknown"
        target_page_name = target_widget.__class__.__name__ if target_widget else "Unknown"

        if current_index == target_index:
            logger.debug(f"🔄 SWITCH VIEW: Already on {target_page_name} (index {target_index})")
            self._update_back_button_visibility() # Still update, as context might change history visibility
            return

        logger.info(f"🔄 SWITCH VIEW: {current_page_name} (index {current_index}) → {target_page_name} (index {target_index})")
        logger.info(f"🔄 SWITCH VIEW: is_back_navigation={is_back_navigation}")
        logger.info(f"🔄 SWITCH VIEW: History before: {self.view_history}")

        if not is_back_navigation:
            if current_index != -1: # Don't add initial invalid index
                # Only avoid adding duplicates if we're navigating to the same page we're already on
                # (which shouldn't happen due to the early return above, but just in case)
                # Always add the current page to history when navigating to a different page
                if current_index != target_index:
                    self.view_history.append(current_index)
                    logger.info(f"🔄 SWITCH VIEW: Added {current_index} ({current_page_name}) to history")
                else:
                    logger.info(f"🔄 SWITCH VIEW: Skipped adding {current_index} ({current_page_name}) - same as target")
        else:
            logger.info(f"🔄 SWITCH VIEW: Back navigation - not adding to history")
        
        self.content_stack.setCurrentIndex(target_index)
        logger.info(f"🔄 SWITCH VIEW: Switched to {target_page_name} (index {target_index})")
        logger.info(f"🔄 SWITCH VIEW: History after: {self.view_history}")
        self._update_back_button_visibility()

    def _handle_back_navigation(self):
        """Handles the back button press from SearchWidget."""
        # Prevent rapid back navigation (debounce)
        import time
        current_time = time.time()
        if hasattr(self, '_last_back_navigation_time'):
            if current_time - self._last_back_navigation_time < 0.5:  # 500ms debounce
                logger.info("🔙 BACK NAVIGATION: Ignoring rapid back navigation (debounce)")
                return
        self._last_back_navigation_time = current_time
        
        current_widget = self.content_stack.currentWidget()
        current_index = self.content_stack.currentIndex()
        current_page_name = current_widget.__class__.__name__ if current_widget else "Unknown"
        
        logger.info(f"🔙 BACK NAVIGATION: Current page: {current_page_name} (index {current_index})")
        logger.info(f"🔙 BACK NAVIGATION: History before pop: {self.view_history}")
        
        if self.view_history:
            previous_index = self.view_history.pop()
            previous_widget = self.content_stack.widget(previous_index)
            previous_page_name = previous_widget.__class__.__name__ if previous_widget else "Unknown"
            
            logger.info(f"🔙 BACK NAVIGATION: Going back to: {previous_page_name} (index {previous_index})")
            logger.info(f"🔙 BACK NAVIGATION: History after pop: {self.view_history}")
            
            self._switch_to_view(previous_index, is_back_navigation=True)
        else:
            logger.warning("🔙 BACK NAVIGATION: View history is empty, cannot go back!")
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
    
    def load_queue_state_deferred(self):
        """Load the download queue state after the main UI is ready."""
        def _do_load():
            try:
                if hasattr(self, 'download_queue_widget') and self.download_queue_widget:
                    logger.info("[Deferred Loading] Loading download queue state...")
                    self.download_queue_widget.load_queue_state()
                    logger.info("[Deferred Loading] Download queue state loaded successfully.")
                    
                    # Start deferred queue processing after UI is ready
                    # Legacy deferred queue processing removed - new system handles this automatically
                else:
                    logger.warning("[Deferred Loading] DownloadQueueWidget not available for queue loading.")
            except Exception as e:
                logger.error(f"[Deferred Loading] Failed to load download queue state: {e}")
        
        # Add a small delay to ensure UI is fully rendered
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(500, _do_load)  # 500ms delay
        
    def closeEvent(self, event):
        """Handle the main window close event."""
        logger.info("MainWindow close event triggered.")
        
        # Stop periodic token refresh timer
        if hasattr(self, 'token_refresh_timer'):
            self.token_refresh_timer.stop()
            logger.info("Stopped periodic token refresh timer")
        
        # Save download queue state before shutdown
        # Removed: self.download_queue_widget.save_queue_state()
        # Cleanup monitor widget
        if hasattr(self, 'monitor_widget'):
            self.monitor_widget.cleanup()
        
        # Perform cleanup tasks
        # Cleanup new download service
        if hasattr(self, 'download_service') and self.download_service:
            logger.info("Shutting down new DownloadService...")
            try:
                self.download_service.stop()
                logger.info("DownloadService shutdown complete.")
            except Exception as e:
                logger.error(f"Error during download service shutdown: {e}")
        
        # Force application exit immediately to prevent hanging
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication
        import sys
        import os
        
        def force_exit():
            logger.info("Forcing immediate application exit")
            try:
                QApplication.instance().quit()
            except:
                pass
            # Ultimate fallback - force system exit immediately
            os._exit(0)  # More aggressive than sys.exit()
        
        # Exit immediately - no delay
        force_exit()
        
        # Legacy download manager shutdown removed - new system handles this
        
        # Cleanup new queue widget
        if hasattr(self, 'download_queue_widget') and isinstance(self.download_queue_widget, NewQueueWidget):
            logger.info("Cleaning up new queue widget...")
            self.download_queue_widget.cleanup()

        # Save any settings or state if necessary
        # Example: self.config.save_settings()
        
        # Properly close any open dialogs or child windows if they don't close automatically

        # Cancel all artwork loading to prevent blocking shutdown
        from src.ui.search_widget import SearchResultCard
        SearchResultCard.cancel_all_artwork_loading()

        logger.info("Proceeding with application exit.")
        super().closeEvent(event) # Proceed with closing
    
    def _setup_periodic_token_refresh(self):
        """Set up periodic token refresh to prevent CSRF errors."""
        if not hasattr(self, 'deezer_api') or not self.deezer_api:
            return
            
        # Create a timer to refresh tokens every 90 seconds
        self.token_refresh_timer = QTimer()
        self.token_refresh_timer.timeout.connect(self._periodic_token_refresh)
        self.token_refresh_timer.start(90000)  # 90 seconds
        logger.info("[Token Refresh] Set up periodic token refresh every 90 seconds")
    
    def _periodic_token_refresh(self):
        """Perform periodic token refresh to prevent CSRF errors."""
        try:
            if hasattr(self, 'deezer_api') and self.deezer_api:
                logger.info("[Token Refresh] Performing periodic token refresh...")
                success = self.deezer_api.force_token_refresh_test()
                if success:
                    logger.info("[Token Refresh] Periodic token refresh successful")
                else:
                    logger.warning("[Token Refresh] Periodic token refresh failed")
        except Exception as e:
            logger.error(f"[Token Refresh] Error during periodic refresh: {e}")
        
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
                    # Legacy download_manager removed - would need to use new download service
                    logger.error("Artist download functionality requires new download service integration")
                else:
                    logger.warning(f"[MainWindow] Skipping album '{album_title}' - missing ID")
            
            logger.info(f"[MainWindow] Initiated downloads for all {len(albums)} releases by artist '{artist_name}'")
            
        except Exception as e:
            logger.error(f"[MainWindow] Error downloading artist content for '{artist_name}' (ID: {artist_id}): {e}", exc_info=True)
        
    def _debug_show_playlist_detail(self, playlist_id: int):
        """Debug method to show playlist detail."""
        logger.info(f"Debug method called with playlist_id: {playlist_id}")
        self.show_playlist_detail(playlist_id)
        