"""Search widget for DeeMusic."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QComboBox, QScrollArea, QFrame,
    QLabel, QGridLayout, QStackedLayout, QSizePolicy, QSpacerItem, QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QRunnable, QThreadPool, QSize, pyqtSlot, QEvent, QPoint, QRect, QThread, QTimer # Added QTimer
import PyQt6.QtGui # Explicitly import the QtGui module first
from PyQt6.QtGui import QPixmap, QImage, QIcon, QPainter, QColor, QPen, QDesktopServices, QCursor, QBitmap, QBrush, QPainterPath, QMouseEvent # Add QMouseEvent, QCursor
import asyncio
# Remove aiohttp import if SearchResultCard doesn't use it anymore
# import aiohttp 
# Import requests for synchronous HTTP calls in worker
import requests 
from io import BytesIO
# Use absolute imports
from services.deezer_api import DeezerAPI
from services.download_manager import DownloadManager
import logging
import os
from PyQt6.sip import isdeleted as sip_is_deleted # Added import

# Import the new caching utility
from utils.image_cache import get_image_from_cache, save_image_to_cache
from utils.icon_utils import get_icon # ADD THIS IMPORT

# Add this global semaphore to limit concurrent downloads
# This will be shared across all instances of SearchResultCard
_ARTWORK_DOWNLOAD_SEMAPHORE = asyncio.Semaphore(5)  # Limit to 5 concurrent downloads

logger = logging.getLogger(__name__)

class ClickableLabel(QLabel):
    """A QLabel that emits a clicked signal when clicked."""
    clicked = pyqtSignal()
    
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

# --- CUSTOM HOVER OVERLAY WIDGET ---
class HoverOverlayWidget(QWidget):
    def __init__(self, associated_artwork_label: QLabel, parent=None):
        super().__init__(parent)
        self.associated_artwork_label = associated_artwork_label
        self.setMouseTracking(True) 

    def leaveEvent(self, event: QEvent):
        if self.associated_artwork_label:
            # REMOVED: Opacity effect removal, as we're not applying it for light overlay initially
            # self.associated_artwork_label.setGraphicsEffect(None) 
            pass
        self.setVisible(False)
        super().leaveEvent(event)

    # Optional: If clicks on the overlay background (not buttons) should be ignored or passed through
    # def mousePressEvent(self, event: QMouseEvent):
    #     event.ignore() # Or handle as needed
# --- END CUSTOM HOVER OVERLAY WIDGET ---

class WorkerSignals(QObject):
    finished = pyqtSignal(dict) # MODIFIED: Emit a dict to carry potentially multiple result sets
    error = pyqtSignal(str)

class SearchWorker(QRunnable):
    def __init__(self, api: DeezerAPI, query: str, filter_name: str, limit: int = 20):
        super().__init__()
        self.api = api
        self.query = query
        self.filter_name = filter_name # Empty string for "all", "tracks", "albums" etc. for specific
        self.limit = limit # This limit is 60 for "all", 20 for specific, used as total for "all" or single for specific
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        try:
            logger.debug(f"SearchWorker.run: Initial filter_name='{self.filter_name}', query='{self.query}', limit={self.limit}")
            
            results_payload = {}

            if not self.filter_name: # "all" search case
                logger.debug("SearchWorker: Performing 'all' search with multiple API calls.")
                # Limits for individual calls in "all" mode
                general_limit = 10
                artist_limit = 10
                album_limit = 10
                track_limit = 20
                playlist_limit = 10

                # 1. General Search (for top diverse results)
                try:
                    general_url = f"https://api.deezer.com/search?q={self.query}&limit={general_limit}&order=RANKING"
                    logger.debug(f"SearchWorker (all): Requesting General URL: {general_url}")
                    response = requests.get(general_url, timeout=10)
                    response.raise_for_status()
                    data = response.json()
                    results_payload['all_results'] = data.get('data', [])
                    logger.debug(f"SearchWorker (all): General search returned {len(results_payload['all_results'])} items.")
                except Exception as e:
                    logger.error(f"SearchWorker (all): Error fetching general results: {e}", exc_info=True)
                    results_payload['all_results'] = []

                # 2. Artist Search
                try:
                    artist_url = f"https://api.deezer.com/search/artist?q={self.query}&limit={artist_limit}"
                    logger.debug(f"SearchWorker (all): Requesting Artist URL: {artist_url}")
                    response = requests.get(artist_url, timeout=10)
                    response.raise_for_status()
                    data = response.json()
                    results_payload['artist_results'] = data.get('data', [])
                    logger.debug(f"SearchWorker (all): Artist search returned {len(results_payload['artist_results'])} items.")
                except Exception as e:
                    logger.error(f"SearchWorker (all): Error fetching artist results: {e}", exc_info=True)
                    results_payload['artist_results'] = []

                # 3. Album Search
                try:
                    album_url = f"https://api.deezer.com/search/album?q={self.query}&limit={album_limit}"
                    logger.debug(f"SearchWorker (all): Requesting Album URL: {album_url}")
                    response = requests.get(album_url, timeout=10)
                    response.raise_for_status()
                    data = response.json()
                    results_payload['album_results'] = data.get('data', [])
                    logger.debug(f"SearchWorker (all): Album search returned {len(results_payload['album_results'])} items.")
                except Exception as e:
                    logger.error(f"SearchWorker (all): Error fetching album results: {e}", exc_info=True)
                    results_payload['album_results'] = []
                
                # 4. Track Search
                try:
                    track_url = f"https://api.deezer.com/search/track?q={self.query}&limit={track_limit}"
                    logger.debug(f"SearchWorker (all): Requesting Track URL: {track_url}")
                    response = requests.get(track_url, timeout=10)
                    response.raise_for_status()
                    data = response.json()
                    results_payload['track_results'] = data.get('data', [])
                    logger.debug(f"SearchWorker (all): Track search returned {len(results_payload['track_results'])} items.")
                except Exception as e:
                    logger.error(f"SearchWorker (all): Error fetching track results: {e}", exc_info=True)
                    results_payload['track_results'] = []

                # 5. Playlist Search
                try:
                    playlist_url = f"https://api.deezer.com/search/playlist?q={self.query}&limit={playlist_limit}"
                    logger.debug(f"SearchWorker (all): Requesting Playlist URL: {playlist_url}")
                    response = requests.get(playlist_url, timeout=10)
                    response.raise_for_status()
                    data = response.json()
                    results_payload['playlist_results'] = data.get('data', [])
                    logger.debug(f"SearchWorker (all): Playlist search returned {len(results_payload['playlist_results'])} items.")
                except Exception as e:
                    logger.error(f"SearchWorker (all): Error fetching playlist results: {e}", exc_info=True)
                    results_payload['playlist_results'] = []
                
                self.signals.finished.emit(results_payload)

            else: # Specific filter search (tracks, albums, artists, playlists)
                api_filter_type = ""
                payload_key = "all_results" 

                if self.filter_name == "tracks":
                    api_filter_type = "/track"
                    payload_key = "track_results"
                elif self.filter_name == "albums":
                    api_filter_type = "/album"
                    payload_key = "album_results"
                elif self.filter_name == "artists":
                    api_filter_type = "/artist"
                    payload_key = "artist_results"
                elif self.filter_name == "playlists":
                    api_filter_type = "/playlist"
                    payload_key = "playlist_results"
                else:
                    logger.warning(f"SearchWorker: Unmapped filter_name '{self.filter_name}', attempting direct use.")
                    api_filter_type = f"/{self.filter_name}"
            
                endpoint_url = f"https://api.deezer.com/search{api_filter_type}?q={self.query}&limit={self.limit}"
                logger.debug(f"SearchWorker (specific filter '{self.filter_name}'): Requesting URL: {endpoint_url}")
            
                response = requests.get(endpoint_url, timeout=10)
                response.raise_for_status()
                data = response.json() 
            
                if 'error' in data:
                    error_msg = f"Search API error ({self.filter_name} filter): {data['error']}"
                    logger.error(error_msg)
                    self.signals.error.emit(error_msg)
                else:
                    results_list = data.get('data', [])
                    logger.debug(f"SearchWorker (specific filter '{self.filter_name}'): Sync search returned {len(results_list)} results.")
                    results_payload[payload_key] = results_list
                    self.signals.finished.emit(results_payload)

        except requests.exceptions.RequestException as e:
            error_msg = f"SearchWorker network error: {str(e)}"
            logger.error(error_msg)
            self.signals.error.emit(error_msg)
        except Exception as e:
            error_msg = f"SearchWorker failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.signals.error.emit(error_msg)

class SearchResultCard(QFrame):
    """Card widget for displaying search results."""
    
    download_clicked = pyqtSignal(dict)  # Emits item data when download button clicked
    card_selected = pyqtSignal(dict)   # Emits item data when the card itself is clicked
    artist_name_clicked = pyqtSignal(int)  # NEW: Emits artist_id when artist name is clicked
    album_name_clicked = pyqtSignal(int)   # NEW: Emits album_id when album name is clicked
    artwork_loaded_signal = pyqtSignal(QPixmap) # Internal signal for artwork
    artwork_error_signal = pyqtSignal(str)   # Internal signal for artwork errors
    
    # Class-level tracking for all cards
    _all_cards = []  # Track all active cards for bulk operations
    
    # --- Constants for Card Sizing ---
    CARD_MIN_WIDTH = 160  # Default width for standard cards (album/playlist)
    CARD_MIN_HEIGHT = 220 # Default height for standard cards
    ARTIST_CARD_WIDTH = 150
    ARTIST_CARD_HEIGHT = 190 # Height for artist card (image + name)
    TRACK_CARD_HEIGHT = 60  # Height for a track row
    TRACK_ARTWORK_SIZE = 48 # Size of artwork for tracks
    
    def __init__(self, item_data: dict, parent=None, is_top_artist_result: bool = False, show_duration: bool = False, track_position: int = None): # ADDED track_position
        super().__init__(parent)
        self.item_data = item_data
        self.item_id = item_data.get('id', 0)
        self.item_type = item_data.get('type', 'unknown')
        self.is_top_artist_result = is_top_artist_result # Flag for special styling if needed
        self.show_duration = show_duration  # Flag to show duration for tracks
        self.track_position = track_position  # Track position for numbered track lists
        self.thread_pool = QThreadPool.globalInstance()  # Store thread pool reference
        
        # Keep track of artwork loader for cancellation
        self._current_artwork_loader = None
        self._artwork_loaded = False  # Track if artwork has been loaded
        self._is_visible = False  # Track if card is currently visible
        
        # Add to class-level tracking
        SearchResultCard._all_cards.append(self)
        
        # Connect the signals
        self.artwork_loaded_signal.connect(self.set_artwork)
        self.artwork_error_signal.connect(self.handle_artwork_error)
        
        # Setup UI components
        self.setup_ui()
        
        # DON'T load artwork immediately - wait for visibility
        # QTimer.singleShot(10, self.load_artwork)  # REMOVED
        
    def cleanup(self):
        """Clean up the card and cancel any ongoing operations."""
        # Cancel artwork loading
        self.cancel_artwork_load()
        
        # Remove from class tracking
        try:
            SearchResultCard._all_cards.remove(self)
        except ValueError:
            pass  # Already removed
    
    def __del__(self):
        """Destructor to ensure cleanup."""
        self.cleanup()
    
    @classmethod
    def cancel_all_artwork_loading(cls):
        """Cancel artwork loading for all active cards."""
        logger.info(f"[SearchResultCard] Cancelling artwork loading for {len(cls._all_cards)} active cards")
        for card in cls._all_cards[:]:  # Create a copy to avoid modification during iteration
            if not sip_is_deleted(card):
                card.cancel_artwork_load()
    
    def _format_duration(self, seconds: int) -> str:
        if not isinstance(seconds, (int, float)):
            return "--:--"
        minutes = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{minutes:02d}:{secs:02d}" # Ensured two digits for seconds
        
    def setup_ui(self):
        self.setObjectName("SearchResultCardFrame")
        self.setFrameShape(QFrame.Shape.StyledPanel) 
        self.setLineWidth(0)

        self.card_layout = QVBoxLayout(self)
        self.card_layout.setContentsMargins(0,0,0,0)
        self.card_layout.setSpacing(0)

        self.artwork_container = QWidget(self)
        self.artwork_container.setMouseTracking(True)
        self.artwork_container.setFixedSize(self.CARD_MIN_WIDTH, self.CARD_MIN_WIDTH) 
        self.artwork_container_layout = QGridLayout(self.artwork_container) 
        self.artwork_container_layout.setContentsMargins(0,0,0,0)
        self.artwork_container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.artwork_label = QLabel(self.artwork_container)
        self.artwork_label.setObjectName("artwork_label")
        self.artwork_label.setScaledContents(False) 
        self.artwork_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artwork_label.setFixedSize(self.CARD_MIN_WIDTH, self.CARD_MIN_WIDTH) 
        self._set_placeholder_artwork(target_label_override=self.artwork_label)
        self.artwork_container_layout.addWidget(self.artwork_label, 0, 0, Qt.AlignmentFlag.AlignCenter)
        self.artwork_display_label = self.artwork_label

        # MODIFIED: Always create the overlay_action_button for relevant types
        # The button's utility (e.g., download) is suitable for tracks, albums, and playlists.
        # Artists might not have a direct "download artist" button, but that can be handled by not connecting a slot
        # or by specific logic in the click handler if needed for artists later.
        # For now, create it if the item type is one that supports a primary overlay action (like download).
        
        # if self.item_type != 'track': <--- REMOVE THIS CONDITION
        self.overlay_action_button = QPushButton(self.artwork_container)
        logger.debug(f"[SearchResultCard] Creating overlay action button for {self.item_type}: {self.item_data.get('title', self.item_data.get('name', 'Unknown'))}")
        self.overlay_action_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.overlay_action_button.setVisible(False)
        self.overlay_action_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.overlay_action_button.setFixedSize(40, 40) 
        
        self.overlay_action_button.setObjectName("OverlayGenericActionButton")
        # Tooltip can be made more specific if needed, e.g., based on item_type
        self.overlay_action_button.setToolTip("Download") 
        
        icon_to_load = "download.png" 
        icon = get_icon(icon_to_load) 
        if icon and not icon.isNull():
            self.overlay_action_button.setIcon(icon)
            self.overlay_action_button.setIconSize(QSize(24, 24))
            logger.debug(f"[SearchResultCard] Download icon loaded successfully for {self.item_type}")
        else:
            logger.warning(f"Failed to load or icon isNull for {icon_to_load}. Button will have no icon.")
            # Set text as fallback
            self.overlay_action_button.setText("↓")
        
        self.overlay_action_button.clicked.connect(lambda: self.download_clicked.emit(self.item_data))
        self.artwork_container_layout.addWidget(self.overlay_action_button, 0, 0, Qt.AlignmentFlag.AlignCenter)
        # else: # <--- REMOVE THIS ELSE BLOCK
            # self.overlay_action_button = None 
        
        self.artwork_container.installEventFilter(self)
        self.card_layout.addWidget(self.artwork_container, 0, Qt.AlignmentFlag.AlignHCenter)

        self.text_info_widget = QWidget()
        self.text_info_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.text_info_widget.setAutoFillBackground(False)
        self.text_info_widget.setStyleSheet("background-color: transparent;") 
        self.text_info_layout = QVBoxLayout(self.text_info_widget)
        self.text_info_layout.setContentsMargins(5, 8, 5, 8) 
        self.text_info_layout.setSpacing(2) 

        title_text = ""
        subtitle_text = ""
        item_type = self.item_data.get('type')

        if item_type == 'artist':
            self.setFixedSize(self.ARTIST_CARD_WIDTH, self.ARTIST_CARD_HEIGHT)
            self.artwork_container.setFixedSize(self.ARTIST_CARD_WIDTH, self.ARTIST_CARD_WIDTH)
            self.artwork_label.setFixedSize(self.ARTIST_CARD_WIDTH, self.ARTIST_CARD_WIDTH)
            self.text_info_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter) 
            title_text = self.item_data.get('name', 'Unknown Artist')
            self.is_top_artist_result = True 
            
        elif item_type == 'album':
            title_text = self.item_data.get('title', 'Unknown Album')
            subtitle_text = self.item_data.get('artist_name') or self.item_data.get('artist', {}).get('name', 'Various Artists')
            self.setFixedSize(self.CARD_MIN_WIDTH, self.CARD_MIN_HEIGHT)
        elif item_type == 'playlist':
            title_text = self.item_data.get('title', 'Unknown Playlist')
            if self.item_data.get('user') and self.item_data['user'].get('name'):
                subtitle_text = f"By {self.item_data['user'].get('name')}"
            elif self.item_data.get('description'):
                subtitle_text = self.item_data.get('description')
            else:
                subtitle_text = f"{self.item_data.get('nb_tracks', 0)} tracks"
            self.setFixedSize(self.CARD_MIN_WIDTH, self.CARD_MIN_HEIGHT) 
        elif item_type == 'track':
            self.setFixedHeight(self.TRACK_CARD_HEIGHT) 
            self.artwork_container.setFixedSize(self.TRACK_ARTWORK_SIZE, self.TRACK_ARTWORK_SIZE)
            self.artwork_label.setFixedSize(self.TRACK_ARTWORK_SIZE, self.TRACK_ARTWORK_SIZE)
            
            self.text_info_widget.deleteLater() 
            
            track_details_widget = QWidget()
            self.track_details_widget = track_details_widget  # Store reference for event filtering
            track_details_layout = QHBoxLayout(track_details_widget)
            track_details_layout.setContentsMargins(10, 0, 10, 0) 
            track_details_layout.setSpacing(8) 

            track_details_layout.addWidget(self.artwork_container)

            # Add track number if position is provided (for playlist tracks)
            if self.track_position is not None:
                self.track_number_label = QLabel(str(self.track_position))
                self.track_number_label.setObjectName("CardTrackNumberLabel_Track")
                self.track_number_label.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
                self.track_number_label.setFixedWidth(30)  # Fixed width for track number
                track_details_layout.addWidget(self.track_number_label, 0)

            title_str = self.item_data.get('title_short', self.item_data.get('title', 'Unknown Track'))
            self.title_label = QLabel(title_str)
            self.title_label.setObjectName("CardTitleLabel_Track")
            self.title_label.setToolTip(self.item_data.get('title', 'Unknown Track'))
            self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.title_label.setWordWrap(False)
            track_details_layout.addWidget(self.title_label, 5) 

            artist_name = self.item_data.get('artist', {}).get('name', 'Unknown Artist')
            artist_id = self.item_data.get('artist', {}).get('id')
            self.artist_label = ClickableLabel(artist_name)
            self.artist_label.setObjectName("CardArtistLabel_Track") 
            self.artist_label.setToolTip(artist_name)
            self.artist_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred) 
            self.artist_label.setWordWrap(False)
            # Connect click signal if we have a valid artist ID
            if artist_id:
                self.artist_label.clicked.connect(lambda: self.artist_name_clicked.emit(artist_id))
            track_details_layout.addWidget(self.artist_label, 3) 

            album_title = self.item_data.get('album', {}).get('title', '')
            album_id = self.item_data.get('album', {}).get('id')
            self.album_label = ClickableLabel(album_title)
            self.album_label.setObjectName("CardAlbumLabel_Track")
            self.album_label.setToolTip(album_title)
            self.album_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred) 
            self.album_label.setWordWrap(False)
            # Connect click signal if we have a valid album ID
            if album_id:
                self.album_label.clicked.connect(lambda: self.album_name_clicked.emit(album_id))
            track_details_layout.addWidget(self.album_label, 3)
            
            if self.show_duration:
                duration_sec = self.item_data.get('duration', 0)
                self.duration_label = QLabel(self._format_duration(duration_sec)) 
                self.duration_label.setObjectName("CardDurationLabel_Track") 
                self.duration_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.duration_label.setFixedWidth(45)
                track_details_layout.addWidget(self.duration_label, 1)
            else:
                duration_spacer = QWidget()
                duration_spacer.setFixedWidth(45) 
                track_details_layout.addWidget(duration_spacer, 1) 
            
            track_details_widget.setLayout(track_details_layout)
            self.card_layout.addWidget(track_details_widget)
            
            # Install event filter for track cards too
            track_details_widget.installEventFilter(self)
        
        else: 
            title_text = self.item_data.get('title', self.item_data.get('name', 'Unknown Item'))
            subtitle_text = f"Type: {item_type}"
            self.setFixedSize(self.CARD_MIN_WIDTH, self.CARD_MIN_HEIGHT)

        if item_type != 'track':
            actual_title_text = title_text if title_text else "Unknown"
            self.title_label = QLabel(actual_title_text)
            self.title_label.setObjectName("CardTitleLabel")
            self.title_label.setToolTip(actual_title_text) 
            
            title_font = self.title_label.font() 
            if item_type in ['album', 'playlist', 'artist']:
                title_font.setBold(True)
            else:
                title_font.setBold(False)
            self.title_label.setFont(title_font)

            if not hasattr(self, 'text_info_layout') or self.text_info_layout is None:
                logger.error(f"SearchResultCard {self.item_id} ({item_type}): text_info_layout missing before adding title_label.")
            else:
                self.text_info_layout.addWidget(self.title_label)

            if subtitle_text:
                self.subtitle_label = QLabel(subtitle_text)
                self.subtitle_label.setObjectName("CardSubtitleLabel")
                self.subtitle_label.setToolTip(subtitle_text)
                if hasattr(self, 'text_info_layout') and self.text_info_layout is not None:
                    self.text_info_layout.addWidget(self.subtitle_label)
                else:
                    logger.error(f"SearchResultCard {self.item_id} ({item_type}): text_info_layout missing before adding subtitle_label.")
            
            if item_type == 'artist':
                self.title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                if hasattr(self, 'subtitle_label') and self.subtitle_label: 
                    self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            else:
                self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
                if hasattr(self, 'subtitle_label') and self.subtitle_label: 
                    self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

            if hasattr(self, 'text_info_widget') and self.text_info_widget is not None:
                self.card_layout.addWidget(self.text_info_widget)
            else:
                logger.error(f"SearchResultCard {self.item_id} ({item_type}): text_info_widget is missing, cannot add to card_layout.")
        
        self.setMouseTracking(True) 
        self.artwork_label.setMouseTracking(True)
        
    # --- Artwork Loading Nested Class and Methods ---
    class _CardArtworkLoader(QRunnable):
        """Worker class to load artwork asynchronously."""

        def __init__(self, url, loaded_signal, error_signal):
            super().__init__()
            self.url = url
            self.loaded_signal = loaded_signal
            self.error_signal = error_signal
            self._is_cancelled = False

        def cancel(self):
            """Cancel the loading operation."""
            self._is_cancelled = True

        @pyqtSlot()
        def run(self):
            """Run the worker to load the image."""
            if self._is_cancelled:
                return

            try:
                # First check if the image is in the cache
                try:
                    cached_image = get_image_from_cache(self.url)
                    if cached_image and not self._is_cancelled:
                        pixmap = QPixmap.fromImage(cached_image)
                        if not pixmap.isNull():
                            if hasattr(self.loaded_signal, 'emit'):
                                self.loaded_signal.emit(pixmap)
                            return
                except Exception as cache_err:
                    logger.debug(f"[SearchResultCard._CardArtworkLoader] Cache check failed: {cache_err}")
                    # Continue to download if cache check fails

                # If not in cache or invalid, download it
                response = requests.get(self.url, timeout=10)
                if self._is_cancelled:
                    return
                response.raise_for_status()

                image_data = response.content
                if self._is_cancelled:
                    return

                # Cache the downloaded image for future use
                try:
                    save_image_to_cache(self.url, image_data)
                except Exception as cache_save_err:
                    logger.debug(f"[SearchResultCard._CardArtworkLoader] Cache save failed: {cache_save_err}")
                    # Continue even if caching fails

                # Load the image into a QImage
                image = QImage()
                if image.loadFromData(image_data):
                    if self._is_cancelled:
                        return
                    pixmap = QPixmap.fromImage(image)
                    if not pixmap.isNull():
                        if hasattr(self.loaded_signal, 'emit'):
                            self.loaded_signal.emit(pixmap)
                        else:
                            logger.error(f"[SearchResultCard._CardArtworkLoader] Signal object does not have emit method")
                    else:
                        if hasattr(self.error_signal, 'emit'):
                            self.error_signal.emit("Generated pixmap is null")
                        else:
                            logger.error(f"[SearchResultCard._CardArtworkLoader] Error signal object does not have emit method")
                else:
                    if hasattr(self.error_signal, 'emit'):
                        self.error_signal.emit("Failed to load image data")
                    else:
                        logger.error(f"[SearchResultCard._CardArtworkLoader] Error signal object does not have emit method")

            except requests.exceptions.Timeout:
                logger.error(f"[SearchResultCard._CardArtworkLoader] Timeout loading image {self.url}")
                if not self._is_cancelled and hasattr(self.error_signal, 'emit'):
                    self.error_signal.emit("Request timed out")
            except requests.exceptions.RequestException as e:
                logger.error(f"[SearchResultCard._CardArtworkLoader] Request error loading image {self.url}: {e}")
                if not self._is_cancelled and hasattr(self.error_signal, 'emit'):
                    self.error_signal.emit(str(e))
            except Exception as e:
                logger.error(f"[SearchResultCard._CardArtworkLoader] Error loading image {self.url}: {e}")
                if not self._is_cancelled and hasattr(self.error_signal, 'emit'):
                    try:
                        self.error_signal.emit(str(e))
                    except Exception as emit_error:
                        logger.error(f"[SearchResultCard._CardArtworkLoader] Failed to emit error signal: {emit_error}")

    def load_artwork(self):
        # Don't load if already loaded or loading
        if self._artwork_loaded or self._current_artwork_loader:
            return
            
        # Cancel any existing loader first
        if hasattr(self, '_current_artwork_loader') and self._current_artwork_loader:
            try:
                self._current_artwork_loader.cancel()
                self._current_artwork_loader = None
            except Exception as e:
                # Just log and continue if cancel fails
                logger.debug(f"[SearchResultCard] Error canceling previous loader: {e}")

        # Ensure we have a valid artwork_label
        if not hasattr(self, 'artwork_label') or not self.artwork_label or sip_is_deleted(self.artwork_label):
            logger.warning(f"[SearchResultCard] Cannot load artwork: artwork_label is invalid/deleted")
            return

        # Build list of URLs to try in order (higher quality first)
        urls = []
        
        # Check for picture_url in item_data (album/artist cover)
        if 'picture_url' in self.item_data and self.item_data['picture_url']:
            urls.append(self.item_data['picture_url'])
        
        # Check for picture_xl, picture_big, picture_medium in top level
        # Use highest quality first
        for size in ['picture_xl', 'picture_big', 'picture_medium', 'picture']:
            if size in self.item_data and self.item_data[size]:
                urls.append(self.item_data[size])
        
        # Check for album cover URLs
        if 'album' in self.item_data and isinstance(self.item_data['album'], dict):
            for size in ['cover_xl', 'cover_big', 'cover_medium', 'cover_small', 'cover']:
                if size in self.item_data['album'] and self.item_data['album'][size]:
                    urls.append(self.item_data['album'][size])
        
        # For artist images
        if 'artist' in self.item_data and isinstance(self.item_data['artist'], dict):
            for size in ['picture_xl', 'picture_big', 'picture_medium', 'picture']:
                if size in self.item_data['artist'] and self.item_data['artist'][size]:
                    urls.append(self.item_data['artist'][size])
        
        # Remove duplicates while preserving order
        unique_urls = []
        for url in urls:
            if url not in unique_urls:
                unique_urls.append(url)
        
        if not unique_urls:
            logger.warning(f"[SearchResultCard] No artwork URLs found for {self.item_data.get('title', self.item_data.get('name', 'Unknown item'))}")
            self._set_placeholder_artwork()
            self._artwork_loaded = True  # Mark as loaded to prevent retries
            return
        
        # Start loading the first URL
        self._start_artwork_loader(unique_urls)

    def _start_artwork_loader(self, urls):
        """
        Start loading the first URL from the list.
        If that fails, we'll try the next one in handle_artwork_error.
        """
        if not urls:
            self._set_placeholder_artwork()
            return
            
        # Try the first URL
        url = urls[0]
        self._remaining_urls = urls[1:]  # Store the rest for fallback
        
        # Create a loader for the first URL
        self._current_artwork_loader = self._CardArtworkLoader(
            url, 
            self.artwork_loaded_signal,  # Pass the class signal
            self.artwork_error_signal    # Pass the class signal
        )
        
        # Start the loader
        QThreadPool.globalInstance().start(self._current_artwork_loader)

    def cancel_artwork_load(self): # ADDED: Method to cancel the current artwork loader
        if self._current_artwork_loader:
            logger.debug(f"[SearchResultCard] Cancelling artwork load for {self.item_data.get('title')}")
            try:
                self._current_artwork_loader.cancel()
            except Exception as e:
                logger.debug(f"[SearchResultCard] Error cancelling artwork loader: {e}")
            finally:
                self._current_artwork_loader = None # Clear reference

    def set_artwork(self, pixmap: QPixmap):
        if sip_is_deleted(self) or not hasattr(self, 'artwork_label') or self.artwork_label is None or sip_is_deleted(self.artwork_label):
            logger.warning(f"[SearchResultCard] artwork_label is deleted or None when trying to set artwork for {self.item_data.get('title')}. Aborting.")
            return
        
        if pixmap is None or pixmap.isNull():
            logger.warning(f"[SearchResultCard] Received null pixmap for {self.item_data.get('title')}. Setting placeholder.")
            self._set_placeholder_artwork()
            self._artwork_loaded = True  # Mark as loaded even for placeholder
            return

        target_label = self.artwork_label
        target_size = target_label.size()

        # Handle artist card specific styling (circular mask)
        if self.item_type == 'artist':
            # Scale the original pixmap to fit the target size while maintaining aspect ratio, then crop to square
            # Ensure target_size is square for artists (usually ARTIST_CARD_WIDTH x ARTIST_CARD_WIDTH for the image part)
            side = min(target_size.width(), target_size.height())
            square_target_size = QSize(side, side)
            
            scaled_pixmap = pixmap.scaled(square_target_size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            
            # Center crop
            crop_x = (scaled_pixmap.width() - side) / 2
            crop_y = (scaled_pixmap.height() - side) / 2
            cropped_pixmap = scaled_pixmap.copy(int(crop_x), int(crop_y), side, side)

            # Create the final pixmap with a transparent background for the circle
            final_pixmap = QPixmap(square_target_size)
            final_pixmap.fill(Qt.GlobalColor.transparent)

            painter = QPainter(final_pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            path = QPainterPath()
            path.addEllipse(0, 0, side, side)
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, cropped_pixmap)
            painter.end()
            
            target_label.setPixmap(final_pixmap)
        else:
            # For other types (album, playlist, track), scale to fit label size (usually square or rectangular)
            # KeepAspectRatio should make it fit without cropping, letterboxing if necessary.
            # SmoothTransformation for better quality.
            scaled_pixmap = pixmap.scaled(target_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            target_label.setPixmap(scaled_pixmap)
        
        target_label.update() # Force repaint
        self._artwork_loaded = True  # Mark as successfully loaded
        self._current_artwork_loader = None  # Clear loader reference

    def handle_artwork_error(self, error_message: str):
        """Handle error loading artwork - try next URL or show placeholder."""
        if sip_is_deleted(self) or not hasattr(self, 'artwork_label') or self.artwork_label is None or sip_is_deleted(self.artwork_label):
            return
            
        logger.debug(f"[SearchResultCard] Error loading artwork for {self.item_data.get('title', self.item_data.get('name', 'Unknown'))}: {error_message}")
        
        # Try next URL if available
        if hasattr(self, '_remaining_urls') and self._remaining_urls:
            next_url = self._remaining_urls[0]
            self._remaining_urls = self._remaining_urls[1:]
            logger.debug(f"[SearchResultCard] Trying next URL: {next_url}")
            
            # Create a new loader for the next URL
            self._current_artwork_loader = self._CardArtworkLoader(
                next_url,
                self.artwork_loaded_signal,
                self.artwork_error_signal
            )
            
            # Start the loader
            QThreadPool.globalInstance().start(self._current_artwork_loader)
        else:
            # No more URLs to try, show placeholder
            logger.debug("[SearchResultCard] No more URLs to try, showing placeholder")
            self._set_placeholder_artwork()
            self._artwork_loaded = True  # Mark as loaded to prevent retries
            self._current_artwork_loader = None  # Clear loader reference

    def _set_placeholder_artwork(self, target_label_override=None, item_type_override=None):
        """Set a placeholder image for the artwork when no image is available or loading fails."""
        if sip_is_deleted(self):
            return

        target_label = target_label_override if target_label_override else self.artwork_label
        if not target_label or sip_is_deleted(target_label):
            # logger.debug(f"[SearchResultCard] _set_placeholder_artwork: target_label is None or deleted for item {self.item_id}")
            return

        current_item_type = item_type_override if item_type_override else self.item_type
        
        # Use fixed size of the label for the placeholder pixmap
        pixmap_size = target_label.size()
        if pixmap_size.isEmpty() or pixmap_size.width() <= 0 or pixmap_size.height() <= 0:
            # Fallback size if label size is invalid
            if current_item_type == 'track':
                pixmap_size = QSize(self.TRACK_ARTWORK_SIZE, self.TRACK_ARTWORK_SIZE)
            elif current_item_type == 'artist':
                pixmap_size = QSize(self.ARTIST_CARD_WIDTH, self.ARTIST_CARD_WIDTH) # Assuming square image part for artist
            else: # album, playlist
                pixmap_size = QSize(self.CARD_MIN_WIDTH, self.CARD_MIN_WIDTH) # Assuming square image part
            # logger.warning(f"[SearchResultCard] Invalid target_label size for placeholder on item {self.item_id}. Using default: {pixmap_size}")

        placeholder_pixmap = QPixmap(pixmap_size)
        placeholder_pixmap.fill(QColor("#333333"))  # Darker placeholder background

        painter = QPainter(placeholder_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Determine placeholder text based on item type
        placeholder_text = "Art"
        if current_item_type == 'artist':
            placeholder_text = "Artist"
        elif current_item_type == 'album':
            placeholder_text = "Album"
        elif current_item_type == 'playlist':
            placeholder_text = "Playlist"
        elif current_item_type == 'track':
            placeholder_text = "Trk" # Shorter for small track art

        # Draw text
        pen = QPen(QColor("#777777")) # Lighter text for dark background
        painter.setPen(pen)
        font = painter.font()
        # Adjust font size based on pixmap height, ensure it's not too large
        font_size = max(8, int(pixmap_size.height() / 5)) 
        font.setPointSize(font_size)
        painter.setFont(font)
        painter.drawText(placeholder_pixmap.rect(), Qt.AlignmentFlag.AlignCenter, placeholder_text)
        
        # For artist cards, apply circular mask to placeholder too
        if current_item_type == 'artist':
            final_artist_pixmap = QPixmap(pixmap_size)
            final_artist_pixmap.fill(Qt.GlobalColor.transparent) # Transparent background for the circle
            
            mask_painter = QPainter(final_artist_pixmap)
            mask_painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            clip_path = QPainterPath()
            clip_path.addEllipse(0, 0, pixmap_size.width(), pixmap_size.height())
            mask_painter.setClipPath(clip_path)
            mask_painter.drawPixmap(0, 0, placeholder_pixmap)
            mask_painter.end()
            target_label.setPixmap(final_artist_pixmap)
        else:
            target_label.setPixmap(placeholder_pixmap)
        
        painter.end() # End painter for the original placeholder_pixmap

    def eventFilter(self, source, event):
        """Handle mouse events for card interaction."""
        if source == self.artwork_container:
            if event.type() == QEvent.Type.Enter:
                # Show download button on hover for all item types
                if hasattr(self, 'overlay_action_button'):
                    logger.debug(f"[SearchResultCard] Showing download button for {self.item_type}: {self.item_data.get('title', self.item_data.get('name', 'Unknown'))}")
                    self.overlay_action_button.setVisible(True)
                return True
            elif event.type() == QEvent.Type.Leave:
                # Hide download button when not hovering
                if hasattr(self, 'overlay_action_button'):
                    logger.debug(f"[SearchResultCard] Hiding download button for {self.item_type}: {self.item_data.get('title', self.item_data.get('name', 'Unknown'))}")
                    self.overlay_action_button.setVisible(False)
                return True
            elif event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    # Emit card selected signal for navigation
                    logger.debug(f"[SearchResultCard] Card clicked for {self.item_type}: {self.item_data.get('title', self.item_data.get('name', 'Unknown'))}")
                    self.card_selected.emit(self.item_data)
                    return True
        elif hasattr(self, 'track_details_widget') and source == self.track_details_widget:
            # Handle events for track cards (which have a different layout)
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    # Emit card selected signal for navigation
                    logger.debug(f"[SearchResultCard] Track card clicked: {self.item_data.get('title', 'Unknown Track')}")
                    self.card_selected.emit(self.item_data)
                    return True
        return super().eventFilter(source, event)

    def mousePressEvent(self, event):
        """Handle mouse press events on the card itself."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Emit card selected signal for navigation
            self.card_selected.emit(self.item_data)
        super().mousePressEvent(event)

    def showEvent(self, event):
        """Called when the widget becomes visible."""
        super().showEvent(event)
        self._is_visible = True
        self._check_and_load_artwork()
    
    def hideEvent(self, event):
        """Called when the widget becomes hidden."""
        super().hideEvent(event)
        self._is_visible = False
        # Cancel artwork loading if it's in progress and widget is hidden
        self.cancel_artwork_load()
    
    def _check_and_load_artwork(self):
        """Check if artwork should be loaded and load it if needed."""
        if self._is_visible and not self._artwork_loaded and not self._current_artwork_loader:
            # Add a small delay to avoid loading during rapid scrolling
            QTimer.singleShot(100, self._delayed_artwork_load)
    
    def _delayed_artwork_load(self):
        """Load artwork after a delay, only if still visible."""
        if self._is_visible and not self._artwork_loaded and not self._current_artwork_loader:
            self.load_artwork()

class SearchWidget(QWidget):
    """Widget for searching and displaying results."""
    
    # Signal to MainWindow when a playlist is selected for detailed view
    playlist_selected = pyqtSignal('qint64')
    album_selected = pyqtSignal(int)    # Emits album_id
    artist_selected = pyqtSignal(int)   # Emits artist_id
    # NEW: Signals for navigation from track artist/album names
    artist_name_clicked_from_track = pyqtSignal(int)  # Emits artist_id when artist name clicked in track
    album_name_clicked_from_track = pyqtSignal(int)   # Emits album_id when album name clicked in track
    back_button_pressed = pyqtSignal() # ADDED: Signal for back button
    
    def __init__(self, deezer_api: DeezerAPI, download_manager: DownloadManager, parent=None):
        super().__init__(parent)
        self.deezer_api = deezer_api
        self.download_manager = download_manager
        self.current_query = ""
        self.active_filter_type = "all" # Default to 'all'
        self.filter_buttons = {} # To store filter buttons for styling
        self.all_loaded_results = [] # Initialize all_loaded_results
        
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the search widget UI."""
        self.top_result_section_container = None # Initialize the attribute
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10) # Add some padding around the SearchWidget content
        
        # --- Header Panel for Back Button and Filters ---
        header_panel_widget = QWidget()
        header_panel_layout = QHBoxLayout(header_panel_widget)
        header_panel_layout.setContentsMargins(0,0,0,0)
        header_panel_layout.setSpacing(5) # Spacing between back button and filter panel

        # Back Button
        self.back_button = QPushButton()
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'back button.png')
        if os.path.exists(icon_path):
            self.back_button.setIcon(QIcon(icon_path))
        else:
            self.back_button.setText("<") # Fallback text
            logger.warning(f"Back button icon not found at {icon_path}")
        self.back_button.setIconSize(QSize(22, 22)) # Adjust as needed
        self.back_button.setFixedSize(QSize(30, 30)) # Adjust as needed
        self.back_button.setObjectName("BackButton") # For QSS styling
        self.back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_button.clicked.connect(self.back_button_pressed.emit) # Emit the new signal
        header_panel_layout.addWidget(self.back_button)

        # ADDED: Label for "View All" title
        self.view_all_title_label = QLabel("")
        self.view_all_title_label.setObjectName("SearchSectionHeader") # Reuse existing style for consistency
        self.view_all_title_label.setVisible(False) # Initially hidden
        header_panel_layout.addWidget(self.view_all_title_label)
        header_panel_layout.addSpacing(10) # Add some spacing between title and filters

        # Filter buttons panel (original)
        self.filter_buttons_panel = QWidget() 
        filter_buttons_layout = QHBoxLayout(self.filter_buttons_panel) 
        filter_buttons_layout.setContentsMargins(0,0,0,0) 
        filter_buttons_layout.setSpacing(0) 
        
        filter_types = ["All", "Tracks", "Albums", "Playlists", "Artists"]
        for filter_text in filter_types:
            button = QPushButton(filter_text)
            button.setObjectName("SearchFilterButton") 
            button.setProperty("filter_type", filter_text.lower())
            button.setCheckable(True) # Make them checkable to manage active state
            button.clicked.connect(self._handle_filter_button_clicked)
            filter_buttons_layout.addWidget(button)
            self.filter_buttons[filter_text.lower()] = button
            
        filter_buttons_layout.addStretch(1) # Push filter type buttons to the left (within their panel)

        header_panel_layout.addWidget(self.filter_buttons_panel) # MODIFIED: Removed stretch factor 1
        header_panel_layout.addStretch(1) # ADDED: General stretch to push content left

        # Set 'All' button as active initially
        if "all" in self.filter_buttons:
            self.filter_buttons["all"].setChecked(True)
            self._update_filter_button_styles("all")

        
        # Results area
        self.results_area = QScrollArea()
        self.results_area.setWidgetResizable(True)
        self.results_widget = QWidget()
        self.results_layout = QVBoxLayout(self.results_widget)
        self.results_area.setWidget(self.results_widget)
        
        # Add to main layout
        layout.addWidget(header_panel_widget) # ADDED: new header panel
        # layout.addWidget(self.filter_buttons_panel) # REMOVED: Now part of header_panel_widget
        layout.addWidget(self.results_area, stretch=1)
        
        self.set_back_button_visibility(False) # Initially hidden
        
    def set_back_button_visibility(self, visible: bool):
        """Sets the visibility of the back button."""
        if hasattr(self, 'back_button'):
            self.back_button.setVisible(visible)

    def _handle_filter_button_clicked(self):
        """Handles clicks on the filter buttons."""
        clicked_button = self.sender()
        if not clicked_button:
            return

        new_filter_type = clicked_button.property("filter_type")
        
        if self.active_filter_type == new_filter_type:
            # If the already active button is clicked again, ensure it remains checked
            clicked_button.setChecked(True) 
            return

        self.active_filter_type = new_filter_type
        self._update_filter_button_styles(new_filter_type)

        # If there's an active query, re-perform the search with the new filter
        if self.current_query:
            logger.info(f"Search filter changed to '{self.active_filter_type}'. Re-searching for '{self.current_query}'.")
            self.perform_search()
            
    def _update_filter_button_styles(self, active_filter: str):
        """Updates the visual style of filter buttons based on the active filter."""
        for filter_type, button in self.filter_buttons.items():
            is_active = (filter_type == active_filter)
            button.setChecked(is_active) # Set check state
            # QSS will handle the visual change based on :checked pseudo-state
            # Forcing a style re-polish can help if QSS is not updating immediately.
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()


    def set_search_query_and_search(self, query: str):
        """Sets the search query and triggers a new search."""
        self.current_query = query.strip()
        # When a new search is initiated, typically "All" filter is selected by default on Deezer.
        # Or, we can keep the current filter. For now, let's reset to 'All' for a new query.
        # self.active_filter_type = "all" # Uncomment to reset filter to 'All' on new search
        # self._update_filter_button_styles(self.active_filter_type)
        logger.info(f"Search query set to: '{self.current_query}'. Current filter: '{self.active_filter_type}'")
        self.perform_search()
        
    def perform_search(self):
        """Execute the search using QThreadPool."""
        if hasattr(self, 'filter_buttons_panel'): # Make sure filters are visible for regular search
            self.filter_buttons_panel.show()
        # ADDED: Hide the view_all_title_label for regular searches
        if hasattr(self, 'view_all_title_label'):
            self.view_all_title_label.setText("")
            self.view_all_title_label.setVisible(False)

        query = self.current_query
        if not query:
            logger.debug("Perform search called but no current query.")
            self._clear_results()
            no_query_label = QLabel("Enter a search term in the header bar.")
            no_query_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.results_layout.addWidget(no_query_label)
            return
            
        search_type_for_api = "" if self.active_filter_type == 'all' else self.active_filter_type
        limit_for_search = 60 if self.active_filter_type == 'all' else 20 # Increased limit for 'all'
        
        self._clear_results()
                
        loading_label = QLabel("Searching...")
        loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.results_layout.addWidget(loading_label)
        
        # Create and run worker
        logger.debug("Creating and starting SearchWorker...")
        worker = SearchWorker(self.deezer_api, query, search_type_for_api, limit=limit_for_search)
        worker.signals.finished.connect(self.handle_search_results)
        worker.signals.error.connect(self.handle_search_error)
        QThreadPool.globalInstance().start(worker)

    def _clear_results(self):
        logger.debug("Calling _clear_results")

        # Clear the main results_layout
        layout_to_clear = self.results_layout
        if hasattr(self, 'results_content_widget') and self.results_content_widget.layout() == self.results_layout:
            pass # results_layout is directly on results_content_widget
        elif hasattr(self, 'results_scroll_area') and self.results_scroll_area.widget() and self.results_scroll_area.widget().layout() == self.results_layout:
            pass # results_layout is on the scroll area's widget.
        else:
            # Fallback or if results_layout is directly on SearchWidget (less likely with current setup_ui)
            pass
            
        if layout_to_clear:
            # Clear top_result_section_container first if it exists and is a child of what results_layout manages
            if self.top_result_section_container and self.top_result_section_container.parentWidget() == layout_to_clear.parentWidget():
                logger.debug(f"Explicitly clearing top_result_section_container: {self.top_result_section_container.objectName() if self.top_result_section_container else 'None'}")
                if self.top_result_section_container.layout():
                    while self.top_result_section_container.layout().count(): # INDENTED
                        child_item = self.top_result_section_container.layout().takeAt(0) # INDENTED
                        actual_widget = child_item.widget() # Store widget # INDENTED
                        if actual_widget: # INDENTED
                            if isinstance(actual_widget, SearchResultCard): # ADDED: Cancel artwork load # INDENTED
                                actual_widget.cancel_artwork_load() # INDENTED
                                actual_widget.cleanup()  # NEW: Call cleanup method
                            actual_widget.setParent(None) # INDENTED
                            actual_widget.deleteLater() # INDENTED
                self.top_result_section_container.setParent(None) # INDENTED
                self.top_result_section_container.deleteLater() # INDENTED
                self.top_result_section_container = None # INDENTED

            # Now clear everything else from results_layout
            while layout_to_clear.count():
                item = layout_to_clear.takeAt(0) # Removes the item from the layout
                if item is None:
                    continue

                widget = item.widget() # ALIGNED
                if widget: # ALIGNED with widget assignment, and subsequent block indented under this if
                    # Check if this widget is the top_result_section_container that might have been handled
                    if self.top_result_section_container is not None and widget == self.top_result_section_container:
                        logger.debug(f"Skipping deletion of top_result_section_container in main loop as it was handled: {widget.objectName()}")
                        # It should have been set to None if handled, this is a safeguard.
                        # If it was handled, it's already deleted. If not, it will be deleted.
                    else:
                        logger.debug(f"Clearing widget from results_layout: {widget.objectName()} of type {type(widget)}")
                        if isinstance(widget, SearchResultCard): # ADDED: Cancel artwork load
                            widget.cancel_artwork_load()
                            widget.cleanup()  # NEW: Call cleanup method
                        widget.setParent(None)
                    widget.deleteLater()
                else:
                    layout_item = item.layout()
                    if layout_item:
                        logger.debug(f"Clearing nested layout from results_layout: {type(layout_item)}")
                        # Recursively clear widgets from this sub-layout
                        while layout_item.count():
                            inner_item = layout_item.takeAt(0) # Removes from inner_item's layout
                            inner_actual_widget = inner_item.widget() # Store widget
                            if inner_actual_widget:
                                logger.debug(f"  Clearing inner widget: {inner_actual_widget.objectName()} of type {type(inner_actual_widget)}")
                                if isinstance(inner_actual_widget, SearchResultCard): # ADDED: Cancel artwork load
                                    inner_actual_widget.cancel_artwork_load()
                                    inner_actual_widget.cleanup()  # NEW: Call cleanup method
                                inner_actual_widget.setParent(None)
                                inner_actual_widget.deleteLater()
                            elif inner_item.layout(): # For even deeper nested layouts
                                # For simplicity, assume deleteLater on parent widget of this layout's items will suffice
                                # or that such deep nesting of layouts-within-layouts isn't used.
                                logger.warning(f"  Found a layout within a layout: {type(inner_item.layout())}. Manual clearing might be needed if issues persist.")
                                pass 
                        # The QLayout object (layout_item) itself doesn't need deleteLater.
                        # It's "deleted" when its owning QLayoutItem (item) is deleted,
                        # which happens as part of layout_to_clear.takeAt(0).
                        # We also need to ensure its parent QWidget (if any) is handled if layout_item was managing shared resources.
                        # However, typically, widgets inside are parented to the main content widget.
                    elif item.spacerItem():
                        logger.debug("Clearing spacer item from results_layout")
                        # Spacer items are just removed from the layout by takeAt(0)
                        pass
            logger.debug("_clear_results completed.")
        else:
            logger.warning("_clear_results called but self.results_layout is None or not found on known parents.")

    def handle_search_results(self, results_payload: dict): # Changed results to results_payload
        logger.debug(f"SearchWidget.handle_search_results received payload with keys: {results_payload.keys()}")
        self.all_loaded_results_payload = results_payload # Store the full payload

        # self._clear_results() # REMOVED: Clearing is done in perform_search before worker starts
        
        if self.active_filter_type == "all":
            # For "All", pass the entire payload to _display_aggregated_search_results
            self._display_aggregated_search_results(results_payload)
        else:
            # For specific tabs, get the relevant list from the payload
            items_to_display = []
            if self.active_filter_type == "tracks":
                items_to_display = results_payload.get('track_results', [])
                self._add_track_list_section(items_to_display) # Tracks have a special display
            elif self.active_filter_type == "albums":
                items_to_display = results_payload.get('album_results', [])
                self._display_categorized_search_results(items_to_display, "Albums")
            elif self.active_filter_type == "artists":
                items_to_display = results_payload.get('artist_results', [])
                self._display_categorized_search_results(items_to_display, "Artists")
            elif self.active_filter_type == "playlists":
                items_to_display = results_payload.get('playlist_results', [])
                self._display_categorized_search_results(items_to_display, "Playlists")
            
            if not items_to_display and self.active_filter_type != "tracks": # Tracks already handled
                no_results_label = QLabel(f"No {self.active_filter_type} found.")
                no_results_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.results_layout.addWidget(no_results_label)
        
        self.results_layout.addStretch() # Add stretch at the end

    def _display_aggregated_search_results(self, results_payload: dict): # Changed argument
        """Displays categorized results for the 'All' filter view using the full payload."""
        logger.debug("_display_aggregated_search_results: Processing full results_payload.")

        # self._clear_results() # Clearing is now done at the start of handle_search_results

        artist_items = list(results_payload.get('artist_results', [])) # Make copies
        album_items = list(results_payload.get('album_results', []))
        playlist_items = list(results_payload.get('playlist_results', []))
        track_items = list(results_payload.get('track_results', []))
        general_items = results_payload.get('all_results', []) # General ranking items

        if not any([artist_items, album_items, playlist_items, track_items, general_items]):
             no_results_label = QLabel("No results found.")
             no_results_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
             self.results_layout.addWidget(no_results_label)
            # self.results_layout.addStretch() # Stretch is added at the end of handle_search_results
             return

        # Determine the top result to display
        top_result_item_to_display = None
        
        # Priority: Artist > Album > Playlist > Non-track from General Search
        if artist_items:
            top_result_item_to_display = artist_items.pop(0) # Use and remove
        elif album_items:
            top_result_item_to_display = album_items.pop(0) # Use and remove
        elif playlist_items:
            top_result_item_to_display = playlist_items.pop(0) # Use and remove
        elif general_items and general_items[0].get('type') != 'track':
            # If the first general item is not a track, it can be a top result.
            # We don't remove it from general_items as general_items are not directly displayed as a category.
            top_result_item_to_display = general_items[0]

        # Add Top Result Section (if a suitable item was found)
        if top_result_item_to_display and top_result_item_to_display.get('type') != 'track':
            logger.debug(f"Top result identified: Type='{top_result_item_to_display.get('type')}', Name='{top_result_item_to_display.get('name', top_result_item_to_display.get('title', 'N/A'))}'")
            self._add_top_result_section(top_result_item_to_display)
        else:
            logger.debug("No suitable non-track top result card to display.")
            if top_result_item_to_display and top_result_item_to_display.get('type') == 'track':
                 logger.debug(f"Top item from general search was a track: '{top_result_item_to_display.get('title', 'N/A')}', will appear in tracks list.")


        # Add other sections if items exist
        self._add_results_section("Artists", artist_items, 'artist')
        self._add_results_section("Albums", album_items, 'album')
        self._add_results_section("Playlists", playlist_items, 'playlist')
        
        # Tracks have a different display style
        self._add_track_list_section(track_items)
        
        # self.results_layout.addStretch() # Stretch is added at the end of handle_search_results

    def _add_top_result_section(self, item_data: dict):
        logger.debug(f"Adding top result section for: {item_data.get('name', item_data.get('title'))}")
        if sip_is_deleted(self) or not hasattr(self, 'results_layout') or self.results_layout is None:
            logger.warning("_add_top_result_section: SearchWidget or results_layout is deleted. Skipping.")
            return

        # Re-create the container each time to ensure it's fresh
        if self.top_result_section_container is not None:
             logger.warning("_add_top_result_section: top_result_section_container was not None. Deleting old one.")
             # Clear layout before deleting widget
             if self.top_result_section_container.layout() is not None:
                while self.top_result_section_container.layout().count():
                    item = self.top_result_section_container.layout().takeAt(0)
                    widget = item.widget()
                    if widget:
                        widget.deleteLater()
             self.top_result_section_container.deleteLater()
        
        self.top_result_section_container = QWidget()
        self.top_result_section_container.setObjectName("TopResultSectionContainer")
        container_layout = QVBoxLayout(self.top_result_section_container)
        container_layout.setContentsMargins(0, 0, 0, 10) # Add some bottom margin

        title_label = QLabel("Top Result")
        title_label.setObjectName("sectionTitle") # Use existing sectionTitle style
        container_layout.addWidget(title_label)

        # Determine if the top result is an artist to pass the flag
        is_top_artist = item_data.get('type') == 'artist'
        card = SearchResultCard(item_data, is_top_artist_result=is_top_artist) # PASS THE FLAG
        card.card_selected.connect(self._handle_card_selection)
        # Only connect download if it's not a top artist result where buttons are hidden
        if not is_top_artist: # Or more broadly, if card has download_btn configured
            if hasattr(card, 'download_btn') and card.download_btn is not None: # Check if download_btn exists
                 card.download_clicked.connect(self._handle_card_download_request)
            elif item_data.get('type') == 'track': # Tracks have their own download button logic in their setup
                 card.download_clicked.connect(self._handle_card_download_request)


        container_layout.addWidget(card)
        
        self.results_layout.addWidget(self.top_result_section_container)

    def _add_results_section(self, title: str, items: list, item_type_for_view_all: str, max_items_in_scroll: int = 5):
        if sip_is_deleted(self) or not hasattr(self, 'results_layout') or self.results_layout is None:
            logger.warning(f"_add_results_section for {title}: SearchWidget or results_layout is deleted. Skipping.")
            return

        if not items:
            logger.debug(f"No items to display for section: {title}")
            return

        logger.debug(f"Adding results section: {title} with {len(items)} items.")
        section_widget = self._create_section_widget(title, items, item_type_for_view_all, horizontal=True, max_items=max_items_in_scroll)
        if section_widget:
            self.results_layout.addWidget(section_widget)
            
    def _add_track_list_section(self, tracks: list):
        if sip_is_deleted(self) or not hasattr(self, 'results_layout') or self.results_layout is None:
            logger.warning("_add_track_list_section: SearchWidget or results_layout is deleted. Skipping.")
            return
            
        if not tracks:
            logger.debug("No tracks to display in track list section for 'All' view.")
            return
        
        logger.debug(f"Adding track list section to 'All' view with {len(tracks)} tracks.")
        
        # --- START HEADER CONSTRUCTION FOR TRACKS SECTION ---
        tracks_header_widget = QWidget()
        tracks_header_layout = QHBoxLayout(tracks_header_widget)
        tracks_header_layout.setContentsMargins(0, 0, 0, 0) # No margins for the internal header layout
        tracks_header_layout.setSpacing(5)
        
        tracks_title_label = QLabel("Tracks")
        tracks_title_label.setObjectName("SearchSectionHeader") # CHANGED from sectionTitle
        tracks_header_layout.addWidget(tracks_title_label)

        # Add "View All" button for tracks if there are more tracks than the display limit (5)
        # We need the original full list of tracks from the payload to decide this, 
        # not just the `tracks` list passed to this function if it was pre-sliced.
        # For now, this function is only called from _display_aggregated_search_results,
        # where track_items is the full list for tracks.
        # Let's assume `tracks` argument here is the full list available for the current query.
        if len(tracks) > 5: # 5 is the display limit for tracks in aggregated view
            view_all_tracks_button = QPushButton("View all")
            view_all_tracks_button.setObjectName("ViewAllButton") # Use existing style
            view_all_tracks_button.setCursor(Qt.CursorShape.PointingHandCursor)
            view_all_tracks_button.clicked.connect(self._handle_view_all_tracks_clicked)
            tracks_header_layout.addWidget(view_all_tracks_button)

        tracks_header_layout.addStretch(1) # Push title and button to the left
        # REMOVED: self.results_layout.addWidget(tracks_header_widget) # Add the header to the main results layout
        # --- END HEADER CONSTRUCTION FOR TRACKS SECTION ---

        # Create a container widget that will be constrained horizontally, similar to _display_categorized_search_results
        constrained_width_container = QWidget()
        # Use a QHBoxLayout for this container to add stretches for centering
        centering_hbox = QHBoxLayout(constrained_width_container)
        centering_hbox.setContentsMargins(0,0,0,0)

        # REMOVING THE INITIAL LEFT STRETCH THAT CAUSED THE GAP
        # centering_hbox.addStretch(1) 

        # This is the widget that will actually hold the track header and list of tracks
        track_list_content_widget = QWidget()
        track_list_content_widget.setObjectName("TrackListContentWidget") # For potential specific styling
        track_list_vbox = QVBoxLayout(track_list_content_widget)
        track_list_vbox.setContentsMargins(0,0,0,0)
        track_list_vbox.setSpacing(0) # No spacing between header and track rows, or between rows

        # Add the "Tracks" title header and give it a bottom margin
        tracks_header_widget.setStyleSheet("QWidget { margin-bottom: 8px; }") # Added bottom margin
        track_list_vbox.addWidget(tracks_header_widget)

        # Create and add the column header (TRACK, ARTIST, etc.) and give it a bottom margin
        track_header = self._create_track_list_header()
        track_list_vbox.addWidget(track_header)

        # For the 'All' view, limit to a certain number of tracks, e.g., 5
        # If this method were to be reused for a dedicated 'View All Tracks' page,
        # this limit would need to be conditional or handled differently.
        tracks_to_display = tracks[:5]

        for item_data in tracks_to_display: # MODIFIED: iterate over the sliced list
            if item_data.get('type') == 'track': # Ensure it's a track
                card = SearchResultCard(item_data)
                card.card_selected.connect(self._handle_card_selection) # Though tracks usually don't have detail views
                card.download_clicked.connect(self._handle_card_download_request)
                # NEW: Connect artist and album name click signals
                card.artist_name_clicked.connect(self.artist_name_clicked_from_track.emit)
                card.album_name_clicked.connect(self.album_name_clicked_from_track.emit)
                track_list_vbox.addWidget(card)
            else:
                logger.warning(f"_add_track_list_section: Encountered non-track item in tracks list: {item_data.get('id')}, type: {item_data.get('type')}")
        
        track_list_vbox.addStretch(1) # Stretch at the end of the vertical track list

        centering_hbox.addWidget(track_list_content_widget, 15) # Content stretch
        centering_hbox.addStretch(1) # Right stretch

        self.results_layout.addWidget(constrained_width_container)

    def _create_track_list_header(self) -> QWidget:
        """Creates the header row for a track list."""
        header_widget = QWidget()
        header_widget.setObjectName("SearchTrackListHeader")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 8, 10, 8) # CHANGED from (10,5,10,5)
        header_layout.setSpacing(10)
        header_widget.setFixedHeight(35) # ADDED to match TrackListHeaderWidget

        artwork_header_label = QLabel("")
        artwork_header_label.setFixedWidth(48)
        header_layout.addWidget(artwork_header_label)

        title_header_label = QLabel("TRACK")
        title_header_label.setObjectName("SearchTrackListHeaderLabel")
        title_header_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        font = title_header_label.font() # Get current font
        font.setBold(True) # Make it bold
        title_header_label.setFont(font) # Set the new font
        header_layout.addWidget(title_header_label, 5, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        artist_header_label = QLabel("ARTIST")
        artist_header_label.setObjectName("SearchTrackListHeaderLabel")
        artist_header_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        font = artist_header_label.font()
        font.setBold(True)
        artist_header_label.setFont(font)
        header_layout.addWidget(artist_header_label, 4, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        album_header_label = QLabel("ALBUM")
        album_header_label.setObjectName("SearchTrackListHeaderLabel")
        album_header_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        font = album_header_label.font()
        font.setBold(True)
        album_header_label.setFont(font)
        header_layout.addWidget(album_header_label, 3, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        duration_header_label = QLabel("DUR.")
        duration_header_label.setObjectName("SearchTrackListHeaderLabel")
        duration_header_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        font = duration_header_label.font()
        font.setBold(True)
        duration_header_label.setFont(font)
        duration_header_label.setFixedWidth(45)
        header_layout.addWidget(duration_header_label, 0)

        return header_widget

    def _display_categorized_search_results(self, results: list, category_title: str):
        """Displays search results for a specific category (e.g., Tracks, Albums)."""
        logger.debug(f"Displaying categorized results for '{category_title}'. Number of items: {len(results)}") # Existing
        if results:
            logger.debug(f"First item in categorized results for '{category_title}': {results[0]}") # Log first item
        # self._clear_results() # REMOVED: Clearing is done in perform_search or other entry points

        if not results:
            no_results_label = QLabel(f"No {category_title.lower()} found.")
            no_results_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.results_layout.addWidget(no_results_label)
            # self.results_layout.addStretch() # Stretch is added at the end of handle_search_results
            return
        
        if category_title.lower() == "tracks":
            # Create a container widget that will be constrained horizontally
            constrained_width_container = QWidget()
            # Use a QHBoxLayout for this container to add stretches
            centering_hbox = QHBoxLayout(constrained_width_container)
            centering_hbox.setContentsMargins(0,0,0,0)

            centering_hbox.addStretch(1) # MODIFIED: Left stretch from 0 to 1 (small margin)

            # This is the widget that will actually hold the track header and list of tracks
            track_list_content_widget = QWidget()
            track_list_content_widget.setObjectName("TrackListContentWidget") # For potential specific styling
            track_list_vbox = QVBoxLayout(track_list_content_widget)
            track_list_vbox.setContentsMargins(0,0,0,0)
            track_list_vbox.setSpacing(0)

            track_header = self._create_track_list_header()
            track_list_vbox.addWidget(track_header)

            for item_data in results:
                card = SearchResultCard(item_data)
                card.card_selected.connect(self._handle_card_selection)
                card.download_clicked.connect(self._handle_card_download_request)
                # NEW: Connect artist and album name click signals for track lists
                card.artist_name_clicked.connect(self.artist_name_clicked_from_track.emit)
                card.album_name_clicked.connect(self.album_name_clicked_from_track.emit)
                track_list_vbox.addWidget(card)
            
            track_list_vbox.addStretch(1) # Stretch at the end of the vertical track list

            centering_hbox.addWidget(track_list_content_widget, 15) # MODIFIED: Content stretch from 3 to 15
            centering_hbox.addStretch(1) # MODIFIED: Right stretch remains 1 (small margin)

            self.results_layout.addWidget(constrained_width_container)

        elif category_title.lower() in ["albums", "artists", "playlists"]: # Grid views
            grid_layout = QGridLayout()
            grid_layout.setSpacing(5) # MODIFIED: Reduced spacing
            # self.results_layout.addLayout(grid_layout) # Grid added below
            row, col = 0, 0
            max_cols = 4 
            for i, item_data in enumerate(results):
                card = SearchResultCard(item_data)
                card.card_selected.connect(self._handle_card_selection)
                card.download_clicked.connect(self._handle_card_download_request)
                grid_layout.addWidget(card, row, col)
                col += 1
                if col >= max_cols:
                    col = 0
                    row += 1
            self.results_layout.addLayout(grid_layout) # Add the populated grid
            # self.results_layout.addStretch() # Stretch is added at the end of handle_search_results
        else: # Fallback for unknown category_title, though should not happen with current filters
            logger.warning(f"Unknown category title for display: {category_title}")
            for item_data in results: # Display as simple vertical list
                card = SearchResultCard(item_data)
                card.card_selected.connect(self._handle_card_selection)
                card.download_clicked.connect(self._handle_card_download_request)
                self.results_layout.addWidget(card)
        # self.results_layout.addStretch() # Stretch is added at the end of handle_search_results


    def _create_section_widget(self, title: str, items: list, item_type_for_view_all: str, horizontal: bool = True, max_items: int = 5):
        """Creates a widget for a section of search results (e.g., Top Result, Tracks, Albums)."""
        section_frame = QFrame()
        section_frame.setObjectName(f"SearchSectionFrame_{title.replace(' ', '')}")
        main_section_layout = QVBoxLayout(section_frame) 
        main_section_layout.setContentsMargins(0, 5, 0, 5) # Add some vertical margin to the whole section frame
        main_section_layout.setSpacing(2) # Reduce spacing between header and content

        # --- START HEADER CONSTRUCTION ---
        header_widget = QWidget()
        header_widget.setMinimumHeight(40) # Increased for more vertical padding
        
        overall_header_layout = QHBoxLayout(header_widget) 
        overall_header_layout.setContentsMargins(0,0,0,0)
        overall_header_layout.setSpacing(5) # Spacing between L-part, stretch, R-part

        # 1. Left Part (Title & View All Button)
        left_part_widget = QWidget()
        # Try to make this part take what it needs but not excessively expand
        left_part_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        left_part_layout = QHBoxLayout(left_part_widget)
        left_part_layout.setContentsMargins(0,0,0,0)
        left_part_layout.setSpacing(5) # Spacing between title and view_all_button

        section_label = QLabel(title)
        section_label.setObjectName("SearchSectionHeader")
        # Make label expand but also elide if not enough space
        section_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        section_label.setTextFormat(Qt.TextFormat.PlainText) # Ensure elision works, RichText can interfere
        section_label.setWordWrap(False) # Ensure it tries to stay on one line for elision
        # Elide text with '...' if it's too long for the available space
        # This requires the label to have a bounded width, which the layout should provide.
        # The actual elision is handled by Qt when painting the label if text overflows.

        # Add section_label first. Its Expanding size policy allows it to take available space.
        left_part_layout.addWidget(section_label, 0, Qt.AlignmentFlag.AlignVCenter)

        if item_type_for_view_all and (len(items) > max_items or title == "Top Result"): 
            view_all_button = QPushButton("View all")
            view_all_button.setObjectName("ViewAllButton")
            view_all_button.setCursor(Qt.CursorShape.PointingHandCursor)
            # Connect the button's clicked signal
            view_all_button.clicked.connect(lambda checked=False, cat=item_type_for_view_all: self._handle_view_all_clicked(cat))
            # Add View All button next (to the right of the title)
            left_part_layout.addWidget(view_all_button, 0, Qt.AlignmentFlag.AlignVCenter) 
        
        # Add a stretch to push the title and button (if any) to the left within left_part_widget
        left_part_layout.addStretch(1)

        overall_header_layout.addWidget(left_part_widget, 1) 

        # 2. Central Stretch
        overall_header_layout.addStretch(0) # Minimize central stretch

        # 3. Right Part (Scroll Arrows)
        right_part_widget = QWidget()
        # Ensure this part gets its required space for the fixed-width arrows
        right_part_widget.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        right_part_layout = QHBoxLayout(right_part_widget)
        right_part_layout.setContentsMargins(0,0,0,0)
        right_part_layout.setSpacing(5) # Spacing between arrows

        left_arrow = QPushButton() # Removed text
        left_arrow.setObjectName("ScrollArrowButtonLeft") # Unique name for potential specific styling
        left_arrow.setFixedSize(22, 22)
        left_arrow.setIcon(QIcon("C:/Users/HOME/Documents/deemusic/src/ui/assets/left scroll arrow.png"))
        left_arrow.setIconSize(QSize(14, 14)) # Adjusted icon size

        right_arrow = QPushButton() # Removed text
        right_arrow.setObjectName("ScrollArrowButtonRight") # Unique name
        right_arrow.setFixedSize(22, 22)
        right_arrow.setIcon(QIcon("C:/Users/HOME/Documents/deemusic/src/ui/assets/right scroll arrow.png"))
        right_arrow.setIconSize(QSize(14, 14)) # Adjusted icon size

        # Define QSS for the ICON scroll arrow buttons
        scroll_arrow_icon_qss = '''
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 11px; /* for hover effect shape */
            }
            QPushButton:hover {
                background-color: #f0f0f0; /* Light grey background on hover */
            }
            QPushButton:disabled {
                background-color: transparent;
                /* Qt will typically make the icon look disabled (e.g., more transparent) */
            }
        '''
        left_arrow.setStyleSheet(scroll_arrow_icon_qss)
        right_arrow.setStyleSheet(scroll_arrow_icon_qss)

        if horizontal:
            right_part_layout.addWidget(left_arrow)
            right_part_layout.addWidget(right_arrow)
            overall_header_layout.addWidget(right_part_widget) 
        else:
            left_arrow.hide() # Ensure hidden if not horizontal, though not added to layout
            right_arrow.hide()
        
        main_section_layout.addWidget(header_widget) # Add the constructed header_widget
        # --- END HEADER CONSTRUCTION ---

        # --- START CONTENT AREA CONSTRUCTION ---
        if horizontal:
            current_scroll_area = QScrollArea()
            current_scroll_area.setWidgetResizable(True)
            current_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff) 
            current_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  
            current_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
            # Try to constrain the scroll area height to fit one row of cards tightly
            # Approximate height: Artwork (190) + Info Container (~45-50) + Card Margins/Spacing (~20-25)
            # Let's try a fixed height, e.g., 270px. This might need adjustment.
            current_scroll_area.setFixedHeight(270) 

            scroll_content_widget = QWidget()
            scroll_content_layout = QHBoxLayout(scroll_content_widget)
            scroll_content_layout.setContentsMargins(0,0,0,0)
            scroll_content_layout.setSpacing(10) 

            for item_data in items:
                card = SearchResultCard(item_data)
                card.card_selected.connect(self._handle_card_selection)
                card.download_clicked.connect(self._handle_card_download_request)
                scroll_content_layout.addWidget(card)
            
            scroll_content_layout.addStretch() 
            scroll_content_widget.setLayout(scroll_content_layout)
            current_scroll_area.setWidget(scroll_content_widget)
            
            # Connections for arrows (now part of header, but instance is available)
            if horizontal: # Re-check, as arrows are only in header if horizontal
                left_arrow.clicked.connect(lambda checked=False, sa=current_scroll_area: self.scroll_horizontal_area(sa, -1))
                right_arrow.clicked.connect(lambda checked=False, sa=current_scroll_area: self.scroll_horizontal_area(sa, 1))
                self.update_scroll_arrows_state(current_scroll_area, left_arrow, right_arrow)
                current_scroll_area.horizontalScrollBar().valueChanged.connect(\
                    lambda value, sa=current_scroll_area, la=left_arrow, ra=right_arrow: self.update_scroll_arrows_state(sa, la, ra)\
                )
            main_section_layout.addWidget(current_scroll_area) \
            
        else: # Vertical layout (typically for Tracks)
            content_widget = QWidget() 
            content_layout = QVBoxLayout(content_widget)
            content_layout.setContentsMargins(0,0,0,0) 

            if title.lower() == "tracks":
                track_header = self._create_track_list_header()
                content_layout.addWidget(track_header)

            # Slice items to display based on max_items for vertical lists
            # The "Top Result" section is handled separately and doesn't typically use this part with a list.
            items_to_display = items[:max_items]

            for item_data in items_to_display: # Iterate over the sliced list
                card = SearchResultCard(item_data)
                card.card_selected.connect(self._handle_card_selection)
                card.download_clicked.connect(self._handle_card_download_request)
                content_layout.addWidget(card)
            
            main_section_layout.addWidget(content_widget)
        # --- END CONTENT AREA CONSTRUCTION ---
        return section_frame

    def scroll_horizontal_area(self, scroll_area: QScrollArea, direction: int):
        """Scrolls the QScrollArea horizontally."""
        h_bar = scroll_area.horizontalScrollBar()
        # A single step often corresponds to one pixel. We want to scroll by one card width approx.
        # Assuming cards are around 150-200px wide. A step of 150 should be reasonable.
        single_step = h_bar.singleStep() if h_bar.singleStep() > 1 else 150 
        page_step = h_bar.pageStep() if h_bar.pageStep() > single_step else single_step * 2 # A larger step

        current_value = h_bar.value()
        if direction < 0: # Scroll left
            h_bar.setValue(current_value - page_step)
        else: # Scroll right
            h_bar.setValue(current_value + page_step)
        
        # update_scroll_arrows_state will be called by valueChanged signal

    def update_scroll_arrows_state(self, scroll_area: QScrollArea, left_arrow: QPushButton, right_arrow: QPushButton):
        """Updates the enabled state of scroll arrows based on scrollbar position."""
        h_bar = scroll_area.horizontalScrollBar()
        left_arrow.setEnabled(h_bar.value() > h_bar.minimum())
        right_arrow.setEnabled(h_bar.value() < h_bar.maximum())

    def _handle_view_all_clicked(self, category_to_view: str):
        """Handles the 'View All' button click for a category."""
        logger.info(f"View All clicked for category: {category_to_view}")
        # Filter self.all_loaded_results for the specific category and display them
        # This assumes self.all_loaded_results contains everything from the last main search query.
        
        category_results = [item for item in self.all_loaded_results if item.get('type') == category_to_view]
        
        # Update filter button style to show which category is being viewed, if desired, or keep "All" active
        # For now, we'll just display the results in a categorized view without changing the top filter buttons.
        # The back button in _display_categorized_search_results will handle returning.
        self._display_categorized_search_results(category_results, f"{category_to_view.capitalize()}s")

    def _handle_card_selection(self, item_data: dict):
        """Handles the card_selected signal from a SearchResultCard."""
        logger.info(f"[SearchWidget] _handle_card_selection called with item: {item_data.get('title', item_data.get('name', 'Unknown'))}") # DEBUG
        item_type = item_data.get('type')
        item_id = item_data.get('id')
        logger.debug(f"SearchWidget: Card selected. Type: {item_type}, ID: {item_id}")

        if item_type == 'playlist' and item_id is not None:
            logger.info(f"SearchWidget: Playlist selected with ID: {item_id}. Emitting signal.")
            self.playlist_selected.emit(item_id)
        elif item_type == 'album':
            logger.debug(f"SearchWidget: Album card selected: ID {item_id}, Title: {item_data.get('title', 'N/A')}")
            self.album_selected.emit(item_id)
        elif item_type == 'artist':
            logger.debug(f"SearchWidget: Artist card selected: ID {item_id}, Title: {item_data.get('title', 'N/A')}")
            self.artist_selected.emit(item_id)
        else:
            logger.warning(f"Search result card clicked for unknown type: {item_type}")

    def handle_search_error(self, error_message: str):
        """Handle errors from the search worker."""
        logger.error(f"Search Error: {error_message}")
        # You might want to display this error to the user, e.g., in a status bar
        # For now, just log it and clear results
        self._clear_results()
        placeholder_label = QLabel(f"Search failed: {error_message}")
        placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.results_layout.addWidget(placeholder_label)

    def download_item(self, item_data: dict):
        """Initiate download for the selected item."""
        item_id = item_data.get('id')
        item_type = item_data.get('type')

        if not item_id or not item_type:
            logger.error(f"Download request missing item_id or item_type: {item_data}")
            return

        logger.info(f"Download requested for item ID: {item_id}, Type: {item_type}")

        try:
            if item_type == 'track':
                self.download_manager.download_track(item_id)
            elif item_type == 'album':
                # For albums, first fetch album details to get all track IDs
                logger.debug(f"Fetching album details for album ID: {item_id} to get track list.")
                album_details = self.deezer_api.get_album_details_sync(item_id) # Use the synchronous version
                
                if album_details and 'tracks' in album_details['tracks']:
                    track_ids = [track.get('id') for track in album_details['tracks']['data'] if track.get('id')]
                    if track_ids:
                        logger.info(f"Queueing album download for ID: {item_id} with {len(track_ids)} tracks.")
                        self.download_manager.download_album(item_id, track_ids)
                    else:
                        logger.error(f"No track IDs found for album {item_id} after fetching details.")
                        # Optionally, inform the user via a signal or UI update
                else:
                    logger.error(f"Failed to get track list for album {item_id}. Details: {album_details}")
                    # Optionally, inform the user
            elif item_type == 'playlist':
                # For playlists, similar to albums, get playlist details then tracks
                logger.debug(f"Fetching playlist details for playlist ID: {item_id}")
                # Assuming a similar method exists or needs to be added in DeezerAPI for playlists
                # For now, let's assume playlist_details contains tracks.data like albums
                # playlist_details = self.deezer_api.get_playlist_details_sync(item_id) # Placeholder
                # if playlist_details and 'tracks' in playlist_details and 'data' in playlist_details['tracks']:
                #     track_ids = [track.get('id') for track in playlist_details['tracks']['data'] if track.get('id')]
                #     playlist_title = playlist_details.get('title', 'Unknown Playlist')
                #     if track_ids:
                #         self.download_manager.download_playlist(item_id, playlist_title, track_ids)
                #     else:
                #         logger.error(f"No track IDs found for playlist {item_id}")
                # else:
                #    logger.error(f"Failed to get track list for playlist {item_id}")
                logger.warning(f"Playlist download not fully implemented yet for ID: {item_id}")
                # Placeholder: Call download_playlist if you have a way to get track_ids and title
                # self.download_manager.download_playlist(item_id, "Playlist Title Placeholder", [track_ids_list])
            elif item_type == 'artist':
                logger.info(f"Downloading all content for artist '{item_data.get('name')}' (ID: {item_id}). This will include albums, singles, and EPs.")
                asyncio.create_task(self._download_artist_content(artist_id=item_id, artist_name=item_data.get('name')))
            else:
                logger.warning(f"Download not supported for item type: {item_type}")
        except Exception as e:
            error_msg = f"Download failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            # Emit a signal or update UI to inform the user about the failure
            # For example, if you have a status bar:
            # self.status_bar.showMessage(error_msg, 5000) # Show for 5 seconds

    def play_item(self, item_data: dict):
        """Handle play action for the selected item."""
        # TODO: Implement playback through MusicPlayer service
        logger.warning(f"Play item called for {item_data.get('title')}, but play feature is removed.")
        pass 

    def display_view_all_category(self, items: list, category_title: str):
        """Displays a list of items under a given category title, typically from a 'View All' action."""
        logger.info(f"[SearchWidget] Displaying 'View All' category: '{category_title}' with {len(items)} items.")

        self._clear_results()
        # self.current_filter = None # REMOVING: This was for active filter type, not general search context
        # self._update_filter_button_styles(None) # REMOVING: Don't change active filter buttons

        # Show View All title and hide filter panel
        if hasattr(self, 'view_all_title_label'):
            self.view_all_title_label.setText(f"Showing All {category_title}")
            self.view_all_title_label.setVisible(True)
        if hasattr(self, 'filter_buttons_panel'):
            self.filter_buttons_panel.setVisible(False)
        # Ensure back button is visible for this view
        self.set_back_button_visibility(True)

        if not items:
            no_results_label = QLabel(f"No items to display for {category_title}.")
            no_results_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.results_layout.addWidget(no_results_label)
            return

        # Create a single section for these items
        # Based on _create_section_widget but simplified (no "View All" button in this view)
        
        section_frame = QFrame()
        section_frame.setObjectName(f"SearchSectionFrame_{category_title.replace(' ', '')}")
        section_layout = QVBoxLayout(section_frame)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(5) # Spacing between header and content for this section

        # Content Area (Grid of Cards) - REPLACED horizontal scroll area
        content_container_widget = QWidget() 
        grid_layout = QGridLayout(content_container_widget)
        grid_layout.setContentsMargins(0, 0, 0, 0) 
        grid_layout.setSpacing(10) # Spacing between cards

        row, col = 0, 0
        # Using 4 columns for the grid, similar to other categorized views
        max_cols = 4 
        for item_data in items:
            card = SearchResultCard(item_data)
            card.card_selected.connect(self._handle_card_selection)
            card.download_clicked.connect(self._handle_card_download_request)
            grid_layout.addWidget(card, row, col)
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
        
        # The grid layout will handle alignment. If the last row is not full, 
        # items will be aligned to the left by default.
        # Adding a stretch to the grid layout might be needed if items should not expand.
        # For now, let grid manage card sizes.

        # Wrap the grid in a QHBoxLayout to center it if it's not full-width
        centering_grid_container = QWidget()
        centering_grid_layout = QHBoxLayout(centering_grid_container)
        centering_grid_layout.setContentsMargins(0,0,0,0)
        centering_grid_layout.addStretch(1) # Add stretch to the left
        centering_grid_layout.addWidget(content_container_widget) # Add the grid itself
        centering_grid_layout.addStretch(1) # Add stretch to the right

        section_layout.addWidget(centering_grid_container) # Add the container with the centered grid
        
        self.results_layout.addWidget(section_frame)
        self.results_layout.addStretch(1) # Pushes content to the top

        if hasattr(self, 'filter_buttons_panel'): # Hide filters for this special view
            self.filter_buttons_panel.hide()

        # Ensure the main results area is scrolled to the top
        if self.results_area:
            self.results_area.verticalScrollBar().setValue(0)

    def _handle_view_all_tracks_clicked(self):
        """Handles the 'View All' button click specifically for the tracks section."""
        logger.info("View All tracks clicked. Switching to Tracks filter.")
        if self.current_query: # Ensure there is a query to search for
            self.active_filter_type = "tracks"
            self._update_filter_button_styles("tracks")
            self.perform_search() # This will use the current_query and new active_filter_type
        else:
            logger.warning("_handle_view_all_tracks_clicked: No current query to perform search with.")

    # CORRECTLY PLACED _handle_card_download_request as a class method
    def _handle_card_download_request(self, item_data: dict):
        item_type = item_data.get('type')
        item_id = item_data.get('id')
        item_title = item_data.get('title', item_data.get('name', 'Unknown Item'))

        if not self.download_manager:
            logger.error("DownloadManager not available in SearchWidget.")
            return

        logger.info(f"[SearchWidget] Download requested for: {item_title} (ID: {item_id}, Type: {item_type})")

        can_proceed = True
        if not item_id:
            logger.error(f"Cannot download {item_type} '{item_title}' because it is missing an ID.")
            can_proceed = False

        if not can_proceed:
            return

        if item_type == 'track':
            logger.debug(f"Calling DownloadManager._queue_individual_track_download for track ID: {item_id} with item_data: {item_data}")
            asyncio.create_task(self.download_manager._queue_individual_track_download(track_id=item_id, item_type='track', track_details=item_data))
        elif item_type == 'album':
            logger.info(f"Calling DownloadManager.download_album for album '{item_title}' (ID: {item_id}). Tracks will be fetched by DM.")
            asyncio.create_task(self.download_manager.download_album(album_id=item_id, track_ids=[]))
        elif item_type == 'playlist':
            playlist_specific_title = item_data.get('title', item_title)
            logger.info(f"Calling DownloadManager.download_playlist for playlist '{playlist_specific_title}' (ID: {item_id}). Tracks will be fetched by DM.")
            asyncio.create_task(self.download_manager.download_playlist(playlist_id=item_id, playlist_title=playlist_specific_title, track_ids=[]))
        elif item_type == 'artist':
            logger.warning(f"Downloading entire artist '{item_title}' (ID: {item_id}) is not directly supported. User should browse artist content.")
        else:
            logger.warning(f"Download not implemented for unknown item type: {item_type} (Title: '{item_title}', ID: {item_id})")

    def _create_and_load_card(self, item_data, parent_widget, on_card_click, on_download_click=None):
        """Centralized helper to create cards with proper image loading."""
        try:
            # Create card
            card = SearchResultCard(item_data, parent=parent_widget)
            
            # Connect signals
            if on_card_click:
                card.card_selected.connect(on_card_click)
            if on_download_click:
                card.download_clicked.connect(on_download_click)
            
            # Load artwork with higher quality settings
            # Force immediate artwork loading
            card.load_artwork()
            
            return card
        except Exception as e:
            logger.error(f"[ArtistDetail] Error creating card for {item_data.get('title', 'unknown item')}: {e}")
            return None

    async def _download_artist_content(self, artist_id, artist_name):
        """Download all albums, singles, and EPs for an artist."""
        try:
            logger.info(f"Starting download of all content for artist '{artist_name}' (ID: {artist_id})")
            
            # Fetch all albums for the artist (this includes albums, singles, and EPs)
            albums = await self.deezer_api.get_artist_albums_generic(artist_id, limit=500)
            
            if not albums:
                logger.warning(f"No albums found for artist '{artist_name}' (ID: {artist_id})")
                return
            
            logger.info(f"Found {len(albums)} releases for artist '{artist_name}'. Starting downloads...")
            
            # Download each album
            for album in albums:
                album_id = album.get('id')
                album_title = album.get('title', 'Unknown Album')
                album_type = album.get('record_type', 'album')  # Can be 'album', 'single', 'ep'
                
                if album_id:
                    logger.info(f"Downloading {album_type}: '{album_title}' (ID: {album_id}) by {artist_name}")
                    # Use the existing download_album method which will fetch tracks automatically
                    asyncio.create_task(self.download_manager.download_album(album_id=album_id, track_ids=[]))
                else:
                    logger.warning(f"Skipping album '{album_title}' - missing ID")
            
            logger.info(f"Initiated downloads for all {len(albums)} releases by artist '{artist_name}'")
            
        except Exception as e:
            logger.error(f"Error downloading artist content for '{artist_name}' (ID: {artist_id}): {e}", exc_info=True)
