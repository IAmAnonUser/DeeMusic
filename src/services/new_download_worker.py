"""
New download worker for the reliable queue management system.

This worker handles downloading individual queue items (albums, playlists, tracks)
with proper event-driven communication and clean error handling.
"""

import logging
import time
import tempfile
import shutil
import threading
import signal
from pathlib import Path
from typing import Optional, Dict, Any
from PyQt6.QtCore import QRunnable, QThreadPool
import requests
from PIL import Image
import io
import re

# Import crypto for decryption
from Crypto.Hash import MD5
from Crypto.Cipher import Blowfish

# Import mutagen for metadata
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TPE1, TPE2, TIT2, TALB, TRCK, TPOS, TDRC, SYLT, USLT
from mutagen.flac import FLAC, Picture

# Import our new models and event system
import sys
from pathlib import Path
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from src.models.queue_models import QueueItem, DownloadState, ItemType, TrackInfo
from src.services.event_bus import EventBus, DownloadEvents
from src.utils.lyrics_utils import LyricsProcessor

logger = logging.getLogger(__name__)


class TrackDownloadRunnable(QRunnable):
    """
    Runnable for downloading individual tracks in parallel.
    """
    
    def __init__(self, parent_worker, track_info, playlist_position):
        super().__init__()
        self.parent_worker = parent_worker
        self.track_info = track_info
        self.playlist_position = playlist_position
        self.success = False
        
    def run(self):
        """Download the track and report results back to parent."""
        try:
            # Check for cancellation before starting
            if self.parent_worker.cancelled:
                return
                
            # Download the track using parent worker's method
            self.success = self.parent_worker._download_track(
                self.track_info, 
                playlist_position=self.playlist_position
            )
            
            # Immediately report completion to parent for real-time progress updates
            self.parent_worker._on_track_completed(self.track_info, self.success)
            
        except Exception as e:
            logger.error(f"[TrackDownloadRunnable] Error downloading track {self.track_info.track_id}: {e}")
            self.success = False
            # Report failure to parent
            self.parent_worker._on_track_completed(self.track_info, False)


class DownloadWorker(QRunnable):
    """
    Worker for downloading a single queue item.
    
    This worker is responsible for:
    - Downloading all tracks in a queue item (album/playlist/track)
    - Reporting progress via events
    - Handling errors gracefully
    - Proper cancellation support
    - Clean resource management
    """
    
    def __init__(self, item: QueueItem, deezer_api, config_manager, event_bus: EventBus):
        super().__init__()
        self.item = item
        self.deezer_api = deezer_api
        self.config = config_manager
        self.event_bus = event_bus
        
        # Worker state
        self.cancelled = False
        self.paused = False
        self._last_progress_time = time.time()
        
        # Download settings
        self.quality = self.config.get_setting('downloads.quality', 'MP3_320')
        self.download_path = Path(self.config.get_setting('downloads.path', 'downloads'))
        self.create_artist_folders = self.config.get_setting('downloads.folder_structure.create_artist_folders', True)
        self.create_album_folders = self.config.get_setting('downloads.folder_structure.create_album_folders', True)
        
        # Use existing concurrent_downloads setting for track-level concurrency
        self.concurrent_tracks = self.config.get_setting('downloads.concurrent_downloads', 3)
        self.track_thread_pool = None
        self._track_progress_lock = threading.Lock()
        
        # Track completion counters for real-time progress updates
        self._completed_tracks = 0
        self._failed_tracks = 0
        self._total_tracks = 0
        
        # Performance optimization: cache compilation detection result
        self._is_compilation_cache = None
        
        # Cache album artwork for multi-disc distribution
        self._cached_album_artwork = None
        
        logger.info(f"[DownloadWorker] Created worker for {self.item.item_type.value}: {self.item.title} by {self.item.artist}")
    
    def run(self):
        """Execute the download task."""
        try:
            logger.info(f"[DownloadWorker] Starting download: {self.item.title} by {self.item.artist}")
            self._last_progress_time = time.time()
            
            # Emit download started event
            self.event_bus.emit(DownloadEvents.DOWNLOAD_STARTED, self.item.id)
            
            if self.item.item_type == ItemType.ALBUM:
                self._download_album()
            elif self.item.item_type == ItemType.PLAYLIST:
                self._download_playlist()
            elif self.item.item_type == ItemType.TRACK:
                self._download_single_track()
            else:
                raise ValueError(f"Unknown item type: {self.item.item_type}")
            
            if not self.cancelled:
                logger.info(f"[DownloadWorker] Completed download: {self.item.title}")
                self.event_bus.emit(DownloadEvents.DOWNLOAD_COMPLETED, self.item.id)
            
        except Exception as e:
            if not self.cancelled:
                error_msg = f"Download failed: {str(e)}"
                logger.error(f"[DownloadWorker] {error_msg}", exc_info=True)
                self.event_bus.emit(DownloadEvents.DOWNLOAD_FAILED, self.item.id, error_msg)
    
    def cancel(self):
        """Cancel the download."""
        self.cancelled = True
        logger.info(f"[DownloadWorker] Cancelled download: {self.item.title}")
        
        # Cancel track-level thread pool if active
        if self.track_thread_pool:
            self.track_thread_pool.clear()
        
        # If we have any ongoing requests, try to interrupt them
        # This helps with faster cancellation during network operations
    
    def _on_track_completed(self, track_info, success):
        """Called when a track completes downloading (success or failure)."""
        with self._track_progress_lock:
            if success:
                self._completed_tracks += 1
                self.event_bus.emit(DownloadEvents.TRACK_COMPLETED, self.item.id, track_info.track_id)
            else:
                self._failed_tracks += 1
                self.event_bus.emit(DownloadEvents.TRACK_FAILED, self.item.id, track_info.track_id, "Download failed")
            
            # Emit real-time progress update
            if self._total_tracks > 0:
                progress = self._completed_tracks / self._total_tracks
                self.event_bus.emit(DownloadEvents.DOWNLOAD_PROGRESS, self.item.id, progress, self._completed_tracks, self._failed_tracks)
                self._last_progress_time = time.time()
                
                logger.info(f"[DownloadWorker] Progress update: {self._completed_tracks}/{self._total_tracks} tracks completed")
    
    def pause(self):
        """Pause the download."""
        self.paused = True
        logger.info(f"[DownloadWorker] Paused download: {self.item.title}")
    
    def resume(self):
        """Resume the download."""
        self.paused = False
        logger.info(f"[DownloadWorker] Resumed download: {self.item.title}")
    
    def _download_album(self):
        """Download all tracks in an album using concurrent downloads."""
        # Reset counters for this download
        self._completed_tracks = 0
        self._failed_tracks = 0
        self._total_tracks = len(self.item.tracks)
        
        # Ensure token freshness before starting concurrent downloads
        # This helps prevent CSRF token expiration issues during batch operations
        logger.info(f"[DownloadWorker] Ensuring token freshness before downloading {self._total_tracks} tracks...")
        try:
            logger.info(f"[DownloadWorker] About to call ensure_token_freshness_sync() on deezer_api...")
            logger.info(f"[DownloadWorker] DeezerAPI instance has ARL: {bool(self.deezer_api.arl)}, ARL length: {len(self.deezer_api.arl) if self.deezer_api.arl else 0}")
            logger.info(f"[DownloadWorker] DeezerAPI instance ARL preview: {self.deezer_api.arl[:20] if self.deezer_api.arl else None}...")
            token_fresh = self.deezer_api.ensure_token_freshness_sync()
            logger.info(f"[DownloadWorker] ensure_token_freshness_sync() returned: {token_fresh}")
            if not token_fresh:
                logger.error(f"[DownloadWorker] Failed to ensure token freshness, aborting album download")
                return
            logger.info(f"[DownloadWorker] Token freshness confirmed, proceeding with download")
        except Exception as e:
            logger.error(f"[DownloadWorker] Exception during token freshness check: {e}", exc_info=True)
            logger.error(f"[DownloadWorker] Aborting album download due to token check failure")
            return
        
        # Create album directory
        album_dir = self._create_album_directory()
        
        # Download and cache album artwork for multi-disc distribution
        self._prepare_album_artwork_for_multi_disc()
        
        # Create thread pool for concurrent track downloads
        self.track_thread_pool = QThreadPool()
        self.track_thread_pool.setMaxThreadCount(self.concurrent_tracks)
        
        # Track download workers
        track_workers = []
        
        logger.info(f"[DownloadWorker] Starting concurrent download of {self._total_tracks} tracks with {self.concurrent_tracks} threads")
        
        try:
            # Submit all tracks to thread pool
            for i, track_info in enumerate(self.item.tracks):
                if self.cancelled:
                    break
                
                # Wait if paused
                while self.paused and not self.cancelled:
                    time.sleep(0.1)
                
                if self.cancelled:
                    break
                
                # Create track worker
                track_worker = TrackDownloadRunnable(
                    parent_worker=self,
                    track_info=track_info,
                    playlist_position=i+1
                )
                
                track_workers.append(track_worker)
                self.track_thread_pool.start(track_worker)
                
                # Add small delay between starting workers to reduce API call clustering
                # This helps prevent multiple workers from hitting expired tokens simultaneously
                if i > 0 and i % 2 == 0:  # Every 2 tracks, pause briefly
                    time.sleep(0.05)  # 50ms delay
            
            # Wait for all downloads to complete with real-time progress updates
            if not self.cancelled:
                # Monitor progress while downloads are running
                while self.track_thread_pool.activeThreadCount() > 0:
                    if self.cancelled:
                        break
                    time.sleep(0.1)  # Small delay to prevent excessive CPU usage
                
                # Wait for thread pool to finish
                self.track_thread_pool.waitForDone(30000)  # 30 second timeout
        
        except Exception as e:
            logger.error(f"[DownloadWorker] Error during concurrent album download: {e}")
        
        finally:
            # Clean up thread pool
            if self.track_thread_pool:
                self.track_thread_pool.clear()
                self.track_thread_pool.waitForDone(1000)  # 1 second cleanup timeout
                self.track_thread_pool = None
        
        logger.info(f"[DownloadWorker] Album download completed: {self._completed_tracks}/{self._total_tracks} tracks successful")
    
    def _download_playlist(self):
        """Download all tracks in a playlist."""
        # Ensure token freshness before starting concurrent downloads
        logger.info(f"[DownloadWorker] Ensuring token freshness before downloading playlist tracks...")
        if not self.deezer_api.ensure_token_freshness_sync():
            logger.error(f"[DownloadWorker] Failed to ensure token freshness, aborting playlist download")
            return
        logger.debug(f"[DownloadWorker] Token freshness confirmed for playlist, proceeding with download")
        
        # Download and cache album artwork for multi-disc distribution if needed
        self._prepare_album_artwork_for_multi_disc()
        
        # Similar to album download but with playlist-specific logic
        self._download_album()  # For now, use same logic as album
    
    def _download_single_track(self):
        """Download a single track."""
        if not self.item.tracks:
            raise ValueError("No track information available")
        
        # Ensure token freshness before downloading
        logger.debug(f"[DownloadWorker] Ensuring token freshness before downloading single track...")
        if not self.deezer_api.ensure_token_freshness_sync():
            logger.error(f"[DownloadWorker] Failed to ensure token freshness, aborting single track download")
            raise Exception("Failed to ensure token freshness")

        track_info = self.item.tracks[0]
        
        success = self._download_track(track_info, playlist_position=1)
        
        if success:
            self.event_bus.emit(DownloadEvents.TRACK_COMPLETED, self.item.id, track_info.track_id)
            self.event_bus.emit(DownloadEvents.DOWNLOAD_PROGRESS, self.item.id, 1.0, 1, 0)
        else:
            raise Exception("Failed to download track")
    
    def _download_track(self, track_info: TrackInfo, playlist_position: int = 1) -> bool:
        """
        Download a single track.
        
        Args:
            track_info: Track information
            playlist_position: Position in playlist (for filename generation)
            
        Returns:
            True if successful, False otherwise
        """
        # Check for cancellation at the very beginning
        if self.cancelled:
            return False
            
        try:
            # Fetch full track data for artist artwork access
            full_track_data = self.deezer_api.get_track_details_sync(track_info.track_id)
            self._current_track_info = full_track_data if full_track_data else track_info.to_dict()
            
            # Get download URL
            logger.info(f"[DownloadWorker] Attempting to get download URL for track {track_info.track_id} with quality {self.quality}")
            download_url = self.deezer_api.get_track_download_url_sync(
                track_info.track_id, 
                quality=self.quality
            )
            logger.info(f"[DownloadWorker] get_track_download_url_sync returned: {download_url}")
            
            if not download_url or isinstance(download_url, str) and download_url.startswith(('RIGHTS_ERROR:', 'API_ERROR:')):
                logger.warning(f"[DownloadWorker] Cannot get download URL for track {track_info.track_id}: {download_url}")
                logger.info(f"[DownloadWorker] download_url type: {type(download_url)}, value: {download_url}")
                return False
            
            # Handle quality skip
            if isinstance(download_url, str) and download_url.startswith('QUALITY_SKIP:'):
                logger.info(f"[DownloadWorker] Skipping track {track_info.track_id}: {download_url}")
                return False
            logger.info(f"[DownloadWorker] Proceeding with download URL: {download_url[:50] if download_url else None}...")
            
            # Create filename and directory (including disc folders if needed)
            filename = self._create_filename(track_info, playlist_position=playlist_position)
            track_dir = self._create_track_directory(track_info)
            file_path = track_dir / filename
            
            # Skip if file already exists
            if file_path.exists():
                logger.info(f"[DownloadWorker] File already exists, skipping: {file_path}")
                
                # Check for cancellation even when skipping files
                if self.cancelled:
                    return False
                
                # Emit track completed event (not download completed!)
                self.event_bus.emit(DownloadEvents.TRACK_COMPLETED, self.item.id, track_info.track_id)
                return True
            
            # Download encrypted file
            temp_file = self._download_encrypted_file(download_url)
            if not temp_file:
                return False
            
            # Decrypt file
            decrypted_file = self._decrypt_file(temp_file, str(track_info.track_id))
            if not decrypted_file:
                return False
            
            # Apply metadata and move to final location
            success = self._finalize_track(decrypted_file, file_path, track_info, playlist_position=playlist_position)
            
            # Cleanup temp files
            try:
                if temp_file and temp_file.exists():
                    temp_file.unlink()
                if decrypted_file and decrypted_file.exists() and decrypted_file != file_path:
                    decrypted_file.unlink()
            except Exception as e:
                logger.warning(f"[DownloadWorker] Error cleaning up temp files: {e}")
            
            return success
            
        except Exception as e:
            logger.error(f"[DownloadWorker] Error downloading track {track_info.track_id}: {e}")
            return False
    
    def _download_encrypted_file(self, download_url: str) -> Optional[Path]:
        """Download the encrypted file from Deezer."""
        try:
            # Create temporary file
            temp_fd, temp_path = tempfile.mkstemp(suffix='.part')
            temp_file = Path(temp_path)
            
            with open(temp_fd, 'wb') as f:
                response = requests.get(download_url, stream=True, timeout=30)
                response.raise_for_status()
                
                for chunk in response.iter_content(chunk_size=8192):
                    if self.cancelled:
                        return None
                    if chunk:
                        f.write(chunk)
            
            return temp_file
            
        except Exception as e:
            logger.error(f"[DownloadWorker] Error downloading encrypted file: {e}")
            return None
    
    def _decrypt_file(self, encrypted_file: Path, track_id: str) -> Optional[Path]:
        """Decrypt the downloaded file using Blowfish CBC."""
        try:
            # Generate decryption key
            key = self._generate_decryption_key(track_id)
            if not key:
                return None
            
            # Create temporary file for decrypted content
            temp_fd, temp_path = tempfile.mkstemp(suffix='.decrypted')
            decrypted_file = Path(temp_path)
            
            # Decrypt file
            with open(encrypted_file, 'rb') as encrypted, open(temp_fd, 'wb') as decrypted:
                self._decrypt_stream(encrypted, decrypted, key)
            
            return decrypted_file
            
        except Exception as e:
            logger.error(f"[DownloadWorker] Error decrypting file: {e}")
            return None
    
    def _generate_decryption_key(self, track_id: str) -> Optional[bytes]:
        """Generate Blowfish decryption key from track ID."""
        try:
            bf_secret = "g4el58wc0zvf9na1"  # Hardcoded Deezer secret
            
            # Generate MD5 hash of track ID
            hash_obj = MD5.new(track_id.encode('ascii', 'ignore'))
            hashed_id = hash_obj.hexdigest()
            
            # XOR algorithm to generate key
            key_chars = []
            for i in range(16):
                xor_val = (ord(hashed_id[i]) ^ 
                          ord(hashed_id[i + 16]) ^ 
                          ord(bf_secret[i]))
                key_chars.append(chr(xor_val))
            
            key_string = "".join(key_chars)
            return key_string.encode('utf-8')
            
        except Exception as e:
            logger.error(f"[DownloadWorker] Error generating decryption key: {e}")
            return None
    
    def _decrypt_stream(self, encrypted_stream, decrypted_stream, key: bytes):
        """Decrypt stream using Blowfish CBC with stripe pattern."""
        iv = bytes.fromhex("0001020304050607")  # Fixed IV as hex bytes
        chunk_size = 2048
        segment_size = chunk_size * 3  # 6144 bytes
        
        buffer = b''
        
        while True:
            if self.cancelled:
                break
                
            # Read data to fill buffer to segment size
            read_amount = segment_size - len(buffer)
            chunk_data = encrypted_stream.read(read_amount)
            
            if not chunk_data and not buffer:
                break
                
            buffer += chunk_data
            
            # Process complete segments
            while len(buffer) >= segment_size:
                segment = buffer[:segment_size]
                buffer = buffer[segment_size:]
                
                # Split segment: first 2048 bytes encrypted, next 4096 bytes plain
                encrypted_part = segment[:chunk_size]
                plain_part = segment[chunk_size:]
                
                # Create new cipher for each chunk (critical for correct decryption)
                cipher = Blowfish.new(key, Blowfish.MODE_CBC, iv)
                decrypted_part = cipher.decrypt(encrypted_part)
                
                decrypted_stream.write(decrypted_part + plain_part)
            
            # If no more data and buffer has remaining bytes
            if not chunk_data and len(buffer) > 0:
                if len(buffer) >= chunk_size:
                    # Decrypt first chunk of remaining buffer
                    encrypted_part = buffer[:chunk_size]
                    plain_part = buffer[chunk_size:]
                    
                    cipher = Blowfish.new(key, Blowfish.MODE_CBC, iv)
                    decrypted_part = cipher.decrypt(encrypted_part)
                    
                    decrypted_stream.write(decrypted_part + plain_part)
                else:
                    # Less than chunk_size remaining, write as-is
                    decrypted_stream.write(buffer)
                break    

    def _finalize_track(self, decrypted_file: Path, final_path: Path, track_info: TrackInfo, playlist_position: int = 1) -> bool:
        """Apply metadata and move file to final location."""
        try:
            # Check for Windows path length limit
            if len(str(final_path)) > 250:
                logger.warning(f"[DownloadWorker] Path too long ({len(str(final_path))} chars), truncating filename")
                # Create a shorter filename
                short_filename = f"{track_info.track_number:02d} - {track_info.title[:50]}{final_path.suffix}"
                short_filename = self._sanitize_filename(short_filename.replace(final_path.suffix, "")) + final_path.suffix
                final_path = final_path.parent / short_filename
                logger.info(f"[DownloadWorker] Using shortened path: {final_path}")
            
            # Ensure parent directory exists
            final_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Verify source file exists
            if not decrypted_file.exists():
                logger.error(f"[DownloadWorker] Source file does not exist: {decrypted_file}")
                return False
            
            # Move file to final location
            logger.debug(f"[DownloadWorker] Moving {decrypted_file} -> {final_path}")
            shutil.move(str(decrypted_file), str(final_path))
            
            # Apply metadata
            self._apply_metadata(final_path, track_info, playlist_position=playlist_position)
            
            return True
            
        except Exception as e:
            logger.error(f"[DownloadWorker] Error finalizing track '{final_path}': {e}")
            logger.error(f"[DownloadWorker] Path length: {len(str(final_path))} characters")
            logger.error(f"[DownloadWorker] Source file: {decrypted_file}, exists: {decrypted_file.exists() if decrypted_file else 'None'}")
            logger.error(f"[DownloadWorker] Target dir: {final_path.parent}, exists: {final_path.parent.exists() if final_path else 'None'}")
            return False
    
    def _apply_metadata(self, file_path: Path, track_info: TrackInfo, playlist_position: int = 1):
        """Apply metadata to the audio file."""
        try:
            # Apply basic metadata
            if file_path.suffix.lower() == '.mp3':
                self._apply_mp3_metadata(file_path, track_info, playlist_position=playlist_position)
            elif file_path.suffix.lower() == '.flac':
                self._apply_flac_metadata(file_path, track_info, playlist_position=playlist_position)
            
            # Download and embed artwork
            self._download_and_embed_artwork(file_path, track_info)
            
            # Download and process lyrics
            self._download_and_embed_lyrics(file_path, track_info)
                
        except Exception as e:
            logger.error(f"[DownloadWorker] Error applying metadata: {e}")
    
    def _apply_mp3_metadata(self, file_path: Path, track_info: TrackInfo, playlist_position: int = 1):
        """Apply metadata to MP3 file."""
        try:
            audio = MP3(str(file_path), ID3=ID3)
            
            # Add ID3 tag if it doesn't exist
            if audio.tags is None:
                audio.add_tags()
            
            # Basic metadata
            audio.tags.add(TIT2(encoding=3, text=track_info.title))  # Title
            artist_for_track = self._build_track_artist_for_metadata(track_info)
            audio.tags.add(TPE1(encoding=3, text=artist_for_track))  # Track Artist (with featured)
            album_artist = self._build_album_artist_for_metadata()
            audio.tags.add(TPE2(encoding=3, text=album_artist))  # Album Artist (compilation-aware)
            audio.tags.add(TALB(encoding=3, text=self.item.title))  # Album Title
            
            # Use playlist position for playlists, track number for albums
            track_number_for_metadata = playlist_position if self.item.item_type == ItemType.PLAYLIST else (track_info.track_number or 1)
            audio.tags.add(TRCK(encoding=3, text=str(track_number_for_metadata)))
            
            if track_info.disc_number:
                audio.tags.add(TPOS(encoding=3, text=str(track_info.disc_number)))
            
            audio.save()
            
        except Exception as e:
            logger.error(f"[DownloadWorker] Error applying MP3 metadata: {e}")
    
    def _apply_flac_metadata(self, file_path: Path, track_info: TrackInfo, playlist_position: int = 1):
        """Apply metadata to FLAC file."""
        try:
            audio = FLAC(str(file_path))
            
            # Basic metadata
            audio['TITLE'] = track_info.title  # Title
            artist_for_track = self._build_track_artist_for_metadata(track_info)
            audio['ARTIST'] = artist_for_track  # Track Artist (with featured)
            album_artist = self._build_album_artist_for_metadata()
            audio['ALBUMARTIST'] = album_artist  # Album Artist (compilation-aware)
            audio['ALBUM'] = self.item.title  # Album Title
            
            # Use playlist position for playlists, track number for albums
            track_number_for_metadata = playlist_position if self.item.item_type == ItemType.PLAYLIST else (track_info.track_number or 1)
            audio['TRACKNUMBER'] = str(track_number_for_metadata)
            
            if track_info.disc_number:
                audio['DISCNUMBER'] = str(track_info.disc_number)
            
            audio.save()
            
        except Exception as e:
            logger.error(f"[DownloadWorker] Error applying FLAC metadata: {e}")
    
    def _build_track_artist_for_metadata(self, track_info: TrackInfo) -> str:
        """Return the track artist string, including featured artists parsed from title.
        Example: 'Ed Sheeran' + title 'Beautiful People (feat. Khalid)' -> 'Ed Sheeran (feat. Khalid)'
        """
        base_artist = (track_info.artist or self.item.artist or '').strip()
        # If base already contains a feat indicator, keep as-is
        if re.search(r'\b(feat\.?|featuring|ft\.|with)\b', base_artist, flags=re.IGNORECASE):
            return base_artist
        title = (track_info.title or '').strip()
        # Look for featured artists in title
        match = re.search(r'\((?:feat\.?|featuring|ft\.|with)\s+([^\)]+)\)', title, flags=re.IGNORECASE)
        featured = None
        if match:
            featured = match.group(1).strip()
        else:
            # Also support titles like 'Song name feat. Artist'
            match2 = re.search(r'(?:feat\.?|featuring|ft\.|with)\s+(.+)$', title, flags=re.IGNORECASE)
            if match2:
                # Stop at common separators
                featured = re.split(r'[-\[]', match2.group(1).strip())[0].strip()
        if featured:
            # Normalize separators and whitespace
            featured = re.sub(r'\s*,\s*', ', ', featured)
            return f"{base_artist} (feat. {featured})"
        return base_artist

    def _is_compilation_album(self) -> bool:
        """Improved heuristic to detect compilation/soundtrack albums.
        Only considers albums as compilations when there's strong evidence:
        - Album artist explicitly indicates 'Various Artists'
        - Album title contains compilation/soundtrack keywords
        - Majority of tracks have different artists than the album artist (with improved logic)
        """
        # Return cached result if available
        if self._is_compilation_cache is not None:
            return self._is_compilation_cache
            
        try:
            album_artist = (self.item.artist or '').lower()
            album_artist_clean = album_artist.strip()
            
            # Debug logging for troubleshooting (only log once per album)
            logger.debug(f"[DownloadWorker] Compilation check for '{self.item.title}' by '{self.item.artist}'")
            
            # Strong indicators: explicit "Various Artists" or similar
            if any(indicator in album_artist for indicator in ['various artists', 'various', 'compilation', 'v.a.']):
                logger.debug(f"[DownloadWorker] Detected compilation by album artist: {album_artist}")
                self._is_compilation_cache = True
                return True
            
            # Radio stations, labels, and compilation entities
            compilation_entities = [
                'triple j', 'bbc', 'radio', 'fm', 'records', 'music', 'entertainment',
                'label', 'productions', 'studios', 'media', 'group', 'corporation',
                'ministry of sound', 'now that\'s what i call', 'kidz bop'
            ]
            if any(entity in album_artist for entity in compilation_entities):
                logger.debug(f"[DownloadWorker] Detected compilation by album artist entity: {album_artist}")
                self._is_compilation_cache = True
                return True
            
            # Soundtrack/compilation keywords in title (be more specific)
            title_lc = (self.item.title or '').lower()
            compilation_keywords = [
                'soundtrack', 'original motion picture soundtrack', 'ost', 'original soundtrack',
                'compilation', 'greatest hits', 'best of', 'the very best',
                'collection', 'anthology', 'mixed by', 'mixed & compiled', 'various artists',
                'anthems', 'hits', 'classics', 'essentials', 'ultimate', 'definitive',
                'vol.', 'volume', 'part', 'chapter', 'series', 'edition'
            ]
            # Only trigger if the keyword is a significant part of the title, not just contained within
            if any(keyword in title_lc and (
                title_lc.startswith(keyword) or 
                title_lc.endswith(keyword) or 
                f' {keyword} ' in title_lc or
                f'({keyword})' in title_lc or
                f'[{keyword}]' in title_lc
            ) for keyword in compilation_keywords):
                logger.debug(f"[DownloadWorker] Detected compilation by title keywords: {title_lc}")
                self._is_compilation_cache = True
                return True
            
            # DISABLED: Artist analysis for compilation detection
            # This was causing too many false positives with albums that have many featured artists
            # Only rely on explicit album artist or title indicators
            
            logger.debug(f"[DownloadWorker] Not a compilation album - no explicit indicators found")
            self._is_compilation_cache = False
            return False
        except Exception as e:
            logger.debug(f"[DownloadWorker] Error in compilation detection: {e}")
            self._is_compilation_cache = False
            return False

    def _build_album_artist_for_metadata(self) -> str:
        """Return the album artist string, using 'Various Artists' for compilations."""
        return 'Various Artists' if self._is_compilation_album() else (self.item.artist or '')
    
    def _download_and_embed_artwork(self, file_path: Path, track_info: TrackInfo):
        """Download and embed artwork if enabled in settings."""
        try:
            # Check if artwork embedding is enabled
            embed_artwork = self.config.get_setting('downloads.embedArtwork', True)
            save_artwork = self.config.get_setting('downloads.saveArtwork', True)
            
            if not embed_artwork and not save_artwork:
                return
            
            # Try to use cached artwork first (from multi-disc preparation)
            artwork_data = getattr(self, '_cached_album_artwork', None)
            
            # If no cached artwork, download it
            if not artwork_data:
                # Get album cover URL
                album_cover_url = getattr(self.item, 'album_cover_url', None)
                if not album_cover_url:
                    logger.warning(f"[DownloadWorker] No album cover URL available for {track_info.title}")
                    return
                
                # Download artwork
                artwork_data = self._download_artwork(album_cover_url)
                if not artwork_data:
                    return
            else:
                logger.debug(f"[DownloadWorker] Using cached album artwork for {track_info.title}")
            
            # Embed artwork in file
            if embed_artwork:
                self._embed_artwork_in_file(file_path, artwork_data)
            
            # Save artwork files (this will handle CD folder distribution if needed)
            if save_artwork:
                self._save_artwork_files(file_path.parent, artwork_data)
                
        except Exception as e:
            logger.error(f"[DownloadWorker] Error handling artwork: {e}")
    
    def _download_artwork(self, url: str) -> Optional[bytes]:
        """Download artwork from URL."""
        try:
            # Get artwork size setting
            artwork_size = self.config.get_setting('downloads.embeddedArtworkSize', 1000)
            
            # Modify URL for desired size if it's a Deezer URL
            if 'dzcdn.net' in url:
                url = url.replace('/1000x1000-', f'/{artwork_size}x{artwork_size}-')
            
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            return response.content
            
        except Exception as e:
            logger.error(f"[DownloadWorker] Error downloading artwork from {url}: {e}")
            return None
    
    def _embed_artwork_in_file(self, file_path: Path, artwork_data: bytes):
        """Embed artwork in audio file."""
        try:
            if file_path.suffix.lower() == '.mp3':
                self._embed_artwork_mp3(file_path, artwork_data)
            elif file_path.suffix.lower() == '.flac':
                self._embed_artwork_flac(file_path, artwork_data)
                
        except Exception as e:
            logger.error(f"[DownloadWorker] Error embedding artwork: {e}")
    
    def _embed_artwork_mp3(self, file_path: Path, artwork_data: bytes):
        """Embed artwork in MP3 file."""
        try:
            audio = MP3(str(file_path), ID3=ID3)
            
            # Remove existing artwork
            audio.tags.delall('APIC')
            
            # Add new artwork
            audio.tags.add(
                APIC(
                    encoding=3,  # UTF-8
                    mime='image/jpeg',
                    type=3,  # Cover (front)
                    desc='Cover',
                    data=artwork_data
                )
            )
            
            audio.save()
            
        except Exception as e:
            logger.error(f"[DownloadWorker] Error embedding MP3 artwork: {e}")
    
    def _embed_artwork_flac(self, file_path: Path, artwork_data: bytes):
        """Embed artwork in FLAC file."""
        try:
            audio = FLAC(str(file_path))
            
            # Clear existing pictures
            audio.clear_pictures()
            
            # Create picture
            picture = Picture()
            picture.data = artwork_data
            picture.type = 3  # Cover (front)
            picture.mime = 'image/jpeg'
            picture.desc = 'Cover'
            
            # Add picture
            audio.add_picture(picture)
            audio.save()
            
        except Exception as e:
            logger.error(f"[DownloadWorker] Error embedding FLAC artwork: {e}")
    
    def _save_artwork_files(self, directory: Path, artwork_data: bytes):
        """Save artwork files to directory based on settings."""
        try:
            # Get artwork settings
            album_template = self.config.get_setting('downloads.albumImageTemplate', 'cover')
            album_format = self.config.get_setting('downloads.albumImageFormat', 'jpg')
            artist_template = self.config.get_setting('downloads.artistImageTemplate', 'folder')
            artist_format = self.config.get_setting('downloads.artistImageFormat', 'jpg')
            
            # Save album artwork in current directory (track directory or CD folder)
            album_filename = f"{album_template}.{album_format}"
            album_path = directory / album_filename
            
            # Only save if it doesn't exist (prevents overwriting during multi-disc processing)
            if not album_path.exists():
                with open(album_path, 'wb') as f:
                    f.write(artwork_data)
                logger.debug(f"[DownloadWorker] Album cover saved to {album_path}")
            else:
                logger.debug(f"[DownloadWorker] Album cover already exists at {album_path}")
            
            # For multi-disc albums where CD folders haven't been pre-populated,
            # save to all CD subfolders (fallback for individual track processing)
            create_cd_folders = self.config.get_setting('downloads.folder_structure.create_cd_folders', True)
            if create_cd_folders and self._is_multi_disc_album() and not hasattr(self, '_cached_album_artwork'):
                self._save_album_artwork_to_cd_folders(artwork_data, album_template, album_format)
            
            # Save artist artwork (in artist directory)
            if self.create_artist_folders:
                # Get the artist directory - always go to the root artist folder
                artist_dir = self._get_artist_directory()
                self._save_artist_artwork(artist_dir, artist_template, artist_format)
                
        except Exception as e:
            logger.error(f"[DownloadWorker] Error saving artwork files: {e}")
    
    def _distribute_artwork_to_cd_folders(self, artwork_data: bytes, album_template: str, album_format: str):
        """Distribute album artwork to all CD subfolders."""
        try:
            # Get the main album directory
            album_dir = self._create_album_directory()
            
            # Get all unique disc numbers from tracks
            disc_numbers = set()
            for track in self.item.tracks:
                disc_number = track.disc_number or 1
                disc_numbers.add(disc_number)
            
            # Get the CD folder template
            cd_template = self.config.get_setting('downloads.folder_structure.templates.cd', 'CD %disc_number%')
            album_filename = f"{album_template}.{album_format}"
            
            logger.info(f"[DownloadWorker] Distributing album artwork to {len(disc_numbers)} CD folders")
            
            # Save album cover to each CD subfolder
            for disc_number in sorted(disc_numbers):
                cd_folder_name = cd_template.replace('%disc_number%', str(disc_number))
                cd_folder_name = self._sanitize_filename(cd_folder_name)
                cd_folder_path = album_dir / cd_folder_name
                
                # Ensure CD folder exists
                cd_folder_path.mkdir(parents=True, exist_ok=True)
                
                # Save album cover in CD folder
                album_cover_path = cd_folder_path / album_filename
                
                # Always save to ensure consistency (will overwrite if exists)
                with open(album_cover_path, 'wb') as f:
                    f.write(artwork_data)
                logger.debug(f"[DownloadWorker] Album cover distributed to: {album_cover_path}")
                    
        except Exception as e:
            logger.error(f"[DownloadWorker] Error distributing album artwork to CD folders: {e}")
    
    def _save_album_artwork_to_cd_folders(self, artwork_data: bytes, album_template: str, album_format: str):
        """Save album artwork to all CD subfolders for multi-disc albums.
        
        Note: This method is kept for backward compatibility but the new approach 
        uses _prepare_album_artwork_for_multi_disc for better efficiency.
        """
        try:
            # Get the main album directory
            album_dir = self._create_album_directory()
            
            # Get all unique disc numbers from tracks
            disc_numbers = set()
            for track in self.item.tracks:
                disc_number = track.disc_number or 1
                disc_numbers.add(disc_number)
            
            # Get the CD folder template
            cd_template = self.config.get_setting('downloads.folder_structure.templates.cd', 'CD %disc_number%')
            album_filename = f"{album_template}.{album_format}"
            
            # Save album cover to each CD subfolder
            for disc_number in sorted(disc_numbers):
                cd_folder_name = cd_template.replace('%disc_number%', str(disc_number))
                cd_folder_name = self._sanitize_filename(cd_folder_name)
                cd_folder_path = album_dir / cd_folder_name
                
                # Ensure CD folder exists
                cd_folder_path.mkdir(parents=True, exist_ok=True)
                
                # Save album cover in CD folder
                album_cover_path = cd_folder_path / album_filename
                
                # Only save if it doesn't already exist
                if not album_cover_path.exists():
                    with open(album_cover_path, 'wb') as f:
                        f.write(artwork_data)
                    logger.debug(f"[DownloadWorker] Album cover saved to CD folder: {album_cover_path}")
                else:
                    logger.debug(f"[DownloadWorker] Album cover already exists in CD folder: {album_cover_path}")
                    
        except Exception as e:
            logger.error(f"[DownloadWorker] Error saving album artwork to CD folders: {e}")
    
    def _prepare_album_artwork_for_multi_disc(self):
        """Download and cache album artwork, then distribute to CD folders for multi-disc albums."""
        try:
            # Check if artwork saving is enabled
            save_artwork = self.config.get_setting('downloads.saveArtwork', True)
            if not save_artwork:
                return
            
            # Check if this is a multi-disc album with CD folders enabled
            create_cd_folders = self.config.get_setting('downloads.folder_structure.create_cd_folders', True)
            if not (create_cd_folders and self._is_multi_disc_album()):
                return
            
            # Get album cover URL
            album_cover_url = getattr(self.item, 'album_cover_url', None)
            if not album_cover_url:
                logger.debug(f"[DownloadWorker] No album cover URL available for multi-disc artwork distribution")
                return
            
            # Download artwork once
            artwork_data = self._download_artwork(album_cover_url)
            if not artwork_data:
                logger.warning(f"[DownloadWorker] Failed to download album artwork for multi-disc distribution")
                return
            
            # Get artwork settings
            album_template = self.config.get_setting('downloads.albumImageTemplate', 'cover')
            album_format = self.config.get_setting('downloads.albumImageFormat', 'jpg')
            
            # Save album artwork to main album directory
            album_dir = self._create_album_directory()
            album_filename = f"{album_template}.{album_format}"
            main_album_path = album_dir / album_filename
            
            if not main_album_path.exists():
                with open(main_album_path, 'wb') as f:
                    f.write(artwork_data)
                logger.info(f"[DownloadWorker] Album cover saved to main album directory: {main_album_path}")
            
            # Distribute to all CD subfolders
            self._distribute_artwork_to_cd_folders(artwork_data, album_template, album_format)
            
            # Cache artwork data for individual track processing
            self._cached_album_artwork = artwork_data
            
        except Exception as e:
            logger.error(f"[DownloadWorker] Error preparing album artwork for multi-disc: {e}")
    
    def _save_artist_artwork(self, artist_dir: Path, artist_template: str, artist_format: str):
        """Save actual artist artwork to artist directory."""
        try:
            artist_filename = f"{artist_template}.{artist_format}"
            artist_path = artist_dir / artist_filename
            
            # Only save if it doesn't exist (avoid overwriting)
            if artist_path.exists():
    
                return
                
            # Get artist image URL from track info
            artist_image_url = None
            artist_artwork_size = self.config.get_setting('downloads.artistArtworkSize', 1200)
            
            # Try to get from current track being processed
            current_track = getattr(self, '_current_track_info', None)
            if current_track:
                # Try to get the best quality artist image and modify URL for correct size
                if 'artist' in current_track and isinstance(current_track['artist'], dict):
                    artist_data = current_track['artist']
                    base_url = None
                    if artist_artwork_size >= 1000 and 'picture_xl' in artist_data:
                        base_url = artist_data['picture_xl']
                    elif artist_artwork_size >= 500 and 'picture_big' in artist_data:
                        base_url = artist_data['picture_big']
                    elif 'picture_medium' in artist_data:
                        base_url = artist_data['picture_medium']
                    
                    # Modify URL to use the configured size instead of the default size
                    if base_url and 'dzcdn.net' in base_url:
                        # Replace any existing size (like 1000x1000) with the configured size
                        size_pattern = r'/\d+x\d+-'
                        new_size = f'/{artist_artwork_size}x{artist_artwork_size}-'
                        artist_image_url = re.sub(size_pattern, new_size, base_url)
                
                # Fallback to private API structure using art_picture
                if not artist_image_url and 'art_picture' in current_track:
                    artist_md5 = current_track.get('art_picture')
                    if artist_md5:
                        size_str = f"{artist_artwork_size}x{artist_artwork_size}"
                        artist_image_url = f"https://e-cdns-images.dzcdn.net/images/artist/{artist_md5}/{size_str}-000000-80-0-0.jpg"
            
            if artist_image_url:

                import requests
                artist_response = requests.get(artist_image_url, timeout=15)
                artist_response.raise_for_status()
                
                with open(artist_path, 'wb') as f:
                    f.write(artist_response.content)
                logger.info(f"[DownloadWorker] Artist image saved to {artist_path}")
            else:
                pass  # No artist image URL available
                
        except Exception as e:
            logger.warning(f"[DownloadWorker] Failed to save artist image: {e}")
    
    def _download_and_embed_lyrics(self, file_path: Path, track_info: TrackInfo):
        """Download and embed lyrics if enabled in settings."""
        try:
            # Check master lyrics switch first
            lyrics_enabled = self.config.get_setting('lyrics.enabled', True)
            if not lyrics_enabled:
                logger.debug(f"[DownloadWorker] Lyrics processing disabled in settings")
                return
            
            # Check if any lyrics feature is enabled
            lrc_enabled = self.config.get_setting('lyrics.lrc_enabled', True)
            txt_enabled = self.config.get_setting('lyrics.txt_enabled', True)
            embed_sync_lyrics = self.config.get_setting('lyrics.embed_sync_lyrics', True)
            embed_plain_lyrics = self.config.get_setting('lyrics.embed_plain_lyrics', False)
            
            # Skip if no lyrics features are enabled
            if not any([lrc_enabled, txt_enabled, embed_sync_lyrics, embed_plain_lyrics]):
                return
            
            # Validate track_info and track_id
            if not track_info or not track_info.track_id:
                logger.debug(f"[DownloadWorker] No valid track_id for lyrics: {track_info.title if track_info else 'Unknown'}")
                return
            
            # Additional validation: ensure file exists and is accessible
            if not file_path or not file_path.exists():
                logger.error(f"[DownloadWorker] Audio file does not exist for lyrics processing: {file_path}")
                return
            
            # Check if file is being used by another process
            try:
                # Test file access before proceeding
                with open(file_path, 'r+b') as test_file:
                    pass
            except (PermissionError, IOError) as e:
                logger.warning(f"[DownloadWorker] Cannot access audio file for lyrics embedding, skipping: {e}")
                return
            
            # Ensure track_id is valid integer
            try:
                track_id_int = int(track_info.track_id)
                if track_id_int <= 0:
                    logger.debug(f"[DownloadWorker] Invalid track_id for lyrics: {track_id_int}")
                    return
            except (ValueError, TypeError) as e:
                logger.error(f"[DownloadWorker] Cannot convert track_id to int: {track_info.track_id}, error: {e}")
                return
            
            # Get lyrics from Deezer API with error handling and timeout
            try:
                # Add timeout protection to prevent hanging
                # Note: signal module timeout only works on Unix-like systems
                lyrics_data = None
                
                if hasattr(signal, 'SIGALRM'):  # Unix-like systems
                    def timeout_handler(signum, frame):
                        raise TimeoutError("Lyrics API request timed out")
                    
                    # Set a 30-second timeout for lyrics fetching
                    signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(30)
                    
                    try:
                        lyrics_data = self.deezer_api.get_track_lyrics_sync(track_id_int)
                    finally:
                        signal.alarm(0)  # Cancel the alarm
                else:
                    # Windows - no signal-based timeout, just make the call
                    logger.debug(f"[DownloadWorker] Signal timeout not available on this platform, proceeding without timeout")
                    lyrics_data = self.deezer_api.get_track_lyrics_sync(track_id_int)
                    
            except TimeoutError:
                logger.warning(f"[DownloadWorker] Lyrics API request timed out for track {track_id_int}")
                return
            except Exception as e:
                logger.error(f"[DownloadWorker] Error fetching lyrics from API for track {track_id_int}: {e}")
                return
                
            if not lyrics_data:
                logger.debug(f"[DownloadWorker] No lyrics found for track: {track_info.title}")
                return
            
            # Parse lyrics data with error handling
            try:
                processed_lyrics = LyricsProcessor.parse_deezer_lyrics(lyrics_data)
            except Exception as e:
                logger.error(f"[DownloadWorker] Error parsing lyrics data for track {track_info.title}: {e}")
                return
                
            if not processed_lyrics or (not processed_lyrics.get('sync_lyrics') and not processed_lyrics.get('plain_text')):
                logger.debug(f"[DownloadWorker] No usable lyrics data for track: {track_info.title}")
                return
            
            logger.info(f"[DownloadWorker] Processing lyrics for: {track_info.title}")
            
            # Get lyrics settings
            lyrics_location = self.config.get_setting('lyrics.location', 'With Audio Files')
            custom_path = self.config.get_setting('lyrics.custom_path', '')
            sync_offset = self.config.get_setting('lyrics.sync_offset', 0)
            encoding = self.config.get_setting('lyrics.encoding', 'UTF-8')
            
            # Save LRC file if enabled and sync lyrics available
            if lrc_enabled and processed_lyrics.get('sync_lyrics'):
                try:
                    lrc_path = LyricsProcessor.get_lyrics_file_path(
                        file_path, lyrics_location, custom_path, 'lrc'
                    )
                    
                    # Create track info dict for LRC headers
                    track_info_dict = {
                        'title': track_info.title or 'Unknown Title',
                        'artist': track_info.artist or 'Unknown Artist',
                        'alb_title': self.item.title or 'Unknown Album'
                    }
                    
                    lrc_content = LyricsProcessor.create_lrc_content(
                        processed_lyrics['sync_lyrics'], track_info_dict, sync_offset
                    )
                    
                    if lrc_content:
                        success = LyricsProcessor.save_lrc_file(lrc_content, lrc_path, encoding)
                        if success:
                            logger.info(f"[DownloadWorker] LRC file saved: {lrc_path}")
                except Exception as e:
                    logger.error(f"[DownloadWorker] Error saving LRC file for {track_info.title}: {e}")
            
            # Save TXT file if enabled and plain text available
            if txt_enabled and processed_lyrics.get('plain_text'):
                try:
                    txt_path = LyricsProcessor.get_lyrics_file_path(
                        file_path, lyrics_location, custom_path, 'txt'
                    )
                    
                    success = LyricsProcessor.save_plain_lyrics(
                        processed_lyrics['plain_text'], txt_path, encoding
                    )
                    if success:
                        logger.info(f"[DownloadWorker] TXT file saved: {txt_path}")
                except Exception as e:
                    logger.error(f"[DownloadWorker] Error saving TXT file for {track_info.title}: {e}")
            
            # Embed synchronized lyrics in audio file if enabled
            if embed_sync_lyrics and processed_lyrics.get('sync_lyrics'):
                try:
                    # Add file locking protection for embedded lyrics operations
                    import fcntl
                    try:
                        with open(file_path, 'r+b') as lock_file:
                            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                            try:
                                self._embed_sync_lyrics_in_file(file_path, processed_lyrics['sync_lyrics'])
                            finally:
                                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    except (OSError, IOError) as lock_error:
                        # File locking not supported on Windows, proceed without locking
                        if "Operation not supported" in str(lock_error) or "Invalid argument" in str(lock_error):
                            self._embed_sync_lyrics_in_file(file_path, processed_lyrics['sync_lyrics'])
                        else:
                            raise
                except Exception as e:
                    logger.error(f"[DownloadWorker] Error embedding sync lyrics for {track_info.title}: {e}")
            
            # Embed plain text lyrics in audio file if enabled
            if embed_plain_lyrics and processed_lyrics.get('plain_text'):
                try:
                    # Add file locking protection for embedded lyrics operations
                    import fcntl
                    try:
                        with open(file_path, 'r+b') as lock_file:
                            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                            try:
                                self._embed_plain_lyrics_in_file(file_path, processed_lyrics['plain_text'])
                            finally:
                                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    except (OSError, IOError) as lock_error:
                        # File locking not supported on Windows, proceed without locking
                        if "Operation not supported" in str(lock_error) or "Invalid argument" in str(lock_error):
                            self._embed_plain_lyrics_in_file(file_path, processed_lyrics['plain_text'])
                        else:
                            raise
                except Exception as e:
                    logger.error(f"[DownloadWorker] Error embedding plain lyrics for {track_info.title}: {e}")
                
        except Exception as e:
            logger.error(f"[DownloadWorker] Error processing lyrics for {track_info.title if track_info else 'Unknown'}: {e}")
    
    def _embed_sync_lyrics_in_file(self, file_path: Path, sync_lyrics: list):
        """Embed synchronized lyrics in audio file."""
        try:
            if file_path.suffix.lower() == '.mp3':
                self._embed_sync_lyrics_mp3(file_path, sync_lyrics)
            elif file_path.suffix.lower() == '.flac':
                self._embed_sync_lyrics_flac(file_path, sync_lyrics)
                
        except Exception as e:
            logger.error(f"[DownloadWorker] Error embedding synchronized lyrics: {e}")
    
    def _embed_plain_lyrics_in_file(self, file_path: Path, plain_lyrics: str):
        """Embed plain text lyrics in audio file."""
        try:
            if file_path.suffix.lower() == '.mp3':
                self._embed_plain_lyrics_mp3(file_path, plain_lyrics)
            elif file_path.suffix.lower() == '.flac':
                self._embed_plain_lyrics_flac(file_path, plain_lyrics)
                
        except Exception as e:
            logger.error(f"[DownloadWorker] Error embedding plain lyrics: {e}")
    
    def _embed_sync_lyrics_mp3(self, file_path: Path, sync_lyrics: list):
        """Embed synchronized lyrics in MP3 file using SYLT tag."""
        try:
            # Validate inputs
            if not file_path or not file_path.exists():
                logger.error(f"[DownloadWorker] MP3 file does not exist for lyrics embedding: {file_path}")
                return
                
            if not sync_lyrics or not isinstance(sync_lyrics, list):
                logger.debug(f"[DownloadWorker] No valid sync lyrics data for MP3 embedding")
                return
            
            # Add retry mechanism for file access
            max_retries = 3
            retry_delay = 0.5
            
            for attempt in range(max_retries):
                try:
                    # Load MP3 file safely with timeout protection
                    import signal
                    
                    def timeout_handler(signum, frame):
                        raise TimeoutError("MP3 file loading timed out")
                    
                    # Set a 10-second timeout for file operations
                    signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(10)
                    
                    try:
                        audio = MP3(str(file_path), ID3=ID3)
                        break  # Success, exit retry loop
                    finally:
                        signal.alarm(0)  # Cancel the alarm
                        
                except TimeoutError:
                    logger.warning(f"[DownloadWorker] MP3 file loading timed out, attempt {attempt + 1}/{max_retries}")
                    if attempt == max_retries - 1:
                        logger.error(f"[DownloadWorker] Failed to load MP3 file after {max_retries} attempts: {file_path}")
                        return
                    time.sleep(retry_delay)
                    continue
                except Exception as e:
                    logger.error(f"[DownloadWorker] Error loading MP3 file for lyrics: {file_path}, error: {e}")
                    if attempt == max_retries - 1:
                        return
                    time.sleep(retry_delay)
                    continue
            
            # Add ID3 tag if it doesn't exist
            if audio.tags is None:
                try:
                    audio.add_tags()
                except Exception as e:
                    logger.error(f"[DownloadWorker] Error adding ID3 tags to MP3: {e}")
                    return
            
            # Remove existing synchronized lyrics with safety check
            try:
                if hasattr(audio.tags, 'delall'):
                    audio.tags.delall('SYLT')
                else:
                    # Fallback for older mutagen versions
                    for tag in list(audio.tags.keys()):
                        if tag.startswith('SYLT'):
                            del audio.tags[tag]
            except Exception as e:
                logger.warning(f"[DownloadWorker] Error removing existing SYLT tags: {e}")
            
            # Convert sync_lyrics to SYLT format with enhanced validation
            sylt_data = []
            for line in sync_lyrics:
                if not isinstance(line, dict):
                    continue
                    
                timestamp_str = line.get('timestamp', '')
                text = line.get('text', '')
                
                if timestamp_str and text:
                    # Parse LRC timestamp [mm:ss.xx] to milliseconds
                    try:
                        import re
                        match = re.match(r'\[(\d{2}):(\d{2})\.(\d{2})\]', timestamp_str)
                        if match:
                            minutes = int(match.group(1))
                            seconds = int(match.group(2))
                            centiseconds = int(match.group(3))
                            timestamp_ms = (minutes * 60 * 1000) + (seconds * 1000) + (centiseconds * 10)
                            
                            # Validate timestamp range
                            if 0 <= timestamp_ms <= 7200000:  # Max 2 hours
                                # Sanitize text to prevent encoding issues
                                sanitized_text = text.encode('utf-8', errors='replace').decode('utf-8')
                                sylt_data.append((sanitized_text, timestamp_ms))
                    except Exception as e:
                        logger.warning(f"[DownloadWorker] Error parsing timestamp {timestamp_str}: {e}")
                        continue
            
            if sylt_data:
                try:
                    # Limit the number of lyrics lines to prevent memory issues
                    if len(sylt_data) > 1000:
                        logger.warning(f"[DownloadWorker] Truncating lyrics to 1000 lines (was {len(sylt_data)})")
                        sylt_data = sylt_data[:1000]
                    
                    # Add synchronized lyrics tag with proper encoding
                    audio.tags.add(
                        SYLT(
                            encoding=3,  # UTF-8
                            lang='eng',  # Language
                            format=2,    # Absolute time in milliseconds
                            type=1,      # Lyrics
                            text=sylt_data
                        )
                    )
                    
                    # Save with error handling and backup
                    try:
                        # Create backup before saving
                        backup_path = file_path.with_suffix(file_path.suffix + '.backup')
                        shutil.copy2(file_path, backup_path)
                        
                        audio.save()
                        
                        # Remove backup if save successful
                        if backup_path.exists():
                            backup_path.unlink()
                            
                        logger.debug(f"[DownloadWorker] Embedded synchronized lyrics in MP3: {len(sylt_data)} lines")
                    except Exception as save_error:
                        logger.error(f"[DownloadWorker] Error saving MP3 with sync lyrics: {save_error}")
                        
                        # Restore backup if save failed
                        if backup_path.exists():
                            shutil.move(backup_path, file_path)
                            logger.info(f"[DownloadWorker] Restored MP3 backup after save failure")
                        
                except Exception as e:
                    logger.error(f"[DownloadWorker] Error adding SYLT tag to MP3: {e}")
                
        except Exception as e:
            logger.error(f"[DownloadWorker] Error embedding MP3 synchronized lyrics: {e}")
    
    def _embed_plain_lyrics_mp3(self, file_path: Path, plain_lyrics: str):
        """Embed plain text lyrics in MP3 file using USLT tag."""
        try:
            # Validate inputs
            if not file_path or not file_path.exists():
                logger.error(f"[DownloadWorker] MP3 file does not exist for lyrics embedding: {file_path}")
                return
                
            if not plain_lyrics or not isinstance(plain_lyrics, str):
                logger.debug(f"[DownloadWorker] No valid plain lyrics data for MP3 embedding")
                return
            
            # Sanitize lyrics text to prevent encoding issues
            try:
                sanitized_lyrics = plain_lyrics.encode('utf-8', errors='replace').decode('utf-8')
                # Limit lyrics length to prevent memory issues
                if len(sanitized_lyrics) > 10000:
                    logger.warning(f"[DownloadWorker] Truncating lyrics to 10000 characters (was {len(sanitized_lyrics)})")
                    sanitized_lyrics = sanitized_lyrics[:10000] + "...\n[Lyrics truncated]"
            except Exception as e:
                logger.error(f"[DownloadWorker] Error sanitizing lyrics text: {e}")
                return
            
            # Load MP3 file safely with retry mechanism
            max_retries = 3
            retry_delay = 0.5
            
            for attempt in range(max_retries):
                try:
                    audio = MP3(str(file_path), ID3=ID3)
                    break  # Success, exit retry loop
                except Exception as e:
                    logger.warning(f"[DownloadWorker] Error loading MP3 file for plain lyrics, attempt {attempt + 1}/{max_retries}: {e}")
                    if attempt == max_retries - 1:
                        logger.error(f"[DownloadWorker] Failed to load MP3 file after {max_retries} attempts: {file_path}")
                        return
                    time.sleep(retry_delay)
                    continue
            
            # Add ID3 tag if it doesn't exist
            if audio.tags is None:
                try:
                    audio.add_tags()
                except Exception as e:
                    logger.error(f"[DownloadWorker] Error adding ID3 tags to MP3: {e}")
                    return
            
            # Remove existing unsynchronized lyrics with safety check
            try:
                if hasattr(audio.tags, 'delall'):
                    audio.tags.delall('USLT')
                else:
                    # Fallback for older mutagen versions
                    for tag in list(audio.tags.keys()):
                        if tag.startswith('USLT'):
                            del audio.tags[tag]
            except Exception as e:
                logger.warning(f"[DownloadWorker] Error removing existing USLT tags: {e}")
            
            # Add unsynchronized lyrics tag
            try:
                audio.tags.add(
                    USLT(
                        encoding=3,  # UTF-8
                        lang='eng',  # Language
                        desc='',     # Description
                        text=sanitized_lyrics
                    )
                )
                
                # Save with error handling and backup
                try:
                    # Create backup before saving
                    backup_path = file_path.with_suffix(file_path.suffix + '.backup')
                    shutil.copy2(file_path, backup_path)
                    
                    audio.save()
                    
                    # Remove backup if save successful
                    if backup_path.exists():
                        backup_path.unlink()
                        
                    logger.debug(f"[DownloadWorker] Embedded plain lyrics in MP3")
                except Exception as save_error:
                    logger.error(f"[DownloadWorker] Error saving MP3 with plain lyrics: {save_error}")
                    
                    # Restore backup if save failed
                    if backup_path.exists():
                        shutil.move(backup_path, file_path)
                        logger.info(f"[DownloadWorker] Restored MP3 backup after save failure")
                        
            except Exception as e:
                logger.error(f"[DownloadWorker] Error adding USLT tag to MP3: {e}")
            
        except Exception as e:
            logger.error(f"[DownloadWorker] Error embedding MP3 plain lyrics: {e}")
    
    def _embed_sync_lyrics_flac(self, file_path: Path, sync_lyrics: list):
        """Embed synchronized lyrics in FLAC file as custom LYRICS tag."""
        try:
            # Validate inputs
            if not file_path or not file_path.exists():
                logger.error(f"[DownloadWorker] FLAC file does not exist for lyrics embedding: {file_path}")
                return
                
            if not sync_lyrics or not isinstance(sync_lyrics, list):
                logger.debug(f"[DownloadWorker] No valid sync lyrics data for FLAC embedding")
                return
            
            # Load FLAC file safely with retry mechanism
            max_retries = 3
            retry_delay = 0.5
            
            for attempt in range(max_retries):
                try:
                    audio = FLAC(str(file_path))
                    break  # Success, exit retry loop
                except Exception as e:
                    logger.warning(f"[DownloadWorker] Error loading FLAC file for sync lyrics, attempt {attempt + 1}/{max_retries}: {e}")
                    if attempt == max_retries - 1:
                        logger.error(f"[DownloadWorker] Failed to load FLAC file after {max_retries} attempts: {file_path}")
                        return
                    time.sleep(retry_delay)
                    continue
            
            # Create LRC format text for FLAC
            lrc_lines = []
            for line in sync_lyrics:
                if not isinstance(line, dict):
                    continue
                    
                timestamp = line.get('timestamp', '')
                text = line.get('text', '')
                if timestamp and text:
                    # Sanitize text to prevent encoding issues
                    sanitized_text = text.encode('utf-8', errors='replace').decode('utf-8')
                    lrc_lines.append(f"{timestamp} {sanitized_text}")
            
            if lrc_lines:
                try:
                    # Limit the number of lyrics lines to prevent memory issues
                    if len(lrc_lines) > 1000:
                        logger.warning(f"[DownloadWorker] Truncating FLAC lyrics to 1000 lines (was {len(lrc_lines)})")
                        lrc_lines = lrc_lines[:1000]
                        lrc_lines.append("[Lyrics truncated]")
                    
                    # Store as LYRICS tag (some players support this)
                    lyrics_content = '\n'.join(lrc_lines)
                    
                    # Limit total lyrics length to prevent memory issues
                    if len(lyrics_content) > 50000:
                        logger.warning(f"[DownloadWorker] Truncating FLAC lyrics content to 50000 characters (was {len(lyrics_content)})")
                        lyrics_content = lyrics_content[:50000] + "\n[Lyrics truncated]"
                    
                    audio['LYRICS'] = lyrics_content
                    
                    # Save with error handling and backup
                    try:
                        # Create backup before saving
                        backup_path = file_path.with_suffix(file_path.suffix + '.backup')
                        shutil.copy2(file_path, backup_path)
                        
                        audio.save()
                        
                        # Remove backup if save successful
                        if backup_path.exists():
                            backup_path.unlink()
                            
                        logger.debug(f"[DownloadWorker] Embedded synchronized lyrics in FLAC: {len(lrc_lines)} lines")
                    except Exception as save_error:
                        logger.error(f"[DownloadWorker] Error saving FLAC with sync lyrics: {save_error}")
                        
                        # Restore backup if save failed
                        if backup_path.exists():
                            shutil.move(backup_path, file_path)
                            logger.info(f"[DownloadWorker] Restored FLAC backup after save failure")
                        
                except Exception as e:
                    logger.error(f"[DownloadWorker] Error adding LYRICS tag to FLAC: {e}")
                
        except Exception as e:
            logger.error(f"[DownloadWorker] Error embedding FLAC synchronized lyrics: {e}")
    
    def _embed_plain_lyrics_flac(self, file_path: Path, plain_lyrics: str):
        """Embed plain text lyrics in FLAC file."""
        try:
            # Validate inputs
            if not file_path or not file_path.exists():
                logger.error(f"[DownloadWorker] FLAC file does not exist for lyrics embedding: {file_path}")
                return
                
            if not plain_lyrics or not isinstance(plain_lyrics, str):
                logger.debug(f"[DownloadWorker] No valid plain lyrics data for FLAC embedding")
                return
            
            # Sanitize lyrics text to prevent encoding issues
            try:
                sanitized_lyrics = plain_lyrics.encode('utf-8', errors='replace').decode('utf-8')
                # Limit lyrics length to prevent memory issues
                if len(sanitized_lyrics) > 50000:
                    logger.warning(f"[DownloadWorker] Truncating FLAC lyrics to 50000 characters (was {len(sanitized_lyrics)})")
                    sanitized_lyrics = sanitized_lyrics[:50000] + "...\n[Lyrics truncated]"
            except Exception as e:
                logger.error(f"[DownloadWorker] Error sanitizing FLAC lyrics text: {e}")
                return
            
            # Load FLAC file safely with retry mechanism
            max_retries = 3
            retry_delay = 0.5
            
            for attempt in range(max_retries):
                try:
                    audio = FLAC(str(file_path))
                    break  # Success, exit retry loop
                except Exception as e:
                    logger.warning(f"[DownloadWorker] Error loading FLAC file for plain lyrics, attempt {attempt + 1}/{max_retries}: {e}")
                    if attempt == max_retries - 1:
                        logger.error(f"[DownloadWorker] Failed to load FLAC file after {max_retries} attempts: {file_path}")
                        return
                    time.sleep(retry_delay)
                    continue
            
            # Add plain text lyrics
            try:
                audio['LYRICS'] = sanitized_lyrics
                
                # Save with error handling and backup
                try:
                    # Create backup before saving
                    backup_path = file_path.with_suffix(file_path.suffix + '.backup')
                    shutil.copy2(file_path, backup_path)
                    
                    audio.save()
                    
                    # Remove backup if save successful
                    if backup_path.exists():
                        backup_path.unlink()
                        
                    logger.debug(f"[DownloadWorker] Embedded plain lyrics in FLAC")
                except Exception as save_error:
                    logger.error(f"[DownloadWorker] Error saving FLAC with plain lyrics: {save_error}")
                    
                    # Restore backup if save failed
                    if backup_path.exists():
                        shutil.move(backup_path, file_path)
                        logger.info(f"[DownloadWorker] Restored FLAC backup after save failure")
                        
            except Exception as e:
                logger.error(f"[DownloadWorker] Error adding LYRICS tag to FLAC: {e}")
            
        except Exception as e:
            logger.error(f"[DownloadWorker] Error embedding FLAC plain lyrics: {e}")
    
    def _create_album_directory(self) -> Path:
        """Create directory structure for album."""
        base_path = self.download_path
        
        if self.create_artist_folders:
            album_artist = self._build_album_artist_for_metadata()
            artist_name = self._sanitize_filename(album_artist)
            base_path = base_path / artist_name
        
        if self.create_album_folders:
            album_name = self._sanitize_filename(self.item.title)
            base_path = base_path / album_name
        
        base_path.mkdir(parents=True, exist_ok=True)
        return base_path

    def _create_track_directory(self, track_info: TrackInfo) -> Path:
        """Create directory structure for individual track, including disc folders if needed."""
        base_path = self._create_album_directory()
        
        # Check if CD folders should be created for multi-disc albums
        create_cd_folders = self.config.get_setting('downloads.folder_structure.create_cd_folders', True)
        
        if create_cd_folders and self._is_multi_disc_album():
            # Get the CD folder template
            cd_template = self.config.get_setting('downloads.folder_structure.templates.cd', 'CD %disc_number%')
            
            # Create disc-specific folder
            disc_number = track_info.disc_number or 1
            cd_folder_name = cd_template.replace('%disc_number%', str(disc_number))
            cd_folder_name = self._sanitize_filename(cd_folder_name)
            base_path = base_path / cd_folder_name
        
        base_path.mkdir(parents=True, exist_ok=True)
        return base_path

    def _get_artist_directory(self) -> Path:
        """Get the artist directory path (without album or disc folders)."""
        if not self.create_artist_folders:
            return self.download_path
        
        album_artist = self._build_album_artist_for_metadata()
        artist_name = self._sanitize_filename(album_artist)
        return self.download_path / artist_name

    def _is_multi_disc_album(self) -> bool:
        """Check if this is a multi-disc album by examining all track disc numbers."""
        if not self.item.tracks:
            return False
        
        disc_numbers = set()
        for track in self.item.tracks:
            disc_number = track.disc_number or 1
            disc_numbers.add(disc_number)
        
        # Multi-disc if we have more than one disc number
        return len(disc_numbers) > 1
    
    def _create_filename(self, track_info: TrackInfo, playlist_position: int = 1) -> str:
        """Create filename for track."""
        # Determine file extension based on quality
        if self.quality.startswith('FLAC'):
            ext = '.flac'
        else:
            ext = '.mp3'
        
        # Get filename template from config based on item type
        if self.item.item_type == ItemType.PLAYLIST:
            template = self.config.get_setting('downloads.filename_templates.playlist_track', '{playlist_position:02d} - {artist} - {title}')
        elif self._is_compilation_album():
            template = self.config.get_setting('downloads.filename_templates.compilation_track', '{track_number:02d} - {artist} - {title}')
        else:
            template = self.config.get_setting('downloads.filename_templates.album_track', '{track_number:02d} - {album_artist} - {title}')
        
        # Create template variables
        album_artist = self._build_album_artist_for_metadata()
        template_vars = {
            'track_number': track_info.track_number or 1,
            'playlist_position': playlist_position,  # Use the passed playlist position
            'title': track_info.title,
            'artist': track_info.artist,
            'album_artist': album_artist,  # Album artist (compilation-aware)
            'album': self.item.title,  # Album/Playlist title
            'disc_number': track_info.disc_number or 1
        }
        
        # Apply template
        try:
            filename = template.format(**template_vars)
        except (KeyError, ValueError) as e:
            logger.warning(f"[DownloadWorker] Error applying filename template '{template}': {e}")
            # Fallback to simple format
            filename = f"{track_info.track_number:02d} - {track_info.title}"
        
        # Sanitize filename
        filename = self._sanitize_filename(filename)
        return filename + ext
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for filesystem compatibility."""
        # Check if character replacement is enabled
        if self.config.get_setting('downloads.character_replacement.enabled', True):
            # Get custom replacements from config
            custom_replacements = self.config.get_setting('downloads.character_replacement.custom_replacements', {})
            default_replacement = self.config.get_setting('downloads.character_replacement.replacement_char', '_')
            
            # Apply custom replacements first
            for char, replacement in custom_replacements.items():
                filename = filename.replace(char, replacement)
            
            # Handle any remaining invalid characters with default replacement
            remaining_invalid_chars = '<>:"/\\|?*'
            for char in remaining_invalid_chars:
                if char not in custom_replacements:
                    filename = filename.replace(char, default_replacement)
        else:
            # Fallback to default behavior if disabled
            invalid_chars = '<>:"/\\|?*'
            for char in invalid_chars:
                filename = filename.replace(char, '_')
        
        # Remove leading/trailing spaces and dots
        filename = filename.strip(' .')
        
        # Limit length to avoid Windows path length issues
        # Windows has a 260 character path limit, so we need to be conservative
        if len(filename) > 150:
            filename = filename[:150]
        
        return filename
    
    def is_finished(self) -> bool:
        """Check if worker is finished (for cleanup purposes)."""
        return self.cancelled or not hasattr(self, '_running') or not self._running


# Example usage and testing
if __name__ == "__main__":
    # This would be used for testing the download worker
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    
    from src.models.queue_models import QueueItem, TrackInfo, ItemType
    from src.services.event_bus import get_event_bus
    
    # Mock config manager for testing
    class MockConfig:
        def get_setting(self, key, default=None):
            settings = {
                'downloads.quality': 'MP3_320',
                'downloads.path': 'test_downloads',
                'downloads.folder_structure.create_artist_folders': True,
                'downloads.folder_structure.create_album_folders': True
            }
            return settings.get(key, default)
    
    # Mock Deezer API for testing
    class MockDeezerAPI:
        def get_track_download_url_sync(self, track_id, quality='MP3_320'):
            return f"https://mock-download-url.com/{track_id}"
    
    # Test the download worker
    track = TrackInfo(
        track_id=123,
        title="Test Track",
        artist="Test Artist",
        duration=180,
        track_number=1
    )
    
    item = QueueItem.create_album(
        deezer_id=456,
        title="Test Album",
        artist="Test Artist",
        tracks=[track]
    )
    
    config = MockConfig()
    deezer_api = MockDeezerAPI()
    event_bus = get_event_bus()
    
    # Create and test worker
    worker = DownloadWorker(item, deezer_api, config, event_bus)
    print(f"Created worker for: {worker.item.title}")
    
    # Test cancellation
    worker.cancel()
    print(f"Worker cancelled: {worker.cancelled}")