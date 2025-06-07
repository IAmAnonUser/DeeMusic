"""
Artist Detail Page for DeeMusic application.
Displays information about a selected artist.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QHBoxLayout, QPushButton, QFrame, 
    QGridLayout, QSizePolicy, QStackedWidget, QTabBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QObject, QRunnable, QThreadPool, pyqtSlot, QThread, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QImage, QPainter, QColor, QPen, QBitmap, QPainterPath
from PyQt6.sip import isdeleted as sip_is_deleted
import logging
import os
import asyncio
from collections.abc import Callable
from io import BytesIO
import requests

# Import the new caching utility
from utils.image_cache import get_image_from_cache, save_image_to_cache

from src.ui.search_widget import SearchResultCard # Added import
from src.ui.track_list_header_widget import TrackListHeaderWidget # ADDED
from ui.components.responsive_grid import ResponsiveGridWidget
from src.ui.flowlayout import FlowLayout # Use our custom FlowLayout

logger = logging.getLogger(__name__)

class ArtistDetailPage(QWidget):
    """
    A widget to display details about an artist, including their discography,
    top tracks, etc.
    """
    back_requested = pyqtSignal() # ADDED: Signal for back navigation
    album_selected = pyqtSignal(int) # ADDED: Emits album_id when an album is selected
    playlist_selected = pyqtSignal('qint64') # CHANGED: Use 64-bit integer to handle large playlist IDs
    track_selected_for_download = pyqtSignal(dict) # ADDED: Emits track_data when download is requested from top tracks or other lists
    track_selected_for_playback = pyqtSignal(dict) # ADDED: Emits track_data to be played
    album_selected_for_download = pyqtSignal(dict, list) # ADDED: For downloading an entire album
    playlist_selected_for_download = pyqtSignal(dict) # ADDED: For downloading an entire playlist
    # NEW: Signals for navigation from track artist/album names
    artist_name_clicked_from_track = pyqtSignal(int)  # Emits artist_id when artist name clicked in track
    album_name_clicked_from_track = pyqtSignal(int)   # Emits album_id when album name clicked in track
    
    # Add signals for artist image loading
    artist_image_loaded = pyqtSignal(QPixmap)
    artist_image_error = pyqtSignal(str)

    def __init__(self, deezer_api, download_manager, parent=None):
        super().__init__(parent)
        self.deezer_api = deezer_api
        self.download_manager = download_manager
        self.current_artist_id = None
        self.current_artist_data = None
        
        # Add tab loading state tracking to prevent unnecessary reloads
        self._tabs_loaded = {
            'top_tracks': False,
            'albums': False,
            'singles': False,
            'eps': False,
            'featured_in': False
        }
        
        # Track current image loader to avoid conflicts
        self._current_image_loader = None

        # Initialize UI
        self._setup_ui()

        # Initialize signals
        self.artist_image_loaded.connect(self._on_artist_image_loaded)
        self.artist_image_error.connect(self._on_artist_image_load_error)

    def showEvent(self, event):
        """Override showEvent to ensure signals are connected when page becomes visible."""
        super().showEvent(event)
        # REMOVED: Complex signal connection code that was causing interference

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0) # Page itself has no margins
        main_layout.setSpacing(0)

        # --- Back Button ---
        back_button_layout = QHBoxLayout()
        back_button_layout.setContentsMargins(10,10,10,0) 
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
        main_layout.addLayout(back_button_layout)

        # --- 1. Header Section (Artist Image, Name, Fans) ---
        header_widget = QWidget()
        header_widget.setObjectName("artist_header_widget")
        header_widget.setFixedHeight(200) # Adjusted height, can be fine-tuned with styling
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(20, 10, 20, 20) # Adjusted top margin
        header_layout.setSpacing(20)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.artist_image_label = QLabel("Artist Img")
        self.artist_image_label.setObjectName("artist_page_image")
        self.artist_image_label.setFixedSize(160, 160) # Slightly smaller to match search top result?
        self.artist_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artist_image_label.setStyleSheet("border: 1px solid #ccc; border-radius: 80px; background-color: #eee;") 
        header_layout.addWidget(self.artist_image_label)

        # Vertical layout for artist text details
        artist_text_details_vbox = QVBoxLayout()
        artist_text_details_vbox.setContentsMargins(0, 0, 0, 0) # Ensure no internal margins
        artist_text_details_vbox.setSpacing(5) 

        # --- Artist Type Label (with spacer) ---
        artist_type_layout = QHBoxLayout()
        artist_type_layout.setContentsMargins(0,0,0,0)
        artist_type_spacer = QWidget()
        artist_type_spacer.setFixedWidth(5) # Adjust this value as needed
        artist_type_layout.addWidget(artist_type_spacer)
        self.artist_type_label = QLabel("Artist")
        self.artist_type_label.setObjectName("artist_page_type_label")
        self.artist_type_label.setStyleSheet("font-size: 10pt; color: #888;")
        artist_type_layout.addWidget(self.artist_type_label)
        artist_type_layout.addStretch(1)
        artist_text_details_vbox.addLayout(artist_type_layout)

        # --- Artist Name Label (no spacer, this is the reference) ---
        self.artist_name_label = QLabel("Artist Name")
        self.artist_name_label.setObjectName("artist_page_name_label")
        artist_text_details_vbox.addWidget(self.artist_name_label, 0, Qt.AlignmentFlag.AlignLeft)

        # --- Fan Count Label (with spacer) ---
        fan_count_layout = QHBoxLayout()
        fan_count_layout.setContentsMargins(0,0,0,0)
        fan_count_spacer = QWidget()
        fan_count_spacer.setFixedWidth(5) # Adjust this value as needed
        fan_count_layout.addWidget(fan_count_spacer)
        self.fan_count_label = QLabel("0 fans")
        self.fan_count_label.setObjectName("artist_page_fan_count_label")
        fan_count_layout.addWidget(self.fan_count_label)
        fan_count_layout.addStretch(1)
        artist_text_details_vbox.addLayout(fan_count_layout)
        
        # Removed the old artist_info_layout and mix_button section
        
        header_layout.addLayout(artist_text_details_vbox, 0) # Add with stretch factor 0
        header_layout.setAlignment(artist_text_details_vbox, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter) # Align the vbox itself
        
        # Add stretch to push download buttons to the far right
        header_layout.addStretch(1)
        
        # Add download buttons section (positioned at far right edge)
        download_buttons_layout = QVBoxLayout()
        download_buttons_layout.setContentsMargins(20, 10, 0, 10)  # Remove right margin to reach edge
        download_buttons_layout.setSpacing(6)  # Reduced spacing for tighter layout
        download_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Download All Albums button
        self.download_all_albums_btn = QPushButton("Download All Albums")
        self.download_all_albums_btn.setObjectName("ArtistDownloadButton")
        self.download_all_albums_btn.setFixedHeight(28)
        self.download_all_albums_btn.setMinimumWidth(140)
        self.download_all_albums_btn.clicked.connect(lambda: asyncio.create_task(self._download_all_albums()))
        download_buttons_layout.addWidget(self.download_all_albums_btn)
        
        # Download All Singles button
        self.download_all_singles_btn = QPushButton("Download All Singles")
        self.download_all_singles_btn.setObjectName("ArtistDownloadButton")
        self.download_all_singles_btn.setFixedHeight(28)
        self.download_all_singles_btn.setMinimumWidth(140)
        self.download_all_singles_btn.clicked.connect(lambda: asyncio.create_task(self._download_all_singles()))
        download_buttons_layout.addWidget(self.download_all_singles_btn)
        
        # Download All EP's button
        self.download_all_eps_btn = QPushButton("Download All EP's")
        self.download_all_eps_btn.setObjectName("ArtistDownloadButton")
        self.download_all_eps_btn.setFixedHeight(28)
        self.download_all_eps_btn.setMinimumWidth(140)
        self.download_all_eps_btn.clicked.connect(lambda: asyncio.create_task(self._download_all_eps()))
        download_buttons_layout.addWidget(self.download_all_eps_btn)
        
        # Add the download buttons layout to header (positioned at far right)
        header_layout.addLayout(download_buttons_layout, 0)

        main_layout.addWidget(header_widget)

        self.tab_bar = QTabBar()
        self.tab_bar.setObjectName("artist_page_tab_bar")
        self.tab_bar.addTab("Top tracks")
        self.tab_bar.addTab("Albums")
        self.tab_bar.addTab("Singles")
        self.tab_bar.addTab("EP's")
        self.tab_bar.addTab("Featured In")
        logger.info(f"[ArtistDetail] Created {self.tab_bar.count()} tabs: {[self.tab_bar.tabText(i) for i in range(self.tab_bar.count())]}")
        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        logger.info(f"[ArtistDetail] Connected tab_bar.currentChanged signal to _on_tab_changed")
        main_layout.addWidget(self.tab_bar)

        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("artist_page_content_stack")
        main_layout.addWidget(self.content_stack, 1)

        # Initialize tab content widgets
        self._init_tab_content_widgets()
        
        logger.info("ArtistDetailPage UI setup complete.")

    def _setup_top_tracks_ui(self):
        """Setup the UI for the top tracks tab."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Add track list header (like other detail pages)
        self.top_tracks_header = TrackListHeaderWidget(self)
        layout.addWidget(self.top_tracks_header)
        
        # Add a scroll area for the list of tracks
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        # Content widget to hold the track list
        content = QWidget()
        content.setObjectName("top_tracks_content")
        
        # Create the layout that will hold the track cards
        self.top_tracks_list_layout = QVBoxLayout(content)
        self.top_tracks_list_layout.setContentsMargins(0, 5, 0, 5)
        self.top_tracks_list_layout.setSpacing(5)
        self.top_tracks_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # Add a placeholder/loading message
        loading_label = QLabel("Loading top tracks...")
        loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.top_tracks_list_layout.addWidget(loading_label)
        
        # Set the content widget as the scroll area's widget
        scroll.setWidget(content)
        
        # Add scroll area to the page layout
        layout.addWidget(scroll)
        
        return page

    def _on_tab_changed(self, index: int):
        logger.debug(f"Artist page tab changed to index: {index} ({self.tab_bar.tabText(index)})")
        logger.info(f"[ArtistDetail] TAB CHANGED: index={index}, tab_name='{self.tab_bar.tabText(index)}', artist_id={self.current_artist_id}")
        self.content_stack.setCurrentIndex(index)
        
        # Don't try to load content if there's no artist ID yet
        if not self.current_artist_id:
            logger.warning("[ArtistDetail] Tab changed but no artist ID set, not loading content")
            return
            
        # Create a dedicated task for loading this tab's content
        # Use create_task to avoid blocking the UI thread
        tab_name = self.tab_bar.tabText(index)
        logger.info(f"Attempting to load content for tab: {tab_name}")
        
        # Cancel any existing content loading tasks
        if hasattr(self, '_current_tab_load_task') and self._current_tab_load_task:
            if not self._current_tab_load_task.done():
                # Just log it - we can't really cancel asyncio tasks cleanly in most cases
                logger.debug(f"[ArtistDetail] Switching tabs while previous tab content was still loading")
        
        # Store the task reference so we can potentially cancel it later
        logger.info(f"[ArtistDetail] Creating asyncio task for tab {index} ({tab_name})")
        self._current_tab_load_task = asyncio.create_task(self.load_content_for_tab(index))
        
        # Optionally show a loading indicator in the tab content area
        # This is important for visual feedback while async loading happens
        current_tab_widget = self.content_stack.widget(index)
        if current_tab_widget and hasattr(current_tab_widget, 'layout') and callable(current_tab_widget.layout):
            layout = current_tab_widget.layout()
            if layout:
                # We could show a loading indicator here if needed
                pass

    async def load_artist_data(self, artist_id: int):
        """Load artist details from Deezer API."""
        if not self.deezer_api:
            logger.error("DeezerAPI not available")
            return

        logger.info(f"Loading artist data for artist ID: {artist_id}")
        
        if not artist_id:
            logger.error("[ArtistDetail] No artist_id provided to load_artist_data.")
            return

        if not self.deezer_api:
            logger.error("[ArtistDetail] DeezerAPI is not initialized. Cannot load artist.")
            return
            
        logger.info(f"[ArtistDetail] Loading artist data for ID: {artist_id}")
        
        # Reset tab loading state only if this is a different artist
        if self.current_artist_id != artist_id:
            logger.info(f"[ArtistDetail] New artist detected ({self.current_artist_id} -> {artist_id}), resetting tab cache")
            self._tabs_loaded = {
                'top_tracks': False,
                'albums': False,
                'singles': False,
                'eps': False,
                'featured_in': False
            }
            # Clear any previous content when switching artists
            self._clear_all_tabs()
        
        self.current_artist_id = artist_id
        
        # Update UI to show loading
        self.artist_name_label.setText("Loading...")
        self.artist_type_label.setText("ARTIST")
        self.fan_count_label.setText("Loading...")
        self._set_artist_image_placeholder()
        
        # Ensure tab content widgets are initialized before loading data
        if not hasattr(self, 'top_tracks_list_layout') or self._safe_sip_is_deleted(self.top_tracks_list_layout):
            logger.info("[ArtistDetail] Re-initializing tab content widgets")
            self._init_tab_content_widgets()
        
        try:
            # Get artist details
            artist_data = await self.deezer_api.get_artist(artist_id)
            if not artist_data:
                logger.error(f"[ArtistDetail] Failed to get artist data for ID: {artist_id}")
                self.artist_name_label.setText("Failed to load artist")
                return
                
            self.current_artist_data = artist_data
            
            # Update UI with artist details
            self.artist_name_label.setText(artist_data.get('name', 'Unknown Artist'))
            
            # Fetch and display the artist image
            image_url = artist_data.get('picture_xl') or artist_data.get('picture_big') or artist_data.get('picture')
            if image_url:
                self._load_artist_image(image_url)
            else:
                self._set_artist_image_placeholder()
            
            # Update fan count with nice formatting
            fan_count = artist_data.get('nb_fan', 0)
            if fan_count > 1000000:
                formatted_fans = f"{fan_count/1000000:.1f}M fans"
            elif fan_count > 1000:
                formatted_fans = f"{fan_count/1000:.1f}K fans"
            else:
                formatted_fans = f"{fan_count} fans"
            self.fan_count_label.setText(formatted_fans)
            
            # Load the current tab's content (based on currently selected tab)
            current_tab_index = self.tab_bar.currentIndex()
            logger.info(f"[ArtistDetail] Initial tab index: {current_tab_index}, tab name: '{self.tab_bar.tabText(current_tab_index)}'")
            await self._load_tab_content(current_tab_index)
            
        except Exception as e:
            logger.error(f"[ArtistDetail] Exception loading artist {artist_id}: {e}", exc_info=True)
            self.artist_name_label.setText("Error loading artist")
            
    def _set_artist_image_placeholder(self):
        # Check if the label still exists
        if self._safe_sip_is_deleted(self.artist_image_label):
            logger.warning("[ArtistDetail] _set_artist_image_placeholder: self or artist_image_label is None or deleted.")
            return

        try:
            pixmap = QPixmap(180, 180)
            pixmap.fill(QColor("#e0e0e0"))
            
            painter = QPainter(pixmap)
            painter.setPen(QColor("#888888")) 
            font = painter.font()
            font.setPointSize(10) 
            painter.setFont(font)
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "Artist Img")
            painter.end()

            self._apply_circular_mask_and_set_pixmap(pixmap)
        except RuntimeError as e:
            # This can happen if the label is deleted during the operation, e.g., by sip_is_deleted check in _apply_circular_mask_and_set_pixmap
            if "wrapped C/C++ object" not in str(e) and "has been deleted" not in str(e): # Avoid redundant logging if already caught by sip_is_deleted
                logger.error(f"[ArtistDetail] RuntimeError in _set_artist_image_placeholder: {e}")
        except Exception as e:
            logger.error(f"[ArtistDetail] Unexpected error in _set_artist_image_placeholder: {e}", exc_info=True)

    def _load_artist_image(self, url: str):
        """Load the artist image from the given URL."""
        logger.debug(f"[ArtistDetail] Loading artist image from URL: {url}")
        if self._safe_sip_is_deleted(self.artist_image_label):
            logger.warning("[ArtistDetail] artist_image_label is deleted or None. Cannot load image.")
            return

        # Try to find the highest quality version by modifying URL patterns
        # For Deezer URLs like https://e-cdns-images.dzcdn.net/images/artist/19cc38f9d69b3571a71d0ad94894d5cd/56x56-000000-80-0-0.jpg
        # We can try to replace dimensions to get higher quality
        higher_quality_url = url
        if "56x56" in url:
            higher_quality_url = url.replace("56x56", "1000x1000")
        elif "250x250" in url:
            higher_quality_url = url.replace("250x250", "1000x1000")
        
        # Try to load from cache first
        if hasattr(self, '_current_image_loader') and self._current_image_loader:
            # Cancel previous loading if any
            try:
                self._current_image_loader.cancel()
            except:
                pass

        class ImageLoaderSignals(QObject):
            artwork_loaded = pyqtSignal(QPixmap)
            error = pyqtSignal(str)

        class ImageLoader(QRunnable):
            def __init__(self, img_url):
                super().__init__()
                self.img_url = img_url
                self.signals = ImageLoaderSignals()
                self._is_cancelled = False
                
            def cancel(self):
                self._is_cancelled = True
                
            @pyqtSlot()
            def run(self):
                if self._is_cancelled:
                    return
                    
                try:
                    from utils.image_cache import get_image_from_cache, save_image_to_cache
                    
                    # Try cache first (faster)
                    cached_image = get_image_from_cache(self.img_url)
                    if cached_image and not self._is_cancelled:
                        pixmap = QPixmap.fromImage(cached_image)
                        if not pixmap.isNull():
                            self.signals.artwork_loaded.emit(pixmap)
                            return
                    
                    # If not in cache or pixmap was null, download it
                    import requests
                    response = requests.get(self.img_url, timeout=10)
                    response.raise_for_status()
                    image_data = response.content
                    
                    if self._is_cancelled:
                        return
                        
                    # Cache the downloaded data
                    save_image_to_cache(self.img_url, image_data)
                    
                    # Create QImage from downloaded data
                    image = QImage()
                    if image.loadFromData(image_data):
                        if self._is_cancelled:
                            return
                            
                        pixmap = QPixmap.fromImage(image)
                        if not pixmap.isNull():
                            self.signals.artwork_loaded.emit(pixmap)
                        else:
                            self.signals.error.emit("Failed to create valid pixmap from image data")
                    else:
                        self.signals.error.emit("Failed to load image data into QImage")
                except requests.exceptions.Timeout:
                    if not self._is_cancelled:
                        self.signals.error.emit("Timeout loading artist image")
                except requests.exceptions.RequestException as e:
                    if not self._is_cancelled:
                        self.signals.error.emit(f"Network error loading artist image: {str(e)}")
                except Exception as e:
                    if not self._is_cancelled:
                        self.signals.error.emit(f"Error loading artist image: {str(e)}")

        self._current_image_loader = ImageLoader(higher_quality_url)
        # Connect to the class-level signals
        self._current_image_loader.signals.artwork_loaded.connect(self.artist_image_loaded)
        self._current_image_loader.signals.error.connect(self.artist_image_error)
        QThreadPool.globalInstance().start(self._current_image_loader)

    @pyqtSlot(QPixmap)
    def _on_artist_image_loaded(self, pixmap: QPixmap):
        if self._safe_sip_is_deleted(self.artist_image_label):
            logger.warning("[ArtistDetail] _on_artist_image_loaded: self or artist_image_label is None or deleted.")
            return
        logger.debug(f"[ArtistDetail] Artist image loaded successfully, pixmap size: {pixmap.size()}")
        self._apply_circular_mask_and_set_pixmap(pixmap)

    def _apply_circular_mask_and_set_pixmap(self, pixmap: QPixmap):
        if self._safe_sip_is_deleted(self.artist_image_label):
            logger.warning("[ArtistDetail] _apply_circular_mask_and_set_pixmap: self or artist_image_label is None or deleted.")
            return

        if self._safe_sip_is_deleted(pixmap) or pixmap.isNull():
            logger.warning("[ArtistDetail] _apply_circular_mask_and_set_pixmap: Received null or invalid pixmap.")
            self._set_artist_image_placeholder() # Fallback to placeholder if pixmap is bad
            return

        try:
            target_size = self.artist_image_label.size()
            if target_size.isEmpty() or target_size.width() <= 0 or target_size.height() <= 0:
                logger.warning(f"[ArtistDetail] Invalid artist_image_label size: {target_size}. Using default 180x180 for mask.")
                target_size = QSize(180, 180) # Fallback size

            # Scale the original pixmap to fit the target size while maintaining aspect ratio, then crop to square
            scaled_pixmap = pixmap.scaled(target_size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            
            # Create a square pixmap for the circular mask
            side = min(scaled_pixmap.width(), scaled_pixmap.height(), target_size.width(), target_size.height())
            final_image_size = QSize(side, side)

            # Center crop the scaled_pixmap to be square
            crop_x = (scaled_pixmap.width() - side) / 2
            crop_y = (scaled_pixmap.height() - side) / 2
            cropped_pixmap = scaled_pixmap.copy(int(crop_x), int(crop_y), side, side)

            # Create the final pixmap with a transparent background for the circle
            final_pixmap = QPixmap(final_image_size)
            final_pixmap.fill(Qt.GlobalColor.transparent)

            painter_final = QPainter(final_pixmap)
            painter_final.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter_final.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            
            # Create and set the circular clipping path
            clip_path = QPainterPath()
            clip_path.addEllipse(0, 0, side, side)
            painter_final.setClipPath(clip_path)
            
            # Draw the (cropped and scaled) image into the circular path
            painter_final.drawPixmap(0, 0, cropped_pixmap)
            painter_final.end()

            self.artist_image_label.setPixmap(final_pixmap)
            self.artist_image_label.setFixedSize(final_image_size) # Ensure label size matches pixmap
            logger.debug(f"[ArtistDetail] Circular mask applied and pixmap set. Final size: {final_image_size}")

        except RuntimeError as e:
            # This can occur if the widget is deleted mid-operation.
            if "wrapped C/C++ object" not in str(e) and "has been deleted" not in str(e):
                logger.error(f"[ArtistDetail] RuntimeError in _apply_circular_mask_and_set_pixmap: {e}")
            self._set_artist_image_placeholder() # Fallback
        except Exception as e:
            logger.error(f"[ArtistDetail] Unexpected error in _apply_circular_mask_and_set_pixmap: {e}", exc_info=True)
            self._set_artist_image_placeholder() # Fallback

    @pyqtSlot(str)
    def _on_artist_image_load_error(self, error_msg: str):
        if self._safe_sip_is_deleted(self.artist_image_label):
            logger.warning("[ArtistDetail] _on_artist_image_load_error: self or artist_image_label is None or deleted.")
            return
        
        logger.error(f"[ArtistDetail] Error loading artist image: {error_msg}")
        self._set_artist_image_placeholder() # Show placeholder on error

    # --- Methods to load content for each tab ---
    async def load_top_tracks(self):
        logger.info(f"[ArtistDetail] Loading top tracks for {self.current_artist_id}")
        # Ensure the layout exists (should be created in _init_tab_content_widgets or _setup_top_tracks_ui)
        if not hasattr(self, 'top_tracks_list_layout') or self._safe_sip_is_deleted(self.top_tracks_list_layout):
            logger.error("[ArtistDetail.load_top_tracks] top_tracks_list_layout is not initialized or deleted.")
            # Optionally, display an error in the UI for this tab
            self._clear_layout(self.top_tracks_page.layout()) # Clear whatever was there
            error_label = QLabel("UI Error: Top tracks layout not ready.")
            self.top_tracks_page.layout().addWidget(error_label)
            return

        self._clear_layout(self.top_tracks_list_layout)
        loading_label = QLabel("Loading top tracks...")
        loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.top_tracks_list_layout.addWidget(loading_label)

        if self._safe_sip_is_deleted(self.current_artist_id) or self._safe_sip_is_deleted(self.deezer_api):
            logger.warning("[ArtistDetail.load_top_tracks] No current_artist_id set.")
            self._show_error_in_layout(self.top_tracks_list_layout, "No artist selected.")
            return

        try:
            tracks = await self.deezer_api.get_artist_top_tracks(self.current_artist_id)
            self._clear_layout(self.top_tracks_list_layout) # Clear loading label

            if tracks:
                for track_data in tracks:
                    if not isinstance(track_data, dict):
                        logger.warning(f"[ArtistDetail.load_top_tracks] Skipping non-dict track item: {track_data}")
                        continue
                    # Ensure 'type' is set if not present, SearchResultCard might expect it
                    if 'type' not in track_data:
                        track_data['type'] = 'track' 
                        
                    card = SearchResultCard(track_data, show_duration=True) # MODIFIED: show_duration=True
                    card.card_selected.connect(self.track_selected_for_playback.emit)
                    card.download_clicked.connect(self.track_selected_for_download.emit)
                    # NEW: Connect artist and album name click signals
                    card.artist_name_clicked.connect(self.artist_name_clicked_from_track.emit)
                    card.album_name_clicked.connect(self.album_name_clicked_from_track.emit)
                    self.top_tracks_list_layout.addWidget(card)
            else:
                self._show_error_in_layout(self.top_tracks_list_layout, "No top tracks found for this artist.")
        except Exception as e:
            logger.error(f"[ArtistDetail.load_top_tracks] Error loading top tracks: {e}", exc_info=True)
            self._show_error_in_layout(self.top_tracks_list_layout, f"Error loading top tracks: {e}")

    def _show_error_in_layout(self, layout, message): # Helper to show errors in a given layout
        self._clear_layout(layout)
        error_label = QLabel(message)
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_label.setObjectName("error_label_detail_page") # Use existing QSS
        layout.addWidget(error_label)

    def _on_track_download_requested(self, item_data: dict):
        logger.info(f"Track download requested from ArtistDetailPage: {item_data.get('title')}")
        # Emit signal for MainWindow to handle
        self.track_selected_for_download.emit(item_data)
        logger.debug(f"[ArtistDetail] Emitted track_selected_for_download for item: {item_data.get('title')}")

    def _initiate_album_download_for_card(self, album_data: dict):
        """Slot for album card's download button. Initiates async fetching of tracks."""
        logger.info(f"[ArtistDetail] Album download initiated via card for: {album_data.get('title')}")
        if self._safe_sip_is_deleted(self.deezer_api):
            logger.error("[ArtistDetail] DeezerAPI not available to fetch album tracks for download.")
            # Optionally, inform the user via a QMessageBox or status bar update
            return
        if self._safe_sip_is_deleted(album_data) or not album_data.get('id'):
            logger.error("[ArtistDetail] Invalid album data received for download initiation.")
            return

        # Ensure this runs in the asyncio event loop correctly
        asyncio.create_task(self._handle_album_card_download_request(album_data))

    def _initiate_playlist_download_for_card(self, playlist_data: dict):
        """Slot for playlist card's download button. Initiates async fetching of tracks."""
        logger.info(f"[ArtistDetail] Playlist download initiated via card for: {playlist_data.get('title')}")
        if self._safe_sip_is_deleted(self.deezer_api):
            logger.error("[ArtistDetail] DeezerAPI not available to fetch playlist tracks for download.")
            return
        if self._safe_sip_is_deleted(playlist_data) or not playlist_data.get('id'):
            logger.error("[ArtistDetail] Invalid playlist data received for download initiation.")
            return

        # Ensure this runs in the asyncio event loop correctly
        asyncio.create_task(self._handle_playlist_card_download_request(playlist_data))

    async def _handle_album_card_download_request(self, album_data: dict):
        """Fetches all tracks for an album and emits a signal to download them."""
        album_id = album_data.get('id')
        album_title = album_data.get('title', 'Unknown Album')
        logger.info(f"[ArtistDetail] Fetching tracks for album ID {album_id} ('{album_title}') for download.")
        
        try:
            # Ensure deezer_api is available
            if self._safe_sip_is_deleted(self.deezer_api):
                logger.error(f"[ArtistDetail] DeezerAPI not available for _handle_album_card_download_request (album: {album_title})")
                return

            tracks_response = await self.deezer_api.get_album_tracks(album_id)
            if tracks_response and isinstance(tracks_response, list): # get_album_tracks now returns a list directly
                track_items = tracks_response
                # Filter out potential tracks without an ID, though unlikely for album tracks
                track_ids = [track['id'] for track in track_items if isinstance(track, dict) and track.get('id')]
                
                if track_ids:
                    logger.info(f"[ArtistDetail] Emitting album_selected_for_download for '{album_title}' (ID: {album_id}) with {len(track_ids)} track IDs.")
                    self.album_selected_for_download.emit(album_data, track_ids)
                else:
                    logger.warning(f"[ArtistDetail] No track IDs found or extracted for album '{album_title}' (ID: {album_id}). Track items: {len(track_items) if track_items else 'None'}")
            elif tracks_response and 'data' in tracks_response: # Fallback for old structure if any API parts still use it
                track_items = tracks_response['data']
                track_ids = [track['id'] for track in track_items if isinstance(track, dict) and track.get('id')]
                if track_ids:
                    logger.info(f"[ArtistDetail] Emitting album_selected_for_download (fallback structure) for '{album_title}' (ID: {album_id}) with {len(track_ids)} track IDs.")
                    self.album_selected_for_download.emit(album_data, track_ids)
                else:
                    logger.warning(f"[ArtistDetail] No track IDs found or extracted (fallback structure) for album '{album_title}' (ID: {album_id}).")
            else:
                error_detail = tracks_response.get('error', 'No data in response') if isinstance(tracks_response, dict) else 'Invalid response or empty list'
                logger.error(f"[ArtistDetail] Failed to fetch tracks for album '{album_title}' (ID: {album_id}). Response: {error_detail}")
        except Exception as e:
            logger.error(f"[ArtistDetail] Exception while fetching tracks for album ID {album_id} ('{album_title}') for download: {e}", exc_info=True)

    async def _handle_playlist_card_download_request(self, playlist_data: dict):
        """Fetches all tracks for a playlist and emits a signal to download them."""
        playlist_id = playlist_data.get('id')
        playlist_title = playlist_data.get('title', 'Unknown Playlist')
        logger.info(f"[ArtistDetail] Fetching tracks for playlist ID {playlist_id} ('{playlist_title}') for download.")
        
        try:
            # Ensure deezer_api is available
            if self._safe_sip_is_deleted(self.deezer_api):
                logger.error(f"[ArtistDetail] DeezerAPI not available for _handle_playlist_card_download_request (playlist: {playlist_title})")
                return

            # Debug: Log the playlist data structure
            logger.debug(f"[ArtistDetail] Playlist data structure being emitted: {playlist_data}")
            
            # For playlists, we just emit the playlist_selected_for_download signal
            # The MainWindow will handle fetching tracks and proper grouping via download_manager.download_playlist()
            logger.info(f"[ArtistDetail] Emitting playlist_selected_for_download for '{playlist_title}' (ID: {playlist_id})")
            self.playlist_selected_for_download.emit(playlist_data)
                    
        except Exception as e:
            logger.error(f"[ArtistDetail] Exception while initiating playlist download for ID {playlist_id} ('{playlist_title}'): {e}", exc_info=True)

    async def load_albums(self):
        logger.info(f"[ArtistDetail.load_albums] METHOD CALLED for artist {self.current_artist_id}")
        if self._safe_sip_is_deleted(self.current_artist_id) or self._safe_sip_is_deleted(self.deezer_api):
            logger.warning(f"[ArtistDetail.load_albums] No artist ID or API available.")
            return

        # Get the scroll area
        if hasattr(self, 'albums_page') and self.albums_page:
            scroll_area = self.albums_page.findChild(QScrollArea)
            if self._safe_sip_is_deleted(scroll_area):
                logger.error("[ArtistDetail] QScrollArea not found in albums_page.")
                return
        else:
            logger.error("[ArtistDetail] albums_page not found.")
            return
        
        # Show loading message
        loading_label = QLabel("Loading albums...")
        loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll_area.setWidget(loading_label)
        
        try:
            # Try multiple times with increasing timeouts
            all_artist_releases = None
            for attempt in range(3):  # Try up to 3 times
                try:
                    timeout_duration = 10 + (attempt * 5)  # 10s, 15s, 20s
                    logger.info(f"[ArtistDetail.load_albums] Attempt {attempt + 1}/3 with {timeout_duration}s timeout")
                    
                    all_artist_releases = await asyncio.wait_for(
                        self.deezer_api.get_artist_albums_generic(self.current_artist_id, limit=100),
                        timeout=timeout_duration
                    )
                    break  # Success, exit retry loop
                    
                except asyncio.TimeoutError:
                    logger.warning(f"[ArtistDetail.load_albums] Attempt {attempt + 1} timed out")
                    if attempt == 2:  # Last attempt
                        logger.error(f"[ArtistDetail.load_albums] All attempts failed for artist {self.current_artist_id}")
                        error_label = QLabel("Loading timed out. Try again later.\nClick on this tab again to retry.")
                        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        error_label.setStyleSheet("color: #ff6b6b; padding: 20px;")
                        scroll_area.setWidget(error_label)
                        return
                    else:
                        # Show retry message
                        retry_label = QLabel(f"Timeout on attempt {attempt + 1}. Retrying...")
                        retry_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        scroll_area.setWidget(retry_label)
                        await asyncio.sleep(1)  # Brief pause before retry
                        
            if self._safe_sip_is_deleted(all_artist_releases) or not all_artist_releases:
                logger.info(f"[ArtistDetail.load_albums] No releases found for artist {self.current_artist_id}")
                no_albums_label = QLabel("No albums found for this artist.")
                no_albums_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                scroll_area.setWidget(no_albums_label)
                return
            
            # Filter just the albums (not singles or EPs)
            # Only include items with record_type explicitly set to 'album'
            albums_data = []
            for item in all_artist_releases:
                record_type = item.get('record_type', '').lower()
                
                # Only consider it an album if record_type is explicitly 'album'
                if record_type == 'album':
                    albums_data.append(item)
                    
            # Debug: Log what we filtered
            logger.debug(f"[ArtistDetail.load_albums] Filtered {len(albums_data)} albums from {len(all_artist_releases)} total releases")
            
            # No fallback - if no albums found, just show "no albums" message
            if not albums_data:
                logger.info(f"[ArtistDetail.load_albums] No albums found for artist {self.current_artist_id}.")
                no_albums_label = QLabel("No albums found for this artist.")
                no_albums_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                scroll_area.setWidget(no_albums_label)
                return
            
            logger.info(f"[ArtistDetail.load_albums] Found {len(albums_data)} albums for artist {self.current_artist_id}")
            
            # Use responsive grid for albums
            responsive_grid = ResponsiveGridWidget(card_min_width=160, card_spacing=15)
            
            # Process each album and create cards
            cards = []
            for album_data in albums_data:
                if not isinstance(album_data, dict):
                    logger.warning(f"[ArtistDetail.load_albums] Skipping non-dict album item: {album_data}")
                    continue
                
                # Add required fields if missing
                if 'type' not in album_data:
                    album_data['type'] = 'album'
                
                # Add artist information since we're on an artist page and the API data may not include it
                if self.current_artist_data and self.current_artist_data.get('name'):
                    album_data['artist_name'] = self.current_artist_data['name']
                    # Also add artist object structure for consistency
                    if 'artist' not in album_data:
                        album_data['artist'] = {
                            'id': self.current_artist_id,
                            'name': self.current_artist_data['name']
                        }
                
                # Ensure there's a picture_url field for album artwork
                if 'picture_url' not in album_data:
                    # Try to set from various cover fields that might exist
                    for field in ['cover_xl', 'cover_big', 'cover_medium', 'cover_small', 'cover']:
                        if field in album_data and album_data[field]:
                            album_data['picture_url'] = album_data[field]
                            break
                
                # Debug: Log the available fields and artwork URL
                logger.debug(f"[ArtistDetail.load_albums] Album '{album_data.get('title', 'Unknown')}' fields: {list(album_data.keys())}")
                logger.debug(f"[ArtistDetail.load_albums] Album '{album_data.get('title', 'Unknown')}' picture_url: {album_data.get('picture_url', 'None')}")
                
                # Create card
                try:
                    card = SearchResultCard(album_data)
                    # Connect signals if needed
                    if hasattr(card, 'card_selected'):
                        card.card_selected.connect(lambda data=album_data: self._on_album_selected_for_navigation(data, 'album'))
                    if hasattr(card, 'download_clicked'):
                        card.download_clicked.connect(lambda data=album_data: self._initiate_album_download_for_card(data))
                    
                    cards.append(card)
                    logger.info(f"[ArtistDetail.load_albums] Successfully created card: {album_data.get('title', 'Unknown')}")
                except Exception as card_error:
                    logger.error(f"[ArtistDetail.load_albums] Error creating card: {card_error}", exc_info=True)
            
            # Set all cards to the responsive grid
            responsive_grid.set_cards(cards)
            scroll_area.setWidget(responsive_grid)
            logger.info(f"[ArtistDetail] Displayed {len(albums_data)} albums in grid layout.")
        except Exception as e:
            logger.error(f"[ArtistDetail.load_albums] Exception in load_albums for artist {self.current_artist_id}: {e}", exc_info=True)
            error_label = QLabel(f"Error: {str(e)[:100]}")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            scroll_area.setWidget(error_label)

    async def load_singles(self):
        logger.info(f"[ArtistDetail.load_singles] METHOD CALLED for artist {self.current_artist_id}")
        if self._safe_sip_is_deleted(self.current_artist_id) or self._safe_sip_is_deleted(self.deezer_api):
            logger.warning(f"[ArtistDetail.load_singles] No artist ID or API available.")
            return

        # Get the scroll area like Featured In does
        if hasattr(self, 'singles_page') and self.singles_page:
            scroll_area = self.singles_page.findChild(QScrollArea)
            if self._safe_sip_is_deleted(scroll_area):
                logger.error("[ArtistDetail] QScrollArea not found in singles_page.")
                return
        else:
            logger.error("[ArtistDetail] singles_page not found.")
            return
        
        try:
            # Get all artist releases with increased timeout tolerance
            try:
                logger.info(f"[ArtistDetail.load_singles] Fetching singles for artist {self.current_artist_id}")
                all_artist_releases = await asyncio.wait_for(
                    self.deezer_api.get_artist_albums_generic(self.current_artist_id, limit=100),
                    timeout=10  # 10 second timeout
                )
                logger.debug(f"[ArtistDetail.load_singles] Raw API response: {all_artist_releases[:2] if all_artist_releases else 'None'}")
                
                # Filter just the singles
                # Be more strict to avoid including EPs
                singles_data = []
                for item in all_artist_releases:
                    record_type = item.get('record_type', '').lower()
                    nb_tracks = item.get('nb_tracks', 0)
                    
                    # Only consider it a single if:
                    # 1. record_type is 'single' AND has 3 or fewer tracks
                    # This excludes EPs which typically have 4+ tracks but might be marked as 'single'
                    
                    if record_type == 'single' and nb_tracks <= 3:
                        singles_data.append(item)
                
                # Debug: Log what we filtered
                logger.debug(f"[ArtistDetail.load_singles] Filtered {len(singles_data)} singles from {len(all_artist_releases)} total releases")
                
                # No fallback - if no singles found, just show "no singles" message
                if not singles_data:
                    logger.info(f"[ArtistDetail.load_singles] No singles found for artist {self.current_artist_id}.")
                    no_singles_label = QLabel("No singles found for this artist.")
                    no_singles_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    scroll_area.setWidget(no_singles_label)
                    return
                
                logger.info(f"[ArtistDetail.load_singles] Found {len(singles_data)} singles for artist {self.current_artist_id}")
                
                # Use responsive grid for singles
                responsive_grid = ResponsiveGridWidget(card_min_width=160, card_spacing=15)
                
                # Process each single and create cards
                cards = []
                for single_data in singles_data:
                    if not isinstance(single_data, dict):
                        logger.warning(f"[ArtistDetail.load_singles] Skipping non-dict single item: {single_data}")
                        continue
                    
                    # Add required fields if missing
                    if 'type' not in single_data:
                        single_data['type'] = 'album'  # Use 'album' type for consistency with card handling
                    
                    # Add artist information since we're on an artist page and the API data may not include it
                    if self.current_artist_data and self.current_artist_data.get('name'):
                        single_data['artist_name'] = self.current_artist_data['name']
                        # Also add artist object structure for consistency
                        if 'artist' not in single_data:
                            single_data['artist'] = {
                                'id': self.current_artist_id,
                                'name': self.current_artist_data['name']
                            }
                    
                    # Ensure there's a picture_url field for single artwork
                    if 'picture_url' not in single_data:
                        # Try to set from various cover fields that might exist
                        for field in ['cover_xl', 'cover_big', 'cover_medium', 'cover_small', 'cover']:
                            if field in single_data and single_data[field]:
                                single_data['picture_url'] = single_data[field]
                                break
                    
                    # Create card
                    try:
                        card = SearchResultCard(single_data)
                        # Connect signals if needed
                        if hasattr(card, 'card_selected'):
                            card.card_selected.connect(lambda data=single_data: self._on_album_selected_for_navigation(data, 'album'))
                        if hasattr(card, 'download_clicked'):
                            card.download_clicked.connect(lambda data=single_data: self._initiate_album_download_for_card(data))
                        
                        cards.append(card)
                        logger.info(f"[ArtistDetail.load_singles] Successfully created card: {single_data.get('title', 'Unknown')}")
                    except Exception as card_error:
                        logger.error(f"[ArtistDetail.load_singles] Error creating card: {card_error}", exc_info=True)
                
                # Set all cards to the responsive grid
                responsive_grid.set_cards(cards)
                scroll_area.setWidget(responsive_grid)
                logger.info(f"[ArtistDetail] Displayed {len(singles_data)} singles in grid layout.")
            except asyncio.TimeoutError:
                logger.error(f"[ArtistDetail.load_singles] Timeout fetching singles for artist {self.current_artist_id}")
                error_label = QLabel("Loading timed out. Try again later.")
                error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                scroll_area.setWidget(error_label)
                return
            
            if self._safe_sip_is_deleted(all_artist_releases) or not all_artist_releases:
                logger.info(f"[ArtistDetail.load_singles] No releases found for artist {self.current_artist_id}")
                no_singles_label = QLabel("No singles found for this artist.")
                no_singles_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                scroll_area.setWidget(no_singles_label)
                return
            
        except Exception as e:
            logger.error(f"[ArtistDetail.load_singles] Exception in load_singles for artist {self.current_artist_id}: {e}", exc_info=True)
            error_label = QLabel(f"Error: {str(e)[:100]}")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            scroll_area.setWidget(error_label)

    async def load_eps(self):
        logger.info(f"[ArtistDetail.load_eps] METHOD CALLED for artist {self.current_artist_id}")
        if self._safe_sip_is_deleted(self.current_artist_id) or self._safe_sip_is_deleted(self.deezer_api):
            logger.warning(f"[ArtistDetail.load_eps] No artist ID or API available.")
            return

        # Get the scroll area like Featured In does
        if hasattr(self, 'eps_page') and self.eps_page:
            scroll_area = self.eps_page.findChild(QScrollArea)
            if self._safe_sip_is_deleted(scroll_area):
                logger.error("[ArtistDetail] QScrollArea not found in eps_page.")
                return
        else:
            logger.error("[ArtistDetail] eps_page not found.")
            return
        
        try:
            # Get all artist releases with increased timeout tolerance
            try:
                logger.info(f"[ArtistDetail.load_eps] Fetching EPs for artist {self.current_artist_id}")
                all_artist_releases = await asyncio.wait_for(
                    self.deezer_api.get_artist_albums_generic(self.current_artist_id, limit=100),
                    timeout=10  # 10 second timeout
                )
                logger.debug(f"[ArtistDetail.load_eps] Raw API response: {all_artist_releases[:2] if all_artist_releases else 'None'}")
                
                # Debug: Let's see what record_types are actually returned
                if all_artist_releases:
                    record_types = [item.get('record_type', 'no_record_type') for item in all_artist_releases[:10]]
                    logger.debug(f"[ArtistDetail.load_eps] First 10 record_types found: {record_types}")
            except asyncio.TimeoutError:
                logger.error(f"[ArtistDetail.load_eps] Timeout fetching EPs for artist {self.current_artist_id}")
                error_label = QLabel("Loading timed out. Try again later.")
                error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                scroll_area.setWidget(error_label)
                return
            
            if self._safe_sip_is_deleted(all_artist_releases) or not all_artist_releases:
                logger.info(f"[ArtistDetail] No releases found for artist {self.current_artist_id}")
                no_eps_label = QLabel("No EPs found for this artist.")
                no_eps_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                scroll_area.setWidget(no_eps_label)
                return
            
            # Filter just the EPs
            # Include both explicit EPs and singles with 4+ tracks
            eps_data = []
            for item in all_artist_releases:
                record_type = item.get('record_type', '').lower()
                nb_tracks = item.get('nb_tracks', 0)
                
                # Consider it an EP if:
                # 1. record_type is 'ep' (explicit EP)
                # 2. record_type is 'single' AND has 4+ tracks (single + remixes/bonus tracks)
                # 3. Has 4-8 tracks and no explicit record_type (fallback heuristic)
                
                if (record_type == 'ep' or 
                    (record_type == 'single' and nb_tracks >= 4) or
                    (not record_type and 4 <= nb_tracks <= 8)):
                    eps_data.append(item)
            
            # Debug: Log what we filtered
            logger.debug(f"[ArtistDetail.load_eps] Filtered {len(eps_data)} EPs from {len(all_artist_releases)} total releases")
            
            # No fallback - if no EPs found, just show "no EPs" message
            if not eps_data:
                logger.info(f"[ArtistDetail.load_eps] No EPs found for artist {self.current_artist_id}.")
                no_eps_label = QLabel("No EPs found for this artist.")
                no_eps_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                scroll_area.setWidget(no_eps_label)
                return
            
            logger.info(f"[ArtistDetail.load_eps] Found {len(eps_data)} EPs for artist {self.current_artist_id}")
            
            # Use responsive grid for EPs
            responsive_grid = ResponsiveGridWidget(card_min_width=160, card_spacing=15)
            
            # Process each EP and create cards
            cards = []
            for ep_data in eps_data:
                if not isinstance(ep_data, dict):
                    logger.warning(f"[ArtistDetail.load_eps] Skipping non-dict EP item: {ep_data}")
                    continue
                
                # Add required fields if missing
                if 'type' not in ep_data:
                    ep_data['type'] = 'album'  # Use 'album' type for consistency with card handling
                
                # Add artist information since we're on an artist page and the API data may not include it
                if self.current_artist_data and self.current_artist_data.get('name'):
                    ep_data['artist_name'] = self.current_artist_data['name']
                    # Also add artist object structure for consistency
                    if 'artist' not in ep_data:
                        ep_data['artist'] = {
                            'id': self.current_artist_id,
                            'name': self.current_artist_data['name']
                        }
                
                # Ensure there's a picture_url field for EP artwork
                if 'picture_url' not in ep_data:
                    # Try to set from various cover fields that might exist
                    for field in ['cover_xl', 'cover_big', 'cover_medium', 'cover_small', 'cover']:
                        if field in ep_data and ep_data[field]:
                            ep_data['picture_url'] = ep_data[field]
                            break
                
                # Create card
                try:
                    card = SearchResultCard(ep_data)
                    # Connect signals if needed
                    if hasattr(card, 'card_selected'):
                        card.card_selected.connect(lambda data=ep_data: self._on_album_selected_for_navigation(data, 'album'))
                    if hasattr(card, 'download_clicked'):
                        card.download_clicked.connect(lambda data=ep_data: self._initiate_album_download_for_card(data))
                    
                    cards.append(card)
                    logger.info(f"[ArtistDetail.load_eps] Successfully created card: {ep_data.get('title', 'Unknown')}")
                except Exception as card_error:
                    logger.error(f"[ArtistDetail.load_eps] Error creating card: {card_error}", exc_info=True)
            
            # Set all cards to the responsive grid
            responsive_grid.set_cards(cards)
            scroll_area.setWidget(responsive_grid)
            logger.info(f"[ArtistDetail] Displayed {len(eps_data)} EPs in grid layout.")
        except Exception as e:
            logger.error(f"[ArtistDetail] Exception in load_eps for artist {self.current_artist_id}: {e}", exc_info=True)
            error_label = QLabel(f"Error: {str(e)[:100]}")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            scroll_area.setWidget(error_label)

    def _on_album_selected_for_navigation(self, item_data: dict, item_type: str): # Assuming item_type is 'album'
        if item_data and item_data.get('id') and item_type == 'album':
            album_id = item_data.get('id')
            logger.info(f"[ArtistDetail] Album selected for navigation: ID {album_id}, Title: {item_data.get('title', 'N/A')}")
            self.album_selected.emit(album_id)
        else:
            logger.warning(f"[ArtistDetail] _on_album_selected_for_navigation called with invalid data: type={item_type}, data_has_id={'id' in item_data if item_data else False}")

    def _on_playlist_selected_for_navigation(self, item_data: dict):
        """Handle playlist card selection for navigation."""
        print(f"DEBUG: _on_playlist_selected_for_navigation called with data: {item_data}")
        if item_data and item_data.get('id'):
            playlist_id = item_data.get('id')
            print(f"DEBUG: About to emit playlist_selected signal with ID {playlist_id}")
            logger.info(f"[ArtistDetail] Playlist selected for navigation: ID {playlist_id}, Title: {item_data.get('title', 'N/A')}")
            self.playlist_selected.emit(playlist_id)
            print(f"DEBUG: Emitted playlist_selected signal with ID {playlist_id}")
        else:
            print(f"DEBUG: Invalid playlist data in _on_playlist_selected_for_navigation: {item_data}")
            logger.warning(f"[ArtistDetail] Invalid playlist data for navigation: {item_data}")

    def _handle_playlist_card_selected(self, item_data: dict):
        """Handle playlist card selection - simple direct approach like home page."""
        print(f"DEBUG: _handle_playlist_card_selected called with data: {item_data}")
        if item_data and item_data.get('id'):
            playlist_id = item_data.get('id')
            print(f"DEBUG: About to emit playlist_selected signal with ID {playlist_id}")
            logger.info(f"[ArtistDetail] Playlist card selected: ID {playlist_id}, Title: {item_data.get('title', 'N/A')}")
            self.playlist_selected.emit(playlist_id)
            print(f"DEBUG: Emitted playlist_selected signal with ID {playlist_id}")
        else:
            print(f"DEBUG: Invalid playlist data in _handle_playlist_card_selected: {item_data}")
            logger.warning(f"[ArtistDetail] Invalid playlist data: {item_data}")

    def _connect_playlist_download(self, card, playlist_data: dict):
        # REMOVED: Old helper method that was causing signal interference
        pass

    async def load_featured_in(self):
        logger.info(f"[ArtistDetail] Loading 'Featured In' for {self.current_artist_id}")
        if self._safe_sip_is_deleted(self.current_artist_id) or self._safe_sip_is_deleted(self.current_artist_data) or not self.current_artist_data.get('name'):
            logger.warning("[ArtistDetail] Artist ID or name not available to load 'Featured In'.")
            if hasattr(self, 'featured_in_page') and self.featured_in_page:
                scroll_area = self.featured_in_page.findChild(QScrollArea)
                if scroll_area:
                    error_label = QLabel("Cannot load 'Featured In': Artist data missing.")
                    error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    scroll_area.setWidget(error_label)
            return

        artist_name = self.current_artist_data.get('name')
        try:
            # Search for playlists featuring the artist's name
            search_results = await self.deezer_api.search(query=artist_name, search_type='playlist', limit=20)

            if hasattr(self, 'featured_in_page') and self.featured_in_page:
                scroll_area = self.featured_in_page.findChild(QScrollArea)
                if self._safe_sip_is_deleted(scroll_area):
                    logger.error("[ArtistDetail] QScrollArea not found in featured_in_page.")
                    return

                if search_results: # search method returns a list directly
                    # We expect items of type 'playlist' from this search
                    playlists_data = [item for item in search_results if item.get('type') == 'playlist']

                    if playlists_data:
                        # Use responsive grid for Featured In playlists
                        responsive_grid = ResponsiveGridWidget(card_min_width=160, card_spacing=15)
                        
                        # Process each playlist and create cards
                        cards = []
                        for playlist_item_data in playlists_data:
                            # Debug: Log the playlist data being processed
                            print(f"DEBUG: Processing playlist in load_featured_in: ID={playlist_item_data.get('id')}, Title={playlist_item_data.get('title')}")
                            logger.debug(f"[ArtistDetail] Processing playlist: ID={playlist_item_data.get('id')}, Title={playlist_item_data.get('title')}")
                            # SearchResultCard should handle 'type': 'playlist' correctly
                            # Ensure 'user' field is present if SearchResultCard expects it for playlist subtitle
                            # Playlist items from search usually have a 'user': {'name': 'xxx'} structure.
                            card = SearchResultCard(playlist_item_data)
                            print(f"DEBUG: Created SearchResultCard for playlist {playlist_item_data.get('id')}")
                            # Connect signals directly like home page does
                            if hasattr(card, 'card_selected'):
                                card.card_selected.connect(self._handle_playlist_card_selected)
                            # Connect download signal for playlists
                            if hasattr(card, 'download_clicked'):
                                card.download_clicked.connect(self._initiate_playlist_download_for_card)
                            cards.append(card)
                        
                        # Set all cards to the responsive grid
                        responsive_grid.set_cards(cards)
                        scroll_area.setWidget(responsive_grid)
                        logger.info(f"[ArtistDetail] Displayed {len(playlists_data)} playlists for 'Featured In' section based on artist name: {artist_name}.")
                    else:
                        no_results_label = QLabel(f"No playlists found featuring '{artist_name}'.")
                        no_results_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        scroll_area.setWidget(no_results_label)
                        logger.info(f"[ArtistDetail] No playlists found featuring '{artist_name}'.")
                else:
                    no_data_label = QLabel(f"Could not find playlists featuring '{artist_name}'.")
                    no_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    scroll_area.setWidget(no_data_label)
                    logger.info(f"[ArtistDetail] No data returned from playlist search for '{artist_name}'.")
            else:
                logger.warning("[ArtistDetail] featured_in_page not found or not initialized.")

        except Exception as e:
            logger.error(f"[ArtistDetail] Error loading 'Featured In' for {artist_name}: {e}", exc_info=True)
            if hasattr(self, 'featured_in_page') and self.featured_in_page:
                scroll_area = self.featured_in_page.findChild(QScrollArea)
                if scroll_area:
                    error_label = QLabel(f"Error loading 'Featured In': {e}")
                    error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    error_label.setWordWrap(True)
                    scroll_area.setWidget(error_label)
        pass
    
    # Ensure any old/removed load methods are either fully deleted or properly commented out
    # e.g.
    # async def load_discography(self): 
    #     pass # Or fully remove
    # async def load_similar_artists(self): 
    #     pass # Or fully remove
    # async def load_playlists(self):
    #     pass # Or fully remove
    # async def load_concerts(self):
    #     pass # Or fully remove
    # async def load_bio(self):
    #     pass # Or fully remove

    async def load_content_for_tab(self, index: int):
        tab_name = self.tab_bar.tabText(index)
        logger.info(f"[ArtistDetail] load_content_for_tab: Attempting to load content for tab: {tab_name} (index {index})")

        # Check if content is already loaded to prevent unnecessary reloads
        tab_cache_key = None
        if tab_name == "Top tracks":
            tab_cache_key = 'top_tracks'
        elif tab_name == "Albums":
            tab_cache_key = 'albums'
        elif tab_name == "Singles":
            tab_cache_key = 'singles'
        elif tab_name == "EP's":
            tab_cache_key = 'eps'
        elif tab_name == "Featured In":
            tab_cache_key = 'featured_in'
        
        # If content is already loaded, skip reloading
        if tab_cache_key and self._tabs_loaded.get(tab_cache_key, False):
            logger.info(f"[ArtistDetail] Tab '{tab_name}' content already loaded, skipping reload")
            return

        if tab_name == "Top tracks":
            logger.info(f"[ArtistDetail] load_content_for_tab: Calling load_top_tracks()")
            await self.load_top_tracks()
            self._tabs_loaded['top_tracks'] = True
        elif tab_name == "Albums":
            logger.info(f"[ArtistDetail] load_content_for_tab: Calling load_albums()")
            await self.load_albums()
            self._tabs_loaded['albums'] = True
        elif tab_name == "Singles":
            logger.info(f"[ArtistDetail] load_content_for_tab: Calling load_singles()")
            await self.load_singles()
            self._tabs_loaded['singles'] = True
        elif tab_name == "EP's":
            logger.info(f"[ArtistDetail] load_content_for_tab: Calling load_eps()")
            await self.load_eps()
            self._tabs_loaded['eps'] = True
        elif tab_name == "Featured In":
            logger.info(f"[ArtistDetail] load_content_for_tab: Calling load_featured_in()")
            await self.load_featured_in()
            self._tabs_loaded['featured_in'] = True
        else:
            logger.warning(f"[ArtistDetail] load_content_for_tab: Unknown tab name: {tab_name}")
        # Ensure no old tab cases are left uncommented or improperly formatted
        pass # Ensure method ends cleanly

    def _emit_back_request(self): # ADDED
        self.back_requested.emit()

    def _clear_layout(self, layout):
        """Clear all items from a layout with better error handling.
        Works with both QLayout and FlowLayout."""
        if not layout:
            return
            
        logger.debug(
            f"[ArtistDetail._clear_layout] Clearing layout: {type(layout)}, id: {id(layout)}, "
            f"sip_is_deleted (before clear): {self._safe_sip_is_deleted(layout)}"
        )
        
        # Different clearing methods depending on layout type
        try:
            items_cleared = 0
            while layout.count() > 0:
                item = layout.takeAt(0)
                if item is None:
                    break
                    
                if item.widget():
                    try:
                        item.widget().setParent(None)
                        item.widget().deleteLater()
                    except Exception as e:
                        logger.debug(f"[ArtistDetail._clear_layout] Error deleting widget: {e}")
                        
                items_cleared += 1
                
            logger.debug(
                f"[ArtistDetail._clear_layout] Finished clearing layout: {type(layout)}, id: {id(layout)}, "
                f"sip_is_deleted (after clear): {self._safe_sip_is_deleted(layout)}. Items cleared: {items_cleared}"
            )
        except Exception as e:
            logger.error(f"[ArtistDetail._clear_layout] Error clearing layout: {e}")
            # If clearing failed, the layout might be damaged - safe to return

    def _init_tab_content_widgets(self): # ADDED METHOD
        logger.debug("[ArtistDetail] Initializing tab content widgets...")
        logger.info(f"[ArtistDetail] _init_tab_content_widgets called - setting up tab pages")
        
        # Top Tracks Page - with header and scrollable list
        self.top_tracks_page = self._setup_top_tracks_ui() # Use the new setup method

        # Albums Page - Will use flow layout
        self.albums_page = QWidget()
        albums_page_layout = QVBoxLayout(self.albums_page)
        albums_page_layout.setContentsMargins(0,0,0,0)
        albums_page_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        albums_scroll_area = QScrollArea()
        albums_scroll_area.setWidgetResizable(True)
        albums_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.albums_content_widget = QWidget()
        self.albums_content_widget.setMinimumWidth(800)  # Set a minimum width to ensure content is visible
        # IMPORTANT: Store references as class variables to prevent garbage collection
        self.albums_scroll_area = albums_scroll_area
        self.albums_page_layout = albums_page_layout
        
        # Initialize the flow layout explicitly
        try:
            # Create the layout with the correct parent
            self.albums_flow_layout = QVBoxLayout()
            # Set the layout to the content widget
            self.albums_content_widget.setLayout(self.albums_flow_layout)
            self.albums_flow_layout.setContentsMargins(10, 10, 10, 10)  # Add some padding
            self.albums_flow_layout.setSpacing(15)  # Add spacing between cards
            logger.debug("[ArtistDetail] Albums flow layout created successfully")
        except Exception as e:
            logger.error(f"[ArtistDetail] Error creating albums flow layout: {e}")
            # Create a standard layout as fallback
            self.albums_flow_layout = QVBoxLayout()
            self.albums_content_widget.setLayout(self.albums_flow_layout)
            self.albums_flow_layout.setContentsMargins(10, 10, 10, 10)
            self.albums_flow_layout.setSpacing(15)
        
        albums_scroll_area.setWidget(self.albums_content_widget)
        albums_page_layout.addWidget(albums_scroll_area)

        # Singles Page - Will use flow layout
        self.singles_page = QWidget()
        singles_page_layout = QVBoxLayout(self.singles_page)
        singles_page_layout.setContentsMargins(0,0,0,0)
        singles_page_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        singles_scroll_area = QScrollArea()
        singles_scroll_area.setWidgetResizable(True)
        singles_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.singles_content_widget = QWidget()
        self.singles_content_widget.setMinimumWidth(800)  # Set a minimum width to ensure content is visible
        # IMPORTANT: Store references as class variables to prevent garbage collection
        self.singles_scroll_area = singles_scroll_area
        self.singles_page_layout = singles_page_layout
        
        # Initialize the flow layout explicitly
        try:
            # TEMPORARY: Create the layout with QVBoxLayout instead of FlowLayout
            self.singles_flow_layout = QVBoxLayout()
            # Set the layout to the content widget
            self.singles_content_widget.setLayout(self.singles_flow_layout)
            self.singles_flow_layout.setContentsMargins(10, 10, 10, 10)  # Add some padding
            self.singles_flow_layout.setSpacing(15)  # Add spacing between cards
            logger.debug("[ArtistDetail] Singles VBox layout created successfully")
        except Exception as e:
            logger.error(f"[ArtistDetail] Error creating singles flow layout: {e}")
            # Create a standard layout as fallback
            self.singles_flow_layout = QVBoxLayout()
            self.singles_content_widget.setLayout(self.singles_flow_layout)
            self.singles_flow_layout.setContentsMargins(10, 10, 10, 10)
            self.singles_flow_layout.setSpacing(15)
        
        singles_scroll_area.setWidget(self.singles_content_widget)
        singles_page_layout.addWidget(singles_scroll_area)

        # EPs Page - Will use flow layout
        self.eps_page = QWidget()
        eps_page_layout = QVBoxLayout(self.eps_page)
        eps_page_layout.setContentsMargins(0,0,0,0)
        eps_page_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        eps_scroll_area = QScrollArea()
        eps_scroll_area.setWidgetResizable(True)
        eps_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.eps_content_widget = QWidget()
        self.eps_content_widget.setMinimumWidth(800)  # Set a minimum width to ensure content is visible
        # IMPORTANT: Store references as class variables to prevent garbage collection
        self.eps_scroll_area = eps_scroll_area
        self.eps_page_layout = eps_page_layout
        
        # Initialize the flow layout explicitly
        try:
            # TEMPORARY: Create the layout with QVBoxLayout instead of FlowLayout
            self.eps_flow_layout = QVBoxLayout()
            # Set the layout to the content widget
            self.eps_content_widget.setLayout(self.eps_flow_layout)
            self.eps_flow_layout.setContentsMargins(10, 10, 10, 10)  # Add some padding
            self.eps_flow_layout.setSpacing(15)  # Add spacing between cards
            logger.debug("[ArtistDetail] EPs VBox layout created successfully")
        except Exception as e:
            logger.error(f"[ArtistDetail] Error creating EPs flow layout: {e}")
            # Create a standard layout as fallback
            self.eps_flow_layout = QVBoxLayout()
            self.eps_content_widget.setLayout(self.eps_flow_layout)
            self.eps_flow_layout.setContentsMargins(10, 10, 10, 10)
            self.eps_flow_layout.setSpacing(15)
        
        eps_scroll_area.setWidget(self.eps_content_widget)
        eps_page_layout.addWidget(eps_scroll_area)

        # Featured In Page - Placeholder for now, can also use FlowLayout or list
        self.featured_in_page = QWidget()
        featured_in_page_layout = QVBoxLayout(self.featured_in_page)
        featured_in_page_layout.setContentsMargins(0,0,0,0)
        featured_in_page_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        featured_in_scroll_area = QScrollArea()
        featured_in_scroll_area.setWidgetResizable(True)
        featured_in_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.featured_in_content_widget = QWidget()
        self.featured_in_content_widget.setMinimumWidth(800)  # Set a minimum width to ensure content is visible
        # IMPORTANT: Store references as class variables to prevent garbage collection
        self.featured_in_scroll_area = featured_in_scroll_area
        self.featured_in_page_layout = featured_in_page_layout
        
        # Initialize the flow layout explicitly
        try:
            # TEMPORARY: Create the layout with QVBoxLayout instead of FlowLayout
            self.featured_in_flow_layout = QVBoxLayout()
            # Set the layout to the content widget
            self.featured_in_content_widget.setLayout(self.featured_in_flow_layout)
            self.featured_in_flow_layout.setContentsMargins(10, 10, 10, 10)  # Add some padding
            self.featured_in_flow_layout.setSpacing(15)  # Add spacing between cards
            logger.debug("[ArtistDetail] Featured in VBox layout created successfully")
        except Exception as e:
            logger.error(f"[ArtistDetail] Error creating featured in flow layout: {e}")
            # Create a standard layout as fallback
            self.featured_in_flow_layout = QVBoxLayout()
            self.featured_in_content_widget.setLayout(self.featured_in_flow_layout)
            self.featured_in_flow_layout.setContentsMargins(10, 10, 10, 10)
            self.featured_in_flow_layout.setSpacing(15)
        
        featured_in_scroll_area.setWidget(self.featured_in_content_widget)
        featured_in_page_layout.addWidget(featured_in_scroll_area)

        # Clear existing widgets from stack before adding new ones
        while self.content_stack.count() > 0:
            widget = self.content_stack.widget(0)
            self.content_stack.removeWidget(widget)
            if widget:
                widget.deleteLater()

        self.content_stack.addWidget(self.top_tracks_page)
        self.content_stack.addWidget(self.albums_page)
        self.content_stack.addWidget(self.singles_page)
        self.content_stack.addWidget(self.eps_page)
        self.content_stack.addWidget(self.featured_in_page)

        logger.debug("[ArtistDetail] Tab content widgets initialized.")

    def _clear_all_tab_content_to_placeholders(self): # ADDED METHOD
        """Resets all tab content areas to their initial placeholder state."""
        logger.debug("[ArtistDetail] Clearing all tab content to placeholders.")
        tabs_map = {
            0: (self.top_tracks_page, "Top Tracks Content - Track List"),
            1: (self.albums_page, "Albums Content - Grid of Albums"),
            2: (self.singles_page, "Singles Content - Grid of Singles"),
            3: (self.eps_page, "EP's Content - Grid of EPs"),
            4: (self.featured_in_page, "Featured In Content - Grid of Playlists/Tracks")
        }
        for _index, (page_widget, placeholder_text) in tabs_map.items():
            if page_widget:
                scroll_area = page_widget.findChild(QScrollArea)
                if scroll_area:
                    # Create a new placeholder label each time to ensure it replaces the old widget
                    placeholder_label = QLabel(placeholder_text)
                    placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    scroll_area.setWidget(placeholder_label)
                else:
                    logger.warning(f"[ArtistDetail] Could not find QScrollArea in page_widget for placeholder: {placeholder_text}")
            else:
                logger.warning(f"[ArtistDetail] page_widget is None for placeholder: {placeholder_text}")

    def _create_and_load_card(self, item_data, parent_widget, on_card_click, on_download_click=None):
        """Centralized helper to create cards with proper image loading."""
        try:
            if not item_data:
                logger.error("[ArtistDetail] _create_and_load_card called with empty item_data")
                return None
                
            if not isinstance(item_data, dict):
                logger.error(f"[ArtistDetail] _create_and_load_card called with non-dict item_data: {type(item_data)}")
                return None
            
            # Make sure 'type' is set correctly for the card
            if 'type' not in item_data:
                # Default to 'album' for Albums/Singles/EPs tabs
                item_data['type'] = 'album'
            
            # Ensure the card has necessary properties for proper display
            if 'id' not in item_data:
                logger.warning(f"[ArtistDetail] Item missing 'id', adding placeholder: {item_data.get('title', 'Unknown')}")
                item_data['id'] = 0
                
            # For debugging
            logger.debug(f"[ArtistDetail] Creating card for {item_data.get('title', 'Unknown')}, type: {item_data.get('type')}")
            
            # Create card with explicit parent
            card = SearchResultCard(item_data, parent=parent_widget)
            
            # Connect signals if provided
            if on_card_click and hasattr(card, 'card_selected'):
                card.card_selected.connect(on_card_click)
            if on_download_click and hasattr(card, 'download_clicked'):
                card.download_clicked.connect(on_download_click)
            
            # Manually trigger artwork loading
            if hasattr(card, 'load_artwork'):
                QTimer.singleShot(100, card.load_artwork)
            
            return card
        except Exception as e:
            logger.error(f"[ArtistDetail] Error creating card: {e}", exc_info=True)
            return None

    def _safe_sip_is_deleted(self, obj):
        """Safely check if a Qt object has been deleted, without raising exceptions.
        Returns True if the object is None or deleted, False otherwise."""
        if obj is None:
            return True
            
        # Handle non-Qt objects (like integers)
        if not isinstance(obj, (object,)) or not hasattr(obj, 'metaObject'):
            return False
            
        try:
            return sip_is_deleted(obj)
        except RuntimeError:
            # Already deleted
            return True
        except Exception as e:
            logger.debug(f"[ArtistDetail._safe_sip_is_deleted] Unexpected error: {e}")
            return True  # If we can't verify, assume it's deleted to be safe

    def _clear_all_tabs(self):
        """Clear content from all tabs."""
        logger.debug("[ArtistDetail] Clearing all tab content.")
        
        # Reset tab loading state so content can be reloaded
        self._tabs_loaded = {
            'top_tracks': False,
            'albums': False,
            'singles': False,
            'eps': False,
            'featured_in': False
        }
        
        # Clear Top Tracks
        if hasattr(self, 'top_tracks_list_layout') and not self._safe_sip_is_deleted(self.top_tracks_list_layout):
            self._clear_layout(self.top_tracks_list_layout)
            loading_label = QLabel("Loading top tracks...")
            loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.top_tracks_list_layout.addWidget(loading_label)
            
        # Clear Albums
        if hasattr(self, 'albums_flow_layout') and not self._safe_sip_is_deleted(self.albums_flow_layout):
            self._clear_layout(self.albums_flow_layout)
            
        # Clear Singles
        if hasattr(self, 'singles_flow_layout') and not self._safe_sip_is_deleted(self.singles_flow_layout):
            self._clear_layout(self.singles_flow_layout)
            
        # Clear EPs
        if hasattr(self, 'eps_flow_layout') and not self._safe_sip_is_deleted(self.eps_flow_layout):
            self._clear_layout(self.eps_flow_layout)
            
    async def _load_tab_content(self, tab_index):
        """Load content for the specified tab index."""
        logger.info(f"[ArtistDetail] Loading content for tab index: {tab_index}")
        
        if tab_index == 0:  # Top Tracks
            logger.info(f"[ArtistDetail] Calling load_top_tracks()")
            await self.load_top_tracks()
        elif tab_index == 1:  # Albums
            logger.info(f"[ArtistDetail] Calling load_albums()")
            await self.load_albums()
        elif tab_index == 2:  # Singles
            logger.info(f"[ArtistDetail] Calling load_singles()")
            await self.load_singles()
        elif tab_index == 3:  # EPs
            logger.info(f"[ArtistDetail] Calling load_eps()")
            await self.load_eps()
        elif tab_index == 4:  # Featured In
            logger.info(f"[ArtistDetail] Calling load_featured_in()")
            await self.load_featured_in()
        else:
            logger.warning(f"[ArtistDetail] Unknown tab index: {tab_index}")

    def cleanup_cards(self):
        """Clean up any SearchResultCard instances to prevent memory leaks."""
        # Import here to avoid circular imports
        from src.ui.search_widget import SearchResultCard
        
        # Clean up any cards in top tracks
        if hasattr(self, 'top_tracks_list_layout'):
            for i in range(self.top_tracks_list_layout.count()):
                item = self.top_tracks_list_layout.itemAt(i)
                if item and item.widget() and isinstance(item.widget(), SearchResultCard):
                    item.widget().cleanup()
        
        # Clean up any cards in album grid
        if hasattr(self, 'albums_grid_layout'):
            for i in range(self.albums_grid_layout.count()):
                item = self.albums_grid_layout.itemAt(i)
                if item and item.widget() and isinstance(item.widget(), SearchResultCard):
                    item.widget().cleanup()

    def closeEvent(self, event):
        """Clean up when the page is closed."""
        self.cleanup_cards()
        super().closeEvent(event)

    async def _download_all_albums(self):
        """Download all albums for the current artist."""
        if not self.current_artist_id or not self.deezer_api:
            logger.warning("[ArtistDetail] Cannot download albums: missing artist ID or API")
            return
            
        try:
            logger.info(f"[ArtistDetail] Starting download of all albums for artist {self.current_artist_id}")
            
            # Get all artist releases
            all_artist_releases = await self.deezer_api.get_artist_albums_generic(self.current_artist_id, limit=100)
            if not all_artist_releases:
                logger.info("[ArtistDetail] No releases found for artist")
                return
            
            # Filter just the albums
            albums_data = []
            for item in all_artist_releases:
                record_type = item.get('record_type', '').lower()
                album_type = item.get('type', '').lower() 
                
                if (record_type == 'album' or 
                    album_type == 'album' or
                    (not record_type and not album_type and item.get('nb_tracks', 0) > 4)):
                    albums_data.append(item)
            
            logger.info(f"[ArtistDetail] Found {len(albums_data)} albums to download")
            
            # Download each album
            for album_data in albums_data:
                try:
                    # Add artist information to the album data
                    if self.current_artist_data and self.current_artist_data.get('name'):
                        album_data['artist_name'] = self.current_artist_data['name']
                        if 'artist' not in album_data:
                            album_data['artist'] = {
                                'id': self.current_artist_id,
                                'name': self.current_artist_data['name']
                            }
                    
                    # Trigger download using existing method
                    await self._handle_album_card_download_request(album_data)
                    logger.info(f"[ArtistDetail] Queued album for download: {album_data.get('title', 'Unknown')}")
                except Exception as e:
                    logger.error(f"[ArtistDetail] Error downloading album {album_data.get('title', 'Unknown')}: {e}")
                    
        except Exception as e:
            logger.error(f"[ArtistDetail] Error in _download_all_albums: {e}", exc_info=True)

    async def _download_all_singles(self):
        """Download all singles for the current artist."""
        if not self.current_artist_id or not self.deezer_api:
            logger.warning("[ArtistDetail] Cannot download singles: missing artist ID or API")
            return
            
        try:
            logger.info(f"[ArtistDetail] Starting download of all singles for artist {self.current_artist_id}")
            
            # Get all artist releases
            all_artist_releases = await self.deezer_api.get_artist_albums_generic(self.current_artist_id, limit=100)
            if not all_artist_releases:
                logger.info("[ArtistDetail] No releases found for artist")
                return
            
            # Filter just the singles
            # Be more strict to avoid including EPs
            singles_data = []
            for item in all_artist_releases:
                record_type = item.get('record_type', '').lower()
                nb_tracks = item.get('nb_tracks', 0)
                
                # Only consider it a single if:
                # 1. record_type is 'single' AND has 3 or fewer tracks
                # This excludes EPs which typically have 4+ tracks but might be marked as 'single'
                
                if record_type == 'single' and nb_tracks <= 3:
                    singles_data.append(item)
            
            logger.info(f"[ArtistDetail] Found {len(singles_data)} singles to download")
            
            # Download each single
            for single_data in singles_data:
                try:
                    # Add artist information to the single data
                    if self.current_artist_data and self.current_artist_data.get('name'):
                        single_data['artist_name'] = self.current_artist_data['name']
                        if 'artist' not in single_data:
                            single_data['artist'] = {
                                'id': self.current_artist_id,
                                'name': self.current_artist_data['name']
                            }
                    
                    # Trigger download using existing method
                    await self._handle_album_card_download_request(single_data)
                    logger.info(f"[ArtistDetail] Queued single for download: {single_data.get('title', 'Unknown')}")
                except Exception as e:
                    logger.error(f"[ArtistDetail] Error downloading single {single_data.get('title', 'Unknown')}: {e}")
                    
        except Exception as e:
            logger.error(f"[ArtistDetail] Error in _download_all_singles: {e}", exc_info=True)

    async def _download_all_eps(self):
        """Download all EPs for the current artist."""
        if not self.current_artist_id or not self.deezer_api:
            logger.warning("[ArtistDetail] Cannot download EPs: missing artist ID or API")
            return
            
        try:
            logger.info(f"[ArtistDetail] Starting download of all EPs for artist {self.current_artist_id}")
            
            # Get all artist releases
            all_artist_releases = await self.deezer_api.get_artist_albums_generic(self.current_artist_id, limit=100)
            if not all_artist_releases:
                logger.info("[ArtistDetail] No releases found for artist")
                return
            
            # Filter just the EPs
            eps_data = []
            for item in all_artist_releases:
                record_type = item.get('record_type', '').lower()
                album_type = item.get('type', '').lower()
                
                if (record_type == 'ep' or 
                    album_type == 'ep' or
                    (not record_type and not album_type and 4 <= item.get('nb_tracks', 0) <= 8)):
                    eps_data.append(item)
            
            logger.info(f"[ArtistDetail] Found {len(eps_data)} EPs to download")
            
            # Download each EP
            for ep_data in eps_data:
                try:
                    # Add artist information to the EP data
                    if self.current_artist_data and self.current_artist_data.get('name'):
                        ep_data['artist_name'] = self.current_artist_data['name']
                        if 'artist' not in ep_data:
                            ep_data['artist'] = {
                                'id': self.current_artist_id,
                                'name': self.current_artist_data['name']
                            }
                    
                    # Trigger download using existing method
                    await self._handle_album_card_download_request(ep_data)
                    logger.info(f"[ArtistDetail] Queued EP for download: {ep_data.get('title', 'Unknown')}")
                except Exception as e:
                    logger.error(f"[ArtistDetail] Error downloading EP {ep_data.get('title', 'Unknown')}: {e}")
                    
        except Exception as e:
            logger.error(f"[ArtistDetail] Error in _download_all_eps: {e}", exc_info=True)

# Example for standalone testing (requires qasync or similar for asyncio with Qt)
if __name__ == '__main__':
    from PyQt6.QtWidgets import QApplication
    import sys

    # Basic logger for test
    logging.basicConfig(level=logging.DEBUG)

    class MockDeezerAPI:
        async def get_artist_details(self, artist_id):
            await asyncio.sleep(0.1)
            if artist_id == 27: # Linkin Park example
                return {
                    'id': 27,
                    'name': 'Linkin Park',
                    'nb_fan': 11466794,
                    'picture_xl': 'https://e-cdns-images.dzcdn.net/images/artist/19cc38f9d69b3571a71d0ad94894d5cd/1000x1000-000000-80-0-0.jpg',
                    'picture_big': 'https://e-cdns-images.dzcdn.net/images/artist/19cc38f9d69b3571a71d0ad94894d5cd/500x500-000000-80-0-0.jpg',
                    'type': 'artist'
                }
            return {'error': {'message': 'Artist not found'}}
        # Add other mock methods as needed

    app = QApplication(sys.argv)
    
    # This is a simplified way to run asyncio with PyQt for testing.
    # For a full app, use a library like qasync.
    async def run_app():
        mock_api = MockDeezerAPI()
        # download_manager can be None for this test if not directly used by basic page load
        artist_page = ArtistDetailPage(deezer_api=mock_api, download_manager=None)
        artist_page.resize(900, 700)
        artist_page.show()
        await artist_page.load_artist_data(artist_id=27) # Example: Linkin Park
        # await artist_page.load_artist_data(artist_id=1) # Example: Daft Punk
        
        # Keep the app running (this part is tricky without a proper event loop integrator)
        # For a simple test, we might just let it show and then exit, 
        # or manually integrate with asyncio event loop.
        # The app.exec() would block the asyncio loop here.

    # Simplistic way to integrate asyncio for testing purposes
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # We need to run app.exec_() in a way that doesn't block the asyncio loop
    # or integrate them. For a simple test, we'll start the load, but app.exec_()
    # will take over. A proper solution involves qasync.
    
    # Create and show the page first
    mock_api_sync = MockDeezerAPI() # Use a sync instance for initial setup if needed
    artist_page_sync = ArtistDetailPage(deezer_api=mock_api_sync, download_manager=None)
    artist_page_sync.resize(900, 700)
    artist_page_sync.show()

    # Schedule the async load
    asyncio.ensure_future(artist_page_sync.load_artist_data(artist_id=27))
    
    sys.exit(app.exec()) # This will block until the app is closed 
