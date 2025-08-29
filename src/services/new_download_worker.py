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
    
    def __init__(self, parent_worker, track_info, album_dir, playlist_position):
        super().__init__()
        self.parent_worker = parent_worker
        self.track_info = track_info
        self.album_dir = album_dir
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
                self.album_dir, 
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
        
        # Create album directory
        album_dir = self._create_album_directory()
        
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
                    album_dir=album_dir,
                    playlist_position=i+1
                )
                
                track_workers.append(track_worker)
                self.track_thread_pool.start(track_worker)
            
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
        # Similar to album download but with playlist-specific logic
        self._download_album()  # For now, use same logic as album
    
    def _download_single_track(self):
        """Download a single track."""
        if not self.item.tracks:
            raise ValueError("No track information available")
        
        track_info = self.item.tracks[0]
        
        # Create directory for single track
        if self.create_artist_folders:
            track_dir = self.download_path / self._sanitize_filename(self.item.artist)
        else:
            track_dir = self.download_path
        
        track_dir.mkdir(parents=True, exist_ok=True)
        
        success = self._download_track(track_info, track_dir, playlist_position=1)
        
        if success:
            self.event_bus.emit(DownloadEvents.TRACK_COMPLETED, self.item.id, track_info.track_id)
            self.event_bus.emit(DownloadEvents.DOWNLOAD_PROGRESS, self.item.id, 1.0, 1, 0)
        else:
            raise Exception("Failed to download track")
    
    def _download_track(self, track_info: TrackInfo, output_dir: Path, playlist_position: int = 1) -> bool:
        """
        Download a single track.
        
        Args:
            track_info: Track information
            output_dir: Directory to save the track
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
            download_url = self.deezer_api.get_track_download_url_sync(
                track_info.track_id, 
                quality=self.quality
            )
            
            if not download_url or isinstance(download_url, str) and download_url.startswith(('RIGHTS_ERROR:', 'API_ERROR:')):
                logger.warning(f"[DownloadWorker] Cannot get download URL for track {track_info.track_id}: {download_url}")
                return False
            
            # Handle quality skip
            if isinstance(download_url, str) and download_url.startswith('QUALITY_SKIP:'):
                logger.info(f"[DownloadWorker] Skipping track {track_info.track_id}: {download_url}")
                return False
            
            # Create filename
            filename = self._create_filename(track_info, playlist_position=playlist_position)
            file_path = output_dir / filename
            
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
            
            # Get album cover URL
            album_cover_url = getattr(self.item, 'album_cover_url', None)
            if not album_cover_url:
                logger.warning(f"[DownloadWorker] No album cover URL available for {track_info.title}")
                return
            
            # Download artwork
            artwork_data = self._download_artwork(album_cover_url)
            if not artwork_data:
                return
            
            # Embed artwork in file
            if embed_artwork:
                self._embed_artwork_in_file(file_path, artwork_data)
            
            # Save artwork files
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
            
            # Save album artwork
            album_filename = f"{album_template}.{album_format}"
            album_path = directory / album_filename
            with open(album_path, 'wb') as f:
                f.write(artwork_data)

            
            # Save artist artwork (in parent directory) - but get the actual artist image
            if self.create_artist_folders:
                self._save_artist_artwork(directory.parent, artist_template, artist_format)
                
        except Exception as e:
            logger.error(f"[DownloadWorker] Error saving artwork files: {e}")
    
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
            
            # Ensure track_id is valid integer
            try:
                track_id_int = int(track_info.track_id)
                if track_id_int <= 0:
                    logger.debug(f"[DownloadWorker] Invalid track_id for lyrics: {track_id_int}")
                    return
            except (ValueError, TypeError) as e:
                logger.error(f"[DownloadWorker] Cannot convert track_id to int: {track_info.track_id}, error: {e}")
                return
            
            # Get lyrics from Deezer API with error handling
            try:
                lyrics_data = self.deezer_api.get_track_lyrics_sync(track_id_int)
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
                    self._embed_sync_lyrics_in_file(file_path, processed_lyrics['sync_lyrics'])
                except Exception as e:
                    logger.error(f"[DownloadWorker] Error embedding sync lyrics for {track_info.title}: {e}")
            
            # Embed plain text lyrics in audio file if enabled
            if embed_plain_lyrics and processed_lyrics.get('plain_text'):
                try:
                    self._embed_plain_lyrics_in_file(file_path, processed_lyrics['plain_text'])
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
            
            # Load MP3 file safely
            try:
                audio = MP3(str(file_path), ID3=ID3)
            except Exception as e:
                logger.error(f"[DownloadWorker] Error loading MP3 file for lyrics: {file_path}, error: {e}")
                return
            
            # Add ID3 tag if it doesn't exist
            if audio.tags is None:
                try:
                    audio.add_tags()
                except Exception as e:
                    logger.error(f"[DownloadWorker] Error adding ID3 tags to MP3: {e}")
                    return
            
            # Remove existing synchronized lyrics
            try:
                audio.tags.delall('SYLT')
            except Exception as e:
                logger.warning(f"[DownloadWorker] Error removing existing SYLT tags: {e}")
            
            # Convert sync_lyrics to SYLT format
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
                            sylt_data.append((text, timestamp_ms))
                    except Exception as e:
                        logger.warning(f"[DownloadWorker] Error parsing timestamp {timestamp_str}: {e}")
                        continue
            
            if sylt_data:
                try:
                    # Add synchronized lyrics tag
                    audio.tags.add(
                        SYLT(
                            encoding=3,  # UTF-8
                            lang='eng',  # Language
                            format=2,    # Absolute time in milliseconds
                            type=1,      # Lyrics
                            text=sylt_data
                        )
                    )
                    
                    audio.save()
                    logger.debug(f"[DownloadWorker] Embedded synchronized lyrics in MP3: {len(sylt_data)} lines")
                except Exception as e:
                    logger.error(f"[DownloadWorker] Error saving MP3 with sync lyrics: {e}")
                
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
            
            # Load MP3 file safely
            try:
                audio = MP3(str(file_path), ID3=ID3)
            except Exception as e:
                logger.error(f"[DownloadWorker] Error loading MP3 file for plain lyrics: {file_path}, error: {e}")
                return
            
            # Add ID3 tag if it doesn't exist
            if audio.tags is None:
                try:
                    audio.add_tags()
                except Exception as e:
                    logger.error(f"[DownloadWorker] Error adding ID3 tags to MP3: {e}")
                    return
            
            # Remove existing unsynchronized lyrics
            try:
                audio.tags.delall('USLT')
            except Exception as e:
                logger.warning(f"[DownloadWorker] Error removing existing USLT tags: {e}")
            
            # Add unsynchronized lyrics tag
            try:
                audio.tags.add(
                    USLT(
                        encoding=3,  # UTF-8
                        lang='eng',  # Language
                        desc='',     # Description
                        text=plain_lyrics
                    )
                )
                
                audio.save()
                logger.debug(f"[DownloadWorker] Embedded plain lyrics in MP3")
            except Exception as e:
                logger.error(f"[DownloadWorker] Error saving MP3 with plain lyrics: {e}")
            
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
            
            # Load FLAC file safely
            try:
                audio = FLAC(str(file_path))
            except Exception as e:
                logger.error(f"[DownloadWorker] Error loading FLAC file for sync lyrics: {file_path}, error: {e}")
                return
            
            # Create LRC format text for FLAC
            lrc_lines = []
            for line in sync_lyrics:
                if not isinstance(line, dict):
                    continue
                    
                timestamp = line.get('timestamp', '')
                text = line.get('text', '')
                if timestamp and text:
                    lrc_lines.append(f"{timestamp} {text}")
            
            if lrc_lines:
                try:
                    # Store as LYRICS tag (some players support this)
                    audio['LYRICS'] = '\n'.join(lrc_lines)
                    audio.save()
                    logger.debug(f"[DownloadWorker] Embedded synchronized lyrics in FLAC: {len(lrc_lines)} lines")
                except Exception as e:
                    logger.error(f"[DownloadWorker] Error saving FLAC with sync lyrics: {e}")
                
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
            
            # Load FLAC file safely
            try:
                audio = FLAC(str(file_path))
            except Exception as e:
                logger.error(f"[DownloadWorker] Error loading FLAC file for plain lyrics: {file_path}, error: {e}")
                return
            
            # Add plain text lyrics
            try:
                audio['LYRICS'] = plain_lyrics
                audio.save()
                logger.debug(f"[DownloadWorker] Embedded plain lyrics in FLAC")
            except Exception as e:
                logger.error(f"[DownloadWorker] Error saving FLAC with plain lyrics: {e}")
            
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