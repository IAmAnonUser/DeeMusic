"""Service for managing music downloads."""

import os
import logging
import asyncio
import json
from typing import Dict, List, Optional, Any
from pathlib import Path
import requests
import re
import tempfile
# Removed subprocess, configparser, tempfile (not needed for direct download)
# import subprocess
# import configparser
import shutil
# Removed deemix imports: Deezer, deemix_settings, Downloader, Single, Collection, formatListener
# Removed aiohttp (likely not needed for new sync approach)
import traceback
# Add imports for QRunnable
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, QThreadPool
import time
# Corrected imports
from src.config_manager import ConfigManager 
from src.services.deezer_api import DeezerAPI # Assuming deezer_api.py is in the same 'services' package
import json

# Add crypto imports
from Crypto.Hash import MD5  # type: ignore
from Crypto.Cipher import Blowfish, AES  # type: ignore
from binascii import a2b_hex, b2a_hex

# Add mutagen imports
from mutagen.mp3 import MP3, EasyMP3  # type: ignore
from mutagen.id3 import ID3, APIC, TPE1, TIT2, TALB, TRCK, TPOS, TDRC, TCON, TCOM, TPE2, TPUB, TSRC, USLT, SYLT  # type: ignore
from mutagen.easyid3 import EasyID3  # type: ignore
from mutagen.flac import FLAC, Picture  # type: ignore

# Add lyrics utils import
from src.utils.lyrics_utils import LyricsProcessor

# Set up file logging
import sys

def setup_rotating_logger():
    """Set up rotating logger to prevent log files from getting too large."""
    try:
        import logging.handlers
        
        appdata = os.getenv('APPDATA') or str(Path.home())
        log_dir = Path(appdata) / 'DeeMusic' / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / 'deemusic_debug.log'
        
        # Clear existing handlers to avoid duplicates
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Create rotating file handler (max 5MB per file, keep 3 files)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path, 
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        
        # Set format
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        file_handler.setFormatter(formatter)
        
        # Configure root logger - use INFO level to reduce log volume
        # Allow override via environment variable for debugging
        log_level = os.getenv('DEEMUSIC_LOG_LEVEL', 'INFO').upper()
        if log_level in ['DEBUG', 'INFO', 'WARNING', 'ERROR']:
            root_logger.setLevel(getattr(logging, log_level))
        else:
            root_logger.setLevel(logging.INFO)
        root_logger.addHandler(file_handler)
        
        # Only add console handler in debug mode
        if '--debug' in sys.argv:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)
        
        return log_path
    except Exception as e:
        # Fallback to basic logging
        log_path = Path('deemusic_debug.log')
        logging.basicConfig(
            level=logging.WARNING,
            format='%(asctime)s %(levelname)s %(message)s',
            handlers=[logging.FileHandler(log_path, encoding='utf-8', mode='w')]
        )
        return log_path

log_path = setup_rotating_logger()
logger = logging.getLogger(__name__)

def cleanup_old_logs():
    """Clean up old log files on startup."""
    try:
        appdata = os.getenv('APPDATA') or str(Path.home())
        log_dir = Path(appdata) / 'DeeMusic' / 'logs'
        if log_dir.exists():
            # Remove log files older than 7 days
            import time
            current_time = time.time()
            for log_file in log_dir.glob('*.log*'):
                if log_file.stat().st_mtime < current_time - (7 * 24 * 60 * 60):  # 7 days
                    try:
                        log_file.unlink()
                        logger.info(f"Cleaned up old log file: {log_file}")
                    except Exception as e:
                        logger.warning(f"Could not remove old log file {log_file}: {e}")
    except Exception as e:
        logger.warning(f"Error during log cleanup: {e}")

# Clean up old logs on startup
cleanup_old_logs()
logger.info(f"Rotating logging initialized at: {log_path}")

# Imports related to deezer-downloader library are now removed/unused
# We only need subprocess, shutil, os, Path, etc. for the CLI approach

# Helper function
def is_valid_arl(arl: Optional[str]) -> bool:
    """Basic check if ARL looks potentially valid."""
    return arl is not None and len(arl) > 100 # Basic length check

# --- Download Worker Signals ---
# REMOVED - Signals will be directly on the manager now
# class DownloadWorkerSignals(QObject): ...

# --- Download Worker ---
class DownloadWorker(QRunnable):
    """Worker for handling downloads in a background thread using direct API calls."""
    
    def __init__(self, download_manager, item_id: int, item_type: str, album_id: Optional[int] = None, playlist_title: Optional[str] = None, track_info: Optional[dict] = None, playlist_id: Optional[int] = None, album_total_tracks: Optional[int] = None, playlist_total_tracks: Optional[int] = None):
        super().__init__()
        self.download_manager = download_manager # Keep reference to manager
        self.item_id = item_id
        self.item_id_str = str(item_id) # String version for consistent signal emission
        self.item_type = item_type
        self.album_id = album_id # Store album_id if provided (for album_track type)
        self.playlist_title = playlist_title # Store playlist_title
        self.playlist_id = playlist_id # Store playlist_id
        self.track_info_initial = track_info # Store pre-fetched track_info if available
        self.album_total_tracks = album_total_tracks
        self.playlist_total_tracks = playlist_total_tracks
        self._file_path: Optional[str] = None
        self._error_message: Optional[str] = None
        self._download_succeeded: bool = False
        self._error_signaled = False # Flag to prevent double error signals
        self._is_stopping = False # Flag for graceful shutdown
        
    def stop(self):
        """Signals the worker to stop its operation gracefully."""
        logger.info(f"[DownloadWorker:{self.item_id_str}] Stop requested - setting stop flag")
        self._is_stopping = True
        
        # If we have a file path and it's a temp file, try to clean it up
        if hasattr(self, '_file_path') and self._file_path:
            try:
                from pathlib import Path
                file_path = Path(self._file_path)
                if file_path.exists() and ('.part' in str(file_path) or 'deemusic_' in str(file_path)):
                    file_path.unlink()
                    logger.debug(f"[DownloadWorker:{self.item_id_str}] Cleaned up temp file: {file_path}")
            except Exception as e:
                logger.debug(f"[DownloadWorker:{self.item_id_str}] Could not clean up temp file: {e}")
        
        # Mark as not successful to prevent completion signals
        self._download_succeeded = False

    def _is_compilation_album(self, track_info: dict) -> bool:
        """Check if an album is a compilation with multiple artists."""
        try:
            album_id = track_info.get('album', {}).get('id')
            if not album_id:
                return False
            
            # Check if we have cached album details
            if hasattr(self.download_manager, '_album_cache') and album_id in self.download_manager._album_cache:
                cached_album = self.download_manager._album_cache[album_id]
                if cached_album and cached_album.get('tracks', {}).get('data'):
                    tracks = cached_album.get('tracks', {}).get('data', [])
                    
                    # Get unique artists from all tracks, but be smarter about compilation detection
                    track_artists = set()
                    album_artist = cached_album.get('artist', {}).get('name', '').strip()
                    
                    for track in tracks:
                        artist_name = track.get('artist', {}).get('name', '').strip()
                        if artist_name:
                            track_artists.add(artist_name)
                    
                    # More intelligent compilation detection:
                    # 1. If album has a clear album artist, it's probably not a compilation
                    if album_artist and album_artist.lower() not in ['various artists', 'various', 'compilation']:
                        logger.debug(f"COMPILATION_CHECK: Album {album_id} has clear album artist '{album_artist}' - NOT a compilation")
                        return False
                    
                    # 2. Only consider it a compilation if there are many different artists (>3) 
                    # and no dominant artist (to handle guest features)
                    if len(track_artists) > 3:
                        # Check if there's a dominant artist (appears in >60% of tracks)
                        artist_counts = {}
                        for track in tracks:
                            artist_name = track.get('artist', {}).get('name', '').strip()
                            if artist_name:
                                artist_counts[artist_name] = artist_counts.get(artist_name, 0) + 1
                        
                        total_tracks = len(tracks)
                        dominant_artist = None
                        max_count = 0
                        
                        for artist, count in artist_counts.items():
                            if count > max_count:
                                max_count = count
                                dominant_artist = artist
                        
                        # If one artist appears in >60% of tracks, it's not a compilation
                        if max_count / total_tracks > 0.6:
                            logger.debug(f"COMPILATION_CHECK: Album {album_id} has dominant artist '{dominant_artist}' ({max_count}/{total_tracks} tracks) - NOT a compilation")
                            return False
                        else:
                            logger.debug(f"COMPILATION_CHECK: Album {album_id} has {len(track_artists)} different artists with no dominant artist - IS a compilation")
                            return True
                    else:
                        logger.debug(f"COMPILATION_CHECK: Album {album_id} has only {len(track_artists)} different artists - NOT a compilation")
                        return False
            
            # If we don't have cached album details, try to fetch them as a last resort
            logger.debug(f"COMPILATION_CHECK: No cached album details for {album_id}, attempting to fetch")
            try:
                # Try to get album details synchronously if possible
                import asyncio
                album_details = None
                
                try:
                    loop = asyncio.get_event_loop()
                    if not loop.is_running():
                        # We can run async code safely
                        album_details = loop.run_until_complete(self.download_manager.deezer_api.get_album_details(album_id))
                    else:
                        # Event loop is running, we can't use run_until_complete
                        # Try to use asyncio.run_coroutine_threadsafe as a last resort
                        import concurrent.futures
                        import threading
                        
                        def fetch_album_sync():
                            new_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(new_loop)
                            try:
                                return new_loop.run_until_complete(self.download_manager.deezer_api.get_album_details(album_id))
                            finally:
                                new_loop.close()
                        
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            future = executor.submit(fetch_album_sync)
                            album_details = future.result(timeout=10)  # 10 second timeout
                            
                except RuntimeError:
                    # No event loop, create one
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        album_details = new_loop.run_until_complete(self.download_manager.deezer_api.get_album_details(album_id))
                    finally:
                        new_loop.close()
                
                if album_details:
                    # Cache it for future use
                    self.download_manager._album_cache[album_id] = album_details
                    logger.debug(f"COMPILATION_CHECK: Fetched and cached album details for {album_id}")
                    
                    # Now check compilation status using the same improved logic
                    if album_details.get('tracks', {}).get('data'):
                        tracks = album_details.get('tracks', {}).get('data', [])
                        track_artists = set()
                        album_artist = album_details.get('artist', {}).get('name', '').strip()
                        
                        for track in tracks:
                            artist_name = track.get('artist', {}).get('name', '').strip()
                            if artist_name:
                                track_artists.add(artist_name)
                        
                        # Same improved compilation logic
                        if album_artist and album_artist.lower() not in ['various artists', 'various', 'compilation']:
                            logger.debug(f"COMPILATION_CHECK: Album {album_id} has clear album artist '{album_artist}' - NOT a compilation")
                            return False
                        
                        if len(track_artists) > 3:
                            # Check for dominant artist
                            artist_counts = {}
                            for track in tracks:
                                artist_name = track.get('artist', {}).get('name', '').strip()
                                if artist_name:
                                    artist_counts[artist_name] = artist_counts.get(artist_name, 0) + 1
                            
                            total_tracks = len(tracks)
                            max_count = max(artist_counts.values()) if artist_counts else 0
                            
                            if max_count / total_tracks > 0.6:
                                logger.debug(f"COMPILATION_CHECK: Album {album_id} has dominant artist - NOT a compilation")
                                return False
                            else:
                                logger.debug(f"COMPILATION_CHECK: Album {album_id} is a compilation")
                                return True
                        else:
                            logger.debug(f"COMPILATION_CHECK: Album {album_id} has few artists - NOT a compilation")
                            return False
                
                logger.debug(f"COMPILATION_CHECK: Could not fetch album details for {album_id}, assuming not compilation")
                return False
                
            except Exception as fetch_error:
                logger.debug(f"COMPILATION_CHECK: Error fetching album details for {album_id}: {fetch_error}")
                return False
            
        except Exception as e:
            logger.debug(f"COMPILATION_CHECK: Error checking compilation status: {e}")
            return False

    def _get_album_artist(self, track_info: dict, track_artist: str) -> str:
        """Get album artist from Deezer API data with proper field mapping."""
        logger.debug(f"ALBUM_ARTIST_FIX: Getting album artist for track: {track_info.get('title', 'Unknown')}")
        
        # Check if this is a compilation album first
        if self._is_compilation_album(track_info):
            logger.debug(f"ALBUM_ARTIST_FIX: Detected compilation album, using 'Various Artists'")
            return "Various Artists"
        
        # Try multiple sources for album artist from Deezer API
        album_artist = None
        
        # Source 1: album.artist.name (most common for album artist)
        if track_info.get('album', {}).get('artist', {}).get('name'):
            potential_album_artist = track_info.get('album', {}).get('artist', {}).get('name')
            # Only use if it's not "Unknown" or empty
            if potential_album_artist and potential_album_artist.lower() not in ['unknown', '']:
                album_artist = potential_album_artist
                logger.debug(f"ALBUM_ARTIST_FIX: Found album artist from album.artist.name: '{album_artist}'")
        
        # Source 2: Try to get album details if we have an album ID and no album artist yet
        # This is crucial for compilation albums where track API doesn't include album artist
        if not album_artist and track_info.get('album', {}).get('id'):
            try:
                album_id = track_info.get('album', {}).get('id')
                logger.debug(f"ALBUM_ARTIST_FIX: Attempting to get album artist for album ID: {album_id}")
                
                # Check if we have cached album details in the download manager
                if hasattr(self.download_manager, '_album_cache') and album_id in self.download_manager._album_cache:
                    cached_album = self.download_manager._album_cache[album_id]
                    if cached_album and cached_album.get('artist', {}).get('name'):
                        potential_album_artist = cached_album.get('artist', {}).get('name')
                        # Only use if it's not "Unknown" or empty
                        if potential_album_artist and potential_album_artist.lower() not in ['unknown', '']:
                            album_artist = potential_album_artist
                            logger.debug(f"ALBUM_ARTIST_FIX: Found album artist from cached album details: '{album_artist}' (track artist: '{track_artist}')")
                        else:
                            logger.debug(f"ALBUM_ARTIST_FIX: Cached album artist '{potential_album_artist}' is invalid")
                else:
                    # Album not cached - try to fetch it synchronously as a last resort
                    logger.debug(f"ALBUM_ARTIST_FIX: Album {album_id} not cached, attempting sync fetch")
                    try:
                        # Use the sync method if available
                        if hasattr(self.download_manager.deezer_api, 'get_album_details_sync'):
                            album_details = self.download_manager.deezer_api.get_album_details_sync(album_id)
                        else:
                            # Try to run async method synchronously (risky but necessary)
                            import asyncio
                            try:
                                loop = asyncio.get_event_loop()
                                if loop.is_running():
                                    # Can't run async in running loop, skip this source
                                    logger.debug(f"ALBUM_ARTIST_FIX: Cannot fetch album details sync - event loop running")
                                    album_details = None
                                else:
                                    album_details = loop.run_until_complete(self.download_manager.deezer_api.get_album_details(album_id))
                            except:
                                logger.debug(f"ALBUM_ARTIST_FIX: Failed to run async album fetch")
                                album_details = None
                        
                        if album_details:
                            # Cache it for future use
                            self.download_manager._album_cache[album_id] = album_details
                            potential_album_artist = album_details.get('artist', {}).get('name')
                            if potential_album_artist and potential_album_artist.lower() not in ['unknown', '']:
                                album_artist = potential_album_artist
                                logger.debug(f"ALBUM_ARTIST_FIX: Found album artist from sync fetch: '{album_artist}'")
                    except Exception as sync_e:
                        logger.debug(f"ALBUM_ARTIST_FIX: Sync album fetch failed: {sync_e}")
                
            except Exception as e:
                logger.debug(f"ALBUM_ARTIST_FIX: Could not get album artist from cache: {e}")
        
        # Source 3: First contributor with role "Main" (primary album artist)
        if not album_artist and track_info.get('contributors'):
            for contributor in track_info.get('contributors', []):
                if isinstance(contributor, dict) and contributor.get('role') == 'Main':
                    album_artist = contributor.get('name')
                    logger.debug(f"ALBUM_ARTIST_FIX: Found album artist from main contributor: '{album_artist}'")
                    break
        
        # Source 4: First contributor (fallback)
        if not album_artist and track_info.get('contributors'):
            first_contributor = track_info.get('contributors')[0]
            if isinstance(first_contributor, dict) and first_contributor.get('name'):
                album_artist = first_contributor.get('name')
                logger.debug(f"ALBUM_ARTIST_FIX: Found album artist from first contributor: '{album_artist}'")
        
        # Source 5: Legacy art_name field (for older API responses)
        if not album_artist and track_info.get('art_name'):
            album_artist = track_info.get('art_name')
            logger.debug(f"ALBUM_ARTIST_FIX: Found album artist from art_name: '{album_artist}'")
        
        # Source 6: Legacy artists array (for older API responses)
        if not album_artist and track_info.get('artists') and len(track_info.get('artists', [])) > 0:
            first_artist = track_info.get('artists')[0]
            if isinstance(first_artist, dict) and first_artist.get('ART_NAME'):
                album_artist = first_artist.get('ART_NAME')
                logger.debug(f"ALBUM_ARTIST_FIX: Found album artist from first artist: '{album_artist}'")
        
        # Fallback to track artist if no album artist found
        if not album_artist:
            album_artist = track_artist
            logger.debug(f"ALBUM_ARTIST_FIX: No album artist found, using track artist: '{album_artist}'")
        
        # Clean the album artist to remove guest features
        cleaned_album_artist = self._clean_artist_name_for_album_artist(album_artist)
        if cleaned_album_artist != album_artist:
            logger.debug(f"ALBUM_ARTIST_FIX: Cleaned album artist '{album_artist}' -> '{cleaned_album_artist}'")
            album_artist = cleaned_album_artist
        
        logger.debug(f"ALBUM_ARTIST_FIX: Final album artist: '{album_artist}' (same as track artist: {album_artist == track_artist})")
        return album_artist

    def _clean_artist_name_for_album_artist(self, artist_name: str) -> str:
        """Clean artist name to remove guest features for use as album artist."""
        if not artist_name:
            return artist_name
        
        # Remove common guest feature patterns
        import re
        
        # Patterns to remove (case insensitive)
        patterns = [
            r'\s+feat\.?\s+.*$',      # " feat. Artist" or " feat Artist"
            r'\s+ft\.?\s+.*$',        # " ft. Artist" or " ft Artist"  
            r'\s+featuring\s+.*$',    # " featuring Artist"
            r'\s+with\s+.*$',         # " with Artist"
            r'\s+&\s+.*$',            # " & Artist" (but be careful with bands)
            r'\s+x\s+.*$',            # " x Artist" (collaboration)
        ]
        
        cleaned = artist_name
        for pattern in patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        cleaned = cleaned.strip()
        
        # If we cleaned too much and got empty string, return original
        if not cleaned:
            cleaned = artist_name
        
        if cleaned != artist_name:
            logger.debug(f"ALBUM_ARTIST_CLEAN: Cleaned '{artist_name}' -> '{cleaned}'")
        
        return cleaned
    
    def run(self):
        """Execute the download task."""
        # Reduced logging - only log for debugging when needed
        pass

        if self._is_stopping: # Check before starting intensive work
            logger.info(f"[DownloadWorker:{self.item_id_str}] Worker was stopped before starting main operation.")
            return

        item_title = "Unknown Title"
        artist_name = "Unknown Artist"
        album_title = "Unknown Album"
        
        # This will hold the definitive track info used for the download operation and initial signal
        authoritative_track_info = None
        album_cover_url_from_track = None # For individual track artwork saving

        try:
            # 1. Fetch definitive track_info first to be used for the download_started signal
            if self._is_stopping: return
            # For album tracks, always fetch detailed track info to get correct track numbers
            # The album listing API uses different field names than the individual track API
            if (self.item_type == 'album_track' or 
                not (self.track_info_initial and isinstance(self.track_info_initial, dict) and 
                     self.track_info_initial.get('title') and self.track_info_initial.get('artist'))):
                # Need to fetch detailed track info
                pass  # Will call API below
            # Always fetch detailed track info for album tracks, or when initial info is insufficient
            if self.download_manager and self.download_manager.deezer_api:
                try:
                    authoritative_track_info = self.download_manager.deezer_api.get_track_details_sync_private(self.item_id)
                    logger.info(f"[DownloadWorker:{self.item_id_str}] Fetched detailed track info via API")
                except Exception as api_exc:
                    logger.error(f"[DownloadWorker:{self.item_id_str}] Error calling get_track_details_sync_private: {api_exc}")
                    # Fallback to initial track info if API fails
                    if (self.track_info_initial and isinstance(self.track_info_initial, dict) and 
                        self.track_info_initial.get('title') and self.track_info_initial.get('artist')):
                        authoritative_track_info = self.track_info_initial
                        logger.info(f"[DownloadWorker:{self.item_id_str}] Falling back to initial track info")
                    else:
                        authoritative_track_info = None
            else:
                logger.warning(f"[DownloadWorker:{self.item_id_str}] DownloadManager or DeezerAPI not available")
                # Fallback to initial track info if available
                if (self.track_info_initial and isinstance(self.track_info_initial, dict) and 
                    self.track_info_initial.get('title') and self.track_info_initial.get('artist')):
                    authoritative_track_info = self.track_info_initial
                    logger.info(f"[DownloadWorker:{self.item_id_str}] Using initial track info (no API available)")
                else:
                    authoritative_track_info = None

            if self._is_stopping: return

            if authoritative_track_info and isinstance(authoritative_track_info, dict):
                logger.info(f"[DownloadWorker:{self.item_id_str}] Successfully fetched authoritative track_info. Processing for signal.")
                
                # IMPORTANT: Preserve playlist_position from initial track_info if it exists
                if self.track_info_initial and isinstance(self.track_info_initial, dict):
                    playlist_position = self.track_info_initial.get('playlist_position')
                    if playlist_position is not None:
                        authoritative_track_info['playlist_position'] = playlist_position
                        logger.debug(f"[DownloadWorker:{self.item_id_str}] Preserved playlist_position {playlist_position} from initial track_info")
                
                # Populate from authoritative_track_info
                item_title = authoritative_track_info.get('title', authoritative_track_info.get('SNG_TITLE', item_title))
                
                artist_data = authoritative_track_info.get('artist')
                if isinstance(artist_data, dict):
                    artist_name = artist_data.get('name', artist_name)
                elif isinstance(artist_data, str) and artist_data: # Direct string for artist name
                    artist_name = artist_data
                if artist_name == "Unknown Artist" or not artist_name: # Fallback to ART_NAME from authoritative_track_info
                    art_name_fallback = authoritative_track_info.get('ART_NAME')
                    if isinstance(art_name_fallback, str) and art_name_fallback:
                        artist_name = art_name_fallback

                album_data = authoritative_track_info.get('album')
                if isinstance(album_data, dict):
                    album_title = album_data.get('title', album_title)
                elif isinstance(album_data, str) and album_data: # Direct string for album title
                    album_title = album_data
                if album_title == "Unknown Album" or not album_title: # Fallback to ALB_TITLE from authoritative_track_info
                    alb_title_fallback = authoritative_track_info.get('ALB_TITLE')
                    if isinstance(alb_title_fallback, str) and alb_title_fallback:
                        album_title = alb_title_fallback
                # Reduced logging
                
                # Try to cache album details for album artist detection
                if authoritative_track_info.get('album', {}).get('id'):
                    album_id = authoritative_track_info.get('album', {}).get('id')
                    if hasattr(self.download_manager, '_album_cache') and album_id not in self.download_manager._album_cache:
                        # We need to fetch album details, but we can't do async calls here
                        # We'll try to get it synchronously if the API supports it, or skip for now
                        logger.debug(f"ALBUM_ARTIST_FIX: Track {self.item_id_str} belongs to album {album_id}, but album details not cached")
                        # TODO: Consider adding sync album details fetching or pre-fetching in download manager
            else:
                logger.warning(f"[DownloadWorker:{self.item_id_str}] Failed to fetch authoritative track_info or it was invalid. Falling back to initial_track_info if available.")
                if isinstance(self.track_info_initial, dict) and self.track_info_initial:
                    logger.info(f"[DownloadWorker:{self.item_id_str}] Using initial_track_info for signal details.")
                    # Populate from self.track_info_initial as a fallback
                    item_title = self.track_info_initial.get('title', self.track_info_initial.get('SNG_TITLE', item_title))
                    
                    artist_data = self.track_info_initial.get('artist')
                    if isinstance(artist_data, dict): artist_name = artist_data.get('name', artist_name)
                    elif isinstance(artist_data, str) and artist_data: artist_name = artist_data
                    if (artist_name == "Unknown Artist" or not artist_name): artist_name = self.track_info_initial.get('ART_NAME', artist_name)

                    album_data = self.track_info_initial.get('album')
                    if isinstance(album_data, dict): album_title = album_data.get('title', album_title)
                    elif isinstance(album_data, str) and album_data: album_title = album_data
                    if (album_title == "Unknown Album" or not album_title): album_title = self.track_info_initial.get('ALB_TITLE', album_title)
                    # Reduced logging
                else:
                    logger.warning(f"[DownloadWorker:{self.item_id_str}] No valid initial_track_info. Signal will use defaults: Title='{item_title}', Artist='{artist_name}', Album='{album_title}'")
            
            # At this point, item_title, artist_name, album_title are set to the best available info.
            if self._is_stopping: return # Check before emitting signal
            logger.info(f"[DownloadWorker:{self.item_id_str}] Download worker starting processing for {self.item_type} {self.item_id_str}. Signal details: Title='{item_title}', Artist='{artist_name}', Album='{album_title}'")
            start_data = {
                'id': self.item_id_str,
                'title': item_title,
                'artist': artist_name,
                'album': album_title,
                'type': self.item_type,
                'album_id': self.album_id if self.album_id is not None else None,
                'playlist_id': self.playlist_id if self.playlist_id is not None else None,
                'album_total_tracks': self.album_total_tracks if self.album_total_tracks is not None else None,
                'playlist_total_tracks': self.playlist_total_tracks if self.playlist_total_tracks is not None else None
            }
            # Reduced logging
            try:
                if not self._is_stopping: self.download_manager.signals.download_started.emit(start_data)
            except RuntimeError as e: # Catch if signals object is deleted
                logger.warning(f"[DownloadWorker:{self.item_id_str}] Could not emit download_started: {e}")
                return # Exit if signals are gone
            
            if self._is_stopping: return
            # Pass the authoritative_track_info (which might be None if API failed) to _perform_download_direct
            self._file_path = self._perform_download_direct(authoritative_track_info)

            if self._is_stopping: # If stopped during download, result might be partial/invalid
                logger.info(f"[DownloadWorker:{self.item_id_str}] Worker stopped during download operation.")
                # Do not emit finished/failed if stopped, unless specifically required
                return

            if self._file_path:
                self._download_succeeded = True
                logger.info(f"Download successful for {self.item_type} {self.item_id_str}: {self._file_path}")
            elif not self._error_signaled: 
                 logger.error(f"Download failed for {self.item_type} {self.item_id_str}, no specific error message.")
                 self._error_message = "Unknown download error."

        except Exception as e:
            if self._is_stopping: # If an exception occurs during stopping, just log and exit
                logger.warning(f"[DownloadWorker:{self.item_id_str}] Exception during shutdown: {e}", exc_info=False)
                return None
            logger.error(f"Unhandled exception in DownloadWorker for {self.item_type} {self.item_id_str}: {e}", exc_info=True)
            self._error_message = f"Internal error: {e}"
            self._download_succeeded = False
        finally:
            if self._is_stopping:
                logger.info(f"[DownloadWorker:{self.item_id_str}] Worker finalizing due to stop request - no signals will be emitted")
                return # Avoid emitting final signals if stopped
            
            # Check if we're still in the active workers list - if not, we were cleared during clear all
            if hasattr(self.download_manager, 'active_workers') and self.item_id_str not in self.download_manager.active_workers:
                logger.info(f"[DownloadWorker:{self.item_id_str}] Worker not in active list - likely cleared during clear all operation")
                return # Don't emit signals if we were cleared
            
            # Level 1
            if self._download_succeeded and self._file_path:
                 # Level 2
                try:
                    if not self._is_stopping: 
                        self.download_manager.signals.download_finished.emit(self.item_id_str)
                except RuntimeError as e: 
                    logger.warning(f"[DownloadWorker:{self.item_id_str}] Could not emit download_finished: {e}")
            elif not self._error_signaled: 
                # Level 2
                error_msg = self._error_message or "Download failed"
                # Level 2 
                try:
                    if not self._is_stopping: 
                        self.download_manager.signals.download_failed.emit(self.item_id_str, error_msg)
                except RuntimeError as e: 
                    logger.warning(f"[DownloadWorker:{self.item_id_str}] Could not emit download_failed: {e}")
            # Level 1
            logger.info(f"Download worker finished for {self.item_type} {self.item_id_str}")

    # Level 0 
    def _emit_error(self, message: str):
        """Helper to emit error signal via manager only once."""
        if self._is_stopping: return # Don't emit errors if stopping
        # Level 1
        if not self._error_signaled:
            # Level 2
            logger.error(message) 
            # Level 2
            try:
                if not self._is_stopping: self.download_manager.signals.download_failed.emit(self.item_id_str, message)
            except RuntimeError as e: 
                logger.warning(f"[DownloadWorker:{self.item_id_str}] Could not emit error signal (download_failed): {e}")
            # Level 2
            self._error_signaled = True

    # --- Direct Download Method ---
    def _perform_download_direct(self, track_info: Optional[dict]) -> Optional[str]:
        temp_file_path = None 
        decrypted_temp_path = None 
        encrypted_temp_path = None 
        
        try:
            # 1. Validate passed track_info
            if not track_info or not isinstance(track_info, dict): # Simplified initial check
                error_msg = f"Cannot proceed with download for {self.item_id_str}: Missing or invalid track_info object provided to _perform_download_direct."
                logger.error(f"[DownloadWorker:{self.item_id_str}] {error_msg} Info: {track_info}")
                self._emit_error(error_msg)
                return None

            if self._is_stopping: return None
            
            # Attempt to get the song ID from track_info robustly
            sng_id_val = track_info.get('sng_id')
            id_source = "'sng_id' (lowercase)"
            if sng_id_val is None:
                sng_id_val = track_info.get('SNG_ID') # Try uppercase
                id_source = "'SNG_ID' (uppercase)"
            if sng_id_val is None:
                sng_id_val = track_info.get('id') # Fallback to top-level 'id'
                id_source = "'id' (top-level)"

            if sng_id_val is None:
                error_msg = f"Cannot determine SNG_ID for decryption for track {self.item_id_str}. track_info keys: {list(track_info.keys())}"
                logger.error(f"[DownloadWorker:{self.item_id_str}] {error_msg}")
                self._emit_error(error_msg)
                return None
            
            sng_id_str = str(sng_id_val)
            logger.info(f"[DownloadWorker:{self.item_id_str}] Using SNG_ID '{sng_id_str}' (obtained from {id_source}) for decryption.")

            # Log relevant track info for debugging URL/decryption later
            logger.debug(f"[DownloadWorker:{self.item_id_str}] _perform_download_direct using track_info. Title: {track_info.get('title')}, Keys: {list(track_info.keys())}")
            # sng_id_str = str(track_info.get('sng_id')) # Already checked sng_id exists # OLD LINE

            # 2. Get Download URL using the DeezerAPI sync method
            logger.debug(f"Getting sync download URL for {self.item_id}") # self.item_id is the one from worker constructor
            if self._is_stopping: return None

            download_url = None
            if self.download_manager and self.download_manager.deezer_api:
                try:
                    download_url = self.download_manager.deezer_api.get_track_download_url_sync(
                        self.item_id,
                        quality=self.download_manager.quality
                    )
                    logger.info(f"[DownloadWorker:{self.item_id_str}] Received download URL: {download_url}") # Log the URL
                except Exception as api_exc:
                    logger.error(f"[DownloadWorker:{self.item_id_str}] Error calling get_track_download_url_sync: {api_exc}", exc_info=True)
                    self._emit_error(f"API error getting download URL for {self.item_id}: {api_exc}")
                    return None
            else:
                logger.error(f"[DownloadWorker:{self.item_id_str}] DownloadManager or DeezerAPI not available for getting download URL.")
                self._emit_error(f"Cannot get download URL for {self.item_id}: API service unavailable.")
                return None

            if self._is_stopping: return None
            if not download_url:
                self._emit_error(f"Failed to get download URL for {self.item_id} via API")
                return None
            
            # Check if the download_url is actually an error message
            if isinstance(download_url, str) and download_url.startswith(('RIGHTS_ERROR:', 'API_ERROR:')):
                # Parse the error type and provide user-friendly messages
                if download_url.startswith('RIGHTS_ERROR:'):
                    error_detail = download_url.replace('RIGHTS_ERROR: ', '')
                    if 'Track not available' in error_detail:
                        user_friendly_error = f"Track unavailable: This track is not available for download in your region or subscription level"
                    elif 'Geographic restriction' in error_detail:
                        user_friendly_error = f"Geographic restriction: This track is not available in your region"
                    elif 'subscription required' in error_detail:
                        user_friendly_error = f"Subscription required: Your account level doesn't allow downloading this track"
                    else:
                        user_friendly_error = f"Rights restriction: {error_detail}"
                    
                    self._emit_error(user_friendly_error)
                elif download_url.startswith('API_ERROR:'):
                    error_detail = download_url.replace('API_ERROR: ', '')
                    user_friendly_error = f"API error: {error_detail}"
                    self._emit_error(user_friendly_error)
                else:
                    self._emit_error(f"Download error: {download_url}")
                
                return None
            
            # Limit logging if URL is very long or sensitive
            logger.debug(f"Got download URL (start): {download_url[:100]}...")

            # --- 3. Prepare Filename and Paths based on Settings (REVISED LOGIC) ---
            logger.debug("Preparing filename and paths based on settings...")
            if self._is_stopping: return None
            config = self.download_manager.config
            base_download_dir = Path(self.download_manager.download_dir)
            
            # Explicitly get the NESTED folder_structure settings
            folder_conf = config.get_setting('downloads.folder_structure', {})
            if not folder_conf: # Fallback if downloads.folder_structure is missing entirely
                logger.warning("'downloads.folder_structure' not found in settings, using root 'folder_structure' or defaults.")
                folder_conf = config.get_setting('folder_structure', {})
            
            # Read creation flags
            create_artist_folder = folder_conf.get('create_artist_folders', True)
            create_album_folder = folder_conf.get('create_album_folders', True)
            # Check the key from your settings.json if this still reads False!
            create_cd_folder = folder_conf.get('create_cd_folders', False) 
            
            # Read folder templates from the nested 'templates' dictionary
            templates_conf = folder_conf.get('templates', {})
            artist_template = templates_conf.get('artist', '%albumartist%')
            album_template = templates_conf.get('album', '%album%')
            cd_template = templates_conf.get('cd', 'CD %disc_number%') # Ensure this key matches your settings
            
            # Prepare placeholder values from track_info
            disc_number_val = track_info.get('disk_number', 1)
            # Get track number with better fallback logic
            track_position = track_info.get('track_position')
            track_number = track_info.get('track_number')
            track_num_raw = track_position or track_number or 1
            
            # Add INFO level logging to debug the issue
            logger.info(f"TRACK_NUMBER_DEBUG: Track '{track_info.get('title', 'Unknown')}' - track_position: {track_position}, track_number: {track_number}, final: {track_num_raw}")
            
            # Ensure it's never 0
            if track_num_raw == 0:
                track_num_raw = 1
                logger.warning(f"TRACK_NUMBER_FIX: Track number was 0, changed to 1 for track: {track_info.get('title', 'Unknown')}")
            track_number_val = str(track_num_raw).zfill(2)
            logger.info(f"TRACK_NUMBER_FIX: Final track number for '{track_info.get('title', 'Unknown')}': {track_number_val}")
            
            # Construct track artist name (with collaboration if multiple artists)
            primary_artist = track_info.get('artist', {}).get('name', 'Unknown Artist')
            artists_array = track_info.get('artists', [])
            
            if len(artists_array) > 1:
                # Multiple artists - build collaborative name
                all_artist_names = [a.get('ART_NAME', '') for a in artists_array if a.get('ART_NAME')]
                if len(all_artist_names) > 1:
                    # Use primary artist + "feat." + other artists
                    other_artists = all_artist_names[1:]  # Skip first (primary) artist
                    if len(other_artists) == 1:
                        artist_val = f"{all_artist_names[0]} feat. {other_artists[0]}"
                    else:
                        artist_val = f"{all_artist_names[0]} feat. {', '.join(other_artists)}"
                    logger.debug(f"ARTIST DEBUG: Constructed collaborative artist name: '{artist_val}' from {all_artist_names}")
                else:
                    artist_val = primary_artist
                    logger.debug(f"ARTIST DEBUG: Using primary artist (insufficient artist data): '{artist_val}'")
            else:
                # Single artist
                artist_val = primary_artist
                logger.debug(f"ARTIST DEBUG: Using single artist: '{artist_val}'")
            
            album_val = track_info.get('album', {}).get('title', track_info.get('alb_title', 'Unknown Album'))
            title_val = track_info.get('title', 'Unknown Title')
            year_val = str(track_info.get('release_date', '0000'))[:4]
            
            # Album Artist logic based on user configuration (uses primary artist)
            logger.debug(f"ALBUM_ARTIST_DEBUG: About to call _get_album_artist with track_info keys: {list(track_info.keys())}")
            logger.debug(f"ALBUM_ARTIST_DEBUG: Album cache has {len(self.download_manager._album_cache)} entries: {list(self.download_manager._album_cache.keys())}")
            album_artist_val = self._get_album_artist(track_info, primary_artist)
            logger.debug(f"ALBUM_ARTIST_DEBUG: _get_album_artist returned: '{album_artist_val}' (primary_artist was: '{primary_artist}')")
            
            # Get track number with better fallback logic
            track_position = track_info.get('track_position')
            track_number = track_info.get('track_number')
            track_num_raw = track_position or track_number or 1
            
            # Add INFO level logging to debug the issue
            logger.info(f"TRACK_NUMBER_DEBUG: Track '{track_info.get('title', 'Unknown')}' - track_position: {track_position}, track_number: {track_number}, final: {track_num_raw}")
            
            if track_num_raw == 0:
                track_num_raw = 1
            track_num_str = str(track_num_raw).zfill(2)
            total_tracks_str = str(track_info.get('album', {}).get('nb_tracks', 0))
            disc_num_str = str(track_info.get('disk_number', 1))
            total_discs_str = "1" # Deezer API doesn't seem to provide total discs easily?
            # Use get method for release_date as well
            release_date = track_info.get('release_date', '1970-01-01') # YYYY-MM-DD
            genre_data = track_info.get('genres', {}).get('data', [])
            genre = genre_data[0].get('name', None) if genre_data else None
            composer = track_info.get('composer', None) # Deezer often lacks composer
            
            publisher = track_info.get('label', track_info.get('record_label')) # Check alternative keys
            isrc = track_info.get('isrc', None)
            
            # Debug metadata extraction
            logger.debug(f"METADATA DEBUG: Extracted track_artist='{artist_val}', album_artist='{album_artist_val}', title='{title_val}', album='{album_val}'")
            logger.debug(f"METADATA DEBUG: Primary artist: '{primary_artist}', Full track artist: '{artist_val}'")
            logger.debug(f"METADATA DEBUG: track_info artist structure: {track_info.get('artist')}")
            logger.debug(f"METADATA DEBUG: track_info album.artist structure: {track_info.get('album', {}).get('artist')}")
            logger.debug(f"METADATA DEBUG: track_info artists array: {[a.get('ART_NAME') for a in track_info.get('artists', [])]}")
            logger.debug(f"METADATA DEBUG: Album artist logic result: '{album_artist_val}' (same as track artist: {album_artist_val == artist_val})")
            
            # Get total number of discs for the album
            # Common Deezer API key for this is 'nb_disk' in the album object
            album_object = track_info.get('album', {})
            total_album_discs = album_object.get('nb_disk', 1)
            try:
                total_album_discs = int(total_album_discs) # Ensure it's an integer
            except (ValueError, TypeError):
                total_album_discs = 1 # Default to 1 if conversion fails
            logger.debug(f"Total discs for album '{album_val}': {total_album_discs}")

            # Convert numbers to integers for formatting
            try:
                track_num_int = int(track_number_val)
                # Ensure it's never 0
                if track_num_int == 0:
                    track_num_int = 1
            except (ValueError, TypeError):
                track_num_int = 1 # Fallback to 1 instead of 0 if conversion fails
            try:
                disc_num_int = int(disc_number_val)
            except (ValueError, TypeError):
                disc_num_int = 1 # Fallback if conversion fails
            
            # For playlist tracks, use playlist position instead of original track number
            if self.item_type == 'playlist_track':
                playlist_pos = track_info.get('playlist_position')
                logger.debug(f"PLAYLIST POSITION DEBUG: track_info keys: {list(track_info.keys())}")
                logger.debug(f"PLAYLIST POSITION DEBUG: playlist_position value: {playlist_pos} (type: {type(playlist_pos)})")
                if playlist_pos is not None:  # Check for None specifically, not falsy values
                    original_track_number = track_num_int
                    track_num_int = int(playlist_pos)
                    logger.debug(f"PLAYLIST POSITION DEBUG: Changed track number from {original_track_number} to {track_num_int} (playlist position) for playlist track")
                else:
                    logger.warning(f"PLAYLIST POSITION DEBUG: No playlist position found. item_type='{self.item_type}', playlist_position={playlist_pos}. Using original track number.")
            else:
                logger.debug(f"PLAYLIST POSITION DEBUG: Not a playlist track. item_type='{self.item_type}'")
            
            # Add debug logging for playlist position in placeholders
            if self.item_type == 'playlist_track':
                logger.debug(f"PLAYLIST TEMPLATE DEBUG: track_number={track_num_int}, playlist_position={track_info.get('playlist_position')}")
            
            # Placeholder dictionary, including playlist_name
            placeholders = {
                'artist': artist_val,
                'album': album_val,
                'title': title_val,
                'track_number': track_num_int, # Use integer (playlist position for playlist tracks)
                'playlist_position': track_info.get('playlist_position', track_num_int), # Add explicit playlist_position placeholder
                'disc_number': disc_num_int,    # Use integer
                'year': year_val,
                'album_artist': album_artist_val,
                'albumartist': album_artist_val,  # Alias for album_artist (for %albumartist% templates)
                'playlist_name': self.playlist_title if self.playlist_title else '', # Add playlist_name
                'playlist': self.playlist_title if self.playlist_title else '', # Add playlist (for %playlist% templates)
                # Add other potential placeholders if needed, e.g., genre
                'genre': track_info.get('genres', {}).get('data', [{}])[0].get('name', 'Unknown Genre'),
                'isrc': track_info.get('isrc', '')
            }
            logger.debug(f"FOLDER_FIX: Using albumartist='{album_artist_val}' for folder structure")
            
            # Logging all available placeholders for debugging
            logger.debug(f"Available placeholders for templating: {placeholders}")
            
            # Special debug for playlist tracks
            if self.item_type == 'playlist_track':
                logger.debug(f"PLAYLIST TEMPLATE DEBUG: track_number={placeholders['track_number']}, playlist_position={placeholders['playlist_position']}")

            def process_template(template_str: str) -> str:
                logger.debug(f"TEMPLATE DEBUG: Processing template '{template_str}' with placeholders: {placeholders}")
                processed_str = template_str
                for key, value in placeholders.items():
                    # Convert value back to string for generic replacement if needed
                    # Ensure {key:format} specifiers work correctly before this conversion
                    old_str = processed_str
                    processed_str = processed_str.replace(f"{{{key}}}", str(value)) 
                    processed_str = processed_str.replace(f"%{key}%", str(value))
                    if old_str != processed_str:
                        logger.debug(f"TEMPLATE DEBUG: Replaced {key} -> {value}, result: '{processed_str}'")
                logger.debug(f"TEMPLATE DEBUG: Final processed template: '{processed_str}'")
                return processed_str

            dir_components = []
            
            # For playlist tracks, use playlist folder structure if enabled
            if self.item_type == 'playlist_track' and self.playlist_title:
                # Check if playlist folders are enabled
                create_playlist_folder = folder_conf.get('create_playlist_folders', True)
                if create_playlist_folder:
                    # Use playlist template from the nested templates or fall back to simple playlist name
                    playlist_template = templates_conf.get('playlist', '%playlist%')
                    processed_playlist = process_template(playlist_template)
                    logger.debug(f"Playlist Folder Check: Adding component '{processed_playlist}'")
                    if processed_playlist: 
                        dir_components.append(processed_playlist)
                else:
                    logger.debug("Playlist Folder Check: create_playlist_folders is disabled, using artist/album structure")
                    # Fall back to artist/album structure if playlist folders are disabled
                    if create_artist_folder:
                        processed_artist = process_template(artist_template)
                        logger.debug(f"Artist Folder Check (playlist fallback): Adding component '{processed_artist}'")
                        if processed_artist: dir_components.append(processed_artist)
                    
                    if create_album_folder:
                        processed_album = process_template(album_template)
                        logger.debug(f"Album Folder Check (playlist fallback): Adding component '{processed_album}'")
                        if processed_album: dir_components.append(processed_album)
            else:
                # Regular artist/album folder structure for non-playlist tracks
                # Artist folder
                if create_artist_folder:
                    processed_artist = process_template(artist_template)
                    logger.debug(f"Artist Folder Check: Adding component '{processed_artist}'")
                    if processed_artist: dir_components.append(processed_artist)
                
                # Album folder (relative to artist if artist folder is created)
                if create_album_folder:
                    processed_album = process_template(album_template)
                    logger.debug(f"Album Folder Check: Adding component '{processed_album}'")
                    if processed_album: dir_components.append(processed_album)

                # CD Folder (relative to album if album folder is created)
                # Only create CD folder if the setting is enabled AND the album has more than 1 disc
                if create_cd_folder and total_album_discs > 1:
                    processed_cd = process_template(cd_template) # cd_template uses disc_number_val from track
                    logger.debug(f"CD Folder Check (multi-disc album): Adding component '{processed_cd}'")
                    if processed_cd: dir_components.append(processed_cd)
                elif create_cd_folder:
                    logger.debug(f"CD Folder Check (single-disc album or setting off for multi-disc): Skipping CD folder for '{album_val}'. Total discs: {total_album_discs}, create_cd_folder: {create_cd_folder}")
                else:
                    logger.debug("CD Folder Check (create_cd_folder is False): Skipping CD folder component.")

            # --- Select and Format Filename Template ---
            filename_template_key = "track" # Default
            default_tpl = "{artist} - {title}"

            if self.item_type == 'album_track':
                # Check if this is a compilation album
                if self._is_compilation_album(track_info):
                    filename_template_key = "compilation_track"
                    default_tpl = "{track_number:02d} - {artist} - {title}"
                    logger.debug(f"COMPILATION_FILENAME: Using compilation track template for album track")
                else:
                    filename_template_key = "album_track"
                    default_tpl = "{track_number:02d}. {title}"
            elif self.item_type == 'playlist_track' and self.playlist_title:
                filename_template_key = "playlist_track"
                default_tpl = "{playlist_position:02d} - {artist} - {title}"
            elif self.item_type == 'track': # Explicitly single track
                filename_template_key = "track"
                default_tpl = "{artist} - {title}"

            chosen_template_str = config.get_setting(f"downloads.filename_templates.{filename_template_key}", default_tpl)
            logger.info(f"Using filename template for '{self.item_type}' (key: {filename_template_key}): {chosen_template_str}")
            
            # Additional debug for playlist tracks
            if self.item_type == 'playlist_track':
                logger.debug(f"FILENAME TEMPLATE DEBUG: About to format template '{chosen_template_str}' with placeholders: track_number={placeholders['track_number']}, playlist_position={placeholders['playlist_position']}")
            
            # The process_template function expects {key} so ensure compatibility or update it
            # For now, we assume process_template handles {key} correctly.
            # The default templates use {key}, so this should be fine.
            # If using formatting like {track_number:02d}, str.format() is better.
            
            # Using str.format for more powerful formatting like :02d
            # Add INFO level logging to debug track number issue
            logger.info(f"FILENAME_DEBUG: About to format filename with track_number={placeholders.get('track_number')} for track '{track_info.get('title', 'Unknown')}'")
            
            try:
                filename_part = chosen_template_str.format(**placeholders)
                if self.item_type == 'playlist_track':
                    logger.debug(f"FILENAME TEMPLATE DEBUG: Formatted filename part: '{filename_part}'")
            except KeyError as e:
                logger.error(f"Missing placeholder {e} in template '{chosen_template_str}'. Falling back to default.")
                filename_part = default_tpl.format(**placeholders) # Try with default, assuming it has valid placeholders
                if self.item_type == 'playlist_track':
                    logger.debug(f"FILENAME TEMPLATE DEBUG: Fallback formatted filename part: '{filename_part}'")
            except Exception as e:
                logger.error(f"Error formatting filename template '{chosen_template_str}': {e}. Falling back to default.")
                filename_part = default_tpl.format(**placeholders)
                if self.item_type == 'playlist_track':
                    logger.debug(f"FILENAME TEMPLATE DEBUG: Error fallback formatted filename part: '{filename_part}'")

            # Determine extension based on quality setting
            quality = self.download_manager.quality
            file_extension = ".flac" if quality == 'FLAC' else ".mp3"
            
            filename_with_ext = filename_part + file_extension
            
            # Sanitize directory parts and filename part separately
            sanitized_dir_parts = [self.download_manager._sanitize_filename(part) for part in dir_components if part]
            sanitized_filename = self.download_manager._sanitize_filename(filename_with_ext)
            
            # Construct final path
            final_file_path = base_download_dir.joinpath(*sanitized_dir_parts, sanitized_filename)
            logger.debug(f"FOLDER_FIX: Final file path: {final_file_path}") 
            logger.info(f"Calculated final path: {final_file_path}")

            # Check if worker is stopping or download manager is clearing before any file operations
            if self._is_stopping:
                logger.info(f"[DownloadWorker:{self.item_id_str}] Worker stopped before file operations - no directories will be created")
                return None
            
            # Also check if download manager is in clearing mode
            if hasattr(self.download_manager, '_clearing_queue') and self.download_manager._clearing_queue:
                logger.info(f"[DownloadWorker:{self.item_id_str}] Download manager is clearing queue - no directories will be created")
                return None

            # Check if file already exists (skip download if it does)
            if final_file_path.exists():
                logger.info(f"[DownloadWorker:{self.item_id_str}] File already exists, skipping download: {final_file_path}")
                return str(final_file_path)

            # --- Prepare Temporary File Paths ---
            unique_suffix = f"deemusic_{self.item_id}_{final_file_path.stem}"
            encrypted_temp_path = Path(tempfile.gettempdir()) / f"{unique_suffix}.encrypted.part"
            decrypted_temp_path = Path(tempfile.gettempdir()) / f"{unique_suffix}.decrypted.part"

            # Check again before creating directories (critical for preventing folder creation after clear)
            if self._is_stopping:
                logger.info(f"[DownloadWorker:{self.item_id_str}] Worker stopped before directory creation - no folders will be created")
                return None
            
            # Double-check if download manager is clearing
            if hasattr(self.download_manager, '_clearing_queue') and self.download_manager._clearing_queue:
                logger.info(f"[DownloadWorker:{self.item_id_str}] Download manager clearing detected before directory creation - no folders will be created")
                return None

            # Ensure final destination directory exists 
            try:
                final_dir_path = base_download_dir.joinpath(*sanitized_dir_parts)
                final_dir_path.mkdir(parents=True, exist_ok=True)
                logger.debug(f"Final download directory created or verified: {final_dir_path}")
            except OSError as e:
                error_msg = f"Failed to create download directory {final_dir_path}: {e}"
                logger.error(f"[DownloadWorker:{self.item_id_str}] {error_msg}")
                self._emit_error(error_msg)
                return None
                 
            # --- 4. Download File ---
            logger.debug(f"Starting download from {download_url} to {encrypted_temp_path}")
            if self._is_stopping: return None
            
            try:
                # Use shared HTTP session for better performance
                session = self.download_manager.get_http_session()
                if session is None:
                    # Fallback to basic requests if session setup failed
                    import requests
                    session = requests
                
                # Download to temporary encrypted file with optimized settings
                response = session.get(download_url, stream=True, timeout=30)
                response.raise_for_status()
                
                # Use larger chunk size for better performance
                chunk_size = 65536  # 64KB chunks instead of 8KB
                
                with open(encrypted_temp_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if self._is_stopping:
                            logger.debug(f"[DownloadWorker:{self.item_id_str}] Download cancelled during streaming.")
                            return None
                        if chunk:
                            f.write(chunk)
                
                # Reduced logging
                
            except Exception as download_exc:
                logger.error(f"[DownloadWorker:{self.item_id_str}] Download failed: {download_exc}")
                self._emit_error(f"Download failed: {download_exc}")
                return None

            # --- 5. Decrypt File ---
            if self._is_stopping: return None
            
            decryption_key = self._generate_decryption_key(sng_id_str)
            if not decryption_key:
                self._emit_error(f"Failed to generate decryption key for {self.item_id}")
                return None

            decrypted_path = self._decrypt_file_bf_cbc_stripe(encrypted_temp_path, decryption_key, sng_id_str)
            if not decrypted_path:
                self._emit_error(f"Failed to decrypt file for {self.item_id}")
                return None

            logger.info(f"[DownloadWorker:{self.item_id_str}] Decrypted file to {decrypted_path}")

            # --- 6. Apply Metadata ---
            if self._is_stopping: return None
            
            try:
                # Pass the correct directory path to metadata method for artwork saving
                final_dir_path = base_download_dir.joinpath(*sanitized_dir_parts)
                self._apply_metadata(str(decrypted_path), track_info, final_dir_path)
                logger.info(f"[DownloadWorker:{self.item_id_str}] Metadata applied successfully")
            except Exception as metadata_exc:
                logger.error(f"[DownloadWorker:{self.item_id_str}] Metadata application failed: {metadata_exc}")
                # Continue with download even if metadata fails
                
            # --- 7. Move to Final Location ---
            if self._is_stopping: return None
            
            try:
                import shutil
                shutil.move(str(decrypted_path), str(final_file_path))
                logger.info(f"[DownloadWorker:{self.item_id_str}] File moved to final location: {final_file_path}")
                
                # --- 8. Process and Save Lyrics ---
                try:
                    self._process_and_save_lyrics_final(track_info, str(final_file_path))
                    logger.info(f"[DownloadWorker:{self.item_id_str}] Lyrics processing completed")
                except Exception as lyrics_exc:
                    logger.warning(f"[DownloadWorker:{self.item_id_str}] Lyrics processing failed: {lyrics_exc}")
                    # Continue - lyrics failure shouldn't fail the download
                
                # Clean up temporary files
                if encrypted_temp_path.exists():
                    encrypted_temp_path.unlink()
                if decrypted_path and Path(decrypted_path).exists():
                    Path(decrypted_path).unlink()
                    
                return str(final_file_path)
                
            except Exception as move_exc:
                logger.error(f"[DownloadWorker:{self.item_id_str}] Failed to move file to final location: {move_exc}")
                self._emit_error(f"Failed to move file to final location: {move_exc}")
                return None

        except Exception as e: 
            logger.error(f"[DownloadWorker:{self.item_id_str}] General error in download: {e}", exc_info=True)
            self._emit_error(f"Download failed: {e}")
            return None
        finally:
            # Clean up temporary files in case of error
            try:
                if encrypted_temp_path and encrypted_temp_path.exists():
                    encrypted_temp_path.unlink()
                # decrypted_temp_path is now a Path object, not a temp path variable
                # The cleanup here is mainly for error cases since success path cleans up above
            except:
                pass

    def _apply_metadata(self, file_path: str, track_info: dict, target_directory: Optional[Path] = None):
        """Apply metadata to the downloaded audio file."""
        try:
            # Import mutagen here to avoid potential loading issues elsewhere
            from mutagen.mp3 import MP3  # type: ignore
            from mutagen.flac import FLAC  # type: ignore
            from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TPOS, TDRC, TPE2, TCON, TCOM, TPUB, TSRC, APIC  # type: ignore
            from mutagen.flac import Picture
            import requests
            
            logger.debug(f"Applying metadata to {file_path} with track_info: {track_info.keys()}")
            
            quality = self.download_manager.quality
            is_mp3 = quality.startswith('MP3_') or quality == 'AAC_64'
            
            if is_mp3:
                try:
                    audio = MP3(file_path, ID3=ID3)
                    if audio.tags is None:
                        audio.add_tags()
                except Exception as e:
                    logger.error(f"Failed to load MP3 file {file_path}: {e}")
                    return
            else: # FLAC
                try:
                    audio = FLAC(file_path)
                except Exception as e:
                    logger.error(f"Failed to load FLAC file {file_path}: {e}")
                    return
            
            if audio is None:
                logger.error(f"Audio object is None after loading attempt for {file_path}")
                return

            title = track_info.get('title', 'Unknown Title')
            
            primary_artist = track_info.get('artist', {}).get('name', 'Unknown Artist')
            artists_array = track_info.get('artists', [])
            
            if len(artists_array) > 1:
                all_artist_names = [a.get('ART_NAME', '') for a in artists_array if a.get('ART_NAME')]
                if len(all_artist_names) > 1:
                    other_artists = all_artist_names[1:]
                    if len(other_artists) == 1:
                        artist = f"{all_artist_names[0]} feat. {other_artists[0]}"
                    else:
                        artist = f"{all_artist_names[0]} feat. {', '.join(other_artists)}"
                else:
                    artist = primary_artist
            else:
                artist = primary_artist
            
            album = track_info.get('alb_title', track_info.get('album', {}).get('title', 'Unknown Album'))
            
            # Get track number with better fallback logic
            track_position = track_info.get('track_position')
            track_number = track_info.get('track_number')
            track_num_int = track_position or track_number or 1
            
            # Add INFO level logging to debug the issue
            logger.info(f"TRACK_NUMBER_DEBUG: Track '{track_info.get('title', 'Unknown')}' - track_position: {track_position}, track_number: {track_number}, final: {track_num_int}")
            
            if track_num_int == 0:
                track_num_int = 1
            
            if self.item_type == 'playlist_track':
                playlist_pos = track_info.get('playlist_position')
                if playlist_pos is not None:
                    track_num_int = int(playlist_pos)
            
            track_num_str = str(track_num_int).zfill(2)
            total_tracks_str = str(track_info.get('album', {}).get('nb_tracks', 0))
            disc_num_str = str(track_info.get('disk_number', 1))
            total_discs_str = "1"
            release_date = track_info.get('release_date', '1970-01-01')
            genre_data = track_info.get('genres', {}).get('data', [])
            genre = genre_data[0].get('name', None) if genre_data else None
            composer = track_info.get('composer', None)
            publisher = track_info.get('label', track_info.get('record_label'))
            isrc = track_info.get('isrc', None)
            album_artist = self._get_album_artist(track_info, primary_artist)

            if is_mp3:
                tags = audio.tags
                if tags is None:
                     tags = ID3()
                     audio.tags = tags
                
                tags.delall("TIT2"); tags.delall("TPE1"); tags.delall("TALB"); tags.delall("TRCK"); tags.delall("TPOS"); tags.delall("TDRC"); tags.delall("TPE2"); tags.delall("TCON"); tags.delall("TCOM"); tags.delall("TPUB"); tags.delall("TSRC"); tags.delall("APIC")

                tags.add(TIT2(encoding=3, text=title))
                tags.add(TPE1(encoding=3, text=artist))
                tags.add(TALB(encoding=3, text=album))
                
                if total_tracks_str and int(total_tracks_str) > 0:
                    tags.add(TRCK(encoding=3, text=f"{track_num_str}/{total_tracks_str}"))
                else:
                    tags.add(TRCK(encoding=3, text=track_num_str))

                if total_discs_str and total_discs_str != "0" and total_discs_str != "1":
                    tags.add(TPOS(encoding=3, text=f"{disc_num_str}/{total_discs_str}"))
                else:
                    tags.add(TPOS(encoding=3, text=disc_num_str))
                    
                if release_date and len(release_date) >= 4:
                     tags.add(TDRC(encoding=3, text=release_date[:4]))
                tags.add(TPE2(encoding=3, text=album_artist))
                if genre: tags.add(TCON(encoding=3, text=genre))
                if composer: tags.add(TCOM(encoding=3, text=composer))
                if publisher: tags.add(TPUB(encoding=3, text=publisher))
                if isrc: tags.add(TSRC(encoding=3, text=isrc))
            else: # FLAC
                audio.delete() 
                tags = audio

                tags['title'] = title
                tags['artist'] = artist
                tags['album'] = album
                tags['tracknumber'] = track_num_str
                if total_tracks_str and int(total_tracks_str) > 0:
                    tags['tracktotal'] = total_tracks_str
                else:
                    if 'tracktotal' in tags: del tags['tracktotal']
                        
                tags['discnumber'] = disc_num_str
                if total_discs_str and total_discs_str != "0" and total_discs_str != "1":
                    tags['disctotal'] = total_discs_str
                else:
                    if 'disctotal' in tags: del tags['disctotal']

                tags['date'] = release_date
                tags['albumartist'] = album_artist
                if genre: tags['genre'] = genre
                if composer: tags['composer'] = composer
                if publisher: tags['organization'] = publisher
                if isrc: tags['isrc'] = isrc

            config = self.download_manager.config
            embed_artwork_enabled = config.get_setting('downloads.embed_artwork', True)
            artwork_size = config.get_setting('downloads.embeddedArtworkSize', 1000)

            if embed_artwork_enabled:
                cover_url = None
                image_data = None
                if 'album' in track_info and isinstance(track_info['album'], dict):
                     key_to_try = None
                     if artwork_size >= 1000: key_to_try = 'cover_xl'
                     elif artwork_size >= 500: key_to_try = 'cover_big'
                     elif artwork_size >= 250: key_to_try = 'cover_medium'
                     
                     if key_to_try and key_to_try in track_info['album']:
                          cover_url = track_info['album'].get(key_to_try)

                if not cover_url and 'alb_picture' in track_info:
                     cover_md5 = track_info.get('alb_picture')
                     if cover_md5:
                          size_str = f"{artwork_size}x{artwork_size}"
                          cover_url = f"https://e-cdns-images.dzcdn.net/images/cover/{cover_md5}/{size_str}-000000-80-0-0.jpg"

                if cover_url:
                     try:
                         cover_response = requests.get(cover_url, timeout=15)
                         cover_response.raise_for_status()
                         image_data = cover_response.content
                         mime_type = cover_response.headers.get('Content-Type', 'image/jpeg')

                         if is_mp3:
                             audio.tags.add(
                                 APIC(encoding=3, mime=mime_type, type=3, desc='Cover', data=image_data)
                             )
                         else: # FLAC
                                 picture = Picture()
                                 picture.data = image_data
                                 picture.type = 3
                                 picture.mime = mime_type
                                 audio.add_picture(picture)
                     except requests.exceptions.RequestException as img_err:
                         logger.warning(f"Failed to download cover art from {cover_url}: {img_err}")
                     except Exception as embed_err:
                          logger.warning(f"Failed to create mutagen picture object: {embed_err}")

            save_artwork_enabled = config.get_setting('downloads.saveArtwork', True)
            
            if save_artwork_enabled:
                album_artwork_size = config.get_setting('downloads.albumArtworkSize', 1000)
                artist_artwork_size = config.get_setting('downloads.artistArtworkSize', 1200)
                album_image_template = config.get_setting('downloads.albumImageTemplate', 'cover')
                artist_image_template = config.get_setting('downloads.artistImageTemplate', 'folder')
                album_image_format = config.get_setting('downloads.albumImageFormat', 'jpg')
                artist_image_format = config.get_setting('downloads.artistImageFormat', 'jpg')
                
                try:
                    album_cover_url = None
                    if 'album' in track_info and isinstance(track_info['album'], dict):
                        if album_artwork_size >= 1000 and 'cover_xl' in track_info['album']:
                            album_cover_url = track_info['album']['cover_xl']
                        elif album_artwork_size >= 500 and 'cover_big' in track_info['album']:
                            album_cover_url = track_info['album']['cover_big']
                        elif 'cover_medium' in track_info['album']:
                            album_cover_url = track_info['album']['cover_medium']
                    
                    if not album_cover_url and 'alb_picture' in track_info:
                        cover_md5 = track_info.get('alb_picture')
                        if cover_md5:
                            size_str = f"{album_artwork_size}x{album_artwork_size}"
                            album_cover_url = f"https://e-cdns-images.dzcdn.net/images/cover/{cover_md5}/{size_str}-000000-80-0-0.jpg"
                    
                    if album_cover_url:
                        if target_directory:
                            album_dir = target_directory
                        else:
                            folder_conf = config.get_setting('downloads.folder_structure', {})
                            create_artist_folder = folder_conf.get('create_artist_folders', True)
                            create_album_folder = folder_conf.get('create_album_folders', True)
                            download_base = config.get_setting('downloads.path', str(Path.home() / 'Downloads'))
                            album_dir = Path(download_base)
                            if create_artist_folder:
                                primary_artist_name = track_info.get('artist', {}).get('name', 'Unknown Artist')
                                artists_list = track_info.get('artists', [])
                                if len(artists_list) > 1:
                                    all_names = [a.get('ART_NAME', '') for a in artists_list if a.get('ART_NAME')]
                                    if len(all_names) > 1:
                                        other_names = all_names[1:]
                                        artist_name_str = f"{all_names[0]} feat. {', '.join(other_names)}" if len(other_names) > 1 else f"{all_names[0]} feat. {other_names[0]}"
                                    else:
                                        artist_name_str = primary_artist_name
                                else:
                                    artist_name_str = primary_artist_name
                                safe_artist_name = self.download_manager._sanitize_filename(artist_name_str)
                                album_dir = album_dir / safe_artist_name
                            if create_album_folder:
                                album_name_str = track_info.get('alb_title', track_info.get('album', {}).get('title', 'Unknown Album'))
                                safe_album_name = self.download_manager._sanitize_filename(album_name_str)
                                album_dir = album_dir / safe_album_name
                        
                        album_cover_filename = f"{album_image_template}.{album_image_format}"
                        album_cover_path = album_dir / album_cover_filename
                        
                        if not album_cover_path.exists():
                            cover_response = requests.get(album_cover_url, timeout=15)
                            cover_response.raise_for_status()
                            with open(album_cover_path, 'wb') as f: f.write(cover_response.content)
                            logger.info(f"Album cover saved to {album_cover_path}")
                except Exception as album_cover_err:
                    logger.warning(f"Failed to save album cover: {album_cover_err}")
                
                try:
                    artist_image_url = None
                    if 'artist' in track_info and isinstance(track_info['artist'], dict):
                        if artist_artwork_size >= 1000 and 'picture_xl' in track_info['artist']:
                            artist_image_url = track_info['artist']['picture_xl']
                        elif artist_artwork_size >= 500 and 'picture_big' in track_info['artist']:
                            artist_image_url = track_info['artist']['picture_big']
                        elif 'picture_medium' in track_info['artist']:
                            artist_image_url = track_info['artist']['picture_medium']
                    
                    if not artist_image_url and 'art_picture' in track_info:
                        artist_md5 = track_info.get('art_picture')
                        if artist_md5:
                            size_str = f"{artist_artwork_size}x{artist_artwork_size}"
                            artist_image_url = f"https://e-cdns-images.dzcdn.net/images/artist/{artist_md5}/{size_str}-000000-80-0-0.jpg"
                    
                    if artist_image_url:
                        artist_dir = None
                        if target_directory:
                            # Determine the correct artist directory based on folder structure
                            folder_conf = config.get_setting('downloads.folder_structure', {})
                            create_artist_folder = folder_conf.get('create_artist_folders', True)
                            create_album_folder = folder_conf.get('create_album_folders', True)
                            
                            if create_artist_folder and create_album_folder:
                                # Both artist and album folders are created: target_directory is album folder, artist folder is parent
                                artist_dir = target_directory.parent if hasattr(target_directory, 'parent') else target_directory
                            elif create_artist_folder and not create_album_folder:
                                # Only artist folder is created: target_directory is artist folder
                                artist_dir = target_directory
                            else:
                                # No artist folder: save in target_directory (download root or album folder)
                                artist_dir = target_directory
                        else:
                            folder_conf = config.get_setting('downloads.folder_structure', {})
                            create_artist_folder = folder_conf.get('create_artist_folders', True)
                            create_album_folder = folder_conf.get('create_album_folders', True)
                            if create_artist_folder:
                                artist_dir = target_directory.parent if (create_album_folder and target_directory is not None and hasattr(target_directory, 'parent')) else target_directory
                            else:
                                folder_conf = config.get_setting('downloads.folder_structure', {})
                                create_artist_folder = folder_conf.get('create_artist_folders', True)
                                if create_artist_folder:
                                    download_base = config.get_setting('downloads.path', str(Path.home() / 'Downloads'))
                                    primary_artist_name = track_info.get('artist', {}).get('name', 'Unknown Artist')
                                    artists_list = track_info.get('artists', [])
                                    if len(artists_list) > 1:
                                        all_names = [a.get('ART_NAME', '') for a in artists_list if a.get('ART_NAME')]
                                        if len(all_names) > 1:
                                            other_names = all_names[1:]
                                            artist_name_str = f"{all_names[0]} feat. {', '.join(other_names)}" if len(other_names) > 1 else f"{all_names[0]} feat. {other_names[0]}"
                                        else:
                                            artist_name_str = primary_artist_name
                                            safe_artist_name = self.download_manager._sanitize_filename(artist_name_str)
                                            artist_dir = Path(download_base) / safe_artist_name
                        
                        if artist_dir:
                            artist_image_filename = f"{artist_image_template}.{artist_image_format}"
                            artist_image_path = artist_dir / artist_image_filename
                            if not artist_image_path.exists():
                                artist_response = requests.get(artist_image_url, timeout=15)
                                artist_response.raise_for_status()
                                with open(artist_image_path, 'wb') as f: f.write(artist_response.content)
                                logger.info(f"Artist image saved to {artist_image_path}")
                except Exception as artist_image_err:
                    logger.warning(f"Failed to save artist image: {artist_image_err}")

            try:
                self._process_and_save_lyrics(track_info, str(file_path), is_mp3, audio)
            except Exception as lyrics_exc:
                logger.warning(f"Lyrics processing failed: {lyrics_exc}")

            audio.save()
            logger.debug(f"Metadata and artwork successfully applied to {file_path}")
            
        except Exception as e:
            logger.error(f"General error applying metadata or artwork: {e}", exc_info=True)
            raise

    def _process_and_save_lyrics(self, track_info: dict, audio_file_path: str, is_mp3: bool, audio_obj) -> None:
        """
        Process and save lyrics for a track.
        
        Args:
            track_info (dict): Track information from Deezer API
            audio_file_path (str): Path to the audio file
            is_mp3 (bool): Whether the audio file is MP3 format
            audio_obj: Mutagen audio object for embedding lyrics
        """
        try:
            # Get lyrics settings
            config = self.download_manager.config
            lrc_enabled = config.get_setting('lyrics.lrc_enabled', True)
            txt_enabled = config.get_setting('lyrics.txt_enabled', False)
            lyrics_location = config.get_setting('lyrics.location', 'With Audio Files')
            custom_path = config.get_setting('lyrics.custom_path', '')
            sync_offset = config.get_setting('lyrics.sync_offset', 0)
            encoding = config.get_setting('lyrics.encoding', 'UTF-8')
            
            # Skip if both LRC and TXT are disabled
            if not lrc_enabled and not txt_enabled:
                logger.debug("Lyrics processing skipped - both LRC and TXT are disabled")
                return
            
            # Get track ID for lyrics fetching
            track_id = track_info.get('id', track_info.get('sng_id'))
            if not track_id:
                logger.warning("Cannot fetch lyrics: track ID not found")
                return
            
            # Convert track_id to int if it's a string
            try:
                track_id = int(track_id)
            except (ValueError, TypeError):
                logger.warning(f"Cannot fetch lyrics: invalid track ID format: {track_id}")
                return
            
            logger.debug(f"Fetching lyrics for track {track_id}")
            
            # Fetch lyrics from Deezer API
            lyrics_data = None
            if self.download_manager.deezer_api:
                try:
                    lyrics_data = self.download_manager.deezer_api.get_track_lyrics_sync(track_id)
                except Exception as e:
                    logger.warning(f"Failed to fetch lyrics for track {track_id}: {e}")
            
            if not lyrics_data:
                logger.debug(f"No lyrics found for track {track_id}")
                return
            
            # Parse lyrics data
            parsed_lyrics = LyricsProcessor.parse_deezer_lyrics(lyrics_data)
            
            if not parsed_lyrics['sync_lyrics'] and not parsed_lyrics['plain_text']:
                logger.debug(f"No usable lyrics content found for track {track_id}")
                return
            
            logger.info(f"Found lyrics for track {track_id} - Sync: {parsed_lyrics['has_sync']}, Plain: {bool(parsed_lyrics['plain_text'])}")
            
            # Save LRC file if enabled and sync lyrics available
            if lrc_enabled and parsed_lyrics['has_sync'] and parsed_lyrics['sync_lyrics']:
                # Calculate the final audio file path for lyrics saving
                final_audio_path = self._calculate_final_file_path(track_info)
                if final_audio_path:
                    self._save_lrc_file(parsed_lyrics, track_info, str(final_audio_path), lyrics_location, custom_path, sync_offset, encoding)
                else:
                    logger.warning("Could not determine final audio file path for LRC saving")
            
            # Save TXT file if enabled and plain text available
            if txt_enabled and parsed_lyrics['plain_text']:
                # Calculate the final audio file path for lyrics saving
                final_audio_path = self._calculate_final_file_path(track_info)
                if final_audio_path:
                    self._save_txt_file(parsed_lyrics, track_info, str(final_audio_path), lyrics_location, custom_path, encoding)
                else:
                    logger.warning("Could not determine final audio file path for TXT saving")
            
            # Embed lyrics into audio file (always try to embed if lyrics exist)
            self._embed_lyrics(parsed_lyrics, is_mp3, audio_obj, track_info)
            
        except Exception as e:
            logger.warning(f"Error processing lyrics: {e}", exc_info=True)

    def _save_lrc_file(self, parsed_lyrics: dict, track_info: dict, audio_file_path: str, 
                       lyrics_location: str, custom_path: str, sync_offset: int, encoding: str) -> None:
        """Save synchronized lyrics as LRC file."""
        try:
            # Create LRC content
            lrc_content = LyricsProcessor.create_lrc_content(
                parsed_lyrics['sync_lyrics'], 
                track_info, 
                sync_offset
            )
            
            if not lrc_content:
                logger.warning("Failed to create LRC content")
                return
            
            # Determine file path
            audio_path = Path(audio_file_path)
            lrc_path = LyricsProcessor.get_lyrics_file_path(
                audio_path, lyrics_location, custom_path, "lrc"
            )
            
            # Save LRC file
            if LyricsProcessor.save_lrc_file(lrc_content, lrc_path, encoding):
                logger.info(f"LRC file saved: {lrc_path}")
            else:
                logger.warning(f"Failed to save LRC file: {lrc_path}")
                
        except Exception as e:
            logger.warning(f"Error saving LRC file: {e}")

    def _save_txt_file(self, parsed_lyrics: dict, track_info: dict, audio_file_path: str, 
                       lyrics_location: str, custom_path: str, encoding: str) -> None:
        """Save plain text lyrics as TXT file."""
        try:
            lyrics_text = parsed_lyrics['plain_text']
            if not lyrics_text:
                logger.warning("No plain text lyrics to save")
                return
            
            # Determine file path
            audio_path = Path(audio_file_path)
            txt_path = LyricsProcessor.get_lyrics_file_path(
                audio_path, lyrics_location, custom_path, "txt"
            )
            
            # Save TXT file
            if LyricsProcessor.save_plain_lyrics(lyrics_text, txt_path, encoding):
                logger.info(f"TXT lyrics file saved: {txt_path}")
            else:
                logger.warning(f"Failed to save TXT lyrics file: {txt_path}")
                
        except Exception as e:
            logger.warning(f"Error saving TXT lyrics file: {e}")

    def _embed_lyrics(self, parsed_lyrics: dict, is_mp3: bool, audio_obj, track_info: dict) -> None:
        """Embed lyrics into the audio file metadata."""
        try:
            # Get lyrics embedding settings
            config = self.download_manager.config
            embed_sync_lyrics = config.get_setting('lyrics.embed_sync_lyrics', True)
            embed_plain_lyrics = config.get_setting('lyrics.embed_plain_lyrics', False)
            
            # Get language for lyrics embedding
            language = parsed_lyrics.get('language', 'eng')  # Default to 'eng' if not specified
            if not language or len(language) > 3:
                language = 'eng'  # Fallback to English
            
            lyrics_embedded = False
            
            # Embed synchronized lyrics if enabled and available
            if embed_sync_lyrics and parsed_lyrics.get('sync_lyrics'):
                try:
                    if is_mp3:
                        # For MP3 files, use SYLT frame (Synchronized Lyrics)
                        if hasattr(audio_obj, 'tags') and audio_obj.tags is not None:
                            
                            # Remove existing synchronized lyrics
                            audio_obj.tags.delall("SYLT")
                            
                            # Convert sync lyrics to SYLT format
                            sync_data = []
                            for line in parsed_lyrics['sync_lyrics']:
                                # SYLT expects time in milliseconds
                                time_ms = int(line.get('timestamp', 0) * 1000)
                                text = line.get('text', '').strip()
                                if text:  # Only add non-empty lyrics
                                    sync_data.append((text, time_ms))
                            
                            if sync_data:
                                # Add synchronized lyrics
                                audio_obj.tags.add(SYLT(
                                    encoding=3,  # UTF-8
                                    lang=language,
                                    format=2,  # Absolute time in milliseconds
                                    type=1,    # Lyrics
                                    desc='',
                                    text=sync_data
                                ))
                                logger.debug("Synchronized lyrics embedded into MP3 file")
                                lyrics_embedded = True
                            else:
                                logger.debug("No valid synchronized lyrics data to embed")
                        else:
                            logger.warning("Cannot embed synchronized lyrics: MP3 file has no tags")
                    else:
                        # For FLAC files, use custom synchronized lyrics field
                        if hasattr(audio_obj, '__setitem__'):
                            # Create LRC-style synchronized lyrics for FLAC
                            sync_lyrics_text = ""
                            for line in parsed_lyrics['sync_lyrics']:
                                timestamp = line.get('timestamp', 0)
                                text = line.get('text', '').strip()
                                if text:  # Only add non-empty lyrics
                                    # Convert timestamp to LRC format [mm:ss.xx]
                                    minutes = int(timestamp // 60)
                                    seconds = timestamp % 60
                                    sync_lyrics_text += f"[{minutes:02d}:{seconds:05.2f}]{text}\n"
                            
                            if sync_lyrics_text:
                                audio_obj['SYNCEDLYRICS'] = sync_lyrics_text.strip()
                                logger.debug("Synchronized lyrics embedded into FLAC file")
                                lyrics_embedded = True
                            else:
                                logger.debug("No valid synchronized lyrics data to embed in FLAC")
                        else:
                            logger.warning("Cannot embed synchronized lyrics: FLAC file format not supported")
                except Exception as e:
                    logger.warning(f"Error embedding synchronized lyrics: {e}")
            
            # Embed plain text lyrics if synchronized lyrics weren't embedded or aren't available
            if not lyrics_embedded and embed_plain_lyrics:
                lyrics_to_embed = parsed_lyrics['plain_text']
                if not lyrics_to_embed:
                    # Create plain text from sync lyrics if no plain text available
                    if parsed_lyrics['sync_lyrics']:
                        lyrics_to_embed = '\n'.join([line['text'] for line in parsed_lyrics['sync_lyrics']])
                
                if not lyrics_to_embed:
                    logger.debug("No lyrics content to embed")
                    return
                
                if is_mp3:
                    # For MP3 files, use USLT frame (Unsynchronized Lyrics)
                    if hasattr(audio_obj, 'tags') and audio_obj.tags is not None:
                        # Remove existing lyrics
                        audio_obj.tags.delall("USLT")
                        
                        # Add new lyrics
                        audio_obj.tags.add(USLT(
                            encoding=3,  # UTF-8
                            lang=language,
                            desc='',
                            text=lyrics_to_embed
                        ))
                        logger.debug("Plain text lyrics embedded into MP3 file")
                    else:
                        logger.warning("Cannot embed lyrics: MP3 file has no tags")
                else:
                    # For FLAC files, use LYRICS field
                    if hasattr(audio_obj, '__setitem__'):
                        audio_obj['LYRICS'] = lyrics_to_embed
                        logger.debug("Plain text lyrics embedded into FLAC file")
                    else:
                        logger.warning("Cannot embed lyrics: FLAC file format not supported")
            elif not lyrics_embedded and not embed_plain_lyrics:
                logger.debug("Plain text lyrics embedding is disabled in settings")
            
        except Exception as e:
            logger.warning(f"Error embedding lyrics: {e}")

    def _generate_decryption_key(self, sng_id_str: str) -> Optional[bytes]:
        try:
            bf_secret_str = "g4el58wc0zvf9na1"
            hashed_sng_id_hex = MD5.new(sng_id_str.encode('ascii', 'ignore')).hexdigest()
            if len(hashed_sng_id_hex) != 32: return None
            key_char_list = []
            for i in range(16):
                xor_val = (ord(hashed_sng_id_hex[i]) ^ ord(hashed_sng_id_hex[i + 16]) ^ ord(bf_secret_str[i]))
                key_char_list.append(chr(xor_val))
            key_string = "".join(key_char_list)
            key_bytes = key_string.encode('utf-8')
            if not (4 <= len(key_bytes) <= 56):
                 key_bytes_ascii = key_string.encode('ascii', 'ignore')
                 if not (4 <= len(key_bytes_ascii) <= 56): return None
                 else: key_bytes = key_bytes_ascii
            return key_bytes
        except Exception as e:
            logger.error(f"Error generating decryption key for {sng_id_str}: {e}", exc_info=True)
            return None

    def _decrypt_file_bf_cbc_stripe(self, encrypted_path: Path, key: bytes, sng_id: str) -> Optional[Path]:
        """Decrypts a file encrypted with Blowfish CBC stripe cipher."""
        decrypted_path = encrypted_path.with_suffix('.decrypted.tmp') # Temporary path for decrypted output 
        iv = bytes.fromhex("0001020304050607")
        chunk_size = 2048
        segment_size = chunk_size * 3

        try:
            bytes_written_decrypted = 0
            buffer = b''
            with open(encrypted_path, "rb") as f_enc, open(decrypted_path, "wb") as f_dec:
                 # ... (Rest of decryption loop as before - ensure its indentation is correct)
                 while True:
                     # Level 4
                     read_amount = segment_size - len(buffer)
                     chunk_data = f_enc.read(read_amount)
                     if not chunk_data and not buffer: break
                     buffer += chunk_data
                     while len(buffer) >= segment_size:
                        # Level 5
                        segment_to_process = buffer[:segment_size]
                        buffer = buffer[segment_size:]
                        first_chunk = segment_to_process[:chunk_size]
                        remaining_segment = segment_to_process[chunk_size:]
                        try:
                            # Level 6
                            cipher_for_chunk = Blowfish.new(key, Blowfish.MODE_CBC, iv)
                            decrypted_chunk = cipher_for_chunk.decrypt(first_chunk)
                            f_dec.write(decrypted_chunk)
                            f_dec.write(remaining_segment)
                            bytes_written_decrypted += segment_size
                        except ValueError as e:
                            # Level 6
                            logger.error(f"Error decrypting segment start (len {len(first_chunk)}): {e}. Writing original.")
                            f_dec.write(segment_to_process)
                            bytes_written_decrypted += segment_size
                     # Back to Level 4
                     if not chunk_data and len(buffer) > 0: break
                 # Back to Level 3 (within 'with open')
                 if len(buffer) > 0:
                    # Level 4
                    logger.debug(f"Processing final buffer of size {len(buffer)}")
                    if len(buffer) >= chunk_size:
                        # Level 5
                        first_chunk = buffer[:chunk_size]
                        remaining_buffer = buffer[chunk_size:]
                        try:
                            # Level 6
                            cipher_for_chunk = Blowfish.new(key, Blowfish.MODE_CBC, iv)
                            decrypted_chunk = cipher_for_chunk.decrypt(first_chunk)
                            f_dec.write(decrypted_chunk)
                            f_dec.write(remaining_buffer)
                            bytes_written_decrypted += len(buffer)
                        except ValueError as e:
                            # Level 6
                            logger.error(f"Error decrypting final buffer start (len {len(first_chunk)}): {e}. Writing original.")
                            f_dec.write(buffer)
                            bytes_written_decrypted += len(buffer)
                    else:
                        # Level 5
                        f_dec.write(buffer)
                        bytes_written_decrypted += len(buffer)
            # Back to Level 2 (within 'try')
            logger.info(f"Successfully decrypted {encrypted_path}. Wrote {bytes_written_decrypted} bytes.") 
            actual_decrypted_size = decrypted_path.stat().st_size
            actual_encrypted_size = encrypted_path.stat().st_size
            if actual_decrypted_size != actual_encrypted_size:
                logger.error(f"Decryption size mismatch: Encrypted={actual_encrypted_size}, Decrypted={actual_decrypted_size}")
                self._emit_error("Internal error during decryption (size mismatch)")
                return None
            return decrypted_path

        except Exception as e:
            logger.error(f"Error decrypting file {encrypted_path} for SNG_ID {sng_id}: {e}", exc_info=True) 
            # Clean up potentially corrupted decrypted file
            if decrypted_path.exists():
                try: os.remove(decrypted_path)
                except OSError as e_rem: logger.warning(f"Could not remove corrupted decrypted file {decrypted_path}: {e_rem}")
            return None

    def _process_and_save_lyrics_final(self, track_info: dict, final_file_path: str) -> None:
        """
        Process and save lyrics for a track after it's been moved to final location.
        
        Args:
            track_info (dict): Track information from Deezer API
            final_file_path (str): Path to the final audio file
        """
        try:
            # Get lyrics settings
            config = self.download_manager.config
            lrc_enabled = config.get_setting('lyrics.lrc_enabled', True)
            txt_enabled = config.get_setting('lyrics.txt_enabled', False)
            lyrics_location = config.get_setting('lyrics.location', 'With Audio Files')
            custom_path = config.get_setting('lyrics.custom_path', '')
            sync_offset = config.get_setting('lyrics.sync_offset', 0)
            encoding = config.get_setting('lyrics.encoding', 'UTF-8')
            
            # Skip if both LRC and TXT are disabled
            if not lrc_enabled and not txt_enabled:
                logger.debug("Lyrics processing skipped - both LRC and TXT are disabled")
                return
            
            # Get track ID for lyrics fetching
            track_id = track_info.get('id', track_info.get('sng_id'))
            if not track_id:
                logger.warning("Cannot fetch lyrics: track ID not found")
                return
            
            # Convert track_id to int if it's a string
            try:
                track_id = int(track_id)
            except (ValueError, TypeError):
                logger.warning(f"Cannot fetch lyrics: invalid track ID format: {track_id}")
                return
            
            logger.debug(f"Fetching lyrics for track {track_id}")
            
            # Fetch lyrics from Deezer API
            lyrics_data = None
            if self.download_manager.deezer_api:
                try:
                    lyrics_data = self.download_manager.deezer_api.get_track_lyrics_sync(track_id)
                except Exception as e:
                    logger.warning(f"Failed to fetch lyrics for track {track_id}: {e}")
            
            if not lyrics_data:
                logger.debug(f"No lyrics found for track {track_id}")
                return
            
            # Parse lyrics data
            parsed_lyrics = LyricsProcessor.parse_deezer_lyrics(lyrics_data)
            
            if not parsed_lyrics['sync_lyrics'] and not parsed_lyrics['plain_text']:
                logger.debug(f"No usable lyrics content found for track {track_id}")
                return
            
            # Save LRC file if enabled and sync lyrics are available
            if lrc_enabled and parsed_lyrics['sync_lyrics']:
                try:
                    logger.info(f"[LYRICS_DEBUG] Attempting to save LRC file for track {track_id}")
                    lrc_path = LyricsProcessor.get_lyrics_file_path(
                        Path(final_file_path), lyrics_location, custom_path, "lrc"
                    )
                    logger.info(f"[LYRICS_DEBUG] LRC file path calculated as: {lrc_path}")
                    lrc_content = LyricsProcessor.create_lrc_content(
                        parsed_lyrics['sync_lyrics'], track_info, sync_offset
                    )
                    logger.info(f"[LYRICS_DEBUG] LRC content created, length: {len(lrc_content) if lrc_content else 0}")
                    if LyricsProcessor.save_lrc_file(lrc_content, lrc_path, encoding):
                        logger.info(f"[SUCCESS] LRC file saved successfully: {lrc_path}")
                    else:
                        logger.warning(f"[FAILED] LRC file saving failed: {lrc_path}")
                except Exception as e:
                    logger.error(f"Failed to save LRC lyrics: {e}", exc_info=True)
            
            # Save TXT file if enabled and plain text lyrics are available
            if txt_enabled and parsed_lyrics['plain_text']:
                try:
                    txt_path = LyricsProcessor.get_lyrics_file_path(
                        Path(final_file_path), lyrics_location, custom_path, "txt"
                    )
                    LyricsProcessor.save_plain_lyrics(parsed_lyrics['plain_text'], txt_path, encoding)
                    logger.info(f"Saved TXT lyrics to: {txt_path}")
                except Exception as e:
                    logger.error(f"Failed to save TXT lyrics: {e}")
                    
        except Exception as e:
            logger.error(f"Error in lyrics processing: {e}", exc_info=True)

    def cancel_download(self, item_id: int):
        """Cancels an ongoing download. Currently conceptual - needs worker integration."""
        # TODO: Implement cancellation if possible. 
        # For requests, this usually involves setting a flag and checking it 
        # within the download loop, or potentially closing the connection, 
        # but QRunnable doesn't have a built-in robust cancel mechanism.
        if item_id in self.downloads:
            worker = self.downloads[item_id]
            logger.warning(f"Cancellation requested for {item_id}, but true cancellation is not yet implemented for direct downloads.")
            # Maybe set a flag on the worker? worker.cancel_requested = True
            # The worker loop would need to check self.cancel_requested
            # For now, just log and remove from tracking (it might finish anyway)
            # del self.downloads[item_id] 
            # self.signals.error.emit(item_id, worker.item_type, "Download cancelled by user (attempted).")
        else:
            logger.warning(f"Attempted to cancel download for {item_id}, but it was not found.")
    
    def cancel_all_downloads(self):
        """Cancel all active downloads and clear the queue."""
        logger.info("Cancelling all active downloads...")
        
        # Stop all active workers
        for worker_id, worker in list(self.active_workers.items()):
            logger.debug(f"Requesting stop for worker: {worker_id}")
            worker.stop()  # Signal worker to stop
        
        # Clear the active workers tracking
        self.active_workers.clear()
        
        # Clear the old downloads dict as well
        self.downloads.clear()
        
        # Clear the queue state file
        queue_state_path = self._get_queue_state_path()
        if queue_state_path.exists():
            try:
                queue_state_path.unlink()
                logger.info("Queue state file deleted")
            except Exception as e:
                logger.error(f"Error deleting queue state file: {e}")
        
        logger.info("All downloads cancelled and queue cleared")

    def get_active_downloads(self) -> List[Dict[str, Any]]:
        """Return info about active downloads (for UI)."""
        # This will need adjustment as progress is handled differently now.
        # We might need the manager to store progress reported by workers.
        active = []
        for item_id, worker in self.downloads.items():
             active.append({'item_id': item_id, 'item_type': worker.item_type, 'progress': 0}) # Placeholder progress
        return active

    def _calculate_final_file_path(self, track_info: dict) -> Optional[Path]:
        """
        Calculate the final file path where the audio file will be saved.
        This replicates the path calculation logic from _perform_download_direct.
        """
        try:
            # Get configuration settings
            config = self.download_manager.config
            
            # Base download directory
            base_download_dir = Path(self.download_manager._setup_download_dir())
            
            # Get folder and template configurations
            folder_conf = config.get_setting('downloads.folder_structure', {})
            templates_conf = config.get_setting('downloads.filename_templates', {})
            
            create_artist_folder = folder_conf.get('create_artist_folders', True)
            create_album_folder = folder_conf.get('create_album_folders', True)
            create_cd_folder = folder_conf.get('create_cd_folders', True)
            
            artist_template = templates_conf.get('artist', '%albumartist%')
            logger.debug(f"FOLDER_PATH DEBUG: Using artist_template: '{artist_template}'")
            album_template = templates_conf.get('album', '%album%')
            cd_template = templates_conf.get('cd', 'CD %disc_number%')

            # Extract track metadata (same as in download logic)
            artist_val = track_info.get('artist', {}).get('name', 'Unknown Artist')
            album_val = track_info.get('alb_title', track_info.get('album', {}).get('title', 'Unknown Album'))
            title_val = track_info.get('title', 'Unknown Title')
            
            # Track and disc numbers
            # Get track number with better fallback logic
            track_position = track_info.get('track_position')
            track_number = track_info.get('track_number')
            track_num_int = track_position or track_number or 1
            
            # Add INFO level logging to debug the issue
            logger.info(f"TRACK_NUMBER_DEBUG: Track '{track_info.get('title', 'Unknown')}' - track_position: {track_position}, track_number: {track_number}, final: {track_num_int}")
            
            if track_num_int == 0:
                track_num_int = 1
            disc_num_int = track_info.get('disk_number', 1)
            
            # Year handling
            release_date = track_info.get('release_date', '1970-01-01')
            year_val = release_date.split('-')[0] if '-' in release_date else release_date[:4]
            
            # Album artist handling - use configuration-based logic
            logger.debug(f"FOLDER_PATH_DEBUG: About to call _get_album_artist with track_info keys: {list(track_info.keys())}")
            logger.debug(f"FOLDER_PATH_DEBUG: Album cache has {len(self.download_manager._album_cache)} entries: {list(self.download_manager._album_cache.keys())}")
            album_artist_val = self._get_album_artist(track_info, artist_val)
            logger.debug(f"FOLDER_PATH_DEBUG: _get_album_artist returned: '{album_artist_val}' (artist_val was: '{artist_val}')")
            
            # Album disc information
            total_album_discs = track_info.get('album', {}).get('nb_discs', 1)
            
            # Create placeholders dictionary
            placeholders = {
                'artist': artist_val,
                'album': album_val,
                'title': title_val,
                'track_number': track_num_int,
                'playlist_position': track_info.get('playlist_position', track_num_int),
                'disc_number': disc_num_int,
                'year': year_val,
                'album_artist': album_artist_val,
                'albumartist': album_artist_val,  # Alias for album_artist (for %albumartist% templates)
                'playlist_name': self.playlist_title if self.playlist_title else '',
                'playlist': self.playlist_title if self.playlist_title else '',
                'genre': track_info.get('genres', {}).get('data', [{}])[0].get('name', 'Unknown Genre'),
                'isrc': track_info.get('isrc', '')
            }
            logger.debug(f"FOLDER_PATH DEBUG: Using placeholders: {placeholders}")
            
            def process_template(template_str: str) -> str:
                processed_str = template_str
                for key, value in placeholders.items():
                    processed_str = processed_str.replace(f"{{{key}}}", str(value))
                    processed_str = processed_str.replace(f"%{key}%", str(value))
                return processed_str

            # Build directory components
            dir_components = []
            
            # Handle playlist vs regular track folder structure
            if self.item_type == 'playlist_track' and self.playlist_title:
                create_playlist_folder = folder_conf.get('create_playlist_folders', True)
                if create_playlist_folder:
                    playlist_template = templates_conf.get('playlist', '%playlist%')
                    processed_playlist = process_template(playlist_template)
                    if processed_playlist:
                        dir_components.append(processed_playlist)
            else:
                    # Fall back to artist/album structure OR regular artist/album folder structure
                    if create_artist_folder:
                        processed_artist = process_template(artist_template)
                        if processed_artist:
                            dir_components.append(processed_artist)
                    
                    if create_album_folder:
                        processed_album = process_template(album_template)
                        if processed_album:
                            dir_components.append(processed_album)
                
                    # CD folder for multi-disc albums
                    # This part is for non-playlist tracks or playlist tracks where playlist folder is disabled
                    if create_cd_folder and total_album_discs > 1:
                        processed_cd = process_template(cd_template)
                        if processed_cd:
                            dir_components.append(processed_cd)
            
            # Determine filename template and create filename
            filename_template_key = "track"  # Default
            default_tpl = "{artist} - {title}"
            
            if self.item_type == 'album_track':
                # Check if this is a compilation album
                if self._is_compilation_album(track_info):
                    filename_template_key = "compilation_track"
                    default_tpl = "{track_number:02d} - {artist} - {title}"
                    logger.debug(f"COMPILATION_FILENAME: Using compilation track template for album track")
                else:
                    filename_template_key = "album_track"
                    default_tpl = "{track_number:02d}. {title}"
            elif self.item_type == 'playlist_track' and self.playlist_title:
                filename_template_key = "playlist_track"
                default_tpl = "{playlist_position:02d} - {artist} - {title}"
            
            chosen_template_str = config.get_setting(f"downloads.filename_templates.{filename_template_key}", default_tpl)
            
            # Format filename
            # Add INFO level logging to debug track number issue
            logger.info(f"FILENAME_DEBUG: About to format filename with track_number={placeholders.get('track_number')} for track '{track_info.get('title', 'Unknown')}'")
            
            try:
                filename_part = chosen_template_str.format(**placeholders)
            except (KeyError, ValueError):
                filename_part = default_tpl.format(**placeholders)
            
            # Determine file extension
            quality = self.download_manager.quality
            file_extension = ".flac" if quality == 'FLAC' else ".mp3"
            filename_with_ext = filename_part + file_extension
            
            # Sanitize components
            sanitized_dir_parts = [self.download_manager._sanitize_filename(part) for part in dir_components if part]
            sanitized_filename = self.download_manager._sanitize_filename(filename_with_ext)
            
            # Construct final path
            final_file_path = base_download_dir.joinpath(*sanitized_dir_parts, sanitized_filename)
            logger.debug(f"FOLDER_FIX: Final file path: {final_file_path}")
            
            return final_file_path

        except Exception as e:
            logger.warning(f"Error calculating final file path: {e}")
            return None





# --- Download Manager ---
class DownloadManagerSignals(QObject):
    """Signals for DownloadManager itself, adapted for DownloadQueueWidget."""
    download_started = pyqtSignal(dict)      # Emits {'id': str, 'title': str, 'type': str, 'album_id': Optional[int], 'playlist_id': Optional[int], 'album_total_tracks': Optional[int], 'playlist_total_tracks': Optional[int]}
    download_progress = pyqtSignal(str, int) # Emits item_id_str, progress_percentage (0-100)
    download_finished = pyqtSignal(str)     # Emits item_id_str (of the successfully downloaded item)
    download_failed = pyqtSignal(str, str)  # Emits item_id_str, error_message
    all_downloads_finished = pyqtSignal()   # Emitted when the queue is empty and all workers are done.
    group_download_enqueued = pyqtSignal(dict) # Emits {'group_id': str, 'group_title': str, 'item_type': str, 'total_tracks': int, 'cover_url': Optional[str], 'artist_name': Optional[str]} for albums

class DownloadManager:
    """Manages the download queue and interacts with the download worker."""
    
    def __init__(self, config_manager: 'ConfigManager', deezer_api: 'DeezerAPI'):
        """Initialize the DownloadManager."""
        self.config = config_manager
        self.deezer_api = deezer_api
        self.download_dir = self._setup_download_dir()
        self.quality = self.config.get_setting('downloads.quality', 'MP3_320')
        # Create dedicated thread pool for downloads to avoid conflicts
        self.thread_pool = QThreadPool()
        max_threads = self.config.get_setting('downloads.concurrent_downloads', 3)
        # Allow more threads for better performance, but cap at reasonable limit
        optimized_max_threads = min(max(max_threads, 5), 20)  # Min 5, max 20
        self.thread_pool.setMaxThreadCount(optimized_max_threads)
        
        # Set thread pool properties for better performance
        self.thread_pool.setExpiryTimeout(30000)  # Keep threads alive for 30 seconds
        
        logger.info(f"DownloadManager: Created dedicated thread pool with {optimized_max_threads} threads (user setting: {max_threads})")
        
        self.downloads: Dict[int, DownloadWorker] = {} # Old, maybe remove if active_workers is better
        self.active_workers: Dict[str, DownloadWorker] = {} # item_id_str: worker instance
        self.signals = DownloadManagerSignals() # Use MANAGER signals object
        
        # Album cache for album artist information
        self._album_cache: Dict[int, dict] = {} # album_id: album_details
        
        # Track completed downloads to prevent re-downloading moved/deleted files
        self.completed_track_ids: set = set()  # Set of track_id strings that have been completed
        self.completed_albums: set = set()     # Set of album_id strings that have been completed

        # Connect signals to manage active_workers
        self.signals.download_finished.connect(self._handle_worker_finished)
        self.signals.download_failed.connect(self._handle_worker_failed)

        # Flag to prevent processing completion signals during clear operations
        self._clearing_queue = False
        
        # Performance optimization: batch queue state saves
        self._pending_queue_save = False
        self._last_queue_save_time = 0
        
        # HTTP session pool for better download performance
        self._http_session = None
        self._setup_http_session()

        logger.info(f"DownloadManager initialized. Download dir: {self.download_dir}, Quality: {self.quality}, Concurrent: {max_threads}")
        
        # Clean any invalid queue entries before restoring
        self.clean_invalid_queue_entries()
        
        # Load and restore previous queue state
        self._restore_queue_state()
        
        # Set up file watcher for live queue monitoring
        self._setup_queue_file_watcher()

    def _restore_queue_state(self):
        """Restore the download queue from the saved state file."""
        state = self._load_queue_state()
        if not state:
            logger.info("No previous queue state to restore")
            return

        # Restore unfinished downloads
        unfinished_downloads = state.get('unfinished_downloads', [])
        if unfinished_downloads:
            logger.info(f"Restoring {len(unfinished_downloads)} unfinished album/playlist downloads")
            for download_group in unfinished_downloads:
                album_id = download_group.get('album_id')
                playlist_id = download_group.get('playlist_id')  # For future playlist support
                queued_tracks = download_group.get('queued_tracks', [])
                
                if album_id and album_id != 'unknown':
                    # Restore album download
                    track_ids = [int(track['track_id']) for track in queued_tracks if track['track_id'] != 'unknown']
                    if track_ids:
                        logger.info(f"Restoring album download: {download_group.get('artist_name')} - {download_group.get('album_title')} ({len(track_ids)} tracks)")
                        try:
                            # Validate album_id before converting to int
                            if album_id and album_id != 'unknown' and str(album_id).isdigit():
                                logger.info(f"RESTORATION: Attempting to restore album download {album_id}")
                                try:
                                    # Try to restore the download directly by queuing individual tracks
                                    # This is more reliable than trying to use async download_album
                                    for track in queued_tracks:
                                        track_id = track.get('track_id')
                                        if track_id and track_id != 'unknown' and str(track_id).isdigit():
                                            try:
                                                logger.info(f"RESTORATION: Queuing track {track_id} from album {album_id}")
                                                self._queue_individual_track_download(
                                                    track_id=int(track_id),
                                                    item_type='album_track',
                                                    album_id=int(album_id),
                                                    track_details=None,
                                                    album_total_tracks=len(track_ids)
                                                )
                                            except Exception as track_error:
                                                logger.error(f"RESTORATION: Failed to queue track {track_id}: {track_error}")
                                        else:
                                            logger.warning(f"RESTORATION: Skipping invalid track ID: {track_id}")
                                    
                                    logger.info(f"RESTORATION: Successfully queued {len([t for t in queued_tracks if t.get('track_id') != 'unknown'])} tracks from album {album_id}")
                                    
                                except Exception as restore_error:
                                    logger.error(f"RESTORATION: Failed to restore album {album_id}: {restore_error}")
                            else:
                                logger.warning(f"Skipping album download with invalid ID: {album_id}")
                        except Exception as e:
                            logger.error(f"Error restoring album download {album_id}: {e}")
                elif playlist_id and playlist_id != 'unknown':
                    # Future: Restore playlist download
                    logger.info(f"Playlist restoration not yet implemented for playlist {playlist_id}")
                else:
                    # Restore individual tracks
                    for track in queued_tracks:
                        track_id = track.get('track_id')
                        if track_id and track_id != 'unknown':
                            try:
                                logger.info(f"Restoring individual track download: {track.get('title')} (ID: {track_id})")
                                self.download_track(int(track_id))
                            except Exception as e:
                                logger.error(f"Error restoring track download {track_id}: {e}")

        # Don't restore completed downloads - they should not be re-downloaded
        completed_downloads = state.get('completed_downloads', [])
        failed_downloads = state.get('failed_downloads', [])
        
        # Restore completed tracking data to prevent re-downloading moved/deleted files
        completed_track_ids = state.get('completed_track_ids', [])
        completed_albums = state.get('completed_albums', [])
        
        if completed_track_ids:
            self.completed_track_ids.update(completed_track_ids)
            logger.info(f"Restored {len(completed_track_ids)} completed track IDs from previous session")
        
        if completed_albums:
            self.completed_albums.update(completed_albums)
            logger.info(f"Restored {len(completed_albums)} completed album IDs from previous session")
        
        if completed_downloads:
            logger.info(f"Ignoring {len(completed_downloads)} completed downloads from previous session (not restoring)")
        if failed_downloads:
            logger.info(f"Found {len(failed_downloads)} failed downloads in history (not auto-retrying)")
            
        logger.info("Queue state restoration completed")

    def _setup_http_session(self):
        """Set up HTTP session with connection pooling for better performance."""
        try:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            
            self._http_session = requests.Session()
            
            # Configure retry strategy
            retry_strategy = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
            )
            
            # Configure HTTP adapter with connection pooling
            adapter = HTTPAdapter(
                pool_connections=10,  # Number of connection pools
                pool_maxsize=20,      # Max connections per pool
                max_retries=retry_strategy,
                pool_block=False
            )
            
            self._http_session.mount("http://", adapter)
            self._http_session.mount("https://", adapter)
            
            # Set optimized headers
            self._http_session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive'
            })
            
            logger.info("HTTP session with connection pooling initialized")
            
        except Exception as e:
            logger.error(f"Failed to setup HTTP session: {e}")
            self._http_session = None

    def get_http_session(self):
        """Get the shared HTTP session for downloads."""
        if self._http_session is None:
            self._setup_http_session()
        return self._http_session

    def _setup_queue_file_watcher(self):
        """Set up file watcher to monitor queue file changes."""
        try:
            from PyQt6.QtCore import QFileSystemWatcher, QTimer
            
            self.queue_file_watcher = QFileSystemWatcher()
            queue_file_path = str(self._get_queue_state_path())
            
            # Watch the queue file
            if Path(queue_file_path).exists():
                self.queue_file_watcher.addPath(queue_file_path)
                logger.info(f"Started monitoring queue file: {queue_file_path}")
            
            # Watch the directory in case the file doesn't exist yet
            queue_dir = str(Path(queue_file_path).parent)
            if Path(queue_dir).exists():
                self.queue_file_watcher.addPath(queue_dir)
                logger.info(f"Started monitoring queue directory: {queue_dir}")
            
            # Connect file change signal with a small delay to avoid multiple rapid triggers
            self.queue_reload_timer = QTimer()
            self.queue_reload_timer.setSingleShot(True)
            self.queue_reload_timer.timeout.connect(self._on_queue_file_changed)
            
            self.queue_file_watcher.fileChanged.connect(self._queue_file_change_detected)
            self.queue_file_watcher.directoryChanged.connect(self._queue_file_change_detected)
            
        except Exception as e:
            logger.error(f"Error setting up queue file watcher: {e}")
    
    def _queue_file_change_detected(self, path):
        """Handle queue file change detection with debouncing."""
        try:
            # Check if we're in the main thread before starting timer
            from PyQt6.QtCore import QThread
            from PyQt6.QtWidgets import QApplication
            # Check if we have a QApplication and are in the main thread
            app = QApplication.instance()
            if app and QThread.currentThread() == app.thread():
                # Safe to start timer directly
                self.queue_reload_timer.start(1000)
            else:
                # We're in a different thread, skip the timer to avoid errors
                logger.debug("Queue file change detected from worker thread, skipping timer")
        except Exception as e:
            logger.error(f"Error handling queue file change: {e}")
    
    def _on_queue_file_changed(self):
        """Handle queue file changes by reloading the queue."""
        try:
            queue_state_path = self._get_queue_state_path()
            
            # Check if file still exists (might have been deleted by clear operation)
            if not queue_state_path.exists():
                logger.info("Queue file was deleted, skipping reload")
                return
            
            # Check if file is empty or has minimal content (might be in process of being cleared)
            try:
                file_size = queue_state_path.stat().st_size
                if file_size < 10:  # Less than 10 bytes is likely empty or just "{}"
                    logger.info("Queue file is empty or minimal, skipping reload")
                    return
            except Exception:
                logger.info("Could not check queue file size, skipping reload")
                return
            
            logger.info("Queue file changed, reloading...")
            self.reload_queue_from_disk()
        except Exception as e:
            logger.error(f"Error reloading queue after file change: {e}")

    def reload_queue_from_disk(self):
        """Reload the download queue from disk without restarting the application."""
        try:
            logger.info("Reloading download queue from disk...")
            
            # Only reload if there are no active workers to prevent interference
            if len(self.active_workers) > 0:
                logger.info(f"Skipping queue reload - {len(self.active_workers)} active workers running")
                return False
            
            self._restore_queue_state()
            logger.info("Download queue reloaded successfully")
            return True
        except Exception as e:
            logger.error(f"Error reloading download queue: {e}")
            return False

    def refresh_settings(self):
        """Refresh download manager settings from config when they are changed."""
        old_quality = self.quality
        old_download_dir = self.download_dir
        old_max_threads = self.thread_pool.maxThreadCount()
        
        # Update cached settings
        self.quality = self.config.get_setting('downloads.quality', 'MP3_320')
        self.download_dir = self._setup_download_dir()
        max_threads = self.config.get_setting('downloads.concurrent_downloads', 3)
        
        # Apply same optimization as in __init__
        optimized_max_threads = min(max(max_threads, 5), 20)  # Min 5, max 20
        self.thread_pool.setMaxThreadCount(optimized_max_threads)
        
        # Log changes
        if old_quality != self.quality:
            logger.info(f"DownloadManager: Quality setting changed from {old_quality} to {self.quality}")
        if old_download_dir != self.download_dir:
            logger.info(f"DownloadManager: Download directory changed from {old_download_dir} to {self.download_dir}")
        if old_max_threads != optimized_max_threads:
            logger.info(f"DownloadManager: Concurrent downloads changed from {old_max_threads} to {optimized_max_threads} (user setting: {max_threads})")

    def _handle_worker_finished(self, item_id_str: str):
        # Check if we're in the middle of clearing the queue
        if self._clearing_queue:
            logger.info(f"[QUEUE_DEBUG] Ignoring worker finished signal for {item_id_str} - queue is being cleared")
            return
        
        logger.info(f"[QUEUE_DEBUG] Worker finished for track {item_id_str}")
        
        # Track this track as completed to prevent re-downloading if moved/deleted
        self.completed_track_ids.add(item_id_str)
        logger.info(f"[QUEUE_DEBUG] Added track {item_id_str} to completed tracking")
        
        # If this was part of an album, check if the whole album is now complete
        if item_id_str in self.active_workers:
            worker = self.active_workers[item_id_str]
            if hasattr(worker, 'album_id') and worker.album_id:
                album_id_str = str(worker.album_id)
                # Check if all tracks in this album are now completed
                album_tracks_completed = self._check_album_completion(album_id_str)
                if album_tracks_completed:
                    self.completed_albums.add(album_id_str)
                    logger.info(f"[QUEUE_DEBUG] Album {album_id_str} marked as fully completed")
        
        if item_id_str in self.active_workers:
            logger.info(f"[QUEUE_DEBUG] Removing finished worker {item_id_str} from active list. Active workers before removal: {len(self.active_workers)}")
            del self.active_workers[item_id_str]
            logger.info(f"[QUEUE_DEBUG] Active workers after removal: {len(self.active_workers)}")
        else:
            logger.warning(f"[QUEUE_DEBUG] Tried to remove finished worker {item_id_str}, but it was not in active_workers list. Current workers: {list(self.active_workers.keys())}")
        
        # Use batched queue saving for better performance
        self._schedule_queue_save(f"worker {item_id_str} finished")
        
        self._check_and_emit_all_finished()

    def _schedule_queue_save(self, reason: str = ""):
        """Schedule a queue save with batching to improve performance."""
        import time
        current_time = time.time()
        
        # If we just saved recently (within 2 seconds), defer the save
        if current_time - self._last_queue_save_time < 2.0:
            if not self._pending_queue_save:
                self._pending_queue_save = True
                # Check if we're in the main thread before using QTimer
                from PyQt6.QtCore import QTimer, QThread
                from PyQt6.QtWidgets import QApplication
                # Check if we have a QApplication and are in the main thread
                app = QApplication.instance()
                if app and QThread.currentThread() == app.thread():
                    QTimer.singleShot(2000, self._perform_pending_queue_save)
                    # Reduced logging
                else:
                    # We're in a worker thread, save immediately
                    self._perform_pending_queue_save()
                    # Reduced logging
            return
        
        # Save immediately if enough time has passed
        try:
            self._save_queue_state()
            self._last_queue_save_time = current_time
            # Reduced logging
        except Exception as e:
            logger.error(f"[QUEUE_DEBUG] Failed to save queue state ({reason}): {e}")

    def _perform_pending_queue_save(self):
        """Perform a pending queue save."""
        if self._pending_queue_save:
            try:
                import time
                self._save_queue_state()
                self._last_queue_save_time = time.time()
                self._pending_queue_save = False
                # Reduced logging
            except Exception as e:
                logger.error(f"[QUEUE_DEBUG] Failed to perform pending queue save: {e}")
                self._pending_queue_save = False

    def _check_album_completion(self, album_id_str: str) -> bool:
        """Check if all tracks in an album are completed."""
        try:
            # Count how many tracks from this album are in our completed tracking
            album_tracks_in_completed = sum(1 for track_id in self.completed_track_ids 
                                          if track_id in self.active_workers and 
                                          hasattr(self.active_workers[track_id], 'album_id') and 
                                          str(self.active_workers[track_id].album_id) == album_id_str)
            
            # Count how many tracks from this album are currently active
            album_tracks_active = sum(1 for worker in self.active_workers.values() 
                                    if hasattr(worker, 'album_id') and 
                                    str(worker.album_id) == album_id_str)
            
            # If no active tracks from this album, check if we have any completed tracks
            if album_tracks_active == 0 and album_tracks_in_completed > 0:
                logger.info(f"[QUEUE_DEBUG] Album {album_id_str} appears complete - no active tracks, {album_tracks_in_completed} completed")
                return True
            
            return False
        except Exception as e:
            logger.error(f"[QUEUE_DEBUG] Error checking album completion for {album_id_str}: {e}")
            return False

    def _handle_worker_failed(self, item_id_str: str, error_message: str):
        # Check if we're in the middle of clearing the queue
        if self._clearing_queue:
            logger.info(f"[QUEUE_DEBUG] Ignoring worker failed signal for {item_id_str} - queue is being cleared")
            return
        
        logger.error(f"[QUEUE_DEBUG] Worker failed for track {item_id_str}: {error_message}")
        if item_id_str in self.active_workers:
            logger.info(f"[QUEUE_DEBUG] Removing failed worker {item_id_str} from active list. Active workers before removal: {len(self.active_workers)}")
            del self.active_workers[item_id_str]
            logger.info(f"[QUEUE_DEBUG] Active workers after removal: {len(self.active_workers)}")
        else:
            logger.warning(f"[QUEUE_DEBUG] Tried to remove failed worker {item_id_str}, but it was not in active_workers list. Current workers: {list(self.active_workers.keys())}")
        
        # Use batched queue saving for better performance
        self._schedule_queue_save(f"worker {item_id_str} failed")
        
        self._check_and_emit_all_finished()

    def _check_and_emit_all_finished(self):
        """Checks if all tasks are done and emits all_downloads_finished if so."""
        # This check is based on QThreadPool.activeThreadCount(), which might not be entirely accurate
        # if tasks are queued but not yet active, or if some tasks finish very quickly.
        # A more robust way might be to count active_workers, but waitForDone in shutdown handles the final wait.
        if self.thread_pool.activeThreadCount() == 0 and not self.active_workers:
            logger.info("All download workers seem to be finished and no active workers tracked. Emitting all_downloads_finished.")
            self.signals.all_downloads_finished.emit()

    def shutdown(self):
        logger.info("DownloadManager shutting down. Stopping all workers...")
        for worker_id, worker in list(self.active_workers.items()): # Iterate over a copy
            logger.debug(f"Requesting stop for worker: {worker_id}")
            worker.stop() # Signal worker to stop
        
        logger.info("Waiting for all download threads to complete...")
        self.thread_pool.waitForDone()
        
        # Clean up HTTP session
        if hasattr(self, '_http_session') and self._http_session:
            try:
                self._http_session.close()
                logger.debug("HTTP session closed")
            except Exception as e:
                logger.error(f"Error closing HTTP session: {e}")
        
        logger.info("All download threads finished. DownloadManager shutdown complete.")
        self.active_workers.clear() # Clear worker tracking

    def _setup_download_dir(self) -> str:
        """Ensure download directory exists and return its path."""
        # Corrected config key based on observed settings.json structure
        download_dir_str = self.config.get_setting('downloads.path', 'downloads') 
        download_dir = Path(download_dir_str).resolve()
        try:
            download_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Download directory set to: {download_dir}")
            return str(download_dir)
        except OSError as e:
            logger.error(f"Failed to create download directory {download_dir}: {e}")
            # Fallback to a default local directory? Or raise an error?
            fallback_dir = Path("deemusic_downloads").resolve()
            try:
                 fallback_dir.mkdir(parents=True, exist_ok=True)
                 logger.warning(f"Using fallback download directory: {fallback_dir}")
                 return str(fallback_dir)
            except OSError as fallback_e:
                 logger.critical(f"Failed to create even fallback download directory {fallback_dir}: {fallback_e}. Downloads will likely fail.")
                 # Propagate the error or return a non-functional path?
                 # Returning original problematic path to make failure obvious downstream.
                 return str(download_dir)

    async def _get_cached_album_details(self, album_id: int) -> dict:
        """Get album details from cache or fetch and cache them."""
        if album_id in self._album_cache:
            logger.debug(f"ALBUM_ARTIST_FIX: Using cached album details for album {album_id}")
            return self._album_cache[album_id]
        
        try:
            logger.debug(f"ALBUM_ARTIST_FIX: Fetching album details for album {album_id}")
            album_details = await self.deezer_api.get_album_details(album_id)
            if album_details:
                self._album_cache[album_id] = album_details
                logger.debug(f"ALBUM_ARTIST_FIX: Cached album details for album {album_id}: '{album_details.get('title')}' by '{album_details.get('artist', {}).get('name', 'Unknown')}'")
                return album_details
            else:
                logger.warning(f"ALBUM_ARTIST_FIX: Failed to fetch album details for album {album_id}")
                return {}
        except Exception as e:
            logger.error(f"ALBUM_ARTIST_FIX: Error fetching album details for album {album_id}: {e}")
            return {}

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize a filename by removing or replacing invalid characters."""
        # Replace slashes and backslashes with a hyphen or underscore
        filename = re.sub(r'[\\/]', '-', filename)
        # Remove characters that are problematic in Windows filenames
        filename = re.sub(r'[:*?"<>|]', '', filename)
        # Remove leading/trailing whitespace
        filename = filename.strip()
        # Reduce multiple spaces to a single space
        filename = re.sub(r'\s+', ' ', filename)
        # Ensure the filename isn't empty after sanitization
        if not filename:
            filename = "untitled"
        return filename

    def _queue_individual_track_download(self, track_id: int, item_type: str = 'track', album_id: Optional[int] = None, playlist_title: Optional[str] = None, track_details: Optional[dict] = None, playlist_id: Optional[int] = None, album_total_tracks: Optional[int] = None, playlist_total_tracks: Optional[int] = None):
        track_id_str = str(track_id)
        
        # Check if we recently cleared the queue to prevent immediate re-queuing
        if hasattr(self, '_recently_cleared') and self._recently_cleared:
            logger.warning(f"[QUEUE] Ignoring download request for track {track_id_str} - queue was recently cleared")
            return
        
        logger.info(f"[QUEUE] Queueing track {track_id_str} for download. Type: {item_type}")
        
        # Check if we have a valid API connection
        if not self.deezer_api:
            logger.error(f"[QUEUE] Cannot queue track {track_id_str} - DeezerAPI not available")
            return
            
        if track_id_str in self.active_workers:
            logger.warning(f"[QUEUE] Download worker for track {track_id_str} already exists. Skipping queue.")
            return
        worker = DownloadWorker(self, track_id, item_type, album_id=album_id, playlist_title=playlist_title, track_info=track_details, playlist_id=playlist_id, album_total_tracks=album_total_tracks, playlist_total_tracks=playlist_total_tracks)
        self.active_workers[track_id_str] = worker
        logger.info(f"[QUEUE_DEBUG] Added worker for track {track_id_str} to active_workers. Total active: {len(self.active_workers)}")
        
        # Defer queue state saving to reduce I/O overhead during bulk operations
        # Only save immediately if this is a single download, otherwise batch save
        if len(self.active_workers) <= 5:  # Save immediately for small queues
            try:
                self._save_queue_state()
                logger.debug(f"[QUEUE_DEBUG] Saved queue state after adding track {track_id_str}")
            except Exception as e:
                logger.error(f"[QUEUE_DEBUG] Failed to save queue state after adding track {track_id_str}: {e}")
        else:
            # For large queues, save less frequently to improve performance
            logger.debug(f"[QUEUE_DEBUG] Deferred queue state save for track {track_id_str} (large queue optimization)")
        
        self.thread_pool.start(worker)
        logger.info(f"[QUEUE_DEBUG] Started worker thread for track {track_id_str}")

    def download_track(self, track_id: int):
        """Queue a single track for download (typically a standalone track)."""
        # Pre-fetch track details to get album ID for album artist detection
        asyncio.create_task(self._pre_fetch_track_album_details(track_id))
        self._queue_individual_track_download(track_id, item_type='track')
    
    async def _pre_fetch_track_album_details(self, track_id: int):
        """Pre-fetch album details for a track to enable proper album artist detection."""
        try:
            logger.debug(f"ALBUM_ARTIST_FIX: Pre-fetching track details for track {track_id} to get album info")
            track_details = await self.deezer_api.get_track_details(track_id)
            
            if track_details and track_details.get('album', {}).get('id'):
                album_id = track_details.get('album', {}).get('id')
                if album_id not in self._album_cache:
                    logger.debug(f"ALBUM_ARTIST_FIX: Pre-fetching album details for album {album_id}")
                    await self._get_cached_album_details(album_id)
                else:
                    logger.debug(f"ALBUM_ARTIST_FIX: Album {album_id} already cached")
            else:
                logger.debug(f"ALBUM_ARTIST_FIX: Track {track_id} has no album ID or invalid track details")
                
        except Exception as e:
            logger.warning(f"ALBUM_ARTIST_FIX: Error pre-fetching album details for track {track_id}: {e}")

    async def download_album(self, album_id: int, track_ids: List[int]):
        """Initiates download for all tracks in an album."""
        logger.info(f"Attempting to download album ID: {album_id} with {len(track_ids)} tracks.")
        album_details = await self.deezer_api.get_album_details(album_id)
        if not album_details or 'tracks' not in album_details or 'data' not in album_details['tracks']:
            logger.error(f"Could not fetch details or track list for album {album_id}.")
            return

        # Cache album details for album artist detection BEFORE starting any downloads
        self._album_cache[album_id] = album_details
        logger.debug(f"ALBUM_ARTIST_FIX: Cached album details for album {album_id}: '{album_details.get('title')}' by '{album_details.get('artist', {}).get('name', 'Unknown')}'")

        # Check if this is a compilation album and log it
        if album_details.get('tracks', {}).get('data'):
            tracks = album_details.get('tracks', {}).get('data', [])
            track_artists = set()
            for track in tracks:
                artist_name = track.get('artist', {}).get('name')
                if artist_name:
                    track_artists.add(artist_name)
            
            is_compilation = len(track_artists) > 1
            logger.info(f"COMPILATION_ALBUM: Album '{album_details.get('title')}' has {len(track_artists)} different artists - Compilation: {is_compilation}")
            if is_compilation:
                logger.info(f"COMPILATION_ALBUM: All tracks will use 'Various Artists' folder and compilation filename template")

        actual_album_tracks = album_details['tracks']['data']
        album_title = album_details.get('title', f"Album {album_id}")
        artist_name = album_details.get('artist', {}).get('name', 'Unknown Artist')
        album_cover_url = album_details.get('cover_medium')
        logger.debug(f"Album {album_id} - Fetched {len(actual_album_tracks)} tracks from API. Passed {len(track_ids)} track IDs.")

        ids_to_download = track_ids if track_ids else [t['id'] for t in actual_album_tracks if t.get('id')]

        if not ids_to_download:
            logger.warning(f"No track IDs to download for album {album_id}.")
            return

        total_album_tracks = len(ids_to_download)
        
        self.signals.group_download_enqueued.emit({
            'group_id': str(album_id),
            'group_title': album_title,
            'artist_name': artist_name,
            'item_type': 'album',
            'total_tracks': total_album_tracks,
            'cover_url': album_cover_url 
        })
        logger.info(f"Emitted group_download_enqueued for album {album_id} - '{album_title}' by '{artist_name}'")

        logger.info(f"Starting download of {total_album_tracks} tracks for album ID: {album_id}")
        for track_id in ids_to_download:
            track_detail_for_worker = next((t for t in actual_album_tracks if t.get('id') == track_id), None)
            if track_detail_for_worker:
                logger.debug(f"Queueing track {track_id} from album {album_id} with details: {track_detail_for_worker.get('title')}")
                # Debug: Check what track number fields are available in album track listing
                track_fields = {k: v for k, v in track_detail_for_worker.items() if 'track' in k.lower() or 'position' in k.lower() or 'number' in k.lower()}
                logger.info(f"ALBUM_TRACK_FIELDS: Track {track_id} from album listing has fields: {track_fields}")
            else:
                logger.warning(f"Could not find details for track_id {track_id} in fetched album_details. Will rely on worker to fetch.")
            
            self._queue_individual_track_download(track_id, item_type='album_track', album_id=album_id, track_details=track_detail_for_worker, album_total_tracks=total_album_tracks)

    async def download_playlist(self, playlist_id: int, playlist_title: str, track_ids: List[int]):
        """Initiates download for all tracks in a playlist."""
        logger.info(f"Attempting to download playlist ID: {playlist_id} ('{playlist_title}') with {len(track_ids) if track_ids else 'all'} tracks.")
        
        # Fetch the list of tracks for the playlist.
        # Based on logs, self.deezer_api.get_playlist_tracks(playlist_id) appears to return the list of tracks directly.
        actual_playlist_tracks = await self.deezer_api.get_playlist_tracks(playlist_id)
        
        # Playlist cover URL is not available from get_playlist_tracks directly.
        # A separate API call or modification to get_playlist_tracks would be needed for this.
        # For now, setting to None to allow downloads to proceed.
        playlist_cover_url = None

        # Check if tracks were fetched successfully (actual_playlist_tracks should be a list or None)
        if not actual_playlist_tracks: # This means the list is empty or None
            logger.error(f"Could not fetch track list for playlist {playlist_id} ('{playlist_title}'), or playlist is empty.")
            return

        # actual_playlist_tracks is already the list of track data.
        # The playlist_title is passed as an argument and should be used.

        logger.debug(f"Playlist {playlist_id} ('{playlist_title}') - Fetched {len(actual_playlist_tracks)} tracks from API. Explicit track_ids provided: {len(track_ids) if track_ids else 'None (download all)'}.")

        ids_to_download = track_ids if track_ids else [t['id'] for t in actual_playlist_tracks if t.get('id')]

        if not ids_to_download:
            logger.warning(f"No track IDs to download for playlist {playlist_id}.")
            return

        total_playlist_tracks = len(ids_to_download)

        # Emit signal that a new playlist download is starting
        self.signals.group_download_enqueued.emit({
            'group_id': str(playlist_id),
            'group_title': playlist_title, # Use the passed title
            'item_type': 'playlist',
            'total_tracks': total_playlist_tracks,
            'cover_url': playlist_cover_url 
        })
        logger.info(f"Emitted group_download_enqueued for playlist {playlist_id} - '{playlist_title}'")

        logger.info(f"Starting download of {total_playlist_tracks} tracks for playlist ID: {playlist_id} ('{playlist_title}')")
        for playlist_position, track_id in enumerate(ids_to_download, start=1):
            track_detail_for_worker = next((t for t in actual_playlist_tracks if t.get('id') == track_id), None)
            if track_detail_for_worker:
                logger.debug(f"Queueing track {track_id} from playlist {playlist_id} with details: {track_detail_for_worker.get('title')}")
                # Add playlist_position to track details for proper numbering
                track_detail_for_worker = track_detail_for_worker.copy()  # Don't modify original
                track_detail_for_worker['playlist_position'] = playlist_position
            else:
                logger.warning(f"Could not find details for track_id {track_id} in fetched playlist_details. Will rely on worker to fetch.")
                # Create minimal track details with playlist position
                track_detail_for_worker = {'id': track_id, 'playlist_position': playlist_position}

            self._queue_individual_track_download(track_id, item_type='playlist_track', playlist_id=playlist_id, playlist_title=playlist_title, track_details=track_detail_for_worker, playlist_total_tracks=total_playlist_tracks)

    def _load_queue_state(self):
        queue_state_path = self._get_queue_state_path()
        logger.debug(f"Attempting to load queue state from: {queue_state_path}")
        if not queue_state_path.exists():
            logger.debug("No previous queue state file found")
            return None
        try:
            with open(queue_state_path, 'r', encoding='utf-8') as f:
                state = json.load(f)
            logger.info(f"Loaded queue state from: {queue_state_path}")
            return state
        except Exception as e:
            logger.error(f"Error loading queue state from {queue_state_path}: {e}")
            return None

    def _get_queue_state_path(self):
        # Always use %APPDATA%/DeeMusic on Windows
        import sys
        from pathlib import Path
        import os
        app_name = "DeeMusic"
        if sys.platform == "win32":
            appdata = os.getenv('APPDATA')
            if appdata:
                path = Path(appdata) / app_name / 'download_queue_state.json'
            else:
                path = Path.home() / app_name / 'download_queue_state.json'
            logger.debug(f"Queue state path determined: {path}")
            logger.debug(f"Parent directory exists: {path.parent.exists()}")
            logger.debug(f"File exists: {path.exists()}")
            return path
        elif sys.platform == "darwin":
            path = Path.home() / "Library" / "Application Support" / app_name / 'download_queue_state.json'
            logger.debug(f"Queue state path determined: {path}")
            return path
        else:
            xdg_config_home = os.getenv('XDG_CONFIG_HOME')
            if xdg_config_home:
                path = Path(xdg_config_home) / app_name / 'download_queue_state.json'
            else:
                path = Path.home() / ".config" / app_name / 'download_queue_state.json'
            logger.debug(f"Queue state path determined: {path}")
            return path

    def _is_valid_queue_entry(self, entry):
        """Check if a queue entry is valid and should be saved/restored."""
        if not isinstance(entry, dict):
            return False
        
        # Check for invalid album_id
        album_id = entry.get('album_id')
        if not album_id or album_id == 'unknown' or album_id == '':
            logger.debug(f"[QUEUE_DEBUG] Invalid album_id: {album_id}")
            return False
        
        # Check for invalid tracks
        queued_tracks = entry.get('queued_tracks', [])
        if not queued_tracks:
            logger.debug(f"[QUEUE_DEBUG] No queued tracks in entry")
            return False
        
        # Filter out tracks with invalid IDs
        valid_tracks = []
        for track in queued_tracks:
            track_id = track.get('track_id')
            if track_id and track_id != 'unknown' and track_id != '' and str(track_id).isdigit():
                valid_tracks.append(track)
            else:
                logger.debug(f"[QUEUE_DEBUG] Invalid track_id: {track_id}")
        
        # Update the entry with only valid tracks
        entry['queued_tracks'] = valid_tracks
        
        # Entry is valid if it has at least one valid track
        return len(valid_tracks) > 0

    def _are_album_tracks_completed(self, album_entry):
        """Check if all tracks in an album are completed by checking internal completion tracking."""
        try:
            queued_tracks = album_entry.get('queued_tracks', [])
            if not queued_tracks:
                return True  # No tracks means nothing to complete
            
            album_id = album_entry.get('album_id')
            album_title = album_entry.get('album_title', 'Unknown Album')
            artist_name = album_entry.get('artist_name', 'Unknown Artist')
            
            # First check: Use internal completion tracking (more reliable)
            completed_count = 0
            total_tracks = len(queued_tracks)
            
            logger.debug(f"[QUEUE_DEBUG] Checking completion for album '{artist_name} - {album_title}' ({total_tracks} tracks)")
            
            for track in queued_tracks:
                track_id = track.get('track_id')
                track_title = track.get('title', 'Unknown Title')
                
                if not track_id or track_id == 'unknown':
                    logger.debug(f"[QUEUE_DEBUG] Skipping track with invalid ID: {track_id}")
                    continue
                
                # Check if this track is in our completed downloads tracking
                if hasattr(self, 'completed_track_ids') and track_id in self.completed_track_ids:
                    completed_count += 1
                    logger.debug(f"[QUEUE_DEBUG] Track '{track_title}' found in completed tracking")
                    continue
                
                # Fallback: Check if track is in active workers and completed
                track_id_str = str(track_id)
                if track_id_str in self.active_workers:
                    worker = self.active_workers[track_id_str]
                    if hasattr(worker, 'status') and worker.status == DownloadStatus.COMPLETED:
                        completed_count += 1
                        logger.debug(f"[QUEUE_DEBUG] Track '{track_title}' found completed in active workers")
                        continue
                
                # Last resort: File existence check (but don't rely on it for moved files)
                try:
                    track_title = track.get('title', 'Unknown Title')
                    artist_name = album_entry.get('artist_name', 'Unknown Artist')
                    
                    # Simple file existence check based on common patterns
                    base_download_dir = Path(self.download_dir)
                    
                    # Try common file patterns
                    possible_paths = []
                    
                    # Pattern 1: Artist/Album/Track.mp3
                    artist_folder = base_download_dir / artist_name / album_title
                    if artist_folder.exists():
                        for file_path in artist_folder.glob("*.mp3"):
                            if track_title.lower() in file_path.name.lower() or track_id in file_path.name:
                                possible_paths.append(file_path)
                    
                    # Pattern 2: Album/Track.mp3 (no artist folder)
                    album_folder = base_download_dir / album_title
                    if album_folder.exists():
                        for file_path in album_folder.glob("*.mp3"):
                            if track_title.lower() in file_path.name.lower() or track_id in file_path.name:
                                possible_paths.append(file_path)
                    
                    # Check if any matching file exists
                    file_found = False
                    for path in possible_paths:
                        if path.exists():
                            completed_count += 1
                            file_found = True
                            # Reduced logging
                            break
                    
                    if not file_found:
                        # Reduced logging
                        pass
                        
                except Exception as e:
                    logger.debug(f"[QUEUE_DEBUG] Error checking track {track_id} file existence: {e}")
            
            is_completed = completed_count == total_tracks and total_tracks > 0
            # Only log completion check for debugging when needed
            if not is_completed and completed_count > 0:
                logger.info(f"[QUEUE] Album '{album_title}' partially complete: {completed_count}/{total_tracks} tracks")
            
            return is_completed
            
        except Exception as e:
            logger.error(f"[QUEUE_DEBUG] Error checking album tracks completion: {e}")
            return False  # Assume not completed on error

    def _save_queue_state(self):
        """Save the current state of the download queue, including unfinished, completed, and failed downloads."""
        # First, load existing unfinished downloads to preserve albums not yet started
        queue_state_path = self._get_queue_state_path()
        existing_unfinished = []
        if queue_state_path.exists():
            try:
                with open(queue_state_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    existing_unfinished = data.get('unfinished_downloads', [])
            except Exception as e:
                logger.warning(f"Could not read existing queue state: {e}")
        
        # Group currently active downloads by album/artist
        active_albums = {}
        for worker in self.active_workers.values():
            # Only include tracks that are not yet completed or failed
            track_info = worker.track_info_initial or {}
            album_id = str(track_info.get('album', {}).get('id', 'unknown'))
            album_title = track_info.get('album', {}).get('title', 'Unknown Album')
            artist_name = track_info.get('artist', {}).get('name', 'Unknown Artist')
            if album_id not in active_albums:
                active_albums[album_id] = {
                    'album_id': album_id,
                    'album_title': album_title,
                    'artist_name': artist_name,
                    'type': 'album',
                    'queued_tracks': []
                }
            active_albums[album_id]['queued_tracks'].append({
                'track_id': str(track_info.get('id', 'unknown')),
                'title': track_info.get('title', 'Unknown Title')
            })
        
        # Combine existing unfinished downloads with currently active ones
        # Keep albums that haven't started downloading yet, update albums that are currently active
        unfinished_downloads = []
        active_album_ids = set(active_albums.keys())
        
        # Add albums that haven't started downloading yet (with filtering and completion check)
        for existing_album in existing_unfinished:
            existing_album_id = str(existing_album.get('album_id', 'unknown'))
            if existing_album_id not in active_album_ids:
                # Filter out invalid entries that cause infinite loops
                if self._is_valid_queue_entry(existing_album):
                    # Check if all tracks in this album are actually completed (files exist)
                    if self._are_album_tracks_completed(existing_album):
                        logger.info(f"[QUEUE_DEBUG] Album '{existing_album.get('album_title', 'Unknown')}' tracks are completed, removing from unfinished downloads")
                    else:
                        unfinished_downloads.append(existing_album)
                else:
                    logger.warning(f"[QUEUE_DEBUG] Filtering out invalid queue entry: {existing_album}")
        
        # Add currently active albums (with filtering)
        for active_album in active_albums.values():
            if self._is_valid_queue_entry(active_album):
                unfinished_downloads.append(active_album)
            else:
                logger.warning(f"[QUEUE_DEBUG] Filtering out invalid active album: {active_album}")
        # Don't persist completed downloads by default - they should only be kept temporarily
        # This prevents completed downloads from being restored after app restart
        completed_downloads = []
        failed_downloads = []
        
        # Only preserve completed/failed downloads if explicitly requested (not during normal save operations)
        # This prevents the issue where completed downloads keep coming back
        # Write the new state
        try:
            queue_state_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"[QUEUE_DEBUG] Saving queue state to: {queue_state_path}")
            logger.info(f"[QUEUE_DEBUG] Current active workers: {len(self.active_workers)} - {list(self.active_workers.keys())}")
            logger.info(f"[QUEUE_DEBUG] Unfinished downloads to save: {len(unfinished_downloads)}")
            logger.info(f"[QUEUE_DEBUG] Completed downloads: {len(completed_downloads)}")
            logger.info(f"[QUEUE_DEBUG] Failed downloads: {len(failed_downloads)}")
            logger.info(f"[QUEUE_DEBUG] Completed track IDs: {len(self.completed_track_ids)}")
            logger.info(f"[QUEUE_DEBUG] Completed albums: {len(self.completed_albums)}")
            
            if unfinished_downloads:
                logger.info(f"[QUEUE_DEBUG] Unfinished download details: {unfinished_downloads}")
            
            with open(queue_state_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'unfinished_downloads': unfinished_downloads,
                    'completed_downloads': completed_downloads,
                    'failed_downloads': failed_downloads,
                    'completed_track_ids': list(self.completed_track_ids),
                    'completed_albums': list(self.completed_albums)
                }, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[QUEUE_DEBUG] Successfully saved queue state to: {queue_state_path}")
        except Exception as e:
            logger.error(f"[QUEUE_DEBUG] Failed to save queue state to {queue_state_path}: {e}")
            logger.error(f"[QUEUE_DEBUG] Error details: {type(e).__name__}: {str(e)}")
            # Try to create a minimal backup
            try:
                backup_path = queue_state_path.with_suffix('.json.backup')
                with open(backup_path, 'w', encoding='utf-8') as f:
                    json.dump({
                        'unfinished_downloads': unfinished_downloads,
                        'completed_downloads': [],
                        'failed_downloads': [],
                        'completed_track_ids': list(self.completed_track_ids),
                        'completed_albums': list(self.completed_albums)
                    }, f, indent=2, ensure_ascii=False)
                logger.info(f"[QUEUE_DEBUG] Created backup queue state at: {backup_path}")
            except Exception as backup_error:
                logger.error(f"[QUEUE_DEBUG] Failed to create backup queue state: {backup_error}")

    def clear_completed_downloads(self):
        """Clear completed downloads from the persistent queue state."""
        try:
            # Set flag to prevent processing completion signals during clear
            self._clearing_queue = True
            logger.info("[QUEUE_DEBUG] Set clearing queue flag for clear completed downloads")
            
            queue_state_path = self._get_queue_state_path()
            
            if not queue_state_path.exists():
                logger.info("[QUEUE_DEBUG] No queue state file exists, nothing to clear")
                return
            
            # Temporarily disable file watcher to prevent reload during clear operation
            file_watcher_was_active = False
            if hasattr(self, 'queue_file_watcher'):
                try:
                    # Remove the file from watcher temporarily
                    watched_files = self.queue_file_watcher.files()
                    if str(queue_state_path) in watched_files:
                        self.queue_file_watcher.removePath(str(queue_state_path))
                        file_watcher_was_active = True
                        logger.debug("[QUEUE_DEBUG] Temporarily disabled file watcher for clear operation")
                except Exception as e:
                    logger.warning(f"[QUEUE_DEBUG] Could not disable file watcher: {e}")
            
            # Read current state
            with open(queue_state_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Clear completed downloads but keep unfinished and failed
            original_completed_count = len(data.get('completed_downloads', []))
            data['completed_downloads'] = []
            
            # Also clear the completed tracking to allow re-downloading if needed
            original_track_count = len(data.get('completed_track_ids', []))
            original_album_count = len(data.get('completed_albums', []))
            data['completed_track_ids'] = []
            data['completed_albums'] = []
            
            # Clear in-memory tracking as well
            self.completed_track_ids.clear()
            self.completed_albums.clear()
            
            logger.info(f"[QUEUE_DEBUG] Cleared {original_track_count} completed track IDs and {original_album_count} completed albums from tracking")
            
            # Write back the updated state
            with open(queue_state_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[QUEUE_DEBUG] Cleared {original_completed_count} completed downloads from queue state")
            
            # Re-enable file watcher
            if file_watcher_was_active and hasattr(self, 'queue_file_watcher'):
                try:
                    self.queue_file_watcher.addPath(str(queue_state_path))
                    logger.debug("[QUEUE_DEBUG] Re-enabled file watcher after clear operation")
                except Exception as e:
                    logger.warning(f"[QUEUE_DEBUG] Could not re-enable file watcher: {e}")
            
        except Exception as e:
            logger.error(f"[QUEUE_DEBUG] Failed to clear completed downloads: {e}")
        finally:
            # Always reset the clearing flag
            self._clearing_queue = False
            logger.info("[QUEUE_DEBUG] Cleared clearing queue flag after clear completed downloads")

    def _save_queue_state_with_completed(self, completed_items=None, failed_items=None):
        """Save queue state including completed/failed items (for UI purposes only)."""
        # This method is used when we want to temporarily track completed downloads for UI
        # but they won't be restored on app restart
        try:
            queue_state_path = self._get_queue_state_path()
            
            # Get current unfinished downloads
            existing_unfinished = []
            if queue_state_path.exists():
                try:
                    with open(queue_state_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        existing_unfinished = data.get('unfinished_downloads', [])
                except Exception as e:
                    logger.warning(f"Could not read existing queue state: {e}")
            
            # Group currently active downloads
            active_albums = {}
            for worker in self.active_workers.values():
                track_info = worker.track_info_initial or {}
                album_id = str(track_info.get('album', {}).get('id', 'unknown'))
                album_title = track_info.get('album', {}).get('title', 'Unknown Album')
                artist_name = track_info.get('artist', {}).get('name', 'Unknown Artist')
                if album_id not in active_albums:
                    active_albums[album_id] = {
                        'album_id': album_id,
                        'album_title': album_title,
                        'artist_name': artist_name,
                        'type': 'album',
                        'queued_tracks': []
                    }
                active_albums[album_id]['queued_tracks'].append({
                    'track_id': str(track_info.get('id', 'unknown')),
                    'title': track_info.get('title', 'Unknown Title')
                })
            
            # Combine unfinished downloads
            unfinished_downloads = []
            active_album_ids = set(active_albums.keys())
            
            for existing_album in existing_unfinished:
                existing_album_id = str(existing_album.get('album_id', 'unknown'))
                if existing_album_id not in active_album_ids:
                    unfinished_downloads.append(existing_album)
            
            unfinished_downloads.extend(list(active_albums.values()))
            
            # Use provided completed/failed items or empty lists
            completed_downloads = completed_items or []
            failed_downloads = failed_items or []
            
            # Write the state
            queue_state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(queue_state_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'unfinished_downloads': unfinished_downloads,
                    'completed_downloads': completed_downloads,
                    'failed_downloads': failed_downloads,
                    'completed_track_ids': list(self.completed_track_ids),
                    'completed_albums': list(self.completed_albums)
                }, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"[QUEUE_DEBUG] Saved queue state with {len(completed_downloads)} completed items")
            
        except Exception as e:
            logger.error(f"[QUEUE_DEBUG] Failed to save queue state with completed items: {e}")

    def clean_invalid_queue_entries(self):
        """Clean up invalid entries from the queue state file."""
        try:
            queue_state_path = self._get_queue_state_path()
            
            if not queue_state_path.exists():
                logger.info("[QUEUE_DEBUG] No queue state file to clean")
                return
            
            # Read current state
            with open(queue_state_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Clean unfinished downloads
            original_unfinished = data.get('unfinished_downloads', [])
            cleaned_unfinished = []
            
            for entry in original_unfinished:
                if self._is_valid_queue_entry(entry):
                    cleaned_unfinished.append(entry)
                else:
                    logger.info(f"[QUEUE_DEBUG] Removing invalid queue entry: {entry.get('album_title', 'Unknown')} - {entry.get('album_id', 'Unknown ID')}")
            
            # Update data
            data['unfinished_downloads'] = cleaned_unfinished
            
            # Write back cleaned data
            with open(queue_state_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            removed_count = len(original_unfinished) - len(cleaned_unfinished)
            logger.info(f"[QUEUE_DEBUG] Cleaned queue state: removed {removed_count} invalid entries, kept {len(cleaned_unfinished)} valid entries")
            
        except Exception as e:
            logger.error(f"[QUEUE_DEBUG] Failed to clean invalid queue entries: {e}")

    def clear_all_queue_state(self):
        """Clear all queue state including unfinished, completed, and failed downloads."""
        try:
            # Set flag to prevent processing completion signals during clear
            self._clearing_queue = True
            logger.info("[QUEUE_DEBUG] Set clearing queue flag - completion signals will be ignored")
            
            queue_state_path = self._get_queue_state_path()
            
            # Temporarily disable file watcher to prevent reload during clear operation
            file_watcher_was_active = False
            if hasattr(self, 'queue_file_watcher'):
                try:
                    watched_files = self.queue_file_watcher.files()
                    if str(queue_state_path) in watched_files:
                        self.queue_file_watcher.removePath(str(queue_state_path))
                        file_watcher_was_active = True
                        logger.debug("[QUEUE_DEBUG] Temporarily disabled file watcher for clear all operation")
                except Exception as e:
                    logger.warning(f"[QUEUE_DEBUG] Could not disable file watcher: {e}")
            
            # Stop the reload timer if it's running
            if hasattr(self, 'queue_reload_timer'):
                self.queue_reload_timer.stop()
            
            # Clear the queue state file completely
            if queue_state_path.exists():
                queue_state_path.unlink()
                logger.info(f"[QUEUE_DEBUG] Deleted queue state file: {queue_state_path}")
            else:
                logger.info("[QUEUE_DEBUG] Queue state file doesn't exist, nothing to delete")
            
            # Stop all active workers first
            workers_to_stop = list(self.active_workers.items())
            for worker_id, worker in workers_to_stop:
                try:
                    worker.stop()
                    logger.info(f"[QUEUE] Stopped worker: {worker_id}")
                except Exception as e:
                    logger.warning(f"[QUEUE] Error stopping worker {worker_id}: {e}")
            
            # Wait briefly for workers to acknowledge stop
            if workers_to_stop:
                import time
                time.sleep(0.2)  # Give workers time to stop
            
            # Clear in-memory state
            self.active_workers.clear()
            if hasattr(self, 'downloads'):
                self.downloads.clear()
            
            # Clear completed tracking
            self.completed_track_ids.clear()
            self.completed_albums.clear()
            
            # Clear any pending queue saves
            self._pending_queue_save = False
            
            # Add a brief delay flag to prevent immediate re-queuing
            self._recently_cleared = True
            
            logger.info("[QUEUE] Cleared all in-memory state and tracking data")
            
            # Force clear thread pool to ensure no lingering tasks
            try:
                self.thread_pool.clear()
                logger.info("[QUEUE] Cleared thread pool")
            except Exception as e:
                logger.warning(f"[QUEUE] Could not clear thread pool: {e}")
            
            # Create a fresh empty queue state file to ensure UI refreshes properly
            empty_state = {
                'unfinished_downloads': [],
                'completed_downloads': [],
                'failed_downloads': [],
                'completed_track_ids': [],
                'completed_albums': []
            }
            
            try:
                queue_state_path.parent.mkdir(parents=True, exist_ok=True)
                with open(queue_state_path, 'w', encoding='utf-8') as f:
                    json.dump(empty_state, f, indent=2)
                logger.info(f"[QUEUE_DEBUG] Created fresh empty queue state file")
            except Exception as e:
                logger.warning(f"[QUEUE_DEBUG] Could not create empty queue state file: {e}")
            
            logger.info("[QUEUE] All queue state cleared successfully")
            
            # Note: We don't re-enable the file watcher here because the file was deleted
            # It will be re-enabled when new downloads are added and the file is recreated
            
        except Exception as e:
            logger.error(f"[QUEUE_DEBUG] Failed to clear all queue state: {e}", exc_info=True)
        finally:
            # Always reset the clearing flag
            self._clearing_queue = False
            
            # Reset the recently cleared flag after a short delay
            def reset_recently_cleared():
                import time
                time.sleep(0.1)  # Wait 0.1 seconds
                if hasattr(self, '_recently_cleared'):
                    self._recently_cleared = False
                    logger.info("[QUEUE] Reset recently cleared flag - new downloads can be queued")
            
            import threading
            threading.Thread(target=reset_recently_cleared, daemon=True).start()
            
            logger.info("[QUEUE] Cleared clearing queue flag - completion signals will be processed normally")

    def clear_pending_downloads(self):
        """Clear only stuck pending downloads from previous sessions."""
        try:
            queue_state_path = self._get_queue_state_path()
            
            if not queue_state_path.exists():
                logger.info("[QUEUE_DEBUG] No queue state file exists, nothing to clear")
                return
            
            # Load current queue state
            with open(queue_state_path, 'r', encoding='utf-8') as f:
                queue_state = json.load(f)
            
            # Clear only unfinished downloads, preserve completed/failed for now
            original_count = len(queue_state.get('unfinished_downloads', []))
            queue_state['unfinished_downloads'] = []
            
            # Save the updated state
            with open(queue_state_path, 'w', encoding='utf-8') as f:
                json.dump(queue_state, f, indent=2)
            
            logger.info(f"[QUEUE_DEBUG] Cleared {original_count} pending downloads from queue state")
            
        except Exception as e:
            logger.error(f"[QUEUE_DEBUG] Error clearing pending downloads: {e}")

# Example usage (if run directly, for testing)
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    
    # Dummy config for testing
    class DummyConfig:
        def get_setting(self, key, default=None):
            settings = {
                'deezer.arl': 'YOUR_ARL_TOKEN_HERE', # Replace with a valid ARL for testing
                'downloads.path': './test_downloads',
                'downloads.quality': 'MP3_320',
                'downloads.concurrent_downloads': 1
            }
            return settings.get(key, default)
    
    config_manager = DummyConfig()
    
    # Dummy DeezerAPI
    class DummyDeezerAPI:
        pass # No methods needed for this basic test
        
    deezer_api = DummyDeezerAPI()

    download_manager = DownloadManager(config_manager, deezer_api) # type: ignore

    # Test queueing a download (requires a running Qt event loop to see signals)
    print("Testing track download queuing...")
    download_manager.download_track(62724015) # Example track ID
    
    print("Testing album download queuing...")
    # This is an async function and should be awaited in an async context
    # For a simple script test, we can use asyncio.run()
    # asyncio.run(download_manager.download_album(302127, [62724015])) # Example album ID (Thriller) with track

    print("Downloads queued. Check logs. Need event loop (e.g., QApplication) to run workers.")
    
    # Keep alive briefly for threads to potentially start (in a real app, the event loop handles this)
    # time.sleep(10) 
    # In a real Qt app, QApplication().exec() would run
    
    # Example of how to run with a minimal Qt app for testing signals:
    import sys
    from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QLabel, QProgressBar, QWidget  # type: ignore
    
    class TestWindow(QMainWindow):
        def __init__(self, manager):
            super().__init__()
            self.manager = manager
            self.widgets = {}
            
            self.setWindowTitle("Download Test")
            central_widget = QWidget()
            self.layout = QVBoxLayout(central_widget)
            self.setCentralWidget(central_widget)

            # Add items to download
            self.manager.download_track(62724015) # Locked out of heaven
            self.manager.download_album(302127, [62724015]) # Example album ID (Thriller) with track

        def _ensure_widget(self, item_id, item_type):
            key = f"{item_type}_{item_id}"
            if key not in self.widgets:
                widget = QWidget()
                item_layout = QVBoxLayout(widget)
                label = QLabel(f"{item_type.capitalize()} {item_id}: Waiting...")
                progress = QProgressBar()
                progress.setRange(0, 100)
                item_layout.addWidget(label)
                item_layout.addWidget(progress)
                self.layout.addWidget(widget)
                self.widgets[key] = {'widget': widget, 'label': label, 'progress': progress}
                 # Connect signals here, AFTER creating the worker in download_track/album
                # Find the worker? This is tricky. Better to connect from manager?
                # For simplicity, let's assume the worker was created and connect signals
                # This requires the DownloadWorker to be accessible or signals routed through manager
                # --> Modification needed: Manager should hold workers or route signals
            return self.widgets[key]

        # --- Slots to connect to worker signals ---
        # These should ideally be connected *before* the worker starts
        # Maybe DownloadManager should emit signals instead?

        def handle_started(self, item_id, item_type):
             widget_info = self._ensure_widget(item_id, item_type)
             widget_info['label'].setText(f"{item_type.capitalize()} {item_id}: Starting...")
             print(f"Signal: Started {item_type} {item_id}")

        def handle_progress(self, item_id, progress):
            # Find widget based on item_id (need item_type too?)
            # This highlights a flaw - need to know type or have unique ID mapping
            # Assuming track for now
            key = f"track_{item_id}" # HACK - How to get type?
            if key not in self.widgets: key = f"album_{item_id}" # Try album
            
            if key in self.widgets:
               widget_info = self.widgets[key]
               widget_info['label'].setText(f"{key}: Downloading {progress:.1f}%")
               widget_info['progress'].setValue(int(progress))
               # print(f"Signal: Progress {key} {progress:.1f}%") # Too verbose
            else:
                print(f"Warning: Received progress for unknown item {item_id}")


        def handle_finished(self, item_id, item_type, file_path):
             widget_info = self._ensure_widget(item_id, item_type)
             widget_info['label'].setText(f"{item_type.capitalize()} {item_id}: Finished ({os.path.basename(file_path)})")
             widget_info['progress'].setValue(100)
             print(f"Signal: Finished {item_type} {item_id} -> {file_path}")

        def handle_error(self, item_id, item_type, error_message):
             widget_info = self._ensure_widget(item_id, item_type)
             widget_info['label'].setText(f"{item_type.capitalize()} {item_id}: Error! {error_message}")
             widget_info['label'].setStyleSheet("color: red;")
             widget_info['progress'].setValue(0) # Or indicate error state visually
             print(f"Signal: Error {item_type} {item_id}: {error_message}")
             
    # --- Modification needed in DownloadManager ---
    # DownloadManager should probably store workers or manage signals
    # to allow connecting them in the TestWindow example.
    # For now, this example won't show live updates correctly without that wiring.

    # app = QApplication(sys.argv)
    # window = TestWindow(download_manager)
    # # Need to connect signals from *future* workers to window slots here
    # # This requires a different architecture (e.g., Manager emits signals)
    # window.show()
    # print("Starting Qt event loop for testing...")
    # sys.exit(app.exec())
    print("Refactoring complete. Placeholder logic added. Needs deezer-downloader API implementation.")
    # --- End Example --- 
