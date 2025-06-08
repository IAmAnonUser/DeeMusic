"""
Optimized SearchResultCard with lazy loading and performance improvements.
"""
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QSizePolicy, QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer, QRect, pyqtSlot
from PyQt6.QtGui import QPixmap, QColor, QPainter, QPainterPath, QPen
import logging
from typing import Optional, List
from PyQt6.sip import isdeleted as sip_is_deleted

from utils.image_cache_optimized import get_optimized_image, preload_images
from utils.icon_utils import get_icon

logger = logging.getLogger(__name__)

class OptimizedSearchCard(QFrame):
    """Optimized search result card with lazy loading and caching."""
    
    download_clicked = pyqtSignal(dict)
    card_selected = pyqtSignal(dict)
    artist_name_clicked = pyqtSignal(int)
    album_name_clicked = pyqtSignal(int)
    
    # Constants
    CARD_MIN_WIDTH = 160
    CARD_MIN_HEIGHT = 220
    ARTIST_CARD_WIDTH = 150
    ARTIST_CARD_HEIGHT = 190
    TRACK_CARD_HEIGHT = 60
    TRACK_ARTWORK_SIZE = 48
    
    def __init__(self, item_data: dict, parent=None, **kwargs):
        super().__init__(parent)
        
        self.item_data = item_data
        self.item_type = item_data.get('type', 'unknown')
        self.item_id = item_data.get('id', 0)
        
        # Performance flags
        self._is_visible = False
        self._artwork_loaded = False
        self._ui_initialized = False
        self._is_in_viewport = False
        
        # Lazy loading timer
        self._visibility_timer = QTimer()
        self._visibility_timer.setSingleShot(True)
        self._visibility_timer.timeout.connect(self._on_visibility_timeout)
        
        # UI elements (created on demand)
        self.artwork_label = None
        self.artwork_container = None
        self.overlay_action_button = None
        
        # Setup basic structure immediately
        self._setup_basic_structure()
        
        # Track all cards for bulk operations
        OptimizedSearchCard._all_cards.append(self)
    
    # Class-level tracking
    _all_cards: List['OptimizedSearchCard'] = []
    
    @classmethod
    def preload_visible_cards(cls, cards: List['OptimizedSearchCard']):
        """Preload images for multiple cards efficiently."""
        urls = []
        for card in cards:
            if card._is_in_viewport and not card._artwork_loaded:
                artwork_urls = card._get_artwork_urls()
                urls.extend(artwork_urls[:2])  # Only preload first 2 URLs per card
        
        if urls:
            target_size = QSize(200, 200)  # Standard preload size
            preload_images(urls, target_size)
            logger.debug(f"Preloading {len(urls)} images for {len(cards)} cards")
    
    @classmethod
    def cleanup_all_cards(cls):
        """Cleanup all card references."""
        cls._all_cards.clear()
    
    def _setup_basic_structure(self):
        """Setup minimal UI structure for fast creation."""
        self.setFrameStyle(QFrame.Shape.Box)
        self.setLineWidth(1)
        self.setStyleSheet(self._get_basic_card_style())
        
        # Set appropriate size constraints
        if self.item_type == 'artist':
            self.setFixedSize(self.ARTIST_CARD_WIDTH, self.ARTIST_CARD_HEIGHT)
        elif self.item_type == 'track':
            self.setFixedHeight(self.TRACK_CARD_HEIGHT)
            self.setMinimumWidth(300)
        else:
            self.setMinimumSize(self.CARD_MIN_WIDTH, self.CARD_MIN_HEIGHT)
            self.setMaximumWidth(200)
        
        # Create placeholder layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(3)
    
    def _get_basic_card_style(self) -> str:
        """Get basic card styling."""
        return """
        OptimizedSearchCard {
            background-color: #2a2a2a;
            border: 1px solid #444;
            border-radius: 8px;
        }
        OptimizedSearchCard:hover {
            background-color: #333;
            border-color: #666;
        }
        """
    
    def _initialize_full_ui(self):
        """Initialize complete UI when card becomes visible."""
        if self._ui_initialized:
            return
        
        logger.debug(f"Initializing full UI for {self.item_type}: {self.item_data.get('title', 'Unknown')}")
        
        # Clear placeholder layout
        while self.main_layout.count():
            child = self.main_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Setup full UI based on item type
        if self.item_type == 'track':
            self._setup_track_ui()
        else:
            self._setup_standard_ui()
        
        self._ui_initialized = True
        
        # Start artwork loading
        self._load_artwork()
    
    def _setup_standard_ui(self):
        """Setup UI for album/artist/playlist cards."""
        # Artwork container with hover overlay
        self.artwork_container = QFrame()
        self.artwork_container.setFixedSize(140, 140)
        
        artwork_layout = QVBoxLayout(self.artwork_container)
        artwork_layout.setContentsMargins(0, 0, 0, 0)
        
        # Artwork label
        self.artwork_label = QLabel()
        self.artwork_label.setFixedSize(140, 140)
        self.artwork_label.setScaledContents(True)
        self.artwork_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        artwork_layout.addWidget(self.artwork_label)
        
        # Download button overlay
        self._create_download_overlay()
        
        # Title and details
        self._create_text_labels()
        
        # Layout
        self.main_layout.addWidget(self.artwork_container, 0, Qt.AlignmentFlag.AlignCenter)
        self.main_layout.addStretch()
        
        # Event filter for hover
        self.artwork_container.installEventFilter(self)
    
    def _setup_track_ui(self):
        """Setup UI for track cards."""
        # Horizontal layout for tracks
        track_layout = QHBoxLayout()
        track_layout.setContentsMargins(0, 0, 0, 0)
        track_layout.setSpacing(8)
        
        # Small artwork
        self.artwork_label = QLabel()
        self.artwork_label.setFixedSize(self.TRACK_ARTWORK_SIZE, self.TRACK_ARTWORK_SIZE)
        self.artwork_label.setScaledContents(True)
        track_layout.addWidget(self.artwork_label)
        
        # Track details
        details_layout = QVBoxLayout()
        details_layout.setSpacing(2)
        
        title_label = QLabel(self.item_data.get('title', 'Unknown Track'))
        title_label.setStyleSheet("font-weight: bold; color: white;")
        details_layout.addWidget(title_label)
        
        artist_name = self.item_data.get('artist', {}).get('name', 'Unknown Artist')
        artist_label = QLabel(artist_name)
        artist_label.setStyleSheet("color: #aaa;")
        details_layout.addWidget(artist_label)
        
        track_layout.addLayout(details_layout, 1)
        
        # Duration
        duration = self._format_duration(self.item_data.get('duration', 0))
        duration_label = QLabel(duration)
        duration_label.setStyleSheet("color: #aaa;")
        track_layout.addWidget(duration_label)
        
        self.main_layout.addLayout(track_layout)
    
    def _create_download_overlay(self):
        """Create download button overlay."""
        if self.item_type in ['album', 'playlist', 'artist']:
            self.overlay_action_button = QPushButton()
            self.overlay_action_button.setFixedSize(40, 40)
            
            # Position in center of artwork
            self.overlay_action_button.setParent(self.artwork_container)
            self.overlay_action_button.move(50, 50)  # Center position
            
            # Style and icon
            download_icon = get_icon('download.png')
            if download_icon:
                self.overlay_action_button.setIcon(download_icon)
                self.overlay_action_button.setIconSize(QSize(20, 20))
            
            self.overlay_action_button.setStyleSheet("""
                QPushButton {
                    background-color: rgba(0, 0, 0, 150);
                    border: none;
                    border-radius: 20px;
                    color: white;
                }
                QPushButton:hover {
                    background-color: rgba(0, 0, 0, 200);
                }
            """)
            
            self.overlay_action_button.clicked.connect(self._on_download_clicked)
            self.overlay_action_button.setVisible(False)
    
    def _create_text_labels(self):
        """Create text labels for title and details."""
        title = self.item_data.get('title', self.item_data.get('name', 'Unknown'))
        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-weight: bold; color: white; padding: 2px;")
        title_label.setMaximumHeight(40)
        self.main_layout.addWidget(title_label)
        
        # Secondary info based on type
        if self.item_type == 'album':
            artist_name = self.item_data.get('artist', {}).get('name', 'Unknown Artist')
            artist_label = QLabel(artist_name)
            artist_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            artist_label.setStyleSheet("color: #aaa; padding: 2px;")
            self.main_layout.addWidget(artist_label)
        elif self.item_type == 'playlist':
            track_count = self.item_data.get('nb_tracks', 0)
            count_label = QLabel(f"{track_count} tracks")
            count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            count_label.setStyleSheet("color: #aaa; padding: 2px;")
            self.main_layout.addWidget(count_label)
    
    def _get_artwork_urls(self) -> List[str]:
        """Get all possible artwork URLs for this item."""
        urls = []
        
        # Try different size variants
        size_keys = ['cover_xl', 'cover_big', 'cover_medium', 'cover_small', 'cover']
        if self.item_type == 'artist':
            size_keys = ['picture_xl', 'picture_big', 'picture_medium', 'picture']
        
        # Check album/artist structure
        for container_key in ['album', 'artist', self.item_type]:
            if container_key in self.item_data and isinstance(self.item_data[container_key], dict):
                for size_key in size_keys:
                    url = self.item_data[container_key].get(size_key)
                    if url and url not in urls:
                        urls.append(url)
        
        # Direct keys
        for size_key in size_keys:
            url = self.item_data.get(size_key)
            if url and url not in urls:
                urls.append(url)
        
        return urls
    
    def _load_artwork(self):
        """Load artwork using optimized cache."""
        if self._artwork_loaded:
            return
        
        urls = self._get_artwork_urls()
        if not urls:
            self._set_placeholder_artwork()
            return
        
        # Determine target size based on card type
        if self.item_type == 'track':
            target_size = QSize(self.TRACK_ARTWORK_SIZE, self.TRACK_ARTWORK_SIZE)
        else:
            target_size = QSize(140, 140)
        
        # Try to get from optimized cache
        for url in urls:
            pixmap = get_optimized_image(url, target_size)
            if pixmap:
                self._set_artwork(pixmap)
                return
        
        # If not in cache, request preload and show placeholder
        preload_images(urls[:1], target_size)  # Preload first URL
        self._set_placeholder_artwork()
        
        # Setup timer to check for loaded image
        self._check_timer = QTimer()
        self._check_timer.timeout.connect(lambda: self._check_for_loaded_artwork(urls, target_size))
        self._check_timer.start(500)  # Check every 500ms
    
    def _check_for_loaded_artwork(self, urls: List[str], target_size: QSize):
        """Check if artwork has been loaded in cache."""
        for url in urls:
            pixmap = get_optimized_image(url, target_size)
            if pixmap:
                self._set_artwork(pixmap)
                if hasattr(self, '_check_timer'):
                    self._check_timer.stop()
                return
    
    def _set_artwork(self, pixmap: QPixmap):
        """Set artwork on the label."""
        if not self.artwork_label or sip_is_deleted(self.artwork_label):
            return
        
        if self.item_type == 'artist':
            # Apply circular mask for artists
            pixmap = self._apply_circular_mask(pixmap)
        
        self.artwork_label.setPixmap(pixmap)
        self._artwork_loaded = True
    
    def _apply_circular_mask(self, pixmap: QPixmap) -> QPixmap:
        """Apply circular mask to pixmap for artist images."""
        size = min(pixmap.width(), pixmap.height())
        masked_pixmap = QPixmap(size, size)
        masked_pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(masked_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)
        
        # Scale and center the original pixmap
        scaled_pixmap = pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding)
        offset_x = (scaled_pixmap.width() - size) // 2
        offset_y = (scaled_pixmap.height() - size) // 2
        painter.drawPixmap(0, 0, scaled_pixmap, offset_x, offset_y, size, size)
        
        painter.end()
        return masked_pixmap
    
    def _set_placeholder_artwork(self):
        """Set placeholder artwork."""
        if not self.artwork_label or sip_is_deleted(self.artwork_label):
            return
        
        size = self.artwork_label.size()
        placeholder = QPixmap(size)
        placeholder.fill(QColor("#333333"))
        
        painter = QPainter(placeholder)
        painter.setPen(QPen(QColor("#777777")))
        
        text = {"artist": "♪", "album": "♫", "playlist": "♬", "track": "♪"}.get(self.item_type, "♪")
        painter.drawText(placeholder.rect(), Qt.AlignmentFlag.AlignCenter, text)
        painter.end()
        
        if self.item_type == 'artist':
            placeholder = self._apply_circular_mask(placeholder)
        
        self.artwork_label.setPixmap(placeholder)
    
    def _format_duration(self, seconds: int) -> str:
        """Format duration in seconds to MM:SS."""
        if seconds <= 0:
            return "0:00"
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"
    
    def _on_download_clicked(self):
        """Handle download button click."""
        self.download_clicked.emit(self.item_data)
    
    def set_in_viewport(self, in_viewport: bool):
        """Set whether this card is in the viewport."""
        if self._is_in_viewport == in_viewport:
            return
        
        self._is_in_viewport = in_viewport
        
        if in_viewport:
            # Start timer for delayed initialization
            self._visibility_timer.start(100)  # 100ms delay
        else:
            # Cancel delayed loading if not in viewport
            self._visibility_timer.stop()
    
    def _on_visibility_timeout(self):
        """Handle visibility timeout."""
        if self._is_in_viewport and not self._ui_initialized:
            self._initialize_full_ui()
    
    def eventFilter(self, source, event):
        """Handle hover events for download button."""
        if source == self.artwork_container and self.overlay_action_button:
            if event.type() == event.Type.Enter:
                self.overlay_action_button.setVisible(True)
            elif event.type() == event.Type.Leave:
                self.overlay_action_button.setVisible(False)
            elif event.type() == event.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    self.card_selected.emit(self.item_data)
                    return True
        return super().eventFilter(source, event)
    
    def mousePressEvent(self, event):
        """Handle card click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.card_selected.emit(self.item_data)
        super().mousePressEvent(event)
    
    def cleanup(self):
        """Cleanup resources."""
        if hasattr(self, '_check_timer'):
            self._check_timer.stop()
        self._visibility_timer.stop()
        
        # Remove from tracking
        if self in OptimizedSearchCard._all_cards:
            OptimizedSearchCard._all_cards.remove(self) 