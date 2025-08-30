"""
Utilities for caching images.
"""
import hashlib
import os
from pathlib import Path
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import QSize
import logging
from typing import Optional
from functools import lru_cache
import threading

logger = logging.getLogger(__name__)

# Define the cache directory (e.g., in user's config folder for the app)
APP_NAME = "deemusic" # Or get this from a central config
CACHE_SUBDIR = "image_cache"

# In-memory cache for frequently accessed images (LRU cache with size limit)
_memory_cache = {}
_memory_cache_lock = threading.Lock()
_memory_cache_max_size = 50  # Default, will be dynamically adjusted
_memory_cache_order = []  # Track access order for LRU eviction

def _update_cache_size():
    """Update cache size based on system resources."""
    # Simple static cache size for stability
    global _memory_cache_max_size
    _memory_cache_max_size = 100  # Reasonable default
    logger.debug(f"Set image cache size to: {_memory_cache_max_size}")

# Initialize cache size
_update_cache_size()

def get_cache_dir() -> Path:
    """Returns the application's image cache directory, creating it if necessary."""
    try:
        # A common place for user-specific application data/cache
        base_cache_path = Path.home() / ".cache" / APP_NAME / CACHE_SUBDIR
    except Exception: # Fallback if Path.home() isn't writable or available
        base_cache_path = Path(".") / ".cache" / APP_NAME / CACHE_SUBDIR
    
    try:
        base_cache_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(f"Failed to create cache directory {base_cache_path}: {e}")
        # Fallback to a temporary directory or handle error appropriately
        # For simplicity, we'll just log and proceed; images won't cache if this fails.
    return base_cache_path

CACHE_DIR = get_cache_dir()

@lru_cache(maxsize=1000)
def _get_cache_filepath(url: str) -> Path:
    """Generates a cache filepath for a given URL (cached for performance)."""
    if not url:
        return None
    # Use a hash of the URL to create a unique, filesystem-safe filename
    filename = hashlib.md5(url.encode('utf-8')).hexdigest()
    return CACHE_DIR / filename

def _manage_memory_cache(url: str, image: QImage):
    """Add image to memory cache with LRU eviction."""
    with _memory_cache_lock:
        # Remove from current position if exists
        if url in _memory_cache:
            _memory_cache_order.remove(url)
        
        # Add to end (most recent)
        _memory_cache_order.append(url)
        _memory_cache[url] = image
        
        # Evict oldest if over limit
        while len(_memory_cache_order) > _memory_cache_max_size:
            oldest_url = _memory_cache_order.pop(0)
            _memory_cache.pop(oldest_url, None)

def _get_from_memory_cache(url: str) -> Optional[QImage]:
    """Get image from memory cache."""
    with _memory_cache_lock:
        if url in _memory_cache:
            # Move to end (most recent)
            _memory_cache_order.remove(url)
            _memory_cache_order.append(url)
            return _memory_cache[url]
    return None

def get_image_from_cache(url: str) -> QImage | None:
    """
    Attempts to load an image from the cache (memory first, then disk).
    Returns a QImage if found and valid, otherwise None.
    """
    if not url:
        return None
    
    # Check memory cache first (fastest)
    memory_image = _get_from_memory_cache(url)
    if memory_image:
        logger.debug(f"Loaded image from memory cache: {url}")
        return memory_image
    
    # Check disk cache
    filepath = _get_cache_filepath(url)
    if not filepath:
        return None

    if filepath.exists() and filepath.is_file():
        try:
            # Optimized file reading - read entire file at once
            image_data = filepath.read_bytes()
            if not image_data:
                logger.warning(f"Cached image file is empty: {filepath}")
                try:
                    filepath.unlink()  # Delete empty file
                except OSError:
                    pass
                return None
            
            image = QImage()
            if image.loadFromData(image_data):
                logger.debug(f"Loaded image from disk cache: {url} (-> {filepath})")
                # Add to memory cache for faster future access
                _manage_memory_cache(url, image)
                return image
            else:
                logger.warning(f"Failed to load cached image data into QImage: {filepath}. Deleting corrupt cache file.")
                try:
                    filepath.unlink()  # Delete corrupt file
                except OSError as e:
                    logger.error(f"Error deleting corrupt cache file {filepath}: {e}")
                return None
        except Exception as e:
            logger.error(f"Error loading image from cache {filepath}: {e}")
            return None
    return None

def get_pixmap_from_cache(url: str, target_size: Optional[QSize] = None) -> Optional[QPixmap]:
    """
    Get a QPixmap from cache, optionally scaled to target size.
    This is more efficient for UI usage than converting QImage to QPixmap repeatedly.
    """
    image = get_image_from_cache(url)
    if image:
        pixmap = QPixmap.fromImage(image)
        if target_size and not target_size.isEmpty():
            # Scale maintaining aspect ratio
            pixmap = pixmap.scaled(target_size, 
                                 aspectRatioMode=1,  # Qt.KeepAspectRatio
                                 transformMode=1)    # Qt.SmoothTransformation
        return pixmap
    return None

def save_image_to_cache(url: str, image_data: bytes):
    """
    Saves image data to the cache.
    """
    if not url or not image_data:
        logger.warning(f"Could not save image to cache. URL or data missing. URL: {url}")
        return

    filepath = _get_cache_filepath(url)
    if not filepath:
        return

    try:
        # Ensure the cache directory exists
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Atomic write: write to temp file then move
        temp_filepath = filepath.with_suffix('.tmp')
        temp_filepath.write_bytes(image_data)
        temp_filepath.replace(filepath)
        
        logger.debug(f"Saved image to cache: {url} (-> {filepath})")
        
        # Also add to memory cache for immediate future access
        image = QImage()
        if image.loadFromData(image_data):
            _manage_memory_cache(url, image)
            
    except Exception as e:
        logger.error(f"Error saving image to cache {filepath}: {e}")

def clear_memory_cache():
    """Clear the in-memory cache."""
    with _memory_cache_lock:
        _memory_cache.clear()
        _memory_cache_order.clear()
    logger.debug("Memory cache cleared")

def batch_preload_from_cache(urls: list[str], target_size: Optional[QSize] = None) -> dict[str, QPixmap]:
    """
    Batch preload multiple images from cache (memory + disk) for performance optimization.
    Returns a dict of url -> QPixmap for images that were found in cache.
    """
    found_pixmaps = {}
    
    for url in urls:
        if not url:
            continue
            
        try:
            pixmap = get_pixmap_from_cache(url, target_size)
            if pixmap and not pixmap.isNull():
                found_pixmaps[url] = pixmap
        except Exception as e:
            logger.debug(f"Error preloading from cache {url}: {e}")
            continue
    
    logger.debug(f"Batch preloaded {len(found_pixmaps)}/{len(urls)} images from cache")
    return found_pixmaps

def get_cache_size() -> int:
    """Returns the total size of the image cache in bytes."""
    try:
        total_size = 0
        for file_path in CACHE_DIR.glob('*'):
            if file_path.is_file() and not file_path.name.endswith('.tmp'):
                total_size += file_path.stat().st_size
        return total_size
    except Exception as e:
        logger.error(f"Error calculating cache size: {e}")
        return 0

def clean_cache(max_size_mb: int = 100, max_age_days: int = 30):
    """
    Cleans the image cache by removing old files when the cache exceeds a maximum size.
    
    Args:
        max_size_mb: Maximum cache size in megabytes
        max_age_days: Maximum age of cache files in days
    """
    try:
        # Convert max_size_mb to bytes
        max_size_bytes = max_size_mb * 1024 * 1024
        
        # Check current cache size
        current_size = get_cache_size()
        if current_size < max_size_bytes:
            # Cache is under the size limit, no need to clean
            return
            
        logger.info(f"Cache size ({current_size / (1024 * 1024):.2f} MB) exceeds maximum ({max_size_mb} MB). Cleaning...")
        
        # Get all cache files with their modification time
        cache_files = []
        for file_path in CACHE_DIR.glob('*'):
            if file_path.is_file() and not file_path.name.endswith('.tmp'):
                # Get file modification time and size
                try:
                    mtime = file_path.stat().st_mtime
                    size = file_path.stat().st_size
                    cache_files.append((file_path, mtime, size))
                except OSError:
                    continue
        
        # Sort by modification time (oldest first)
        cache_files.sort(key=lambda x: x[1])
        
        # Remove files until we're under the size limit
        deleted_count = 0
        deleted_size = 0
        for file_path, mtime, size in cache_files:
            if current_size - deleted_size <= max_size_bytes * 0.8:  # Clean until 80% of max size
                break
                
            try:
                file_path.unlink()
                deleted_size += size
                deleted_count += 1
            except OSError as e:
                logger.error(f"Failed to delete cache file {file_path}: {e}")
                continue
                
        logger.info(f"Cache cleanup complete. Removed {deleted_count} files ({deleted_size / (1024 * 1024):.2f} MB)")
        
        # Clear memory cache after disk cleanup
        clear_memory_cache()
        
    except Exception as e:
        logger.error(f"Error cleaning cache: {e}", exc_info=True)

# Optional: Add functions for cache management (e.g., clear_cache, get_cache_size) if needed. 