"""Service for streaming track previews."""

import os
import logging
import aiohttp
import asyncio
from typing import Dict, Optional, BinaryIO
from pathlib import Path
from deemusic.config_manager import ConfigManager
from .deezer_api import DeezerAPI
import requests
import io

logger = logging.getLogger(__name__)

class PreviewStreamer:
    """Service for streaming track previews."""
    
    def __init__(self, config: ConfigManager, deezer_api: DeezerAPI):
        self.config = config
        self.deezer_api = deezer_api
        self.cache_dir = Path(config.get_setting('cache.path', str(Path.home() / '.deemusic' / 'cache')))
        self._setup_cache_dir()
        
    def _setup_cache_dir(self):
        """Create cache directory if it doesn't exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
    def _get_cache_path(self, track_id: int) -> Path:
        """Get the cache file path for a track preview."""
        return self.cache_dir / f"preview_{track_id}.mp3"
        
    async def get_preview_stream(self, track_id: int) -> Optional[Path]:
        """Get a preview stream for a track.
        
        This will first check if the preview is cached. If not, it will
        download it to the cache and return the path to the cached file.
        
        Args:
            track_id: Deezer track ID
            
        Returns:
            Path to the cached preview file, or None if preview not available
        """
        try:
            # Check cache first
            cache_path = self._get_cache_path(track_id)
            if cache_path.exists():
                return cache_path
                
            # Get preview URL
            preview_url = await self.deezer_api.get_preview_url(track_id)
            if not preview_url:
                logger.warning(f"No preview available for track {track_id}")
                return None
                
            # Download preview to cache
            async with aiohttp.ClientSession() as session:
                async with session.get(preview_url) as response:
                    if response.status != 200:
                        logger.error(f"Failed to download preview: {response.status}")
                        return None
                        
                    with open(cache_path, 'wb') as f:
                        while True:
                            chunk = await response.content.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)
                            
            return cache_path
            
        except Exception as e:
            logger.error(f"Failed to get preview stream for track {track_id}: {str(e)}")
            return None
            
    def clear_cache(self, track_id: Optional[int] = None):
        """Clear preview cache.
        
        Args:
            track_id: If provided, only clear cache for this track.
                     If None, clear entire cache.
        """
        try:
            if track_id is not None:
                cache_path = self._get_cache_path(track_id)
                if cache_path.exists():
                    cache_path.unlink()
            else:
                # Clear all preview files
                for cache_file in self.cache_dir.glob("preview_*.mp3"):
                    cache_file.unlink()
                    
        except Exception as e:
            logger.error(f"Failed to clear preview cache: {str(e)}")
            
    async def get_preview_info(self, track_id: int) -> Dict:
        """Get information about a track preview.
        
        Args:
            track_id: Deezer track ID
            
        Returns:
            Dictionary containing:
                - available: bool - Whether preview is available
                - duration: int - Duration in seconds (usually 30)
                - file_path: Optional[str] - Path to cached preview if available
        """
        try:
            track_data = await self.deezer_api.get_track(track_id)
            preview_path = await self.get_preview_stream(track_id)
            
            return {
                'available': preview_path is not None,
                'duration': 30,  # Deezer previews are typically 30 seconds
                'file_path': str(preview_path) if preview_path else None
            }
            
        except Exception as e:
            logger.error(f"Failed to get preview info for track {track_id}: {str(e)}")
            return {
                'available': False,
                'duration': 0,
                'file_path': None
            } 