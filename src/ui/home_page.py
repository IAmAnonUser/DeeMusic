"""Home page component for DeeMusic."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QFrame, QPushButton, QGridLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTimer, QThread
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QIcon
import asyncio
import logging

def safe_single_shot(delay_ms, callback):
    """Safely execute QTimer.singleShot, checking thread safety first."""
    try:
        from PyQt6.QtCore import QThread, QTimer
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app and QThread.currentThread() == app.thread():
            QTimer.singleShot(delay_ms, callback)
        else:
            # We're in a worker thread, execute immediately
            callback()
    except Exception as e:
        logging.getLogger(__name__).error(f"Error in safe_single_shot: {e}")
        # Fallback: execute immediately
        try:
            callback()
        except Exception as callback_error:
            logging.getLogger(__name__).error(f"Error in callback fallback: {callback_error}")
import os
import logging

# Import SearchResultCard from ui.search_widget
from src.ui.search_widget import SearchResultCard

logger = logging.getLogger(__name__)

VIEW_ALL_LIMIT = 50 # Max items to fetch for "View all"

class HomePage(QWidget):
    """Home page displaying featured content and recommendations."""
    
    # Signals to MainWindow for navigation
    album_selected = pyqtSignal(int)
    playlist_selected = pyqtSignal('qint64')
    artist_selected = pyqtSignal(int)
    view_all_requested = pyqtSignal(list, str) # ADDED: Signal for "View all"
    home_item_selected = pyqtSignal(dict, str) # ADDED: For general item selection from home page
    home_item_download_requested = pyqtSignal(dict) # ADDED: For item download from home page
    
    # Signal for thread-safe scroll arrow updates
    update_scroll_arrows_signal = pyqtSignal(object, object, object)
    
    def __init__(self, deezer_api, download_manager=None, parent=None):
        super().__init__(parent)
        self.deezer_api = deezer_api
        self.download_manager = download_manager # Will be set by MainWindow
        self.section_content_layouts = {} # New: to store QHBoxLayouts for scrollable content
        
        # Connect the signal to the slot for thread-safe updates
        self.update_scroll_arrows_signal.connect(self._update_scroll_arrows_delayed)
        self.section_scroll_arrows = {} # New: to store (left_arrow, right_arrow) for each section
        self.section_scroll_areas = {} # New: to store QScrollArea for each section
        self._placeholder_image_path = os.path.join(
            os.path.dirname(__file__), "assets", "placeholder_cover.png"
        )
        self.setup_ui()
        # Call load_content after UI is set up
        # Ensure this is called from a context where an event loop is running if it makes async calls
        # For now, let's assume MainWindow will trigger it appropriately.
        
    def setup_ui(self):
        """Set up the home page UI."""
        logger.info("HomePage.setup_ui: Starting UI setup.")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0) # Reduced main spacing, sections will have their own
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded) # Allow vertical scroll for the whole page
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        content_widget = QWidget()
        content_widget.setObjectName("HomePageContentWidget")
        self.main_content_layout = QVBoxLayout(content_widget)
        self.main_content_layout.setContentsMargins(20, 20, 20, 20) # Overall padding for content
        self.main_content_layout.setSpacing(25) # Spacing between sections
        
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
        # Sections are now created and added by load_content
        logger.info("HomePage.setup_ui: Finished UI setup. Content will be loaded by load_content.")
        
    def _create_scrollable_section_widget(self, title: str, item_type_for_view_all: str, max_items: int = 10): # max_items for view all logic
        """Creates a widget for a section of scrollable content (e.g., Top Charts, New Releases)."""
        section_frame = QFrame()
        section_frame.setObjectName(f"HomeSectionFrame_{title.replace(' ', '')}")
        main_section_layout = QVBoxLayout(section_frame) 
        main_section_layout.setContentsMargins(0, 0, 0, 0) 
        main_section_layout.setSpacing(10)

        header_widget = QWidget()
        header_widget.setMinimumHeight(45)
        
        overall_header_layout = QHBoxLayout(header_widget) 
        overall_header_layout.setContentsMargins(0,0,0,0)
        overall_header_layout.setSpacing(5)

        left_part_widget = QWidget()
        left_part_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        left_part_layout = QHBoxLayout(left_part_widget)
        left_part_layout.setContentsMargins(0,0,0,0)
        left_part_layout.setSpacing(10)

        section_label = QLabel(title)
        section_label.setObjectName("SearchSectionHeader") # Use the same object name for styling
        section_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        left_part_layout.addWidget(section_label, 0, Qt.AlignmentFlag.AlignVCenter)

        # if item_type_for_view_all: # For now, "View all" button always added, connect later
        view_all_button = QPushButton("View all")
        view_all_button.setObjectName("ViewAllButton") # Use the same object name
        view_all_button.setCursor(Qt.CursorShape.PointingHandCursor)
        view_all_button.clicked.connect(lambda checked=False, sec_title=title: self._initiate_view_all_action(sec_title))
        left_part_layout.addWidget(view_all_button, 0, Qt.AlignmentFlag.AlignVCenter) 
        
        left_part_layout.addStretch(1)
        overall_header_layout.addWidget(left_part_widget, 1) 
        overall_header_layout.addStretch(0)

        right_part_widget = QWidget()
        right_part_widget.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        right_part_layout = QHBoxLayout(right_part_widget)
        right_part_layout.setContentsMargins(0,0,0,0)
        right_part_layout.setSpacing(5)

        asset_path = os.path.dirname(__file__)
        left_arrow = QPushButton()
        left_arrow.setObjectName("ScrollArrowButtonLeft")
        left_arrow.setFixedSize(22, 22)
        left_arrow.setIcon(QIcon(os.path.join(asset_path, "assets", "left scroll arrow.png")))
        left_arrow.setIconSize(QSize(14, 14))

        right_arrow = QPushButton()
        right_arrow.setObjectName("ScrollArrowButtonRight")
        right_arrow.setFixedSize(22, 22)
        right_arrow.setIcon(QIcon(os.path.join(asset_path, "assets", "right scroll arrow.png")))
        right_arrow.setIconSize(QSize(14, 14))

        scroll_arrow_icon_qss = '''
            QPushButton { background-color: transparent; border: none; border-radius: 11px; }
            QPushButton:hover { background-color: #f0f0f0; }
            QPushButton:disabled { background-color: transparent; } '''
        left_arrow.setStyleSheet(scroll_arrow_icon_qss)
        right_arrow.setStyleSheet(scroll_arrow_icon_qss)

        right_part_layout.addWidget(left_arrow)
        right_part_layout.addWidget(right_arrow)
        overall_header_layout.addWidget(right_part_widget) 
        
        main_section_layout.addWidget(header_widget)

        current_scroll_area = QScrollArea()
        current_scroll_area.setWidgetResizable(True)
        current_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff) 
        current_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  
        current_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        current_scroll_area.setFixedHeight(270) # Adjust as needed for card height

        scroll_content_widget = QWidget()
        scroll_content_layout = QHBoxLayout(scroll_content_widget) # This is what we need to store
        scroll_content_layout.setContentsMargins(0,5,0,5) # Add some top/bottom margin for cards
        scroll_content_layout.setSpacing(15) 

        # Cards will be added here by load_content
        
        scroll_content_layout.addStretch() 
        current_scroll_area.setWidget(scroll_content_widget)
        
        left_arrow.clicked.connect(lambda checked=False, sa=current_scroll_area: self.scroll_horizontal_area(sa, -1))
        right_arrow.clicked.connect(lambda checked=False, sa=current_scroll_area: self.scroll_horizontal_area(sa, 1))
        
        # Store for dynamic updates
        self.section_content_layouts[title] = scroll_content_layout
        self.section_scroll_arrows[title] = (left_arrow, right_arrow)
        self.section_scroll_areas[title] = current_scroll_area

        current_scroll_area.horizontalScrollBar().valueChanged.connect(
            lambda value, sa=current_scroll_area, la=left_arrow, ra=right_arrow: self.update_scroll_arrows_state(sa, la, ra)
        )
        # Initial state update for arrows
        # Need to do this after content might be added, so maybe in load_content after populating.
        # Or defer it with a QTimer.singleShot(0, lambda: self.update_scroll_arrows_state(current_scroll_area, left_arrow, right_arrow))
        
        main_section_layout.addWidget(current_scroll_area)
        return section_frame

    def create_section(self, title: str, item_type_for_view_all: str):
        """Creates a styled, scrollable section and adds it to the main layout."""
        logger.info(f"HomePage.create_section: Creating section '{title}'.")
        section_widget = self._create_scrollable_section_widget(title, item_type_for_view_all)
        self.main_content_layout.addWidget(section_widget)
        # Return the content layout for load_content to populate
        return self.section_content_layouts[title]

    async def load_content(self):
        """Load content from Deezer API."""
        logger.critical("!!!!!!!!!!!!!! HomePage.load_content CALLED !!!!!!!!!!!!!!") # Prominent log
        if not self.deezer_api:
            logger.error("HomePage: DeezerAPI not initialized. Cannot load content.")
            self._show_error_message("DeezerAPI not initialized. Please restart the application.")
            return
            
        # Check if ARL token is configured
        arl_token = self.deezer_api.arl if hasattr(self.deezer_api, 'arl') else None
        if not arl_token:
            logger.error("HomePage: Cannot load content - No ARL token configured.")
            self._show_error_message("No ARL token configured. Please go to Settings > Account to configure your Deezer ARL token.")
            return

        # Clear existing sections from layout if any (in case of reload)
        while self.main_content_layout.count():
            item = self.main_content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.section_content_layouts.clear()
        self.section_scroll_arrows.clear()
        self.section_scroll_areas.clear()

        # --- Define section loading configurations ---
        sections_to_load = [
            # {"title": "Top Charts", "api_call": self.deezer_api.get_charts_all_types, "item_type": "chart_multi", "limit": 10, "card_type_field": 'type'}, # REMOVED - Method does not exist
            {"title": "New Releases", "api_call": self.deezer_api.get_editorial_releases, "item_type": "album", "limit": 25, "card_type_field": None}, # MODIFIED to use editorial releases for actual new releases
            {"title": "Popular Playlists", "api_call": self.deezer_api.get_chart_playlists, "item_type": "playlist", "limit": 25, "card_type_field": None}, # limit changed to 25
            {"title": "Most Streamed Artists", "api_call": self.deezer_api.get_chart_artists, "item_type": "artist", "limit": 25, "card_type_field": None}, # limit changed to 25
            {"title": "Top Albums", "api_call": self.deezer_api.get_chart_albums, "item_type": "album", "limit": 25, "card_type_field": None}, # limit changed to 25
        ]

        for config in sections_to_load:
            section_title = config["title"]
            api_call = config["api_call"]
            default_item_type = config["item_type"]
            limit = config["limit"]
            card_type_field = config.get("card_type_field")


            logger.info(f"HomePage: Creating and loading section: '{section_title}'")
            content_layout = self.create_section(section_title, default_item_type) # item_type for view all
            
            if not content_layout:
                logger.error(f"Failed to create content layout for section '{section_title}'")
                continue

            try:
                items_data = await api_call(limit=limit)
                if items_data:
                    logger.info(f"HomePage: Received {len(items_data)} items for '{section_title}'.")
                    
                    # Clear previous items in this specific section's content layout
                    while content_layout.count() > 1: # Keep the stretch
                        item_to_remove = content_layout.takeAt(0)
                        if item_to_remove.widget():
                            item_to_remove.widget().deleteLater()
                    
                    # Get the parent widget (scroll_content_widget) for the cards in this section
                    current_section_scroll_area = self.section_scroll_areas.get(section_title)
                    parent_widget_for_cards = current_section_scroll_area.widget() if current_section_scroll_area else None

                    if not parent_widget_for_cards:
                        logger.error(f"HomePage: Could not find parent widget for cards in section '{section_title}'. Skipping card creation.")
                        continue
                    
                    for item_data in items_data:
                        # Determine the actual type of the item for SearchResultCard
                        actual_item_type = item_data.get(card_type_field) if card_type_field else default_item_type
                        if actual_item_type == "chart_multi": # Special handling for mixed charts
                            if "albums" in item_data and item_data["albums"]["data"]:
                                # For simplicity, take the first album from the chart's album list
                                actual_item_type = "album"
                                item_data = item_data["albums"]["data"][0] 
                            elif "artists" in item_data and item_data["artists"]["data"]:
                                actual_item_type = "artist"
                                item_data = item_data["artists"]["data"][0]
                            elif "playlists" in item_data and item_data["playlists"]["data"]:
                                actual_item_type = "playlist"
                                item_data = item_data["playlists"]["data"][0]
                            elif "tracks" in item_data and item_data["tracks"]["data"]:
                                actual_item_type = "track" # Should ideally not happen for home page sections
                                item_data = item_data["tracks"]["data"][0]
                            else:
                                logger.warning(f"Skipping chart_multi item due to no recognizable sub-data: {item_data.get('id')}")
                                continue # Skip this item if no valid sub-type found
                        
                        # Ensure item_data is a dictionary and has an 'id'
                        if not isinstance(item_data, dict) or 'id' not in item_data:
                            logger.warning(f"Skipping item due to missing 'id' or invalid format: {item_data}")
                            continue

                        # Add 'type' to item_data if not present, using actual_item_type
                        if 'type' not in item_data:
                            item_data['type'] = actual_item_type

                        logger.debug(f"HomePage: Preparing to create SearchResultCard with item_data: {item_data}")
                        
                        card = SearchResultCard(item_data, parent=parent_widget_for_cards)
                        # Connect card signals
                        card.card_selected.connect(self._on_home_card_item_selected)
                        card.download_clicked.connect(self._on_home_card_download_requested)
                        
                        content_layout.insertWidget(content_layout.count() -1, card) # Insert before the stretch

                    # Update scroll arrows for this section
                    if section_title in self.section_scroll_areas and section_title in self.section_scroll_arrows:
                        scroll_area_ref = self.section_scroll_areas[section_title] # Renamed to avoid lambda capture issue
                        left_arrow_ref, right_arrow_ref = self.section_scroll_arrows[section_title]
                        # Delay update to allow layout to settle
                        # Use signal for thread-safe scroll arrow updates
                        self.update_scroll_arrows_signal.emit(scroll_area_ref, left_arrow_ref, right_arrow_ref)

                else:
                    logger.info(f"HomePage: No items returned for '{section_title}'.")
            except Exception as e:
                logger.error(f"HomePage: Error loading content for '{section_title}': {e}", exc_info=True)
        
                logger.critical(f"!!!!!!!!!!!!!! HomePage.load_content FINISHED. Total sections in main_content_layout: {self.main_content_layout.count()} !!!!!!!!!!!!!!")
        self.main_content_layout.addStretch(1) # Add a final stretch to the main page layout

    def _show_error_message(self, message: str):
        """Show error message on the home page."""
        try:
            # Clear existing content
            while self.main_content_layout.count():
                item = self.main_content_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            
            # Show error message
            error_label = QLabel(message)
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            error_label.setStyleSheet("color: #ff6b6b; font-size: 16px; padding: 20px;")
            error_label.setWordWrap(True)
            self.main_content_layout.addWidget(error_label)
            
            # Add a retry button
            from PyQt6.QtWidgets import QPushButton
            retry_button = QPushButton("Retry Loading Content")
            retry_button.clicked.connect(lambda: asyncio.create_task(self.load_content()))
            retry_button.setStyleSheet("padding: 10px 20px; font-size: 14px;")
            self.main_content_layout.addWidget(retry_button, alignment=Qt.AlignmentFlag.AlignCenter)
            
        except Exception as e:
            logger.error(f"Error showing error message: {e}")

    def _update_scroll_arrows_delayed(self, scroll_area, left_arrow, right_arrow):
        """Thread-safe helper to update scroll arrows with a delay."""
        try:
            # Check if we're in the main thread before using QTimer
            from PyQt6.QtCore import QThread
            from PyQt6.QtWidgets import QApplication
            # Check if we have a QApplication and are in the main thread
            app = QApplication.instance()
            # Use the safe timer function
            safe_single_shot(100, lambda: self.update_scroll_arrows_state(scroll_area, left_arrow, right_arrow))
        except Exception as e:
            logger.error(f"Error updating scroll arrows: {e}")
            # Fallback: update immediately without delay
            try:
                self.update_scroll_arrows_state(scroll_area, left_arrow, right_arrow)
            except Exception as fallback_error:
                logger.error(f"Fallback scroll arrow update also failed: {fallback_error}")

    # --- Helper methods for scrolling, adapted from SearchWidget ---
    def scroll_horizontal_area(self, scroll_area: QScrollArea, direction: int):
        h_bar = scroll_area.horizontalScrollBar()
        single_step = h_bar.singleStep() if h_bar.singleStep() > 1 else 150 
        page_step = h_bar.pageStep() if h_bar.pageStep() > single_step else single_step * 2

        current_value = h_bar.value()
        if direction < 0:
            h_bar.setValue(current_value - page_step)
        else:
            h_bar.setValue(current_value + page_step)

    def update_scroll_arrows_state(self, scroll_area: QScrollArea, left_arrow: QPushButton, right_arrow: QPushButton):
        if not scroll_area.isVisible() or not left_arrow.isVisible() or not right_arrow.isVisible():
             # If any part is not visible (e.g. during setup/teardown), try to defer or skip
             # Use signal for thread-safe scroll arrow updates
             self.update_scroll_arrows_signal.emit(scroll_area, left_arrow, right_arrow)
             return
        try:
            h_bar = scroll_area.horizontalScrollBar()
            logger.debug(f"HomePage.update_scroll_arrows_state for {scroll_area.parent().objectName() if scroll_area.parent() else 'UnknownSection'}: Min={h_bar.minimum()}, Max={h_bar.maximum()}, Val={h_bar.value()}, Visible={h_bar.isVisible()}")
            left_arrow.setEnabled(h_bar.value() > h_bar.minimum())
            right_arrow.setEnabled(h_bar.value() < h_bar.maximum())
        except RuntimeError as e: # Catch if widgets are deleted
            logger.warning(f"HomePage.update_scroll_arrows_state: RuntimeError (widget likely deleted): {e}")

    def _initiate_view_all_action(self, section_display_title: str):
        """Initiates the process of fetching all items for a given section title."""
        logger.info(f"HomePage: View All action initiated for section: '{section_display_title}'")
        # We need to find the original API call config for this section_display_title
        # This requires that section_display_title matches one of the 'title' keys in sections_to_load
        asyncio.create_task(self._handle_home_view_all_clicked(section_display_title))

    async def _handle_home_view_all_clicked(self, section_display_title: str):
        """Fetches all items for a category and emits the view_all_requested signal."""
        logger.info(f"HomePage: Handling 'View All' click for section title: {section_display_title}")

        # Find the correct section configuration based on the display title
        original_section_config = None
        # This assumes sections_to_load is defined as it was in the initial load_content context.
        # It might be better to store these configs if load_content is not re-run.
        # For this flow, we'll re-define/access it.
        # Re-defining sections_to_load here for lookup. This is not ideal if it changes.
        # A better approach would be to pass the 'item_type' or the specific API call method.
        # However, to directly use the section_display_title, we need this map.

        temp_sections_to_load_for_lookup = [ # Duplicating for lookup logic, ideally refactor
            {"title": "New Releases", "api_call": self.deezer_api.get_editorial_releases, "item_type": "album"},
            {"title": "Popular Playlists", "api_call": self.deezer_api.get_chart_playlists, "item_type": "playlist"},
            {"title": "Most Streamed Artists", "api_call": self.deezer_api.get_chart_artists, "item_type": "artist"},
            {"title": "Top Albums", "api_call": self.deezer_api.get_chart_albums, "item_type": "album"},
        ]
        for config in temp_sections_to_load_for_lookup:
            if config["title"] == section_display_title:
                original_section_config = config
                break
        
        if not original_section_config:
            logger.error(f"HomePage: Could not find section config for title '{section_display_title}' to fetch all items.")
            return

        api_call_for_all = original_section_config["api_call"]
        # item_type_for_signal = original_section_config["item_type"] # No longer sending item_type

        try:
            logger.info(f"HomePage: Fetching all items for '{section_display_title}' using limit {VIEW_ALL_LIMIT}.")
            # Call the API with the larger limit
            items_for_view_all = await api_call_for_all(limit=VIEW_ALL_LIMIT) 

            if items_for_view_all:
                logger.info(f"HomePage: Emitting view_all_requested for '{section_display_title}' with {len(items_for_view_all)} items.")
                # Map artwork URLs if necessary, similar to load_content
                for item_data in items_for_view_all:
                    actual_item_type = item_data.get('type', original_section_config["item_type"]) # Use 'type' from data or config
                    if actual_item_type == 'album' and 'cover_medium' not in item_data and 'picture_medium' in item_data:
                        item_data['cover_medium'] = item_data['picture_medium']
                    elif actual_item_type == 'album' and 'cover_medium' not in item_data and item_data.get('album', {}).get('cover_medium'): # For chart tracks that are albums
                        item_data['cover_medium'] = item_data['album']['cover_medium']
                    # Add more mappings as identified for other types if needed

                self.view_all_requested.emit(items_for_view_all, section_display_title) # MODIFIED: Emit display title
            else:
                logger.warning(f"HomePage: No items returned when fetching all for '{section_display_title}'.")
        except Exception as e:
            logger.error(f"HomePage: Error fetching all items for '{section_display_title}': {e}", exc_info=True)
            # Optionally, emit an error signal or show a message to the user

    def _on_home_card_item_selected(self, item_data: dict):
        """Handle the card selection signal from SearchResultCard."""
        print(f"[PRINT DEBUG] HomePage._on_home_card_item_selected called with: {item_data.get('title', item_data.get('name', 'Unknown'))}, type: {item_data.get('type')}")
        if not item_data:
            logger.warning("HomePage: Received empty item_data in _on_home_card_item_selected")
            return
            
        item_type = item_data.get('type')
        if not item_type:
            logger.warning(f"HomePage: Item data missing 'type' in _on_home_card_item_selected: {item_data.get('id', 'unknown-id')}")
            return
            
        logger.info(f"HomePage: Card selected. Type: {item_type}, ID: {item_data.get('id')}")
        
        # Emit the home_item_selected signal with the item data and its type
        self.home_item_selected.emit(item_data, item_type)
        
        # Also emit the more specific signals for backward compatibility
        item_id = item_data.get('id')
        if item_id:
            if item_type == 'album':
                logger.info(f"HomePage: Emitting album_selected with ID: {item_id}")
                self.album_selected.emit(item_id)
            elif item_type == 'playlist':
                logger.info(f"HomePage: Emitting playlist_selected with ID: {item_id}")
                self.playlist_selected.emit(item_id)
            elif item_type == 'artist':
                print(f"[PRINT DEBUG] HomePage: About to emit artist_selected with ID: {item_id}")
                logger.info(f"HomePage: Emitting artist_selected with ID: {item_id}")
                self.artist_selected.emit(item_id)
                print(f"[PRINT DEBUG] HomePage: artist_selected.emit({item_id}) completed")
            else:
                logger.warning(f"HomePage: Unsupported item type for navigation: {item_type}")
        else:
            logger.warning(f"HomePage: Item missing ID for navigation. Type: {item_type}")

    def _on_home_card_download_requested(self, item_data: dict):
        """Handle the download button click signal from SearchResultCard."""
        if not item_data:
            logger.warning("HomePage: Received empty item_data in _on_home_card_download_requested")
            return
            
        item_type = item_data.get('type')
        item_id = item_data.get('id')
        
        if not item_id or not item_type:
            logger.warning(f"HomePage: Item missing ID or type for download. Data: {item_data}")
            return
            
        logger.info(f"HomePage: Download requested. Type: {item_type}, ID: {item_id}")
        
        # Emit the signal to MainWindow to handle the download
        self.home_item_download_requested.emit(item_data)
        
    def _handle_card_download_request(self, item_data: dict):
        """Handle a download request from a card directly."""
        # This method might be needed if cards emit signals directly to HomePage
        # rather than or in addition to emitting to MainWindow
        if not self.download_manager:
            logger.warning("Download manager not available in HomePage.")
            # Forward the request to MainWindow to handle
            self.home_item_download_requested.emit(item_data)
            return
        
        # Implementation would be similar to MainWindow._handle_home_item_download 