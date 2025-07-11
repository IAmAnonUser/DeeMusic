"""
Playlist Detail Page for DeeMusic application.
Displays tracks within a selected playlist.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, 
    QPushButton, QHBoxLayout, 
    QFrame, QStackedLayout, QGridLayout,
    QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QRunnable, QThreadPool, QSize, pyqtSlot, QEvent
from PyQt6.QtGui import QIcon, QPixmap, QImage, QPainter, QColor, QPen 
import logging
import os
import asyncio
import requests

# Import SearchResultCard
from src.ui.search_widget import SearchResultCard
from src.ui.track_list_header_widget import TrackListHeaderWidget
# Import caching utility for main playlist cover
from src.utils.image_cache import get_image_from_cache, save_image_to_cache
from src.utils.icon_utils import get_icon

logger = logging.getLogger(__name__)

# Create a separate thread pool just for artwork
ARTWORK_THREAD_POOL = QThreadPool()
ARTWORK_THREAD_POOL.setMaxThreadCount(3)

class PlaylistDetailPage(QWidget):
    """
    A widget to display the tracks of a selected playlist.
    """
    back_requested = pyqtSignal() 
    track_selected_for_download = pyqtSignal(dict) 
    track_selected_for_playback = pyqtSignal(dict)
    # NEW: Signals for navigation from track artist/album names
    artist_name_clicked_from_track = pyqtSignal(int)  # Emits artist_id when artist name clicked in track
    album_name_clicked_from_track = pyqtSignal(int)   # Emits album_id when album name clicked in track
    main_playlist_cover_loaded = pyqtSignal(QPixmap) 
    _on_main_cover_artwork_error_signal = pyqtSignal(str)
    request_full_playlist_download = pyqtSignal(dict, list)  # NEW: For downloading the full playlist

    def __init__(self, deezer_api, download_manager, parent=None):
        super().__init__(parent)
        self.deezer_api = deezer_api
        self.download_manager = download_manager
        self.current_playlist_id = None
        self.current_playlist_data = None 
        self.main_playlist_cover_loaded.connect(self._set_main_playlist_cover)
        self._on_main_cover_artwork_error_signal.connect(self._on_main_cover_artwork)
        
        # We'll only use the dedicated thread pool for the main cover
        self.thread_pool = ARTWORK_THREAD_POOL
        
        self._setup_ui()

    def _setup_ui(self):
        main_page_layout = QVBoxLayout(self)
        main_page_layout.setContentsMargins(10, 10, 10, 10)
        main_page_layout.setSpacing(0)

        # --- Back Button ---
        back_button_layout = QHBoxLayout()
        back_button_layout.setContentsMargins(0,0,0,10)
        self.back_button = QPushButton()
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'back button.png')
        if os.path.exists(icon_path):
            self.back_button.setIcon(QIcon(icon_path))
            self.back_button.setIconSize(QSize(24, 24))
        else:
            self.back_button.setText("< Back")
            logger.warning(f"Back button icon not found at {icon_path}")
        self.back_button.setObjectName("PageBackButton")
        self.back_button.setFixedSize(QSize(40, 40))
        self.back_button.clicked.connect(self._emit_back_request)
        back_button_layout.addWidget(self.back_button)
        back_button_layout.addStretch(1)
        main_page_layout.addLayout(back_button_layout)

        # --- Header Section (Cover Image, Title, Details) ---
        header_widget = QWidget()
        header_widget.setMinimumHeight(180)
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 0, 10, 10)
        header_layout.setSpacing(20)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        # Playlist Cover Container (similar to album detail page structure)
        self.playlist_cover_container = QWidget()
        self.playlist_cover_container.setFixedSize(160, 160)
        self.playlist_cover_container.setObjectName("playlist_page_image_container")
        
        cover_layout = QGridLayout(self.playlist_cover_container)
        cover_layout.setContentsMargins(0,0,0,0)

        self.playlist_cover_label = QLabel() 
        self.playlist_cover_label.setFixedSize(160, 160)
        self.playlist_cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.playlist_cover_label.setObjectName("playlist_page_image")
        self.playlist_cover_container.installEventFilter(self)  # Event filter for hover detection
        cover_layout.addWidget(self.playlist_cover_label, 0, 0)
        
        header_layout.addWidget(self.playlist_cover_container)

        # Download button (child of playlist_cover_container)
        self.playlist_download_button = QPushButton()
        self.playlist_download_button.setObjectName("PlaylistCoverDownloadButton")
        download_icon = get_icon("download.png")
        if download_icon:
            self.playlist_download_button.setIcon(download_icon)
            self.playlist_download_button.setIconSize(QSize(24, 24))
            self.playlist_download_button.setText("")
        else:
            self.playlist_download_button.setText("DL")
            logger.warning("Playlist download button icon not found.")
        self.playlist_download_button.setFixedSize(QSize(40, 40))
        self.playlist_download_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.playlist_download_button.setToolTip("Download Playlist")
        self.playlist_download_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.playlist_download_button.clicked.connect(self._trigger_full_playlist_download)
        self.playlist_download_button.setVisible(False)
        cover_layout.addWidget(self.playlist_download_button, 0, 0, Qt.AlignmentFlag.AlignCenter)

        # Vertical layout for playlist text details
        playlist_text_details_vbox = QVBoxLayout()
        playlist_text_details_vbox.setContentsMargins(0, 0, 0, 0)
        playlist_text_details_vbox.setSpacing(5)

        self.playlist_type_label = QLabel("PLAYLIST")
        self.playlist_type_label.setObjectName("playlist_page_type_label")
        playlist_text_details_vbox.addWidget(self.playlist_type_label)
        
        self.playlist_title_label = QLabel("Playlist Title") 
        self.playlist_title_label.setObjectName("playlist_page_name_label")
        self.playlist_title_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.playlist_title_label.setWordWrap(True)
        playlist_text_details_vbox.addWidget(self.playlist_title_label)

        self.playlist_creator_label = QLabel("By Creator Name")
        self.playlist_creator_label.setObjectName("playlist_page_subtitle_label")
        self.playlist_creator_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.playlist_creator_label.setWordWrap(True)
        playlist_text_details_vbox.addWidget(self.playlist_creator_label)

        # Optional: Description (can be long, so consider placement/visibility)
        self.playlist_description_label = QLabel("Playlist description...") 
        self.playlist_description_label.setObjectName("playlist_page_description_label")
        self.playlist_description_label.setWordWrap(True)
        self.playlist_description_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.playlist_description_label.setVisible(False)
        playlist_text_details_vbox.addWidget(self.playlist_description_label)

        self.playlist_stats_label = QLabel("Tracks: 0 | Duration: 0m | Fans: 0") 
        self.playlist_stats_label.setObjectName("playlist_page_meta_label")
        playlist_text_details_vbox.addWidget(self.playlist_stats_label)

        playlist_text_details_vbox.addStretch(1)

        header_layout.addLayout(playlist_text_details_vbox, 1)
        main_page_layout.addWidget(header_widget)

        # --- Track List Header ---
        self.track_header = TrackListHeaderWidget(self, show_track_numbers=True)
        main_page_layout.addWidget(self.track_header)

        # --- Track List Area (Using QScrollArea and SearchResultCard) ---
        self.track_list_scroll_area = QScrollArea()
        self.track_list_scroll_area.setWidgetResizable(True)
        self.track_list_scroll_area.setObjectName("playlist_track_list_scroll_area")
        
        self.track_list_content_widget = QWidget()
        self.tracks_layout = QVBoxLayout(self.track_list_content_widget)
        self.tracks_layout.setContentsMargins(0, 5, 0, 5)
        self.tracks_layout.setSpacing(5)
        self.tracks_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.track_list_scroll_area.setWidget(self.track_list_content_widget)
        main_page_layout.addWidget(self.track_list_scroll_area, 1)

        logger.debug("PlaylistDetailPage UI setup complete with new header style.")

    def _emit_back_request(self):
        self.back_requested.emit()

    def set_loading_state(self):
        """Set the page to show a loading state immediately for responsive navigation."""
        self.playlist_title_label.setText("Loading playlist...")
        self.playlist_creator_label.setText("")
        self.playlist_description_label.setText("")
        self.playlist_description_label.setVisible(False)
        self.playlist_stats_label.setText("")
        self._set_placeholder_main_playlist_cover()
        self._clear_track_list()
        self.playlist_download_button.setVisible(False)

    def eventFilter(self, source, event):
        """Handle hover events for playlist cover to show/hide download button."""
        if source is self.playlist_cover_container:
            if event.type() == QEvent.Type.Enter:
                if self.current_playlist_data: 
                    self.playlist_download_button.setVisible(True)
                    self.playlist_download_button.setEnabled(True)
                    self.playlist_download_button.raise_() 
                else:
                    self.playlist_download_button.setVisible(False)
            elif event.type() == QEvent.Type.Leave:
                self.playlist_download_button.setVisible(False)
        return super().eventFilter(source, event)

    @pyqtSlot()
    def _trigger_full_playlist_download(self):
        """Trigger the download of the entire playlist."""
        if not self.current_playlist_data:
            logger.warning("[PlaylistDetail] _trigger_full_playlist_download called but no playlist data available.")
            return
        
        logger.info(f"[PlaylistDetail] Initiating full playlist download for playlist '{self.current_playlist_data.get('title')}'.")
        asyncio.create_task(self._prepare_and_emit_full_playlist_download())

    async def _prepare_and_emit_full_playlist_download(self):
        """Prepare and emit the full playlist download request."""
        if not self.current_playlist_data:
            logger.error("[PlaylistDetail] No playlist data available for download.")
            return

        try:
            # Get all tracks in the playlist
            playlist_id = self.current_playlist_id
            tracks_data = await self.deezer_api.get_playlist_tracks(playlist_id)
            
            if not tracks_data or not tracks_data.get('data'):
                logger.error(f"[PlaylistDetail] No tracks found for playlist {playlist_id}")
                return

            # Extract track IDs
            track_ids = []
            for track in tracks_data['data']:
                if track.get('id'):
                    track_ids.append(track['id'])

            if not track_ids:
                logger.warning(f"[PlaylistDetail] No valid track IDs found in playlist {playlist_id}")
                return

            logger.info(f"[PlaylistDetail] Emitting request_full_playlist_download for playlist '{self.current_playlist_data.get('title')}' with {len(track_ids)} tracks.")
            self.request_full_playlist_download.emit(self.current_playlist_data, track_ids)

        except Exception as e:
            logger.error(f"[PlaylistDetail] Error preparing playlist download: {e}", exc_info=True)

    async def load_playlist_details(self, playlist_id):
        logger.info(f"[PlaylistDetail] Attempting to load playlist with ID: {playlist_id}")
        if not self.deezer_api:
            logger.error("[PlaylistDetail] DeezerAPI not initialized.")
            self.playlist_title_label.setText("Error: API Service unavailable")
            self.playlist_creator_label.setText("")
            self.playlist_description_label.setText("")
            self.playlist_description_label.setVisible(False)
            self.playlist_stats_label.setText("")
            self._clear_track_list()
            return

        if not playlist_id:
            logger.error("[PlaylistDetail] load_playlist_details called with no playlist_id.")
            self.playlist_title_label.setText("Error: Playlist ID missing")
            self._clear_track_list()
            return

        self.current_playlist_id = playlist_id
        # Loading state is already set by set_loading_state() for immediate UI response

        try:
            playlist_details = await self.deezer_api.get_playlist_details(playlist_id)
            if not playlist_details:
                error_msg = 'Playlist not found or unavailable'
                logger.error(f"[PlaylistDetail] Error loading playlist details for ID {playlist_id}: {error_msg}")
                self.playlist_title_label.setText(f"Error: {error_msg}")
                return
            elif playlist_details.get('error'):
                error_msg = playlist_details.get('error', {}).get('message', 'Failed to fetch playlist details')
                logger.error(f"[PlaylistDetail] Error loading playlist details for ID {playlist_id}: {error_msg}")
                self.playlist_title_label.setText(f"Error: {error_msg}")
                return

            self.current_playlist_data = playlist_details
            self.playlist_title_label.setText(playlist_details.get('title', 'N/A'))
            # self.playlist_type_label is static "PLAYLIST", already set

            creator_name = playlist_details.get('creator', {}).get('name', 'N/A')
            self.playlist_creator_label.setText(f"By {creator_name}")

            description = playlist_details.get('description', '')
            if description:
                self.playlist_description_label.setText(description)
                self.playlist_description_label.setVisible(True)
            else:
                self.playlist_description_label.setText("") # Ensure it's cleared
                self.playlist_description_label.setVisible(False)
            
            num_tracks = playlist_details.get('nb_tracks', 0)
            total_duration_sec = playlist_details.get('duration', 0)
            fans = playlist_details.get('fans', 0)
            self.playlist_stats_label.setText(f"{num_tracks} songs • {self._format_duration(total_duration_sec)} • {fans:,} fans")

            cover_url = playlist_details.get('picture_xl') or playlist_details.get('picture_big') or playlist_details.get('picture_medium')
            if cover_url:
                logger.debug(f"[PlaylistDetail] Found cover_url: {cover_url} for playlist {playlist_id}. Calling _load_main_playlist_cover.")
                self._load_main_playlist_cover(cover_url)
            else:
                logger.warning(f"[PlaylistDetail] No cover_url found for playlist {playlist_id}. Setting placeholder.")
                self._set_placeholder_main_playlist_cover()
            
            tracks = playlist_details.get('tracks', {}).get('data', [])
            if tracks:
                logger.info(f"[PlaylistDetail] Received {len(tracks)} tracks with playlist details for {playlist_id}.")
                self._clear_track_list()
                
                # Load tracks in batches - faster initial rendering
                for i, track_data in enumerate(tracks):
                    if not isinstance(track_data, dict):
                        logger.warning(f"[PlaylistDetail] Skipping non-dict track item: {track_data}")
                        continue
                        
                    # Create the card with track position (1-indexed)
                    track_position = i + 1
                    card = SearchResultCard(track_data, show_duration=True, track_position=track_position)
                    card.card_selected.connect(self._handle_track_card_selected)
                    card.download_clicked.connect(self._handle_track_download_selected)
                    # NEW: Connect artist and album name click signals
                    card.artist_name_clicked.connect(self.artist_name_clicked_from_track.emit)
                    card.album_name_clicked.connect(self.album_name_clicked_from_track.emit)
                    self.tracks_layout.addWidget(card)
                    
                    # DON'T force immediate artwork loading - let cards load when they become visible
                    # This prevents UI blocking and ensures smooth page navigation
                    # Cards will automatically load artwork via their showEvent with 1000ms delay
            else:
                logger.info(f"[PlaylistDetail] No tracks found in initial details for playlist {playlist_id}.")
                self._show_track_load_error("No tracks found in this playlist.")

        except Exception as e:
            logger.error(f"[PlaylistDetail] General error loading playlist {playlist_id}: {e}", exc_info=True)
            self.playlist_title_label.setText("Error loading playlist.")
            self.playlist_creator_label.setText("")
            self.playlist_description_label.setText("")
            self.playlist_description_label.setVisible(False)
            self.playlist_stats_label.setText("")
            self._show_track_load_error(f"An error occurred: {e}")

    def _clear_track_list(self):
        while self.tracks_layout.count():
            child = self.tracks_layout.takeAt(0)
            if child.widget():
                if isinstance(child.widget(), SearchResultCard):
                    child.widget().cancel_artwork_load() # Cancel artwork if it's a card
                child.widget().deleteLater()

    def _show_track_load_error(self, message: str):
        self._clear_track_list()
        error_label = QLabel(message)
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_label.setObjectName("error_label_detail_page")
        self.tracks_layout.addWidget(error_label)

    def _handle_track_card_selected(self, track_data: dict):
        logger.debug(f"[PlaylistDetail] Track card selected for playback: {track_data.get('title')}")
        self.track_selected_for_playback.emit(track_data)

    def _handle_track_download_selected(self, track_data: dict):
        logger.debug(f"[PlaylistDetail] Track card selected for download: {track_data.get('title')}")
        self.track_selected_for_download.emit(track_data) # This signal is already connected in MainWindow

    def _format_duration(self, seconds: int) -> str: 
        if not isinstance(seconds, (int, float)):
            return "--:--"
        minutes = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{minutes:02d}:{secs:02d}"

    # --- Main Playlist Cover Handling ---
    class MainCoverLoader(QRunnable):
        def __init__(self, url: str, success_signal: pyqtSignal, error_signal: pyqtSignal):
            super().__init__()
            self.url = url
            self.success_signal = success_signal
            self.error_signal = error_signal
            self._is_cancelled = False
            self.session = requests.Session()

        def cancel(self):
            logger.debug(f"PlaylistDetailPage.MainCoverLoader for {self.url} received cancel signal.")
            self._is_cancelled = True

        @pyqtSlot()
        def run(self):
            if self._is_cancelled:
                return

            if not self.url:
                self.error_signal.emit("No URL for main cover")
                return

            # Check if the image is already in cache
            try:
                # Try medium size from cache first for faster loading
                medium_url = None
                if 'xl' in self.url:
                    medium_url = self.url.replace('xl', 'medium')
                elif 'big' in self.url:
                    medium_url = self.url.replace('big', 'medium')
                
                # Try to get medium from cache
                if medium_url:
                    medium_image = get_image_from_cache(medium_url)
                    if isinstance(medium_image, QImage) and not self._is_cancelled:
                        pixmap = QPixmap.fromImage(medium_image)
                        self.success_signal.emit(pixmap)
                        logger.debug(f"[PlaylistDetail] Using cached medium image: {medium_url}")
                
                # Try original from cache
                image_data_or_qimage = get_image_from_cache(self.url)
                if isinstance(image_data_or_qimage, QImage) and not self._is_cancelled:
                    pixmap = QPixmap.fromImage(image_data_or_qimage)
                    self.success_signal.emit(pixmap)
                    logger.debug(f"[PlaylistDetail] Using cached original image: {self.url}")
                    return
            except Exception as e:
                logger.warning(f"[PlaylistDetail] Cache error: {e}")

            # Not in cache, download image with short timeout
            try:
                # Use a short timeout to avoid blocking downloads
                response = self.session.get(self.url, timeout=4)
                if self._is_cancelled:
                    return
                    
                if response.status_code == 200:
                    image_data = response.content
                    if not image_data or self._is_cancelled:
                        return
                        
                    # Save to cache for future use
                    save_image_to_cache(self.url, image_data)
                    
                    # Convert to QImage/QPixmap
                    image = QImage()
                    if image.loadFromData(image_data) and not self._is_cancelled:
                        pixmap = QPixmap.fromImage(image)
                        self.success_signal.emit(pixmap)
                    else:
                        self.error_signal.emit("Failed to load image data")
                else:
                    self.error_signal.emit(f"HTTP error: {response.status_code}")
            except Exception as e:
                if not self._is_cancelled:
                    self.error_signal.emit(f"Error loading image: {str(e)}")

    def _load_main_playlist_cover(self, url: str):
        if not url:
            logger.error("[PlaylistDetail.MainCoverLoader] No URL provided for loading main playlist cover.")
            return
        
        if hasattr(self, '_current_cover_loader') and self._current_cover_loader:
            self._current_cover_loader.cancel()
        
        loader = self.MainCoverLoader(url, self.main_playlist_cover_loaded, self._on_main_cover_artwork_error_signal)
        self._current_cover_loader = loader
        # Use the dedicated artwork thread pool
        self.thread_pool.start(loader)

    def _set_main_playlist_cover(self, pixmap: QPixmap):
        if self.playlist_cover_label:
            scaled_pixmap = pixmap.scaled(
                self.playlist_cover_label.size(), 
                Qt.AspectRatioMode.KeepAspectRatioByExpanding, 
                Qt.TransformationMode.SmoothTransformation
            )
            crop_x = (scaled_pixmap.width() - self.playlist_cover_label.width()) / 2
            crop_y = (scaled_pixmap.height() - self.playlist_cover_label.height()) / 2
            final_pixmap = scaled_pixmap.copy(int(crop_x), int(crop_y), self.playlist_cover_label.width(), self.playlist_cover_label.height())
            self.playlist_cover_label.setPixmap(final_pixmap)
        self._current_cover_loader = None

    def _set_placeholder_main_playlist_cover(self):
        if self.playlist_cover_label:
            self.playlist_cover_label.setText("?")
            self.playlist_cover_label.setStyleSheet("background-color: #E0E0E0; border-radius: 5px; color: #777;")
        if hasattr(self, '_current_cover_loader') and self._current_cover_loader:
            self._current_cover_loader.cancel()
            self._current_cover_loader = None

    def _on_main_cover_artwork(self, error_msg: str):
        logger.error(f"[PlaylistDetail] Error loading main playlist cover: {error_msg}")
        self._set_placeholder_main_playlist_cover()

    def cleanup_cards(self):
        """Clean up any SearchResultCard instances to prevent memory leaks."""
        # Import here to avoid circular imports
        from src.ui.search_widget import SearchResultCard
        
        # Clean up any cards in tracks layout
        if hasattr(self, 'tracks_layout'):
            for i in range(self.tracks_layout.count()):
                item = self.tracks_layout.itemAt(i)
                if item and item.widget() and isinstance(item.widget(), SearchResultCard):
                    item.widget().cleanup()

    def closeEvent(self, event):
        """Clean up when the page is closed."""
        self.cleanup_cards()
        super().closeEvent(event)
