"""
Advanced image caching system with preloading and memory optimization.
"""
import hashlib
import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Set, Tuple, List
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import QObject, QThread, pyqtSignal, QTimer, QSize, Qt
import logging
import weakref
from collections import OrderedDict
import requests
from io import BytesIO

logger = logging.getLogger(__name__)

class MemoryCache:
    """LRU memory cache for pixmaps with size limits."""
    
    def __init__(self, max_size_mb: int = 50, max_items: int = 200):
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.max_items = max_items
        self.cache: OrderedDict[str, Tuple[QPixmap, int]] = OrderedDict()  # url -> (pixmap, size_bytes)
        self.current_size = 0
        self.lock = threading.RLock()
    
    def get(self, url: str) -> Optional[QPixmap]:
        """Get pixmap from memory cache."""
        with self.lock:
            if url in self.cache:
                # Move to end (most recently used)
                pixmap, size = self.cache.pop(url)
                self.cache[url] = (pixmap, size)
                return pixmap
        return None
    
    def put(self, url: str, pixmap: QPixmap):
        """Store pixmap in memory cache."""
        if pixmap.isNull():
            return
            
        with self.lock:
            # Estimate pixmap size in bytes
            size_bytes = pixmap.width() * pixmap.height() * 4  # RGBA
            
            # Remove if already exists
            if url in self.cache:
                _, old_size = self.cache.pop(url)
                self.current_size -= old_size
            
            # Make room if needed
            while (self.current_size + size_bytes > self.max_size_bytes or 
                   len(self.cache) >= self.max_items) and self.cache:
                _, (removed_pixmap, removed_size) = self.cache.popitem(last=False)  # Remove oldest
                self.current_size -= removed_size
            
            # Add new item
            self.cache[url] = (pixmap, size_bytes)
            self.current_size += size_bytes
            
            # Only log cache stats occasionally to reduce spam
            if len(self.cache) % 20 == 0:  # Log every 20 items
                logger.debug(f"Memory cache: {len(self.cache)} items, {self.current_size / (1024*1024):.1f}MB")
    
    def clear(self):
        """Clear the memory cache."""
        with self.lock:
            self.cache.clear()
            self.current_size = 0

class ImagePreloader(QThread):
    """Background thread for preloading images."""
    
    image_loaded = pyqtSignal(str, QPixmap)  # url, pixmap
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.queue: List[Tuple[str, QSize]] = []  # (url, target_size)
        self.queue_lock = threading.Lock()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.running = True
    
    def add_to_queue(self, url: str, target_size: QSize = None):
        """Add URL to preload queue."""
        if not url:
            return
            
        with self.queue_lock:
            # Don't add duplicates
            if (url, target_size) not in self.queue:
                self.queue.append((url, target_size))
    
    def run(self):
        """Main preloader loop."""
        while self.running:
            try:
                with self.queue_lock:
                    if not self.queue:
                        self.msleep(100)  # Sleep 100ms if no work
                        continue
                    url, target_size = self.queue.pop(0)
                
                # Check if already in memory cache
                cached = OptimizedImageCache.instance().memory_cache.get(url)
                if cached:
                    continue
                
                # Load image
                pixmap = self._load_image(url, target_size)
                if pixmap and not pixmap.isNull():
                    self.image_loaded.emit(url, pixmap)
                    
            except Exception as e:
                logger.error(f"Preloader error: {e}")
                self.msleep(1000)  # Wait before retrying
    
    def _load_image(self, url: str, target_size: QSize = None) -> Optional[QPixmap]:
        """Load and optionally resize image."""
        try:
            # Try disk cache first
            from utils.image_cache import get_image_from_cache, save_image_to_cache
            
            cached_image = get_image_from_cache(url)
            if cached_image:
                pixmap = QPixmap.fromImage(cached_image)
                if target_size and not target_size.isEmpty():
                    pixmap = pixmap.scaled(target_size, 
                                         Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation)
                return pixmap
            
            # Download with timeout
            response = self.session.get(url, timeout=5, stream=True)
            response.raise_for_status()
            
            image_data = BytesIO()
            for chunk in response.iter_content(chunk_size=8192):
                image_data.write(chunk)
            
            image_data.seek(0)
            image_bytes = image_data.getvalue()
            
            # Save to disk cache
            save_image_to_cache(url, image_bytes)
            
            # Create QImage and scale if needed
            image = QImage()
            if image.loadFromData(image_bytes):
                pixmap = QPixmap.fromImage(image)
                if target_size and not target_size.isEmpty():
                    pixmap = pixmap.scaled(target_size,
                                         Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation)
                return pixmap
                
        except Exception as e:
            logger.debug(f"Error loading image {url}: {e}")
        
        return None
    
    def stop(self):
        """Stop the preloader thread."""
        self.running = False
        self.quit()
        self.wait()

class OptimizedImageCache(QObject):
    """Optimized image cache with memory caching and preloading."""
    
    _instance = None
    
    @classmethod
    def instance(cls):
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.memory_cache = MemoryCache(max_size_mb=30, max_items=150)
        self.preloader = ImagePreloader(self)
        self.preloader.image_loaded.connect(self._on_preloaded_image)
        self.preloader.start()
        
        # Track what's being loaded to avoid duplicates
        self.loading_urls: Set[str] = set()
        self.loading_lock = threading.Lock()
        
        # Cleanup timer
        self.cleanup_timer = QTimer(self)
        self.cleanup_timer.timeout.connect(self._cleanup_cache)
        self.cleanup_timer.start(300000)  # 5 minutes
    
    def get_image(self, url: str, target_size: QSize = None) -> Optional[QPixmap]:
        """Get image from cache or start loading."""
        if not url:
            return None
        
        # Try memory cache first (fastest)
        pixmap = self.memory_cache.get(url)
        if pixmap:
            return self._resize_if_needed(pixmap, target_size)
        
        # Try disk cache
        from utils.image_cache import get_image_from_cache
        cached_image = get_image_from_cache(url)
        if cached_image:
            pixmap = QPixmap.fromImage(cached_image)
            if target_size:
                pixmap = self._resize_if_needed(pixmap, target_size)
            self.memory_cache.put(url, pixmap)
            return pixmap
        
        # Add to preload queue if not already loading
        with self.loading_lock:
            if url not in self.loading_urls:
                self.loading_urls.add(url)
                self.preloader.add_to_queue(url, target_size)
        
        return None
    
    def _resize_if_needed(self, pixmap: QPixmap, target_size: QSize) -> QPixmap:
        """Resize pixmap if target size is specified and different."""
        if not target_size or target_size.isEmpty():
            return pixmap
        
        if pixmap.size() != target_size:
            return pixmap.scaled(target_size,
                               Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
        return pixmap
    
    def _on_preloaded_image(self, url: str, pixmap: QPixmap):
        """Handle preloaded image."""
        self.memory_cache.put(url, pixmap)
        
        with self.loading_lock:
            self.loading_urls.discard(url)
    
    def preload_urls(self, urls: List[str], target_size: QSize = None):
        """Preload multiple URLs."""
        for url in urls:
            if url and self.memory_cache.get(url) is None:
                self.preloader.add_to_queue(url, target_size)
    
    def _cleanup_cache(self):
        """Periodic cache cleanup."""
        try:
            from utils.image_cache import clean_cache
            clean_cache(max_size_mb=100, max_age_days=7)
        except Exception as e:
            logger.error(f"Cache cleanup error: {e}")
    
    def clear_memory_cache(self):
        """Clear memory cache."""
        self.memory_cache.clear()
    
    def shutdown(self):
        """Shutdown the cache system."""
        if self.preloader:
            self.preloader.stop()
        self.cleanup_timer.stop()

# Global functions for easy access
def get_optimized_image(url: str, target_size: QSize = None) -> Optional[QPixmap]:
    """Get image from optimized cache."""
    return OptimizedImageCache.instance().get_image(url, target_size)

def preload_images(urls: List[str], target_size: QSize = None):
    """Preload multiple images."""
    OptimizedImageCache.instance().preload_urls(urls, target_size)

def clear_image_cache():
    """Clear memory cache."""
    OptimizedImageCache.instance().clear_memory_cache()

def shutdown_image_cache():
    """Shutdown image cache system."""
    OptimizedImageCache.instance().shutdown() 