"""
Album Detail Page for DeeMusic application.
Displays tracks within a selected album.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, # QTableWidget, - Removed
    # QTableWidgetItem, # - Removed
    QPushButton, QHBoxLayout, # QHeaderView, QAbstractItemView, # - Removed
    QFrame, QStackedLayout, QGridLayout,
    QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QRunnable, QThreadPool, QSize, pyqtSlot, QEvent
from PyQt6.QtGui import QIcon, QPixmap, QImage, QPainter, QColor, QPen
import logging
import os 
# import requests # No longer directly needed here after removing ArtworkLoaderWorker
# from io import BytesIO # No longer directly needed here
import asyncio 

# Import SearchResultCard
from src.ui.search_widget import SearchResultCard
from src.ui.track_list_header_widget import TrackListHeaderWidget # ADDED
from src.utils.image_cache import get_image_from_cache, save_image_to_cache # For main album cover
from src.utils.icon_utils import get_icon # ADDED

logger = logging.getLogger(__name__)

# --- ArtworkLoaderWorker and ArtworkSignals are removed as SearchResultCard handles its own image loading ---

# --- AlbumTrackCellWidget is removed as SearchResultCard will be used ---

class AlbumDetailPage(QWidget):
    """
    A widget to display the tracks of a selected album.
    """
    main_album_cover_loaded = pyqtSignal(QPixmap) 
    back_requested = pyqtSignal() 
    track_selected_for_download = pyqtSignal(dict) 
    track_selected_for_playback = pyqtSignal(dict) # ADDED: For playing a track from the album
    album_selected_from_track = pyqtSignal(int) 
    artist_selected_from_track = pyqtSignal(int) 
    artist_name_clicked_from_track = pyqtSignal(int)  # Emits artist_id when artist name clicked in track
    album_name_clicked_from_track = pyqtSignal(int)   # Emits album_id when album name clicked in track
    request_full_album_download = pyqtSignal(dict, list) # ADDED: For downloading the full album
    _on_main_cover_artwork_error_signal = pyqtSignal(str) # Moved to class level

    def __init__(self, deezer_api, download_manager, parent=None):
        super().__init__(parent)
        self.deezer_api = deezer_api
        self.download_manager = download_manager
        self.current_album_id = None
        self.current_album_data = None 
        self.main_album_cover_loaded.connect(self._set_main_album_cover)
        self.thread_pool = QThreadPool.globalInstance() # For main album cover loading

        self._setup_ui()

    def _setup_ui(self):
        main_page_layout = QVBoxLayout(self)
        main_page_layout.setContentsMargins(10, 10, 10, 10) # Keep page margins
        main_page_layout.setSpacing(0) # Main layout spacing 0

        # --- Back Button (remains the same) ---
        back_button_layout = QHBoxLayout()
        back_button_layout.setContentsMargins(0,0,0,10) # Standardized margins for back button container
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
        # header_widget.setObjectName("album_header_widget") # Optional: if specific QSS needed for this container
        # header_widget.setFixedHeight(200) # Let content define height or use min height
        header_widget.setMinimumHeight(180) # Ensure some minimum space
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 0, 10, 10) # Left/Right 10, Bottom 10, Top 0 (covered by back button's bottom margin)
        header_layout.setSpacing(20) # Spacing between image and text block
        header_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop) # Align content to top-left

        # Album Cover Container (changed from QLabel to QWidget to hold layout for button)
        self.album_cover_container = QWidget()
        self.album_cover_container.setFixedSize(160, 160)
        self.album_cover_container.setObjectName("album_page_image_container") # Optional: for styling container
        
        cover_layout = QGridLayout(self.album_cover_container) # Layout for the cover image and overlay button
        cover_layout.setContentsMargins(0,0,0,0)

        self.album_cover_label = QLabel() # No parent initially, will be added to cover_layout
        self.album_cover_label.setFixedSize(160, 160)
        self.album_cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.album_cover_label.setObjectName("album_page_image")
        # self.album_cover_label.installEventFilter(self) # Event filter REMOVED from label
        self.album_cover_container.installEventFilter(self) # Event filter ADDED to container
        cover_layout.addWidget(self.album_cover_label, 0, 0)
        
        header_layout.addWidget(self.album_cover_container)

        # Download button (now child of album_cover_container, added to its layout)
        self.album_download_button = QPushButton() # No parent initially
        self.album_download_button.setObjectName("AlbumCoverDownloadButton")
        download_icon = get_icon("download.png")
        if download_icon:
            self.album_download_button.setIcon(download_icon)
            self.album_download_button.setIconSize(QSize(24, 24)) # Consistent icon size
            self.album_download_button.setText("") # Explicitly clear text if icon is present
        else:
            self.album_download_button.setText("DL")
            logger.warning("Album download button icon not found.")
        self.album_download_button.setFixedSize(QSize(40, 40)) # Consistent button size
        self.album_download_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.album_download_button.setToolTip("Download Album")
        self.album_download_button.setFocusPolicy(Qt.FocusPolicy.NoFocus) # Added for consistency
        self.album_download_button.clicked.connect(self._trigger_full_album_download)
        self.album_download_button.setVisible(False)
        cover_layout.addWidget(self.album_download_button, 0, 0, Qt.AlignmentFlag.AlignCenter) # Add to layout, centered

        # Vertical layout for album text details (NEW STRUCTURE)
        album_text_details_vbox = QVBoxLayout()
        album_text_details_vbox.setContentsMargins(0, 0, 0, 0)
        album_text_details_vbox.setSpacing(5) # Spacing between text elements

        # Album Type Label (e.g., "ALBUM") - styled small
        self.album_type_label = QLabel("ALBUM") # Static text
        self.album_type_label.setObjectName("album_page_type_label") # For QSS (e.g., font-size: 10pt; color: #888;)
        album_text_details_vbox.addWidget(self.album_type_label)

        # Album Title Label (Main Title) - styled large and bold
        self.album_title_label = QLabel("Album Title") 
        self.album_title_label.setObjectName("album_page_name_label") # For QSS (e.g., font-size: 18pt; font-weight: bold;)
        self.album_title_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.album_title_label.setWordWrap(True) # Allow title to wrap
        album_text_details_vbox.addWidget(self.album_title_label)

        # Artist Name Label - styled as subtitle
        self.album_artist_label = QLabel("By Artist Name")
        self.album_artist_label.setObjectName("album_page_subtitle_label") # For QSS (e.g., font-size: 11pt; color: #555;)
        self.album_artist_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.album_artist_label.setWordWrap(True)
        album_text_details_vbox.addWidget(self.album_artist_label)

        # Album Stats (Tracks, Duration, Release Date) - styled as smaller subtitle
        self.album_stats_label = QLabel("Tracks: 0 | Duration: 0m | Released: YYYY-MM-DD")
        self.album_stats_label.setObjectName("album_page_meta_label") # For QSS (e.g., font-size: 9pt; color: #777;)
        album_text_details_vbox.addWidget(self.album_stats_label)

        album_text_details_vbox.addStretch(1) # Push text content to the top of its vbox

        header_layout.addLayout(album_text_details_vbox, 1) # Text details take remaining horizontal space
        # header_layout.addStretch(1) # Removed: Let the text details vbox take space via stretch factor 1

        main_page_layout.addWidget(header_widget)

        # --- Track List Header (remains the same) ---
        self.track_header = TrackListHeaderWidget(self)
        main_page_layout.addWidget(self.track_header)

        # --- Track List Area (remains the same) ---
        self.track_list_scroll_area = QScrollArea()
        self.track_list_scroll_area.setWidgetResizable(True)
        self.track_list_scroll_area.setObjectName("album_track_list_scroll_area")
        
        self.track_list_content_widget = QWidget()
        self.tracks_layout = QVBoxLayout(self.track_list_content_widget)
        self.tracks_layout.setContentsMargins(0, 5, 0, 5)
        self.tracks_layout.setSpacing(5)
        self.tracks_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.track_list_scroll_area.setWidget(self.track_list_content_widget)
        main_page_layout.addWidget(self.track_list_scroll_area, 1)

        logger.debug("AlbumDetailPage UI setup complete with new header style.")

    def eventFilter(self, source, event): # ADDED: Handle hover events for album cover
        if source is self.album_cover_container: # MODIFIED: Hover on the container
            if event.type() == QEvent.Type.Enter:
                if self.current_album_data: 
                    self.album_download_button.setVisible(True)
                    self.album_download_button.setEnabled(True)
                    # self._position_download_button() # REMOVED - Handled by layout
                    self.album_download_button.raise_() 
                else:
                    self.album_download_button.setVisible(False)
            elif event.type() == QEvent.Type.Leave:
                # Check if the mouse is still within the bounds of a child widget (like the button itself)
                # This simple check might not be enough if the button is exactly the same size
                # A more robust way is to check if QCursor.pos() is still within self.album_cover_container.geometry()
                # For now, let's assume if the leave event is for the container, we hide.
                # The flickering happens if the button itself causes a leave event for the label, then an enter.
                # By putting the filter on the container, this should be more stable.
                self.album_download_button.setVisible(False)
        return super().eventFilter(source, event)

    def _emit_back_request(self): # ADDED
        self.back_requested.emit()

    def set_loading_state(self):
        """Set the page to show a loading state immediately for responsive navigation."""
        self.album_title_label.setText("Loading album...")
        self.album_artist_label.setText("")
        self.album_stats_label.setText("")
        self.album_type_label.setText("ALBUM") # Set default type
        self._set_placeholder_main_album_cover()
        self._clear_track_list()
        self.album_download_button.setVisible(False)

    async def load_album(self, album_id: int):
        logger.info(f"[AlbumDetail] Attempting to load album with ID: {album_id}")
        if not self.deezer_api:
            logger.error("[AlbumDetail] DeezerAPI not initialized.")
            self.album_title_label.setText("Error: API Service unavailable")
            self.album_artist_label.setText("")
            self.album_stats_label.setText("")
            self.album_type_label.setText("ALBUM") # Ensure type label is reset
            self._clear_track_list()
            return

        if not album_id:
            logger.error("[AlbumDetail] load_album called with no album_id.")
            self.album_title_label.setText("Error: Album ID missing")
            self.album_artist_label.setText("")
            self.album_stats_label.setText("")
            self.album_type_label.setText("ALBUM")
            self._clear_track_list()
            return

        self.current_album_id = album_id
        # Loading state is already set by set_loading_state() for immediate UI response

        try:
            album_details = await self.deezer_api.get_album_details(album_id)
            if not album_details or album_details.get('error'):
                error_msg = album_details.get('error', {}).get('message', 'Failed to fetch album details')
                logger.error(f"[AlbumDetail] Error loading album details for ID {album_id}: {error_msg}")
                self.album_title_label.setText(f"Error: {error_msg}")
                self.album_artist_label.setText("")
                self.album_stats_label.setText("")
                return

            self.current_album_data = album_details
            self.album_title_label.setText(album_details.get('title', 'N/A'))
            
            # Correctly set album type (static for album page)
            self.album_type_label.setText(album_details.get('record_type', 'ALBUM').upper()) 

            artist_name_parts = []
            if album_details.get('artist'): # Single artist structure
                artist_name_parts.append(album_details['artist'].get('name', 'N/A'))
            elif album_details.get('artists') and isinstance(album_details['artists'], list): # Multiple artists
                for art in album_details['artists']:
                    artist_name_parts.append(art.get('name', 'N/A'))
            
            if not artist_name_parts: artist_name_parts.append('Unknown Artist')
            self.album_artist_label.setText("By " + ", ".join(artist_name_parts))

            num_tracks = album_details.get('nb_tracks', 0)
            total_duration_sec = album_details.get('duration', 0)
            release_date_str = album_details.get('release_date', 'N/A')
            # Try to format release_date if it's YYYY-MM-DD
            try:
                from datetime import datetime
                if release_date_str and release_date_str != 'N/A':
                    dt_obj = datetime.strptime(release_date_str, '%Y-%m-%d')
                    release_date_formatted = dt_obj.strftime('%B %d, %Y') # e.g., August 23, 2024
                else:
                    release_date_formatted = 'N/A'
            except ValueError:
                release_date_formatted = release_date_str # Keep original if parsing fails

            self.album_stats_label.setText(f"{num_tracks} songs • {self._format_duration(total_duration_sec)} • Released: {release_date_formatted}")

            cover_url = album_details.get('cover_xl') or album_details.get('cover_big') or album_details.get('cover_medium')
            if cover_url:
                self._load_main_album_cover(cover_url)
            else:
                self._set_placeholder_main_album_cover()

            await self._fetch_and_display_tracks(album_id, album_details)

        except Exception as e:
            logger.error(f"[AlbumDetail] General error loading album {album_id}: {e}", exc_info=True)
            self.album_title_label.setText("Error loading album.")
            self.album_artist_label.setText("")
            self.album_stats_label.setText("")
            self._show_track_load_error(f"An error occurred: {e}")
            self.album_download_button.setVisible(False)

    async def _fetch_and_display_tracks(self, album_id: int, album_details_for_card_enrichment: dict):
        """Helper function to fetch tracks and update UI, including download button state."""
        tracks_data = await self.deezer_api.get_album_tracks(album_id)
        
        if tracks_data: # Directly a list
            logger.info(f"[AlbumDetail] Received {len(tracks_data)} tracks for album {album_id}.")
            self._clear_track_list() # Clear before adding new ones
            for track_data in tracks_data:
                if not isinstance(track_data, dict):
                    logger.warning(f"[AlbumDetail] Skipping non-dict track item: {track_data}")
                    continue
                
                if 'album' not in track_data:
                    track_data['album'] = {
                        'id': album_details_for_card_enrichment.get('id'),
                        'title': album_details_for_card_enrichment.get('title'),
                        'cover_small': album_details_for_card_enrichment.get('cover_small'),
                        # Ensure 'artist' is also present if SearchResultCard expects it at track_data['album']['artist']
                    }
                if 'artist' not in track_data: # Ensure top-level artist for SearchResultCard if it expects it
                    track_data['artist'] = album_details_for_card_enrichment.get('artist', {})
                
                if 'type' not in track_data:
                    track_data['type'] = 'track'

                # Create SearchResultCard for the track, ensure show_duration=True
                card = SearchResultCard(track_data, show_duration=True) # MODIFIED: show_duration=True
                card.card_selected.connect(self._handle_track_card_selected)
                card.download_clicked.connect(self._handle_track_download_selected)
                # NEW: Connect artist and album name click signals
                card.artist_name_clicked.connect(self.artist_name_clicked_from_track.emit)
                card.album_name_clicked.connect(self.album_name_clicked_from_track.emit)
                # LEGACY: Also connect to the old signal names for backward compatibility
                card.artist_name_clicked.connect(self.artist_selected_from_track.emit)
                card.album_name_clicked.connect(self.album_selected_from_track.emit)
                self.tracks_layout.addWidget(card)
            
            self.tracks_layout.addStretch(1)
            # self.album_download_button.setVisible(True) # Visibility now handled by hover
            # self.album_download_button.setEnabled(True)
            # No direct call to _update_download_button_state for visibility here
            # Its enabled state will be checked by hover if current_album_data is set.
        elif isinstance(tracks_data, dict) and tracks_data.get('error'):
            error_msg = tracks_data.get('error', {}).get('message', 'Failed to fetch tracks')
            logger.error(f"[AlbumDetail] Error fetching tracks for album {album_id}: {error_msg}")
            self._show_track_load_error(f"Could not load tracks: {error_msg}")
        else:
            logger.warning(f"[AlbumDetail] No tracks found or unexpected data for album {album_id}.")
            self._show_track_load_error("No tracks found for this album.")
            # self.album_download_button.setVisible(True) 
            # self.album_download_button.setEnabled(False) # Hover handles visibility and enabled state

    def _clear_track_list(self):
        """Clears all widgets from the tracks_layout."""
        if hasattr(self, 'tracks_layout') and self.tracks_layout is not None:
            while self.tracks_layout.count():
                child = self.tracks_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
        # Also hide the album download button when tracks are cleared
        if hasattr(self, 'album_download_button'):
            self.album_download_button.setVisible(False) # Explicitly hide if tracks/album cleared

    def _show_track_load_error(self, message: str):
        self._clear_track_list() # This will hide the download button
        error_label = QLabel(message)
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tracks_layout.addWidget(error_label)

    def _handle_track_card_selected(self, track_data: dict):
        """Handles when a track card (not download button) is clicked."""
        logger.info(f"[AlbumDetail] Track card selected for playback: {track_data.get('title')}")
        self.track_selected_for_playback.emit(track_data)

    def _handle_track_download_selected(self, track_data: dict):
        """Handles when a track's download button is clicked on a SearchResultCard."""
        logger.info(f"[AlbumDetail] Track download selected from card: {track_data.get('title')}")
        self.track_selected_for_download.emit(track_data)

    def _format_duration(self, seconds: int) -> str: 
        if not isinstance(seconds, (int, float)): return "--:--"
        minutes = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{minutes:02d}:{secs:02d}"

    def _load_main_album_cover(self, url: str):
        # Using a generic ArtworkLoaderWorker, but it needs row/col which is not relevant here.
        # For simplicity, create a one-off worker or adapt ArtworkLoaderWorker.
        # This is a simplified version, consider using ArtworkLoaderWorker if complex error handling/threading is needed.
        
        # Re-implementing a simple image loader using the new cache mechanism
        logger.debug(f"[AlbumDetail] Loading main album cover from: {url}")

        class MainCoverLoader(QRunnable):
            def __init__(self, img_url, signal_emitter_pixmap: pyqtSignal, error_signal: pyqtSignal):
                super().__init__()
                self.img_url = img_url
                self.signal_emitter_pixmap = signal_emitter_pixmap # Emits QPixmap
                self.error_signal = error_signal # Emits str

            @pyqtSlot()
            def run(self):
                if not self.img_url:
                    self.error_signal.emit("No image URL provided for main album cover.")
                    return

                cached_qimage = get_image_from_cache(self.img_url)
                if cached_qimage:
                    pixmap = QPixmap.fromImage(cached_qimage)
                    if not pixmap.isNull():
                        self.signal_emitter_pixmap.emit(pixmap)
                        return
                    else:
                        logger.warning(f"[AlbumDetail.MainCoverLoader] Failed to create QPixmap from cached QImage for {self.img_url}")
                try:
                    # Fallback to network if cache failed or not found
                    import requests # Local import as it's only used here now
                    logger.debug(f"[AlbumDetail.MainCoverLoader] Fetching image {self.img_url} (cache miss or bad cache)")
                    response = requests.get(self.img_url, timeout=10)
                    response.raise_for_status()
                    image_data = response.content

                    if not image_data:
                        self.error_signal.emit("Downloaded image data is empty for main album cover.")
                        return
                    
                    save_image_to_cache(self.img_url, image_data) # Save to cache

                    q_image = QImage()
                    if q_image.loadFromData(image_data):
                        pixmap = QPixmap.fromImage(q_image)
                        if not pixmap.isNull():
                            self.signal_emitter_pixmap.emit(pixmap)
                        else:
                             self.error_signal.emit("Failed to convert downloaded QImage to QPixmap for main album cover.")
                    else:
                        self.error_signal.emit("Failed to load downloaded image data into QImage for main album cover.")

                except Exception as e:
                    logger.error(f"[AlbumDetail.MainCoverLoader] Error loading main album cover {self.img_url}: {e}", exc_info=True)
                    self.error_signal.emit(str(e))
        
        # Create signals instance for this specific loader, if needed for direct connection.
        # However, we are directly connecting main_album_cover_loaded and _on_main_cover_artwork_error
        loader = MainCoverLoader(url, self.main_album_cover_loaded, self._on_main_cover_artwork_error_signal)
        self.thread_pool.start(loader)

    def _on_main_cover_artwork_loaded(self, image: QImage): # This was for the old loader
        # This method is likely now redundant if MainCoverLoader directly emits a QPixmap
        # to self.main_album_cover_loaded. Let's keep it for now if the signal structure changes.
        # If main_album_cover_loaded directly receives QPixmap, this can be removed.
        # For now, let's assume MainCoverLoader emits QPixmap as per its definition.
        logger.debug(f"[AlbumDetail] Main cover QImage loaded, converting to QPixmap. Size: {image.size()}")
        # This method seems to expect QImage, but self.main_album_cover_loaded is QPixmap.
        # This indicates a mismatch or leftover from previous structure.
        # Assuming self.main_album_cover_loaded is connected and receives QPixmap directly.
        pass


    def _set_main_album_cover(self, pixmap: QPixmap):
        if pixmap and not pixmap.isNull():
            scaled_pixmap = pixmap.scaled(
                self.album_cover_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio, # Changed to KeepAspectRatio
                Qt.TransformationMode.SmoothTransformation
            )
            self.album_cover_label.setPixmap(scaled_pixmap)
            # self._position_download_button() # REMOVED
        else:
            self._set_placeholder_main_album_cover()

    def _set_placeholder_main_album_cover(self):
        pixmap = QPixmap(self.album_cover_label.size())
        pixmap.fill(QColor("#e0e0e0"))
        painter = QPainter(pixmap)
        painter.setPen(QColor("#888888"))
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "Album Art")
        painter.end()
        self.album_cover_label.setPixmap(pixmap)
        # self._position_download_button() # REMOVED
        self.album_download_button.setVisible(False)

    def _on_main_cover_artwork_error(self, error_msg: str): # Connected to _on_main_cover_artwork_error_signal
        logger.error(f"[AlbumDetail] Error loading main album cover: {error_msg}")
        self._set_placeholder_main_album_cover()

    def _update_download_button_state(self, loaded: bool, enabled: bool = True):
        """Updates visibility and enabled state of the album download button."""
        if not hasattr(self, 'album_download_button'):
            logger.warning("album_download_button attribute missing when trying to update its state.")
            return

        if self.album_download_button.isVisible() != loaded:
            self.album_download_button.setVisible(loaded)
        
        new_enabled_state = loaded and enabled
        if self.album_download_button.isEnabled() != new_enabled_state:
            self.album_download_button.setEnabled(new_enabled_state)

        if loaded: 
            # self._position_download_button() # REMOVED
            self.album_download_button.raise_() 
        
        if not self.album_download_button.icon().isNull():
            self.album_download_button.setText("") 
        else:
            self.album_download_button.setText("DL") 
            # Warning for missing icon already happens in _setup_ui.
            # Consider logging only if icon state changes or once.
            # logger.warning("Album download icon is not available during state update. Using text 'DL'.")

        logger.debug(f"Album download button state (via _update): visible={self.album_download_button.isVisible()}, enabled={self.album_download_button.isEnabled()}, text='{self.album_download_button.text()}'")

    # _load_track_artwork and _on_artwork_loaded are removed as SearchResultCard handles its image loading
    
    # _request_track_download is removed, track_selected_for_download signal is used directly or via _handle_track_download_selected

    @pyqtSlot()
    def _trigger_full_album_download(self):
        if not self.current_album_id or not self.current_album_data:
            logger.warning("[AlbumDetail] No current album loaded to trigger download.")
            return
        
        # Ensure this runs in the asyncio event loop correctly
        # MainWindow will handle the actual download process.
        # We just need to gather track IDs here.
        logger.info(f"[AlbumDetail] Download button clicked for album: {self.current_album_data.get('title')}")
        asyncio.create_task(self._prepare_and_emit_full_album_download())

    async def _prepare_and_emit_full_album_download(self):
        if not self.current_album_id or not self.current_album_data or not self.deezer_api:
            logger.error("[AlbumDetail] Missing data for preparing full album download.")
            # Optionally, disable button or show user feedback
            self.album_download_button.setEnabled(False)
            return

        try:
            self.album_download_button.setEnabled(False) # Prevent double-clicks
            current_icon = self.album_download_button.icon() # Store current icon before temp change

            # Example: Temporarily change icon to an 'in-progress' or different color if available
            #busy_icon = get_icon("downloading.png") 
            #if busy_icon: self.album_download_button.setIcon(busy_icon)
            
            tracks_response = await self.deezer_api.get_album_tracks(self.current_album_id)
            
            if tracks_response and isinstance(tracks_response, list):
                track_ids = [track['id'] for track in tracks_response if isinstance(track, dict) and track.get('id')]
                if track_ids:
                    logger.info(f"[AlbumDetail] Emitting request_full_album_download for album '{self.current_album_data.get('title')}' with {len(track_ids)} tracks.")
                    self.request_full_album_download.emit(self.current_album_data, track_ids)
                else:
                    logger.warning(f"[AlbumDetail] No track IDs found for album {self.current_album_id} after fetching.")
                    # Maybe show a message to the user via status bar or a temp label
            elif tracks_response and 'error' in tracks_response:
                logger.error(f"[AlbumDetail] Error fetching tracks for full album download: {tracks_response.get('error')}")
            else:
                logger.error(f"[AlbumDetail] Unexpected response when fetching tracks for full album download: {tracks_response}")
        
        except Exception as e:
            logger.error(f"[AlbumDetail] Exception in _prepare_and_emit_full_album_download: {e}", exc_info=True)
        finally:
            # Re-enable button, maybe change text back
            if hasattr(self, 'album_download_button'): # Ensure it still exists
                 # self.album_download_button.setEnabled(True)
                 # self.album_download_button.setText("Download Album") # No text
                 # Restore original icon if it was changed
                 self.album_download_button.setIcon(current_icon) # Restore original icon
                 # Visibility and final enabled state are controlled by hover and current_album_data existence
                 pass 

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

# --- Example for standalone testing ---
if __name__ == '__main__':
    from PyQt6.QtWidgets import QApplication
    import sys
    # ... (standalone testing setup, ensure it's adapted for SearchResultCard if run) ...