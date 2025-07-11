"""
Performance manager for DeeMusic application.
Handles lazy loading, preloading, and optimization strategies.
"""
import logging
from typing import List, Dict, Optional, Set
from PyQt6.QtCore import QObject, QTimer, pyqtSignal, QRect, QPoint
from PyQt6.QtWidgets import QWidget, QScrollArea, QAbstractScrollArea
from PyQt6.QtGui import QPixmap

from src.utils.image_cache_optimized import preload_images, OptimizedImageCache

logger = logging.getLogger(__name__)

class ViewportTracker(QObject):
    """Tracks which widgets are visible in viewport."""
    
    widgets_in_viewport_changed = pyqtSignal(list)  # List of visible widgets
    
    def __init__(self, scroll_area: QScrollArea, parent=None):
        super().__init__(parent)
        self.scroll_area = scroll_area
        self.tracked_widgets: List[QWidget] = []
        self.visible_widgets: Set[QWidget] = set()
        
        # Setup timer for periodic checking
        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self._check_visibility)
        self.check_timer.start(200)  # Check every 200ms
        
        # Connect scroll events
        if hasattr(scroll_area, 'verticalScrollBar'):
            scroll_area.verticalScrollBar().valueChanged.connect(self._on_scroll)
        if hasattr(scroll_area, 'horizontalScrollBar'):
            scroll_area.horizontalScrollBar().valueChanged.connect(self._on_scroll)
    
    def add_widget(self, widget: QWidget):
        """Add widget to viewport tracking."""
        if widget not in self.tracked_widgets:
            self.tracked_widgets.append(widget)
    
    def remove_widget(self, widget: QWidget):
        """Remove widget from tracking."""
        if widget in self.tracked_widgets:
            self.tracked_widgets.remove(widget)
        self.visible_widgets.discard(widget)
    
    def _on_scroll(self):
        """Handle scroll events."""
        self._check_visibility()
    
    def _check_visibility(self):
        """Check which widgets are currently visible."""
        if not self.scroll_area or not hasattr(self.scroll_area, 'viewport'):
            return
        
        viewport_rect = self.scroll_area.viewport().rect()
        scroll_widget = self.scroll_area.widget()
        
        if not scroll_widget:
            return
        
        new_visible = set()
        
        for widget in self.tracked_widgets:
            if not widget or widget.isHidden():
                continue
            
            # Get widget position relative to scroll area
            widget_pos = widget.mapTo(scroll_widget, QPoint(0, 0))
            widget_rect = QRect(widget_pos, widget.size())
            
            # Check if widget intersects with viewport
            if viewport_rect.intersects(widget_rect):
                new_visible.add(widget)
                
                # Notify widget it's in viewport
                if hasattr(widget, 'set_in_viewport'):
                    widget.set_in_viewport(True)
        
        # Notify widgets no longer in viewport
        for widget in self.visible_widgets - new_visible:
            if hasattr(widget, 'set_in_viewport'):
                widget.set_in_viewport(False)
        
        # Update visible set
        if new_visible != self.visible_widgets:
            self.visible_widgets = new_visible
            self.widgets_in_viewport_changed.emit(list(new_visible))

class ImagePreloadManager(QObject):
    """Manages preloading of images for better performance."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.preload_queue: List[Dict] = []
        self.preloaded_urls: Set[str] = set()
        
        # Preload timer
        self.preload_timer = QTimer()
        self.preload_timer.timeout.connect(self._process_preload_queue)
        self.preload_timer.start(1000)  # Process every second
    
    def request_preload(self, items: List[Dict], priority: int = 1):
        """Request preloading of images for items."""
        for item in items:
            urls = self._extract_image_urls(item)
            for url in urls:
                if url not in self.preloaded_urls:
                    self.preload_queue.append({
                        'url': url,
                        'priority': priority,
                        'item_type': item.get('type', 'unknown')
                    })
        
        # Sort by priority
        self.preload_queue.sort(key=lambda x: x['priority'], reverse=True)
    
    def _extract_image_urls(self, item: Dict) -> List[str]:
        """Extract image URLs from item data."""
        urls = []
        
        # Direct URLs
        for key in ['cover_xl', 'cover_big', 'cover_medium', 'picture_xl', 'picture_big']:
            url = item.get(key)
            if url:
                urls.append(url)
        
        # Nested URLs
        for container in ['album', 'artist']:
            if container in item and isinstance(item[container], dict):
                for key in ['cover_xl', 'cover_big', 'picture_xl', 'picture_big']:
                    url = item[container].get(key)
                    if url:
                        urls.append(url)
        
        return urls
    
    def _process_preload_queue(self):
        """Process items in preload queue."""
        if not self.preload_queue:
            return
        
        # Process up to 5 items at once
        batch_size = 5
        batch = self.preload_queue[:batch_size]
        self.preload_queue = self.preload_queue[batch_size:]
        
        urls = [item['url'] for item in batch if item['url'] not in self.preloaded_urls]
        
        if urls:
            preload_images(urls)
            self.preloaded_urls.update(urls)
            logger.debug(f"Preloaded {len(urls)} images")

class PerformanceManager(QObject):
    """Central performance management system."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Components
        self.viewport_trackers: Dict[str, ViewportTracker] = {}
        self.preload_manager = ImagePreloadManager(self)
        
        # Performance settings
        self.lazy_loading_enabled = True
        self.preloading_enabled = True
        self.memory_cache_size_mb = 30
        
        # Statistics
        self.stats = {
            'images_loaded': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }
    
    def register_scroll_area(self, name: str, scroll_area: QScrollArea):
        """Register a scroll area for viewport tracking."""
        tracker = ViewportTracker(scroll_area, self)
        tracker.widgets_in_viewport_changed.connect(
            lambda widgets: self._on_viewport_changed(name, widgets)
        )
        self.viewport_trackers[name] = tracker
        logger.debug(f"Registered scroll area: {name}")
    
    def add_widget_to_tracking(self, scroll_area_name: str, widget: QWidget):
        """Add widget to viewport tracking."""
        if scroll_area_name in self.viewport_trackers:
            self.viewport_trackers[scroll_area_name].add_widget(widget)
    
    def _on_viewport_changed(self, area_name: str, visible_widgets: List[QWidget]):
        """Handle viewport changes."""
        logger.debug(f"Viewport '{area_name}': {len(visible_widgets)} visible widgets")
        
        if self.preloading_enabled:
            # Extract items for preloading
            items = []
            for widget in visible_widgets:
                if hasattr(widget, 'item_data'):
                    items.append(widget.item_data)
            
            if items:
                self.preload_manager.request_preload(items, priority=2)
    
    def optimize_for_search_results(self, items: List[Dict]):
        """Optimize for displaying search results."""
        if not self.preloading_enabled:
            return
        
        # Preload first few items with high priority
        priority_items = items[:10]  # First 10 items
        self.preload_manager.request_preload(priority_items, priority=3)
        
        # Preload remaining items with lower priority
        remaining_items = items[10:30]  # Next 20 items
        if remaining_items:
            self.preload_manager.request_preload(remaining_items, priority=1)
    
    def optimize_for_album_view(self, album_data: Dict, tracks: List[Dict]):
        """Optimize for album detail view."""
        if not self.preloading_enabled:
            return
        
        # Preload album cover with highest priority
        if album_data:
            self.preload_manager.request_preload([album_data], priority=5)
        
        # Preload track artwork with medium priority
        if tracks:
            self.preload_manager.request_preload(tracks[:20], priority=2)
    
    def optimize_for_artist_view(self, artist_data: Dict, albums: List[Dict]):
        """Optimize for artist detail view."""
        if not self.preloading_enabled:
            return
        
        # Preload artist image with highest priority
        if artist_data:
            self.preload_manager.request_preload([artist_data], priority=5)
        
        # Preload album covers
        if albums:
            self.preload_manager.request_preload(albums[:15], priority=2)
    
    def update_settings(self, settings: Dict):
        """Update performance settings."""
        self.lazy_loading_enabled = settings.get('lazy_loading', True)
        self.preloading_enabled = settings.get('preloading', True)
        self.memory_cache_size_mb = settings.get('memory_cache_mb', 30)
        
        logger.info(f"Performance settings updated: lazy={self.lazy_loading_enabled}, "
                   f"preload={self.preloading_enabled}, cache={self.memory_cache_size_mb}MB")
    
    def get_performance_stats(self) -> Dict:
        """Get performance statistics."""
        return self.stats.copy()
    
    def cleanup(self):
        """Cleanup resources."""
        for tracker in self.viewport_trackers.values():
            tracker.check_timer.stop()
        self.preload_manager.preload_timer.stop()
        
        # Clear caches
        OptimizedImageCache.instance().clear_memory_cache()

# Global performance manager instance
_performance_manager = None

def get_performance_manager() -> PerformanceManager:
    """Get global performance manager instance."""
    global _performance_manager
    if _performance_manager is None:
        _performance_manager = PerformanceManager()
    return _performance_manager 