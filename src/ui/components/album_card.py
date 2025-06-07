from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QRunnable, QThreadPool, QObject
from PyQt6.QtGui import QPixmap, QIcon, QPainter, QBitmap, QBrush
import os # Added for path joining
import requests # Added for image downloading
import logging

logger = logging.getLogger(__name__)

class AlbumCard(QWidget):
    clicked = pyqtSignal(str, str)  # Emits title and artist (Kept for now, review if still needed)
    card_selected = pyqtSignal(dict) # New: Emits {'id': item_id, 'type': item_type}
    play_clicked = pyqtSignal(str, str)  # Emits title and artist
    download_requested = pyqtSignal(dict) # New signal for download requests
    
    # --- Helper class for image downloading ---
    class ImageDownloaderSignals(QObject): # QObject needed for signals
        image_loaded = pyqtSignal(QPixmap)
        load_failed = pyqtSignal()

    class ImageDownloaderRunnable(QRunnable):
        def __init__(self, url: str):
            super().__init__()
            self.url = url
            self.signals = AlbumCard.ImageDownloaderSignals()

        def run(self):
            logger.debug(f"AlbumCard.ImageDownloaderRunnable: Starting download for URL: {self.url}")
            try:
                response = requests.get(self.url, stream=True, timeout=10)
                response.raise_for_status()
                image_data = response.content
                pixmap = QPixmap()
                if pixmap.loadFromData(image_data):
                    logger.debug(f"AlbumCard.ImageDownloaderRunnable: Image data loaded successfully for {self.url}. Emitting image_loaded.")
                    self.signals.image_loaded.emit(pixmap)
                else:
                    logger.error(f"AlbumCard.ImageDownloaderRunnable: QPixmap.loadFromData failed for {self.url}. Emitting load_failed.")
                    self.signals.load_failed.emit()
            except requests.exceptions.RequestException as e:
                logger.error(f"AlbumCard.ImageDownloaderRunnable: RequestException for {self.url}: {e}. Emitting load_failed.")
                self.signals.load_failed.emit()
            except Exception as e: 
                logger.error(f"AlbumCard.ImageDownloaderRunnable: General Exception for {self.url}: {e}. Emitting load_failed.", exc_info=True)
                self.signals.load_failed.emit()
    # --- End Helper class ---
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("album-card")
        self.title_text = ""
        self.artist_text = ""
        self.item_id = None # To store the ID of the item (album, playlist, artist)
        self.current_cover_url = None # To avoid re-loading the same image if set_data is called multiple times
        self.item_type = "album" # Default item type
        self.thread_pool = QThreadPool()
        self._placeholder_image_path = os.path.join(
            os.path.dirname(__file__), "..", "assets", "placeholder_cover.png" 
        )
        # You might want to limit the number of concurrent downloads
        # self.thread_pool.setMaxThreadCount(5) 
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # Cover image container
        self.cover_container = QWidget()
        self.cover_container.setObjectName("cover-container")
        self.cover_container.setFixedSize(180, 180)
        
        # Cover container layout
        cover_layout = QVBoxLayout(self.cover_container)
        cover_layout.setContentsMargins(0, 0, 0, 0)
        cover_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Cover image
        self.cover_image = QLabel(self.cover_container)
        self.cover_image.setObjectName("cover-image")
        self.cover_image.setFixedSize(180, 180)
        # self.cover_image.setScaledContents(True) # We will handle scaling manually for circle
        cover_layout.addWidget(self.cover_image)
        
        # Play button overlay
        self.play_button = QPushButton(self.cover_container)
        self.play_button.setObjectName("play-button")
        self.play_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_button.setFixedSize(40, 40)
        # Corrected asset path (relative to this file, going up one to ui/, then to assets/)
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'play.svg')
        self.play_button.setIcon(QIcon(icon_path))
        self.play_button.setIconSize(QSize(20, 20))
        self.play_button.clicked.connect(self._on_play_clicked)
        self.play_button.hide()  # Initially hidden
        
        # Download button overlay
        self.download_button = QPushButton(self.cover_container)
        self.download_button.setObjectName("download-button")
        self.download_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.download_button.setFixedSize(32, 32) # Slightly smaller than play
        # Use the absolute path provided by the user for the download icon
        download_icon_path = r"C:\Users\HOME\Documents\deemusic\src\ui\assets\download.png"
        self.download_button.setIcon(QIcon(download_icon_path))
        self.download_button.setIconSize(QSize(18, 18))
        self.download_button.clicked.connect(self._on_download_clicked)
        self.download_button.hide() # Initially hidden
        
        # Center the play button & position download button
        self.play_button.move(
            (self.cover_container.width() - self.play_button.width()) // 2,
            (self.cover_container.height() - self.play_button.height()) // 2
        )
        # Position download button (e.g., top-right corner)
        self.download_button.move(
            self.cover_container.width() - self.download_button.width() - 5, # 5px padding
            5 # 5px padding
        )
        
        # Title
        self.title = QLabel()
        self.title.setObjectName("album-title")
        self.title.setWordWrap(True)
        self.title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        # Artist
        self.artist = QLabel()
        self.artist.setObjectName("album-artist")
        self.artist.setWordWrap(True)
        self.artist.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        layout.addWidget(self.cover_container)
        layout.addWidget(self.title)
        layout.addWidget(self.artist)
        self.setLayout(layout)
        
        # Make the whole card clickable
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
    def set_data(self, title: str, artist: str, cover_url: str = None, item_type: str = "album", item_id=None):
        self.title_text = title
        self.artist_text = artist
        self.item_type = item_type
        self.item_id = item_id 
        logger.debug(f"AlbumCard.set_data: Received - Title: {self.title_text}, Artist: {self.artist_text}, Item ID: {self.item_id}, Item Type: {self.item_type}, Cover URL: {cover_url}")
        self.title.setText(title)
        self.artist.setText(artist)

        # Adjust QSS for cover_image based on item_type for circular effect
        if self.item_type == "artist":
            # This makes the QLabel itself circular, pixmap will be clipped.
            self.cover_image.setStyleSheet("border-radius: 90px; background-color: #E0E0E0; color: #888;") 
        else:
            # Default square with potentially rounded corners from theme/parent QSS
            self.cover_image.setStyleSheet("background-color: #E0E0E0; color: #888;") # Placeholder style

        if cover_url and cover_url != self.current_cover_url:
            self.current_cover_url = cover_url
            self.cover_image.clear() 
            self.cover_image.setText("...") # Loading indicator

            if cover_url.lower().startswith("http://") or cover_url.lower().startswith("https://"):
                logger.debug(f"AlbumCard.set_data: New web cover URL {cover_url}. Starting ImageDownloaderRunnable.")
                downloader = AlbumCard.ImageDownloaderRunnable(cover_url)
                downloader.signals.image_loaded.connect(self._on_image_loaded)
                downloader.signals.load_failed.connect(self._on_image_load_failed)
                self.thread_pool.start(downloader)
            # elif os.path.exists(cover_url):
            #     logger.debug(f"AlbumCard.set_data: New local cover URL {cover_url}. Loading directly.")
            else:
                # Enhanced check for local files
                logger.debug(f"AlbumCard.set_data: Checking local path. cover_url: '{cover_url}', abspath: '{os.path.abspath(cover_url)}'")
                is_local_file = False
                try:
                    # Attempt to normalize and check existence
                    normalized_path = os.path.normpath(cover_url)
                    logger.debug(f"AlbumCard.set_data: Normalized local path for check: '{normalized_path}'")
                    if os.path.exists(normalized_path) and os.path.isfile(normalized_path):
                        is_local_file = True
                except Exception as e:
                    logger.error(f"AlbumCard.set_data: Error checking local path '{cover_url}': {e}")

                if is_local_file:
                    logger.debug(f"AlbumCard.set_data: Confirmed local file: '{normalized_path}'. Loading directly.")
                    pixmap = QPixmap(normalized_path)
                    if not pixmap.isNull():
                        self._on_image_loaded(pixmap)
                    else:
                        logger.error(f"AlbumCard.set_data: Failed to load local QPixmap from {normalized_path}.")
                        self._on_image_load_failed()
                else:
                    logger.warning(f"AlbumCard.set_data: Cover URL '{cover_url}' is not a web URL and not a valid local file path. Failing.")
                    self._on_image_load_failed()

        elif not cover_url:
            logger.debug(f"AlbumCard.set_data: No cover_url provided. Clearing image.")
            self.current_cover_url = None
            self._on_image_load_failed() # Show placeholder if no URL

    def _on_image_loaded(self, pixmap: QPixmap):
        logger.debug(f"AlbumCard._on_image_loaded: Slot called for item ID {self.item_id}, Title: {self.title_text}. Pixmap isNull: {pixmap.isNull()}")
        if not pixmap.isNull():
            self.cover_image.setText("") 
            processed_pixmap = pixmap

            if self.item_type == "artist":
                # Scale the pixmap to be a square, fitting the shortest side
                size = min(pixmap.width(), pixmap.height())
                cropped_pixmap = pixmap.copy(
                    (pixmap.width() - size) // 2, 
                    (pixmap.height() - size) // 2, 
                    size, 
                    size
                )
                # Now scale this square pixmap to the label size
                scaled_pixmap = cropped_pixmap.scaled(
                    self.cover_image.size(), 
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding, # Fill the square
                    Qt.TransformationMode.SmoothTransformation
                )

                # Create a circular mask
                mask = QBitmap(scaled_pixmap.size())
                mask.fill(Qt.GlobalColor.white) # Changed from Qt.black to Qt.white for inverted mask logic
                painter = QPainter(mask)
                painter.setBrush(Qt.GlobalColor.black) # Paint black circle on white mask
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.drawEllipse(0, 0, mask.width(), mask.height())
                painter.end()
                
                scaled_pixmap.setMask(mask)
                processed_pixmap = scaled_pixmap
                self.cover_image.setStyleSheet("border-radius: 90px; background-color: transparent;")
            else:
                # Standard scaling for albums/playlists
                processed_pixmap = pixmap.scaled(
                    self.cover_image.size(), 
                    Qt.AspectRatioMode.KeepAspectRatio, 
                    Qt.TransformationMode.SmoothTransformation
                )
                # Instead of clearing stylesheet, set a defined background
                self.cover_image.setStyleSheet("background-color: transparent;") # Ensure background doesn't hide pixmap

            self.cover_image.setPixmap(processed_pixmap)
        else:
            self._on_image_load_failed()

    def _on_image_load_failed(self):
        logger.error(f"AlbumCard._on_image_load_failed: Slot called for item ID {self.item_id}, Title: {self.title_text}. Current cover URL: {self.current_cover_url}")
        self.cover_image.clear()
        self.cover_image.setText("") # Clear any loading text
        
        # Attempt to load the defined placeholder pixmap
        logger.debug(f"AlbumCard._on_image_load_failed: Attempting to load placeholder. Path: '{self._placeholder_image_path}', Exists: {os.path.exists(self._placeholder_image_path)}, IsFile: {os.path.isfile(self._placeholder_image_path) if os.path.exists(self._placeholder_image_path) else 'N/A'}")
        placeholder_pixmap = QPixmap(self._placeholder_image_path)
        if not placeholder_pixmap.isNull():
            # Apply the same processing (circular for artist, scaled for others) to the placeholder
            processed_placeholder = placeholder_pixmap
            if self.item_type == "artist":
                size = min(placeholder_pixmap.width(), placeholder_pixmap.height())
                cropped_pixmap = placeholder_pixmap.copy(
                    (placeholder_pixmap.width() - size) // 2, 
                    (placeholder_pixmap.height() - size) // 2, 
                    size, 
                    size
                )
                scaled_pixmap = cropped_pixmap.scaled(
                    self.cover_image.size(), 
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding, 
                    Qt.TransformationMode.SmoothTransformation
                )
                mask = QBitmap(scaled_pixmap.size())
                mask.fill(Qt.GlobalColor.white)
                painter = QPainter(mask)
                painter.setBrush(Qt.GlobalColor.black)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.drawEllipse(0, 0, mask.width(), mask.height())
                painter.end()
                scaled_pixmap.setMask(mask)
                processed_placeholder = scaled_pixmap
                self.cover_image.setStyleSheet("border-radius: 90px; background-color: transparent;")
            else:
                processed_placeholder = placeholder_pixmap.scaled(
                    self.cover_image.size(), 
                    Qt.AspectRatioMode.KeepAspectRatio, 
                    Qt.TransformationMode.SmoothTransformation
                )
                self.cover_image.setStyleSheet("background-color: transparent;")
            self.cover_image.setPixmap(processed_placeholder)
        else:
            # Fallback text and style if even placeholder fails (should not happen if path is correct)
            self.cover_image.setText("!")
            if self.item_type == "artist":
                self.cover_image.setStyleSheet("border-radius: 90px; background-color: #FFE0E0; color: red;")
            else:
                self.cover_image.setStyleSheet("background-color: #FFE0E0; color: red;")
            
    def enterEvent(self, event):
        self.play_button.show()
        self.download_button.show() # Show download button on hover
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        self.play_button.hide()
        self.download_button.hide() # Hide download button on leave
        super().leaveEvent(event)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Emit the old signal (for now, can be reviewed)
            self.clicked.emit(self.title_text, self.artist_text)
            
            # Emit the new signal for navigation if item_id and item_type are set
            if self.item_id is not None and self.item_type:
                item_data = {'id': self.item_id, 'type': self.item_type, 'title': self.title_text}
                self.card_selected.emit(item_data)
                # print(f"AlbumCard: card_selected emitted: {item_data}") # Debug
            # else: # Debug
                # print(f"AlbumCard: card_selected NOT emitted. item_id: {self.item_id}, item_type: {self.item_type}") # Debug

        super().mousePressEvent(event)
        
    def _on_play_clicked(self):
        self.play_clicked.emit(self.title_text, self.artist_text) 

    def _on_download_clicked(self):
        if self.item_id is not None:
            download_data = {
                'id': self.item_id,
                'type': self.item_type,
                'title': self.title_text,
                # Potentially add artist_text or other useful info here
            }
            self.download_requested.emit(download_data)
        else:
            # print(f"Download clicked for {self.title_text}, but item_id is None.") # Debug
            pass 