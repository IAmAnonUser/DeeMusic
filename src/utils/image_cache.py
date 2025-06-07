"""
Utilities for caching images.
"""
import hashlib
import os
from pathlib import Path
from PyQt6.QtGui import QImage
import logging

logger = logging.getLogger(__name__)

# Define the cache directory (e.g., in user's config folder for the app)
APP_NAME = "deemusic" # Or get this from a central config
CACHE_SUBDIR = "image_cache"

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

def _get_cache_filepath(url: str) -> Path:
    """Generates a cache filepath for a given URL."""
    if not url:
        return None
    # Use a hash of the URL to create a unique, filesystem-safe filename
    # Adding a common extension like .jpg can help if opening files manually,
    # but QImage can usually determine type from data.
    # We'll store raw bytes, so extension isn't strictly necessary for QImage.
    filename = hashlib.md5(url.encode('utf-8')).hexdigest()
    return CACHE_DIR / filename

def get_image_from_cache(url: str) -> QImage | None:
    """
    Attempts to load an image from the cache.
    Returns a QImage if found and valid, otherwise None.
    """
    filepath = _get_cache_filepath(url)
    if not filepath:
        return None

    if filepath.exists() and filepath.is_file():
        try:
            with open(filepath, 'rb') as f:
                image_data = f.read()
            if not image_data:
                logger.warning(f"Cached image file is empty: {filepath}")
                # Optionally delete the empty file: os.remove(filepath)
                return None
            
            image = QImage()
            if image.loadFromData(image_data):
                logger.debug(f"Loaded image from cache: {url} (-> {filepath})")
                return image
            else:
                logger.warning(f"Failed to load cached image data into QImage: {filepath}. Deleting corrupt cache file.")
                try:
                    os.remove(filepath)
                except OSError as e:
                    logger.error(f"Error deleting corrupt cache file {filepath}: {e}")
                return None
        except IOError as e:
            logger.error(f"IOError reading cached image {filepath}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error loading image from cache {filepath}: {e}")
            return None # Or re-raise if critical
    return None

def save_image_to_cache(url: str, image_data: bytes):
    """
    Saves image data to the cache.
    """
    filepath = _get_cache_filepath(url)
    if not filepath or not image_data:
        logger.warning(f"Could not save image to cache. URL or data missing. URL: {url}")
        return

    try:
        # Ensure the cache directory exists (should be handled by get_cache_dir, but good practice)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'wb') as f:
            f.write(image_data)
        logger.debug(f"Saved image to cache: {url} (-> {filepath})")
    except IOError as e:
        logger.error(f"IOError saving image to cache {filepath}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error saving image to cache {filepath}: {e}")

def get_cache_size() -> int:
    """Returns the total size of the image cache in bytes."""
    try:
        total_size = 0
        for file_path in CACHE_DIR.glob('*'):
            if file_path.is_file():
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
            if file_path.is_file():
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
                os.remove(file_path)
                deleted_size += size
                deleted_count += 1
            except OSError as e:
                logger.error(f"Failed to delete cache file {file_path}: {e}")
                continue
                
        logger.info(f"Cache cleanup complete. Removed {deleted_count} files ({deleted_size / (1024 * 1024):.2f} MB)")
    except Exception as e:
        logger.error(f"Error cleaning cache: {e}", exc_info=True)

# Optional: Add functions for cache management (e.g., clear_cache, get_cache_size) if needed. 