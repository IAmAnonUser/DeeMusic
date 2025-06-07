"""Service for managing music downloads."""

import os
import logging
import asyncio
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
from config_manager import ConfigManager 
from services.deezer_api import DeezerAPI # Assuming deezer_api.py is in the same 'services' package

# Add crypto imports
from Crypto.Hash import MD5
from Crypto.Cipher import Blowfish, AES
from binascii import a2b_hex, b2a_hex

# Add mutagen imports
from mutagen.mp3 import MP3, EasyMP3
from mutagen.id3 import ID3, APIC, TPE1, TIT2, TALB, TRCK, TPOS, TDRC, TCON, TCOM, TPE2, TPUB, TSRC, USLT, SYLT
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC, Picture

# Add lyrics utils import
from utils.lyrics_utils import LyricsProcessor

logger = logging.getLogger(__name__) # Initialize logger earlier

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
        logger.info(f"[DownloadWorker:{self.item_id_str}] Stop requested - DEBUGGING WHY DOWNLOADS ARE CANCELLED")
        import traceback
        logger.info(f"[DownloadWorker:{self.item_id_str}] Stop call stack: {traceback.format_stack()}")
        self._is_stopping = True

    def run(self):
        """Execute the download task."""
        logger.debug(f"[DownloadWorker:{self.item_id_str}] Worker running. Initial self.track_info_initial: {self.track_info_initial}")

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
            logger.info(f"[DownloadWorker:{self.item_id_str}] Attempting to fetch authoritative track details for {self.item_id}")
            
            if self.download_manager and self.download_manager.deezer_api:
                try:
                    authoritative_track_info = self.download_manager.deezer_api.get_track_details_sync_private(self.item_id)
                except Exception as api_exc:
                    logger.error(f"[DownloadWorker:{self.item_id_str}] Error calling get_track_details_sync_private: {api_exc}", exc_info=True)
                    authoritative_track_info = None # Ensure it's None on error
            else:
                logger.warning(f"[DownloadWorker:{self.item_id_str}] DownloadManager or DeezerAPI not available for fetching authoritative track_info. Will rely on initial track_info if provided.")
                authoritative_track_info = None # Explicitly None

            if self._is_stopping: return

            if authoritative_track_info and isinstance(authoritative_track_info, dict):
                logger.info(f"[DownloadWorker:{self.item_id_str}] Successfully fetched authoritative track_info. Processing for signal.")
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
                logger.debug(f"[DownloadWorker:{self.item_id_str}] Using details from API: Title='{item_title}', Artist='{artist_name}', Album='{album_title}'")
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
                    logger.debug(f"[DownloadWorker:{self.item_id_str}] Using details from initial_track_info: Title='{item_title}', Artist='{artist_name}', Album='{album_title}'")
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
            logger.debug(f"[DownloadWorker:{self.item_id_str}] Emitting download_started with data: {start_data}")
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
                logger.info(f"[DownloadWorker:{self.item_id_str}] Worker finalizing due to stop request.")
                return # Avoid emitting final signals if stopped
            # Level 1
            if self._download_succeeded and self._file_path:
                 # Level 2
                try:
                    if not self._is_stopping: self.download_manager.signals.download_finished.emit(self.item_id_str)
                except RuntimeError as e: logger.warning(f"[DownloadWorker:{self.item_id_str}] Could not emit download_finished: {e}")
            elif not self._error_signaled: 
                # Level 2
                error_msg = self._error_message or "Download failed"
                # Level 2 
                try:
                    if not self._is_stopping: self.download_manager.signals.download_failed.emit(self.item_id_str, error_msg)
                except RuntimeError as e: logger.warning(f"[DownloadWorker:{self.item_id_str}] Could not emit download_failed: {e}")
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
        if self._is_stopping: return None
        temp_file_path = None 
        decrypted_temp_path = None 
        encrypted_temp_path = None 
        
        try:
            # 1. Validate passed track_info
            if not track_info or not isinstance(track_info, dict): # Simplified initial check
                if self._is_stopping: return None
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
                if self._is_stopping: return None
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
            artist_template = templates_conf.get('artist', '%artist%')
            album_template = templates_conf.get('album', '%album%')
            cd_template = templates_conf.get('cd', 'CD %disc_number%') # Ensure this key matches your settings
            
            # Prepare placeholder values from track_info
            disc_number_val = track_info.get('disk_number', 1)
            track_number_val = str(track_info.get('track_position', track_info.get('track_number', 0))).zfill(2)
            artist_val = track_info.get('artist', {}).get('name', 'Unknown Artist')
            album_val = track_info.get('album', {}).get('title', track_info.get('alb_title', 'Unknown Album'))
            title_val = track_info.get('title', 'Unknown Title')
            year_val = str(track_info.get('release_date', '0000'))[:4]
            
            # Fixed: Use track artist as album artist unless it's a compilation album
            # Same logic as in metadata section for consistency
            album_artist_from_api = track_info.get('album', {}).get('artist', {}).get('name', artist_val)
            if album_artist_from_api and album_artist_from_api.lower() in ['various artists', 'various', 'compilation']:
                album_artist_val = album_artist_from_api  # Keep "Various Artists" for compilations
            else:
                album_artist_val = artist_val  # Use track artist as album artist for consistency
            
            track_num_str = str(track_info.get('track_number', track_info.get('track_position', 0))).zfill(2)
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
            logger.debug(f"METADATA DEBUG: Extracted artist='{artist_val}', album_artist='{album_artist_val}', title='{title_val}', album='{album_val}'")
            logger.debug(f"METADATA DEBUG: track_info artist structure: {track_info.get('artist')}")
            logger.debug(f"METADATA DEBUG: track_info album.artist structure: {track_info.get('album', {}).get('artist')}")
            logger.debug(f"METADATA DEBUG: album_artist_from_api='{album_artist_from_api}', using album_artist='{album_artist_val}'")
            
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
            except (ValueError, TypeError):
                track_num_int = 0 # Fallback if conversion fails
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
                logger.debug(f"PLAYLIST POSITION: Final track_num_int={track_num_int}, playlist_position={track_info.get('playlist_position')}")
            
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
                'playlist_name': self.playlist_title if self.playlist_title else '', # Add playlist_name
                'playlist': self.playlist_title if self.playlist_title else '', # Add playlist (for %playlist% templates)
                # Add other potential placeholders if needed, e.g., genre
                'genre': track_info.get('genres', {}).get('data', [{}])[0].get('name', 'Unknown Genre'),
                'isrc': track_info.get('isrc', '')
            }
            
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
            logger.info(f"Calculated final path (New Flag Logic): {final_file_path}")

            # --- Prepare Temporary File Paths ---
            unique_suffix = f"deemusic_{self.item_id}_{final_file_path.stem}"
            encrypted_temp_path = Path(tempfile.gettempdir()) / f"{unique_suffix}.encrypted.part"
            decrypted_temp_path = Path(tempfile.gettempdir()) / f"{unique_suffix}.decrypted.part"

            # Ensure final destination directory exists 
            try:
                 # Use the constructed directory path
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
                # Download to temporary encrypted file
                response = requests.get(download_url, stream=True, timeout=30)
                response.raise_for_status()
                
                with open(encrypted_temp_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if self._is_stopping: 
                            logger.info(f"[DownloadWorker:{self.item_id_str}] Download cancelled during streaming.")
                            return None
                        if chunk:
                            f.write(chunk)
                            
                logger.info(f"[DownloadWorker:{self.item_id_str}] Downloaded encrypted file to {encrypted_temp_path}")
                
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
                self._apply_metadata(str(decrypted_path), track_info)
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
                if self._is_stopping: return None
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
                # decrypted_path is now a Path object, not a temp path variable
                # The cleanup here is mainly for error cases since success path cleans up above
            except:
                pass

    def _apply_metadata(self, file_path: str, track_info: dict):
        logger.info(f"Applying metadata to {file_path}")
        try:
            audio = None
            is_mp3 = False
            try:
                audio = MP3(file_path, ID3=ID3)
                if audio.tags is None: audio.add_tags() 
                is_mp3 = True
            except Exception:
                 try: audio = FLAC(file_path); is_mp3 = False
                 except Exception as flac_err:
                     logger.error(f"Failed to load audio file {file_path}: {flac_err}")
                     return
            
            if audio is None:
                 logger.error(f"Audio object is None after loading attempt for {file_path}")
                 return

            # --- Map track_info to tags --- 
            # Use .get() with fallbacks to avoid KeyErrors
            title = track_info.get('title', 'Unknown Title')
            artist = track_info.get('artist', {}).get('name', 'Unknown Artist')
            # --- Check for alb_title first for metadata too --- 
            album = track_info.get('alb_title', track_info.get('album', {}).get('title', 'Unknown Album'))
            track_num_str = str(track_info.get('track_number', track_info.get('track_position', 0))).zfill(2)
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
            
            # Fixed: Use track artist as album artist unless it's a compilation album
            # Same logic as in filename section for consistency
            album_artist_from_api = track_info.get('album', {}).get('artist', {}).get('name', artist)
            if album_artist_from_api and album_artist_from_api.lower() in ['various artists', 'various', 'compilation']:
                album_artist = album_artist_from_api  # Keep "Various Artists" for compilations
            else:
                album_artist = artist  # Use track artist as album artist for consistency

            # --- Apply tags ---
            if is_mp3:
                # For MP3, work with the existing tags object or create if needed
                tags = audio.tags
                if tags is None: # Should have been added above, but double-check
                     tags = ID3()
                     audio.tags = tags
                
                # Clear specific frames before adding to avoid duplicates (safer than full delete)
                tags.delall("TIT2") # Title
                tags.delall("TPE1") # Artist
                tags.delall("TALB") # Album
                tags.delall("TRCK") # Track Number
                tags.delall("TPOS") # Disc Number
                tags.delall("TDRC") # Recording Date (Year)
                tags.delall("TPE2") # Album Artist
                tags.delall("TCON") # Genre
                tags.delall("TCOM") # Composer
                tags.delall("TPUB") # Publisher
                tags.delall("TSRC") # ISRC
                tags.delall("APIC") # Picture

                tags.add(TIT2(encoding=3, text=title))
                tags.add(TPE1(encoding=3, text=artist))
                tags.add(TALB(encoding=3, text=album))
                
                # Track number: only add total if known and > 0
                if total_tracks_str and int(total_tracks_str) > 0:
                    tags.add(TRCK(encoding=3, text=f"{track_num_str}/{total_tracks_str}"))
                else:
                    tags.add(TRCK(encoding=3, text=track_num_str))

                # Disc number: only add total if it's known and different from '1' (our hardcoded default)
                if total_discs_str and total_discs_str != "0" and total_discs_str != "1": # Crude check for now
                    tags.add(TPOS(encoding=3, text=f"{disc_num_str}/{total_discs_str}"))
                else:
                    tags.add(TPOS(encoding=3, text=disc_num_str))
                    
                if release_date and len(release_date) >= 4: # Ensure we have at least year
                     tags.add(TDRC(encoding=3, text=release_date[:4])) # Year only for TDRC
                tags.add(TPE2(encoding=3, text=album_artist))
                if genre: tags.add(TCON(encoding=3, text=genre))
                if composer: tags.add(TCOM(encoding=3, text=composer))
                if publisher: tags.add(TPUB(encoding=3, text=publisher))
                if isrc: tags.add(TSRC(encoding=3, text=isrc))
            else: # FLAC - Vorbis Comments
                # Clear existing comments first (optional but recommended)
                audio.delete() 
                tags = audio # Use the audio object directly for Vorbis comments

                tags['title'] = title
                tags['artist'] = artist
                tags['album'] = album
                tags['tracknumber'] = track_num_str
                # Only add tracktotal if known and > 0
                if total_tracks_str and int(total_tracks_str) > 0:
                    tags['tracktotal'] = total_tracks_str
                else:
                    if 'tracktotal' in tags: # Remove if it exists from a previous run or default
                        del tags['tracktotal']
                        
                tags['discnumber'] = disc_num_str
                # Only add disctotal if known and different from '1'
                if total_discs_str and total_discs_str != "0" and total_discs_str != "1":
                    tags['disctotal'] = total_discs_str
                else:
                    if 'disctotal' in tags: # Remove if it exists
                        del tags['disctotal']

                tags['date'] = release_date # YYYY-MM-DD
                tags['albumartist'] = album_artist
                if genre: tags['genre'] = genre
                if composer: tags['composer'] = composer
                if publisher: tags['organization'] = publisher # Or 'label'? Let's stick to ORGANIZATION
                if isrc: tags['isrc'] = isrc

            # --- Embed Cover Art --- 
            # Read relevant settings
            config = self.download_manager.config
            embed_artwork_enabled = config.get_setting('downloads.embed_artwork', True) # Default to True
            artwork_size = config.get_setting('downloads.embeddedArtworkSize', 1000) # Default to 1000
            logger.debug(f"Artwork settings: Embed={embed_artwork_enabled}, Size={artwork_size}")

            if embed_artwork_enabled:
                cover_url = None
                image_data = None # Define image_data here
                # Prefer public API structure first if available
                if 'album' in track_info and isinstance(track_info['album'], dict):
                     # Construct size-specific keys based on setting
                     size_str = f"{artwork_size}x{artwork_size}"
                     public_api_size_keys = {
                          1000: 'cover_xl',
                          500: 'cover_big', # Approximate, Deezer uses 500x500 for big
                          250: 'cover_medium', # Approximate, Deezer uses 250x250 for medium
                          # Add more sizes if needed and if Deezer provides corresponding keys
                     }
                     # Find the best available key <= desired size 
                     # (Simplistic: try exact size key first, fallback needed)
                     # TODO: Implement better fallback logic if exact size key doesn't exist
                     key_to_try = None
                     if artwork_size == 1000: key_to_try = 'cover_xl'
                     elif artwork_size >= 500: key_to_try = 'cover_big' # Fallback if 1000 unavailable or size < 1000
                     elif artwork_size >= 250: key_to_try = 'cover_medium'
                     # else: use default small? 
                     
                     if key_to_try and key_to_try in track_info['album']:
                          cover_url = track_info['album'].get(key_to_try)
                          logger.debug(f"Found public API cover URL using key '{key_to_try}': {cover_url}")
                     else:
                          logger.debug(f"Public API keys ('{key_to_try}') not found for desired size {artwork_size}, will try private API structure.")

                # Fallback for private API structure if public URL wasn't found or album structure is different
                if not cover_url and 'alb_picture' in track_info:
                     cover_md5 = track_info.get('alb_picture')
                     if cover_md5:
                          # Construct URL with desired size
                          size_str = f"{artwork_size}x{artwork_size}"
                          cover_url = f"https://e-cdns-images.dzcdn.net/images/cover/{cover_md5}/{size_str}-000000-80-0-0.jpg"
                          logger.debug(f"Constructed private API cover URL with size {artwork_size}: {cover_url}")
                     else:
                          logger.debug("Private API alb_picture key not found.")
                elif not cover_url:
                     logger.warning(f"Could not determine cover URL from either public or private API structures for track {track_info.get('id')}")
                     cover_url = None # Ensure it's None if logic fails

                if cover_url:
                     logger.debug(f"Attempting to fetch cover art from {cover_url}")
                     try:
                         cover_response = requests.get(cover_url, timeout=15)
                         cover_response.raise_for_status()
                         image_data = cover_response.content # Store fetched data
                         mime_type = cover_response.headers.get('Content-Type', 'image/jpeg') # Default to jpeg if not specified

                         if is_mp3:
                             audio.tags.add( # Add directly to the tags object
                                 APIC(
                                     encoding=3, # 3 is UTF-8
                                     mime=mime_type,
                                     type=3, # 3 means cover (front)
                                     desc='Cover',
                                     data=image_data
                                 )
                             )
                         else: # FLAC
                                 picture = Picture()
                                 picture.data = image_data
                                 picture.type = 3 # Cover (front)
                                 picture.mime = mime_type
                                 audio.add_picture(picture)
                             
                         logger.debug("Successfully prepared cover art for embedding.")
                     except requests.exceptions.RequestException as img_err:
                         logger.warning(f"Failed to download cover art from {cover_url}: {img_err}")
                     except Exception as embed_err:
                          logger.warning(f"Failed to create mutagen picture object: {embed_err}")
                else:
                     logger.debug("No cover URL available for artwork embedding.")

            # --- Save Separate Artwork Files ---
            save_artwork_enabled = config.get_setting('downloads.saveArtwork', True)
            logger.debug(f"Checking separate artwork saving: saveArtwork={save_artwork_enabled}")
            
            if save_artwork_enabled:
                logger.debug("Saving separate artwork files to disk...")
                
                # Get artwork settings using correct setting names from user's config
                album_artwork_size = config.get_setting('downloads.albumArtworkSize', 1000)
                artist_artwork_size = config.get_setting('downloads.artistArtworkSize', 1200)
                album_image_template = config.get_setting('downloads.albumImageTemplate', 'cover')
                artist_image_template = config.get_setting('downloads.artistImageTemplate', 'folder')
                album_image_format = config.get_setting('downloads.albumImageFormat', 'jpg')
                artist_image_format = config.get_setting('downloads.artistImageFormat', 'jpg')
                
                logger.debug(f"Artwork settings: Album={album_artwork_size}px, Artist={artist_artwork_size}px, AlbumTemplate={album_image_template}, ArtistTemplate={artist_image_template}")
                
                # Save album cover to album directory
                try:
                    album_cover_url = None
                    
                    # Get album cover URL (prefer higher quality for file saving)
                    if 'album' in track_info and isinstance(track_info['album'], dict):
                        # Try to get the best quality cover
                        if album_artwork_size >= 1000 and 'cover_xl' in track_info['album']:
                            album_cover_url = track_info['album']['cover_xl']
                        elif album_artwork_size >= 500 and 'cover_big' in track_info['album']:
                            album_cover_url = track_info['album']['cover_big']
                        elif 'cover_medium' in track_info['album']:
                            album_cover_url = track_info['album']['cover_medium']
                    
                    # Fallback to private API structure
                    if not album_cover_url and 'alb_picture' in track_info:
                        cover_md5 = track_info.get('alb_picture')
                        if cover_md5:
                            size_str = f"{album_artwork_size}x{album_artwork_size}"
                            album_cover_url = f"https://e-cdns-images.dzcdn.net/images/cover/{cover_md5}/{size_str}-000000-80-0-0.jpg"
                    
                    if album_cover_url:
                        # Determine album directory from the temporary file path
                        # The temp file is in format: deemusic_trackid_filename.encrypted.decrypted.part
                        # We need to construct the final album directory based on settings
                        
                        # Get folder structure settings
                        folder_conf = config.get_setting('downloads.folder_structure', {})
                        create_artist_folder = folder_conf.get('create_artist_folders', True)
                        create_album_folder = folder_conf.get('create_album_folders', True)
                        
                        # Get base download directory
                        download_base = config.get_setting('downloads.path', str(Path.home() / 'Downloads'))
                        
                        # Build the directory structure based on settings
                        album_dir = Path(download_base)
                        
                        if create_artist_folder:
                            # Get artist name from track_info
                            artist_name = track_info.get('artist', {}).get('name', 'Unknown Artist')
                            # Sanitize artist name for filesystem
                            safe_artist = self.download_manager._sanitize_filename(artist_name)
                            album_dir = album_dir / safe_artist
                            
                        if create_album_folder:
                            # Get album name from track_info  
                            album_name = track_info.get('alb_title', track_info.get('album', {}).get('title', 'Unknown Album'))
                            # Sanitize album name for filesystem
                            safe_album = self.download_manager._sanitize_filename(album_name)
                            album_dir = album_dir / safe_album
                        
                        album_cover_filename = f"{album_image_template}.{album_image_format}"
                        album_cover_path = album_dir / album_cover_filename
                        
                        # Only download if file doesn't exist
                        if not album_cover_path.exists():
                            logger.debug(f"Downloading album cover to {album_cover_path}")
                            cover_response = requests.get(album_cover_url, timeout=15)
                            cover_response.raise_for_status()
                            
                            with open(album_cover_path, 'wb') as f:
                                f.write(cover_response.content)
                            logger.info(f"Album cover saved to {album_cover_path}")
            else:
                            logger.debug(f"Album cover already exists at {album_cover_path}")
                    else:
                        logger.debug("No album cover URL available for separate file saving")
                        
                except Exception as album_cover_err:
                    logger.warning(f"Failed to save album cover: {album_cover_err}")
                
                # Save artist image to artist directory
                try:
                    artist_image_url = None
                    
                    # Get artist image URL
                    if 'artist' in track_info and isinstance(track_info['artist'], dict):
                        # Try to get the best quality artist image
                        if artist_artwork_size >= 1000 and 'picture_xl' in track_info['artist']:
                            artist_image_url = track_info['artist']['picture_xl']
                        elif artist_artwork_size >= 500 and 'picture_big' in track_info['artist']:
                            artist_image_url = track_info['artist']['picture_big']
                        elif 'picture_medium' in track_info['artist']:
                            artist_image_url = track_info['artist']['picture_medium']
                    
                    # Fallback to private API structure using art_picture
                    if not artist_image_url and 'art_picture' in track_info:
                        artist_md5 = track_info.get('art_picture')
                        if artist_md5:
                            size_str = f"{artist_artwork_size}x{artist_artwork_size}"
                            artist_image_url = f"https://e-cdns-images.dzcdn.net/images/artist/{artist_md5}/{size_str}-000000-80-0-0.jpg"
                    
                    if artist_image_url:
                        # Determine artist directory using the same logic as album directory
                        # Get folder structure settings
                        folder_conf = config.get_setting('downloads.folder_structure', {})
                        create_artist_folder = folder_conf.get('create_artist_folders', True)
                        create_album_folder = folder_conf.get('create_album_folders', True)
                        
                        # Get base download directory
                        download_base = config.get_setting('downloads.path', str(Path.home() / 'Downloads'))
                        
                        if create_artist_folder:
                            # Get artist name from track_info
                            artist_name = track_info.get('artist', {}).get('name', 'Unknown Artist')
                            # Sanitize artist name for filesystem
                            safe_artist = self.download_manager._sanitize_filename(artist_name)
                            artist_dir = Path(download_base) / safe_artist
                        else:
                            # No artist folder structure, skip artist image
                            logger.debug("Artist folders disabled, skipping artist image save")
                            artist_dir = None
                        
                        if artist_dir:
                            artist_image_filename = f"{artist_image_template}.{artist_image_format}"
                            artist_image_path = artist_dir / artist_image_filename
                            
                            # Only download if file doesn't exist
                            if not artist_image_path.exists():
                                logger.debug(f"Downloading artist image to {artist_image_path}")
                                artist_response = requests.get(artist_image_url, timeout=15)
                                artist_response.raise_for_status()
                                
                                with open(artist_image_path, 'wb') as f:
                                    f.write(artist_response.content)
                                logger.info(f"Artist image saved to {artist_image_path}")
                            else:
                                logger.debug(f"Artist image already exists at {artist_image_path}")
                    else:
                        logger.debug("No artist image URL available for separate file saving")
                        
                except Exception as artist_image_err:
                    logger.warning(f"Failed to save artist image: {artist_image_err}")
            else:
                logger.debug("Separate artwork saving is disabled")

            # --- Process and Save Lyrics ---
            logger.info(f"[DEBUG] About to process lyrics for track {track_info.get('id', 'unknown')}")
            try:
                # Fetch and embed lyrics into the audio file
                self._process_and_save_lyrics(track_info, str(final_file_path), is_mp3, audio)
                logger.info(f"[DEBUG] Lyrics processing completed for track {track_info.get('id', 'unknown')}")
            except Exception as lyrics_exc:
                logger.warning(f"Lyrics processing failed: {lyrics_exc}")
                # Continue - lyrics failure shouldn't fail the metadata application

            # Save the file
            audio.save()
            logger.debug(f"Metadata and artwork successfully applied to {decrypted_path}")
            
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
        if self._is_stopping: return None
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
            
            artist_template = templates_conf.get('artist', '%artist%')
            album_template = templates_conf.get('album', '%album%')
            cd_template = templates_conf.get('cd', 'CD %disc_number%')

            # Extract track metadata (same as in download logic)
            artist_val = track_info.get('artist', {}).get('name', 'Unknown Artist')
            album_val = track_info.get('alb_title', track_info.get('album', {}).get('title', 'Unknown Album'))
            title_val = track_info.get('title', 'Unknown Title')
            
            # Track and disc numbers
            track_num_int = track_info.get('track_number', track_info.get('track_position', 1))
            disc_num_int = track_info.get('disk_number', 1)
            
            # Year handling
            release_date = track_info.get('release_date', '1970-01-01')
            year_val = release_date.split('-')[0] if '-' in release_date else release_date[:4]
            
            # Album artist handling
            album_artist_from_api = track_info.get('album', {}).get('artist', {}).get('name', artist_val)
            if album_artist_from_api and album_artist_from_api.lower() in ['various artists', 'various', 'compilation']:
                album_artist_val = album_artist_from_api
            else:
                album_artist_val = artist_val
            
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
                'playlist_name': self.playlist_title if self.playlist_title else '',
                'playlist': self.playlist_title if self.playlist_title else '',
                'genre': track_info.get('genres', {}).get('data', [{}])[0].get('name', 'Unknown Genre'),
                'isrc': track_info.get('isrc', '')
            }
            
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
                    # Fall back to artist/album structure
                    if create_artist_folder:
                        processed_artist = process_template(artist_template)
                        if processed_artist:
                            dir_components.append(processed_artist)
                    
                    if create_album_folder:
                        processed_album = process_template(album_template)
                        if processed_album:
                            dir_components.append(processed_album)
            else:
                # Regular artist/album folder structure
                if create_artist_folder:
                    processed_artist = process_template(artist_template)
                    if processed_artist:
                        dir_components.append(processed_artist)
                
                if create_album_folder:
                    processed_album = process_template(album_template)
                    if processed_album:
                        dir_components.append(processed_album)
                
                # CD folder for multi-disc albums
                if create_cd_folder and total_album_discs > 1:
                    processed_cd = process_template(cd_template)
                    if processed_cd:
                        dir_components.append(processed_cd)
            
            # Determine filename template and create filename
            filename_template_key = "track"  # Default
            default_tpl = "{artist} - {title}"
            
            if self.item_type == 'album_track':
                filename_template_key = "album_track"
                default_tpl = "{track_number:02d}. {title}"
            elif self.item_type == 'playlist_track' and self.playlist_title:
                filename_template_key = "playlist_track"
                default_tpl = "{playlist_position:02d} - {artist} - {title}"
            
            chosen_template_str = config.get_setting(f"downloads.filename_templates.{filename_template_key}", default_tpl)
            
            # Format filename
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
        self.thread_pool = QThreadPool.globalInstance()
        max_threads = self.config.get_setting('downloads.concurrent_downloads', 3)
        self.thread_pool.setMaxThreadCount(max_threads)
        
        self.downloads: Dict[int, DownloadWorker] = {} # Old, maybe remove if active_workers is better
        self.active_workers: Dict[str, DownloadWorker] = {} # item_id_str: worker instance
        self.signals = DownloadManagerSignals() # Use MANAGER signals object

        # Connect signals to manage active_workers
        self.signals.download_finished.connect(self._handle_worker_finished)
        self.signals.download_failed.connect(self._handle_worker_failed)

        logger.info(f"DownloadManager initialized. Download dir: {self.download_dir}, Quality: {self.quality}, Concurrent: {max_threads}")

    def _handle_worker_finished(self, item_id_str: str):
        if item_id_str in self.active_workers:
            logger.debug(f"Removing finished worker {item_id_str} from active list.")
            del self.active_workers[item_id_str]
        else:
            logger.warning(f"Tried to remove finished worker {item_id_str}, but it was not in active_workers list.")
        self._check_and_emit_all_finished()

    def _handle_worker_failed(self, item_id_str: str, error_message: str):
        # error_message is already logged by the worker or _emit_error
        if item_id_str in self.active_workers:
            logger.debug(f"Removing failed worker {item_id_str} from active list.")
            del self.active_workers[item_id_str]
        else:
            logger.warning(f"Tried to remove failed worker {item_id_str}, but it was not in active_workers list.")
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
        """Queues a single track for download using a DownloadWorker."""
        track_id_str = str(track_id)
        logger.info(f"Queueing track {track_id_str} for download. Type: {item_type}, AlbumID: {album_id}, PlaylistID: {playlist_id}, PlaylistTitle: {playlist_title}, AlbumTotal: {album_total_tracks}, PlaylistTotal: {playlist_total_tracks}")
        
        if track_id_str in self.active_workers:
            logger.warning(f"Download worker for track {track_id_str} already exists. Skipping queue.")
            # Optionally, one could re-queue or handle this as an error/update.
            # For now, we assume one worker per track ID at a time.
            return

        worker = DownloadWorker(self, track_id, item_type, album_id=album_id, playlist_title=playlist_title, track_info=track_details, playlist_id=playlist_id, album_total_tracks=album_total_tracks, playlist_total_tracks=playlist_total_tracks)
        self.active_workers[track_id_str] = worker # Store worker instance
        # Connect worker finished signal to remove from active_workers? 
        # Or handle in DownloadManager's own finished/failed slots. 
        # For now, explicit removal on completion/failure in manager signals is cleaner.
        self.thread_pool.start(worker)

    def download_track(self, track_id: int):
        """Queue a single track for download (typically a standalone track)."""
        # Potentially pre-fetch minimal details if useful for UI before worker starts
        # For now, worker fetches its own details if not provided
        self._queue_individual_track_download(track_id, item_type='track')

    async def download_album(self, album_id: int, track_ids: List[int]):
        """Initiates download for all tracks in an album."""
        logger.info(f"Attempting to download album ID: {album_id} with {len(track_ids)} tracks.")
        album_details = await self.deezer_api.get_album_details(album_id)
        if not album_details or 'tracks' not in album_details or 'data' not in album_details['tracks']:
            logger.error(f"Could not fetch details or track list for album {album_id}.")
            return

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

    download_manager = DownloadManager(config_manager, deezer_api)

    # Test queueing a download (requires a running Qt event loop to see signals)
    print("Testing track download queuing...")
    download_manager.download_track(62724015) # Example track ID
    
    print("Testing album download queuing...")
    download_manager.download_album(302127, [62724015]) # Example album ID (Thriller) with track

    print("Downloads queued. Check logs. Need event loop (e.g., QApplication) to run workers.")
    
    # Keep alive briefly for threads to potentially start (in a real app, the event loop handles this)
    # time.sleep(10) 
    # In a real Qt app, QApplication().exec() would run
    
    # Example of how to run with a minimal Qt app for testing signals:
    import sys
    from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QLabel, QProgressBar, QWidget
    
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
