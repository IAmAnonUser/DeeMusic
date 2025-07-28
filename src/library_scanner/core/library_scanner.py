"""
Music Library Scanner - Scans and extracts metadata from music files
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import json
import queue

from mutagen import File as MutagenFile  # type: ignore

logger = logging.getLogger(__name__)

@dataclass
class TrackInfo:
    """Information about a music track."""
    file_path: str
    title: str
    artist: str
    album: str
    album_artist: str
    track_number: int
    disc_number: int
    year: int
    duration: int  # in seconds
    genre: str
    file_size: int
    file_format: str
    bitrate: int
    sample_rate: int

class LibraryScanner:
    """Scans music library and extracts metadata."""
    
    def __init__(self, config):
        """Initialize the library scanner."""
        self.config = config
        self.tracks: List[TrackInfo] = []
        self.scan_progress = 0
        self.scan_total = 0
        self.scan_lock = threading.Lock()
        self.is_scanning = False
        self._album_key_lock = threading.Lock()  # Ensure lock is always available
        # Progress callbacks
        self.progress_callback = None
        self.status_callback = None
    
    def set_progress_callback(self, callback):
        """Set callback for progress updates."""
        self.progress_callback = callback
    
    def set_status_callback(self, callback):
        """Set callback for status updates."""
        self.status_callback = callback
    
    def _update_progress(self, current: int, total: int, status: str = ""):
        """Update scan progress."""
        with self.scan_lock:
            self.scan_progress = current
            self.scan_total = total
            
            if self.progress_callback:
                self.progress_callback(current, total)
            
            if self.status_callback and status:
                self.status_callback(status)
    
    def scan_library(self, library_paths: List[str], incremental: bool = False, last_scan_timestamp: Optional[str] = None) -> List[Dict]:
        print("scan_library called")
        try:
            scan_type = "incremental" if incremental else "full"
            logger.info(f"Starting {scan_type} album-level library scan of {len(library_paths)} paths")
            if self.status_callback:
                self.status_callback(f"Starting {scan_type} album-level scan...")
            self.is_scanning = True
            mtime_cache_path = Path(self.config.config_dir) / 'folder_mtimes.json'
            if mtime_cache_path.exists():
                with open(mtime_cache_path, 'r', encoding='utf-8') as f:
                    folder_mtimes = json.load(f)
            else:
                folder_mtimes = {}
            new_folder_mtimes = {}
            album_entries = []
            seen_album_keys = set()
            # --- Streaming producer-consumer model ---
            folder_queue = queue.Queue()
            discovered_folders = 0
            processed_folders = 0
            discovered_total = [0]  # Use list for mutability in closure
            processed_total = [0]
            max_workers = min(8, os.cpu_count() or 4)
            stop_sentinel = (None, None)
            # --- Worker function ---
            def process_album_folder():
                while True:
                    args = folder_queue.get()
                    try:
                        if args == stop_sentinel:
                            break
                        root, files = args
                        try:
                            music_files = [os.path.join(root, f) for f in files if self.config.is_supported_format(os.path.join(root, f))]
                            if not music_files:
                                logger.debug(f"No music files found in folder: {root}")
                                continue
                            logger.info(f"Found {len(music_files)} music files in folder: {root}")
                            track_infos = [self._extract_metadata(f) for f in music_files]
                            track_infos = [t for t in track_infos if t]
                            if not track_infos:
                                logger.warning(f"No valid metadata extracted from folder: {root}")
                                continue
                            logger.info(f"Extracted metadata from {len(track_infos)} tracks in folder: {root}")
                            # Find the most common album_artist and album from all tracks
                            # This is more robust than using just the first track
                            album_artists = [t.album_artist for t in track_infos if t.album_artist and t.album_artist.lower() != 'various artists']
                            albums = [t.album for t in track_infos if t.album]
                            
                            if not album_artists or not albums:
                                logger.warning(f"Skipping folder {root} - no valid album artist or album found")
                                continue
                            
                            # Use the most common values
                            from collections import Counter
                            album_artist = Counter(album_artists).most_common(1)[0][0]
                            album = Counter(albums).most_common(1)[0][0]
                            
                            logger.info(f"Processing album: '{album_artist}' - '{album}' in folder: {root}")
                            
                            if not album_artist or not album or album_artist.lower() == 'various artists':
                                logger.warning(f"Skipping album after processing: '{album_artist}' - '{album}'")
                                continue
                            album_key = f"{album_artist}|{album}"
                            with self._album_key_lock:
                                if album_key in seen_album_keys:
                                    continue
                                seen_album_keys.add(album_key)
                            year = min([t.year for t in track_infos if t.year > 0], default=0)
                            genre = track_infos[0].genre
                            num_tracks = len(track_infos)
                            total_duration = sum(t.duration for t in track_infos)
                            file_formats = list(set(t.file_format for t in track_infos))
                            album_entry = {
                                'album_artist': album_artist,
                                'album': album,
                                'folder_path': root,
                                'year': year,
                                'genre': genre,
                                'num_tracks': num_tracks,
                                'total_duration': total_duration,
                                'file_formats': file_formats,
                            }
                            logger.info(f"Added album: {album_artist} - {album} ({num_tracks} tracks)")
                            if self.status_callback:
                                self.status_callback(f"Processed album: {album_artist} - {album}")
                            album_entries.append(album_entry)
                        except Exception as e:
                            logger.error(f"Error processing folder {root}: {e}")
                        finally:
                            processed_total[0] += 1
                            if self.progress_callback:
                                self.progress_callback(processed_total[0], discovered_total[0])
                    finally:
                        folder_queue.task_done()
            # --- Start worker threads ---
            workers = []
            for _ in range(max_workers):
                t = threading.Thread(target=process_album_folder)
                t.daemon = True
                t.start()
                workers.append(t)
            # --- Producer: walk folders and stream to queue ---
            for path in library_paths:
                if not os.path.exists(path):
                    logger.warning(f"Library path does not exist: {path}")
                    continue
                for root, dirs, files in os.walk(path):
                    if not files:
                        continue
                    folder_mtime = os.path.getmtime(root)
                    new_folder_mtimes[root] = folder_mtime
                    prev_mtime = folder_mtimes.get(root)
                    if incremental and prev_mtime and prev_mtime == folder_mtime:
                        logger.info(f"Skipping unchanged folder: {root}")
                        continue  # Skip unchanged folders
                    folder_queue.put((root, files))
                    discovered_total[0] += 1
                    if self.progress_callback:
                        # Report discovered folders as total
                        self.progress_callback(processed_total[0], discovered_total[0])
            # --- Signal workers to stop ---
            for _ in range(max_workers):
                folder_queue.put(stop_sentinel)
            folder_queue.join()  # Wait for all tasks to finish
            for t in workers:
                t.join()
            # Post-scan cleanup: remove albums whose folders no longer exist
            if incremental and mtime_cache_path.exists():
                with open(mtime_cache_path, 'r', encoding='utf-8') as f:
                    old_folder_mtimes = json.load(f)
                album_entries = [a for a in album_entries if os.path.exists(a['folder_path'])]
            # Save new folder mtimes
            with open(mtime_cache_path, 'w', encoding='utf-8') as f:
                json.dump(new_folder_mtimes, f, indent=2)
            self.is_scanning = False
            logger.info(f"Album scan complete: {len(album_entries)} albums found.")
            if self.status_callback:
                self.status_callback(f"Album scan complete: {len(album_entries)} albums found.")
            if self.progress_callback:
                self.progress_callback(discovered_total[0], discovered_total[0])
            return album_entries
        except Exception as e:
            logger.error(f"Fatal error in scan_library: {e}", exc_info=True)
            if self.status_callback:
                self.status_callback(f"Scan failed: {e}")
            if self.progress_callback:
                self.progress_callback(0, 0)
            return []
    
    def _collect_music_files(self, root_path: str, incremental: bool = False, last_scan_timestamp: Optional[str] = None) -> List[str]:
        """Collect all music files from a directory.
        
        Args:
            root_path: Directory to scan
            incremental: If True, only return files modified after last_scan_timestamp
            last_scan_timestamp: ISO timestamp to compare file modification times against
        """
        music_files = []
        supported_formats = self.config.get_supported_formats()
        
        # Parse last scan timestamp for incremental scanning
        last_scan_time = None
        if incremental and last_scan_timestamp:
            try:
                from datetime import datetime
                last_scan_time = datetime.fromisoformat(last_scan_timestamp)
            except (ValueError, TypeError):
                logger.warning(f"Invalid last scan timestamp: {last_scan_timestamp}")
                incremental = False  # Fall back to full scan
        
        try:
            for root, dirs, files in os.walk(root_path):
                # Filter out hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                for file in files:
                    if file.startswith('.'):
                        continue
                    
                    file_path = os.path.join(root, file)
                    
                    # Check file extension
                    if not self.config.is_supported_format(file_path):
                        continue
                    
                    # Check file size (skip very small files)
                    try:
                        if os.path.getsize(file_path) < 1024:  # 1KB minimum
                            continue
                    except OSError:
                        continue
                    
                    # For incremental scans, check if file was modified after last scan
                    if incremental and last_scan_time:
                        try:
                            from datetime import datetime
                            file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                            if file_mtime <= last_scan_time:
                                continue  # File hasn't been modified since last scan
                        except OSError:
                            # If we can't get modification time, include the file to be safe
                            pass
                    
                    music_files.append(file_path)
        
        except Exception as e:
            logger.error(f"Error collecting files from {root_path}: {e}")
        
        return music_files
    
    def _extract_metadata(self, file_path: str) -> Optional[TrackInfo]:
        """Extract metadata from a music file."""
        try:
            # Use mutagen to read metadata
            audio_file = MutagenFile(file_path)
            if audio_file is None:
                logger.debug(f"Could not read metadata from {file_path}")
                return None
            
            # Get file info
            file_size = os.path.getsize(file_path)
            file_format = Path(file_path).suffix.lower()[1:]  # Remove the dot
            
            # Extract basic metadata
            title = self._get_tag(audio_file, ['TIT2', 'TITLE', '\xa9nam', 'Title'])
            artist = self._get_tag(audio_file, ['TPE1', 'ARTIST', '\xa9ART', 'Artist'])
            album = self._get_tag(audio_file, ['TALB', 'ALBUM', '\xa9alb', 'Album'])
            album_artist = self._get_tag(audio_file, ['TPE2', 'ALBUMARTIST', 'aART', 'AlbumArtist'])
            genre = self._get_tag(audio_file, ['TCON', 'GENRE', '\xa9gen', 'Genre'])
            
            # Debug logging for metadata extraction
            logger.debug(f"Raw metadata extracted from {file_path}:")
            logger.debug(f"  Title: '{title}'")
            logger.debug(f"  Artist: '{artist}'")
            logger.debug(f"  Album: '{album}'")
            logger.debug(f"  Album Artist: '{album_artist}'")
            logger.debug(f"  Genre: '{genre}'")
            
            # Extract numeric metadata
            track_number = self._get_numeric_tag(audio_file, ['TRCK', 'TRACKNUMBER', 'trkn', 'TrackNumber'])
            disc_number = self._get_numeric_tag(audio_file, ['TPOS', 'DISCNUMBER', 'disk', 'DiscNumber'])
            year = self._get_numeric_tag(audio_file, ['TDRC', 'YEAR', 'DATE', '\xa9day', 'Year', 'Date'])
            
            # Get duration from audio info
            duration = 0
            bitrate = 0
            sample_rate = 0
            
            if hasattr(audio_file, 'info') and audio_file.info:
                duration = int(audio_file.info.length) if audio_file.info.length else 0
                bitrate = getattr(audio_file.info, 'bitrate', 0)
                sample_rate = getattr(audio_file.info, 'sample_rate', 0)
            
            # Use filename as title if not available
            if not title:
                title = Path(file_path).stem
            
            # Validate and clean extracted metadata
            def is_valid_metadata(value):
                """Check if metadata value is valid (not a path or system string)"""
                if not value or not isinstance(value, str):
                    return False
                value = value.strip()
                # Check for path-like strings
                if ('\\' in value or '/' in value or ':' in value or 
                    len(value) <= 3 or value.lower() in ['unknown', 'various', 'va']):
                    return False
                return True
            
            # Clean and validate artist
            if not is_valid_metadata(artist):
                # Try to extract artist from folder structure
                folder_parts = Path(file_path).parts
                if len(folder_parts) >= 2:
                    potential_artist = folder_parts[-2]  # Parent folder name
                    if is_valid_metadata(potential_artist):
                        artist = potential_artist
                        logger.info(f"Using folder name as artist: '{artist}' for file: {file_path}")
                    else:
                        artist = "Unknown Artist"
                else:
                    artist = "Unknown Artist"
            
            # Clean and validate album
            if not is_valid_metadata(album):
                # Try to extract album from folder name
                folder_name = Path(file_path).parent.name
                if is_valid_metadata(folder_name):
                    album = folder_name
                    logger.info(f"Using folder name as album: '{album}' for file: {file_path}")
                else:
                    album = "Unknown Album"
            
            # Clean and validate album_artist
            if not is_valid_metadata(album_artist):
                album_artist = artist  # Use the cleaned artist as album_artist
            
            # Final validation - if we still have invalid data, skip this file
            if not is_valid_metadata(artist) or not is_valid_metadata(album):
                logger.warning(f"Skipping file with invalid metadata: {file_path} (artist: '{artist}', album: '{album}')")
                return None
            
            return TrackInfo(
                file_path=file_path,
                title=title,
                artist=artist,
                album=album,
                album_artist=album_artist,
                track_number=track_number,
                disc_number=disc_number or 1,
                year=year,
                duration=duration,
                genre=genre or "",
                file_size=file_size,
                file_format=file_format,
                bitrate=bitrate,
                sample_rate=sample_rate
            )
            
        except Exception as e:
            logger.error(f"Error extracting metadata from {file_path}: {e}")
            return None
    
    def _get_tag(self, audio_file, tag_names: List[str]) -> str:
        """Get a tag value from audio file, trying multiple tag names."""
        for tag_name in tag_names:
            try:
                if tag_name in audio_file:
                    value = audio_file[tag_name]
                    if isinstance(value, list) and value:
                        return str(value[0])
                    elif value:
                        return str(value)
            except (KeyError, AttributeError):
                continue
        return ""
    
    def _get_numeric_tag(self, audio_file, tag_names: List[str]) -> int:
        """Get a numeric tag value from audio file."""
        for tag_name in tag_names:
            try:
                if tag_name in audio_file:
                    value = audio_file[tag_name]
                    # If value is a list, extract the first element
                    if isinstance(value, list):
                        if not value:
                            continue
                        value = value[0]
                    # Handle track/disc numbers that might be "1/10" format
                    if isinstance(value, str) and '/' in value:
                        value = value.split('/')[0]
                    # Only try to convert if value is str or int
                    if isinstance(value, (str, int)):
                        try:
                            return int(value)
                        except (ValueError, TypeError):
                            continue
            except (KeyError, AttributeError):
                continue
        return 0
    
    def get_artists(self) -> List[str]:
        """Get list of all artists in the library."""
        artists = set()
        for track in self.tracks:
            artists.add(track.artist)
            if track.album_artist and track.album_artist != track.artist:
                artists.add(track.album_artist)
        return sorted(list(artists))
    
    def get_albums_by_artist(self, artist: str) -> List[str]:
        """Get list of albums by a specific artist."""
        albums = set()
        for track in self.tracks:
            if track.artist == artist or track.album_artist == artist:
                albums.add(track.album)
        return sorted(list(albums))
    
    def get_tracks_by_artist(self, artist: str) -> List[TrackInfo]:
        """Get all tracks by a specific artist."""
        return [track for track in self.tracks if track.artist == artist or track.album_artist == artist] 