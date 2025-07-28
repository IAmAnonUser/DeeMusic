"""
DeeMusic Integration - Handles launching DeeMusic for downloads
"""

import os
import subprocess
import logging
import json
import tempfile
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

from ..core.data_models import MissingAlbum, MissingTrack

logger = logging.getLogger(__name__)

class DeeMusicIntegration:
    """Handles integration with DeeMusic for downloading missing items."""
    
    def __init__(self, config):
        """Initialize DeeMusic integration."""
        self.config = config
        self.deemusic_path = config.get_deemusic_path()
    
    def is_deemusic_available(self) -> bool:
        """Check if DeeMusic is available and accessible."""
        if not self.deemusic_path:
            return False
        
        deemusic_path = Path(self.deemusic_path)
        return deemusic_path.exists() and deemusic_path.is_file()
    
    def set_deemusic_path(self, path: str) -> bool:
        """Set the path to DeeMusic executable."""
        if not path:
            return False
        
        deemusic_path = Path(path)
        if deemusic_path.exists() and deemusic_path.is_file():
            self.deemusic_path = path
            self.config.set_deemusic_path(path)
            return True
        
        return False
    
    def launch_deemusic(self) -> bool:
        """Launch DeeMusic application."""
        if not self.is_deemusic_available():
            logger.error("DeeMusic is not available or path not set")
            return False
        
        try:
            # Launch DeeMusic in a separate process
            subprocess.Popen([self.deemusic_path], shell=True)
            logger.info("DeeMusic launched successfully")
            return True
        except Exception as e:
            logger.error(f"Error launching DeeMusic: {e}")
            return False
    
    def download_missing_albums(self, missing_albums: List[MissingAlbum]) -> bool:
        """Download missing albums using DeeMusic."""
        if not self.is_deemusic_available():
            logger.error("DeeMusic is not available")
            return False
        
        if not missing_albums:
            logger.info("No missing albums to download")
            return True
        
        try:
            # Create download list
            download_list = []
            for missing_album in missing_albums:
                album_info = {
                    "type": "album",
                    "id": missing_album.deezer_album.id,
                    "title": missing_album.deezer_album.title,
                    "artist": missing_album.deezer_album.artist,
                    "year": missing_album.deezer_album.year,
                    "track_count": missing_album.deezer_album.track_count,
                    "url": f"https://www.deezer.com/album/{missing_album.deezer_album.id}"
                }
                download_list.append(album_info)
            
            # Create temporary file with download list
            temp_file = self._create_download_file(download_list)
            
            # Launch DeeMusic with download file
            cmd = [self.deemusic_path, "--import", temp_file]
            subprocess.Popen(cmd, shell=True)
            
            logger.info(f"Initiated download of {len(missing_albums)} albums")
            return True
            
        except Exception as e:
            logger.error(f"Error downloading albums: {e}")
            return False
    
    def download_missing_tracks(self, missing_tracks: List[MissingTrack]) -> bool:
        """Download missing tracks using DeeMusic."""
        if not self.is_deemusic_available():
            logger.error("DeeMusic is not available")
            return False
        
        if not missing_tracks:
            logger.info("No missing tracks to download")
            return True
        
        try:
            # Create download list
            download_list = []
            for missing_track in missing_tracks:
                track_info = {
                    "type": "track",
                    "id": missing_track.deezer_track.id,
                    "title": missing_track.deezer_track.title,
                    "artist": missing_track.deezer_track.artist,
                    "album": missing_track.deezer_track.album,
                    "duration": missing_track.deezer_track.duration,
                    "url": f"https://www.deezer.com/track/{missing_track.deezer_track.id}"
                }
                download_list.append(track_info)
            
            # Create temporary file with download list
            temp_file = self._create_download_file(download_list)
            
            # Launch DeeMusic with download file
            cmd = [self.deemusic_path, "--import", temp_file]
            subprocess.Popen(cmd, shell=True)
            
            logger.info(f"Initiated download of {len(missing_tracks)} tracks")
            return True
            
        except Exception as e:
            logger.error(f"Error downloading tracks: {e}")
            return False
    
    def _create_download_file(self, download_list: List[Dict[str, Any]]) -> str:
        """Create a temporary file with download information."""
        try:
            # Create temporary file
            temp_fd, temp_path = tempfile.mkstemp(suffix=".json", prefix="deemusic_downloads_")
            
            # Write download list to file
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                json.dump({
                    "downloads": download_list,
                    "source": "DeeMusic Library Scanner",
                    "timestamp": str(datetime.now())
                }, f, indent=2, ensure_ascii=False)
            
            return temp_path
            
        except Exception as e:
            logger.error(f"Error creating download file: {e}")
            raise
    
    def get_deezer_urls(self, missing_albums: List[MissingAlbum]) -> List[str]:
        """Get Deezer URLs for missing albums."""
        urls = []
        for missing_album in missing_albums:
            url = f"https://www.deezer.com/album/{missing_album.deezer_album.id}"
            urls.append(url)
        return urls
    
    def get_track_urls(self, missing_tracks: List[MissingTrack]) -> List[str]:
        """Get Deezer URLs for missing tracks."""
        urls = []
        for missing_track in missing_tracks:
            url = f"https://www.deezer.com/track/{missing_track.deezer_track.id}"
            urls.append(url)
        return urls
    
    def copy_urls_to_clipboard(self, urls: List[str]) -> bool:
        """Copy URLs to clipboard."""
        try:
            import pyperclip
            url_text = "\n".join(urls)
            pyperclip.copy(url_text)
            logger.info(f"Copied {len(urls)} URLs to clipboard")
            return True
        except ImportError:
            logger.warning("pyperclip not available, cannot copy to clipboard")
            return False
        except Exception as e:
            logger.error(f"Error copying to clipboard: {e}")
            return False
    
    def auto_detect_deemusic(self) -> str:
        """Auto-detect DeeMusic installation."""
        possible_paths = [
            # Current directory
            "./DeeMusic.exe",
            "../DeeMusic.exe",
            "../tools/dist/DeeMusic.exe",
            
            # Program Files
            "C:/Program Files/DeeMusic/DeeMusic.exe",
            "C:/Program Files (x86)/DeeMusic/DeeMusic.exe",
            
            # User directory
            os.path.expanduser("~/DeeMusic/DeeMusic.exe"),
            os.path.expanduser("~/Desktop/DeeMusic.exe"),
            os.path.expanduser("~/Downloads/DeeMusic.exe"),
        ]
        
        for path in possible_paths:
            if Path(path).exists():
                logger.info(f"Auto-detected DeeMusic at: {path}")
                return path
        
        logger.warning("Could not auto-detect DeeMusic installation")
        return "" 