"""
Minimal Library Scanner Widget for DeeMusic - Testing Integration
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Any
import json

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QPushButton, QProgressBar, QTextEdit, 
    QTreeWidget, QTreeWidgetItem, QGroupBox, QLineEdit,
    QFileDialog, QMessageBox, QSplitter, QCheckBox, QProgressDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
import time
import threading
import json

# Import QueueIntegration for DeeMusic integration
try:
    from library_scanner.utils.queue_integration import QueueIntegration
    from library_scanner.core.data_models import DeezerAlbum, MissingAlbum
    QUEUE_INTEGRATION_AVAILABLE = True
except ImportError as e:
    logging.warning(f"QueueIntegration not available: {e}")
    QUEUE_INTEGRATION_AVAILABLE = False

logger = logging.getLogger(__name__)

class ImportWorker(QThread):
    """Worker thread for importing albums with progress tracking."""
    
    # Signals for progress updates
    progress_updated = pyqtSignal(int)  # Progress percentage (0-100)
    current_album_updated = pyqtSignal(str)  # Current album being imported
    import_completed = pyqtSignal(bool, int)  # (success, imported_count)
    
    def __init__(self, selected_albums, queue_integration):
        super().__init__()
        self.selected_albums = selected_albums
        self.queue_integration = queue_integration
        self.imported_count = 0
        
    def run(self):
        """Run the import process with progress updates."""
        try:
            total_albums = len(self.selected_albums)
            self.imported_count = 0
            
            # Process albums in batches for better performance
            batch_size = 5
            for batch_start in range(0, total_albums, batch_size):
                batch_end = min(batch_start + batch_size, total_albums)
                batch = self.selected_albums[batch_start:batch_end]
                
                for i, missing_album in enumerate(batch):
                    overall_index = batch_start + i
                    
                    # Update progress
                    progress = int((overall_index / total_albums) * 100)
                    self.progress_updated.emit(progress)
                    
                    album_name = f"{missing_album.deezer_album.title} by {missing_album.deezer_album.artist}"
                    self.current_album_updated.emit(f"Adding ({overall_index+1}/{total_albums}): {album_name}")
                    
                    # Skip albums with invalid or missing IDs
                    album_id = missing_album.deezer_album.id
                    if not album_id or album_id == 0 or str(album_id) == 'unknown':
                        logger.warning(f"Skipping album '{missing_album.deezer_album.title}' with invalid ID: {album_id}")
                        continue
                    
                    try:
                        # Use the download service to add the album
                        if hasattr(self.queue_integration, 'download_service') and self.queue_integration.download_service:
                            success = self.queue_integration.download_service.download_album(album_id)
                            if success:
                                self.imported_count += 1
                        
                    except Exception as e:
                        logger.error(f"Error adding album {overall_index+1}: {e}")
            
            # Final progress update
            self.progress_updated.emit(100)
            self.current_album_updated.emit("Import completed!")
            
            # Signal completion
            self.import_completed.emit(self.imported_count > 0, self.imported_count)
            
        except Exception as e:
            logger.error(f"Error in import worker: {e}")
            self.import_completed.emit(False, 0)

class ScanWorker(QThread):
    """Worker thread for library scanning with detailed progress tracking."""
    
    # Signals for progress updates
    progress_updated = pyqtSignal(int)  # Progress percentage (0-100)
    current_file_updated = pyqtSignal(str)  # Current file being scanned
    status_updated = pyqtSignal(str)  # Status message
    file_count_updated = pyqtSignal(int, int)  # (current_count, total_count)
    speed_updated = pyqtSignal(str)  # Scanning speed
    scan_completed = pyqtSignal(dict)  # Scan results
    scan_error = pyqtSignal(str)  # Error message
    
    def __init__(self, library_paths, scan_type="full", previous_mtimes=None):
        super().__init__()
        self.library_paths = library_paths
        self.scan_type = scan_type  # "full" or "incremental"
        self.previous_mtimes = previous_mtimes or {}
        self.should_cancel = False
        self.music_extensions = {'.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg', '.wma'}
        
    def cancel(self):
        """Cancel the scanning process."""
        self.should_cancel = True
        
    def run(self):
        """Run the scanning process."""
        try:
            self.status_updated.emit("🔍 Initializing scan...")
            print(f"DEBUG SCAN: Starting scan with paths: {self.library_paths}")
            
            # Collect all files to scan
            all_files = []
            
            if self.scan_type == "incremental":
                self.status_updated.emit("🔄 Checking for modified albums...")
                all_files = self._get_modified_albums()
                if not all_files:
                    self.status_updated.emit("✅ No modified albums found")
                    self.scan_completed.emit({"type": "no_changes"})
                    return
            else:
                self.status_updated.emit("🔍 Performing full album scan...")
                all_files = self._get_all_albums()
                print(f"DEBUG SCAN: Found {len(all_files)} album folders")
            
            if not all_files:
                self.status_updated.emit("⚠️ No music files found")
                self.scan_completed.emit({"type": "no_files"})
                return
            
            total_files = len(all_files)
            if total_files == 0:
                self.status_updated.emit("⚠️ No music files found")
                self.scan_completed.emit({"type": "no_files"})
                return
            
            self.status_updated.emit(f"🎵 Found {total_files} music files to scan")
            
            # High-performance parallel scanning
            scanned_files = []
            start_time = time.time()
            
            # Detect network drives and optimize accordingly
            is_network_drive = self._is_network_drive(all_files[0] if all_files else None)
            
            if is_network_drive:
                self.status_updated.emit(f"🌐 Network drive detected - optimizing for network scanning...")
                scanned_files = self._network_optimized_scan(all_files, total_files, start_time)
            else:
                # Choose optimal scanning strategy based on library size for local drives
                if total_files > 5000:
                    # Ultra-fast parallel scan for very large libraries
                    self.status_updated.emit(f"🚀 Ultra-fast scan mode for {total_files:,} files...")
                    scanned_files = self._ultra_fast_scan(all_files, total_files, start_time)
                elif total_files > 1000:
                    # Parallel scan for large libraries
                    scanned_files = self._parallel_scan(all_files, total_files, start_time)
                else:
                    # Sequential scan for smaller libraries
                    scanned_files = self._sequential_scan(all_files, total_files, start_time)
            
            # Complete the scan
            self.progress_updated.emit(100)
            self.status_updated.emit("✅ Scan completed successfully")
            
            # Return results (now album-based instead of file-based)
            results = {
                "type": "success",
                "total_files": total_files,  # Keep for compatibility (now represents album folders)
                "total_albums": total_files,  # total_files now represents total album folders
                "scanned_files": scanned_files,  # scanned_files now contains album data
                "scan_time": time.time() - start_time,
                "scan_type": self.scan_type
            }
            
            print(f"DEBUG SCAN: Emitting results with {len(scanned_files)} scanned files")
            self.scan_completed.emit(results)
            
        except Exception as e:
            logger.error(f"Error during scan: {e}")
            self.scan_error.emit(str(e))
    
    def _get_changed_folders(self):
        """Get folders that have changed since last scan."""
        # Simplified approach - if no previous mtimes exist, do full scan
        if not self.previous_mtimes:
            self.status_updated.emit("📁 No previous scan data - performing full scan")
            return self.library_paths
        
        self.status_updated.emit("🔍 Checking for changes...")
        
        # For now, just check if any library paths have changed
        # This is much faster than checking every subdirectory
        changed_folders = []
        
        for lib_path in self.library_paths:
            path = Path(lib_path)
            if not path.exists():
                continue
                
            lib_path_str = str(path)
            try:
                current_mtime = path.stat().st_mtime
                # Check if this path has changed or is new
                if lib_path_str not in self.previous_mtimes or abs(self.previous_mtimes[lib_path_str] - current_mtime) > 1:
                    changed_folders.append(lib_path_str)
                    self.status_updated.emit(f"🔄 Changes detected in {path.name}")
            except Exception:
                # If we can't get mtime, assume it changed
                changed_folders.append(lib_path_str)
        
        if len(changed_folders) == 0:
            # Check if we should force a scan anyway (for debugging/testing)
            import os
            force_scan = os.environ.get('DEEMUSIC_FORCE_UPDATE_SCAN', '').lower() == 'true'
            
            if force_scan:
                logger.info("[UpdateScan] FORCE_UPDATE_SCAN enabled - scanning anyway")
                self.status_updated.emit("🔄 Force scanning (debug mode)")
                return self.library_paths
            
            self.status_updated.emit("✅ No changes detected")
            logger.info(f"[UpdateScan] No changes detected. Previous mtimes: {len(self.previous_mtimes)} entries")
            
            # Enhanced debugging: Log detailed mtime comparisons
            logger.info("[UpdateScan] Detailed mtime comparison:")
            for lib_path_str in self.library_paths:
                try:
                    path = Path(lib_path_str)
                    if path.exists():
                        current_mtime = path.stat().st_mtime
                        prev_mtime = self.previous_mtimes.get(lib_path_str, 0)
                        diff = abs(current_mtime - prev_mtime)
                        logger.info(f"[UpdateScan] {path.name}: current={current_mtime:.2f}, previous={prev_mtime:.2f}, diff={diff:.2f}")
                        
                        # Also check if there are any new subdirectories
                        if path.is_dir():
                            try:
                                subdir_count = sum(1 for p in path.iterdir() if p.is_dir())
                                logger.debug(f"[UpdateScan] {path.name}: {subdir_count} subdirectories")
                            except Exception:
                                pass
                except Exception as e:
                    logger.debug(f"[UpdateScan] Error checking {lib_path_str}: {e}")
        else:
            self.status_updated.emit(f"🔄 Found changes in {len(changed_folders)} library path(s)")
            logger.info(f"[UpdateScan] Found changes in {len(changed_folders)} folders: {changed_folders[:3]}...")
        
        return changed_folders
    
    def _get_all_albums(self):
        """Get all album folders from library paths."""
        all_albums = []
        folder_count = 0
        
        for folder_path in self.library_paths:
            if self.should_cancel:
                return []
                
            folder = Path(folder_path)
            if folder.exists():
                self.status_updated.emit(f"📁 Scanning {folder.name}...")
                
                try:
                    for subfolder in folder.rglob('*'):
                        if self.should_cancel:
                            return []
                            
                        if subfolder.is_dir():
                            folder_count += 1
                            if folder_count % 100 == 0:  # Update every 100 folders
                                self.status_updated.emit(f"📊 Found {folder_count} folders so far...")
                            
                            # Check if this folder contains music files (is an album folder)
                            has_music = any(
                                f.suffix.lower() in self.music_extensions 
                                for f in subfolder.iterdir() 
                                if f.is_file()
                            )
                            
                            if has_music:
                                all_albums.append(subfolder)
                                
                except Exception as e:
                    logger.error(f"Error scanning {folder_path}: {e}")
                    continue
        
        return all_albums
    
    def _get_modified_files(self):
        """Get only files that have been modified since last scan."""
        if not self.previous_mtimes:
            self.status_updated.emit("📁 No previous scan data - performing full scan")
            return self._get_all_files()
        
        # Since previous_mtimes contains folder modification times, not file times,
        # we'll check if any folders have changed and scan files in those folders
        modified_files = []
        changed_folders = self._get_changed_folders()
        
        if not changed_folders:
            self.status_updated.emit("✅ No folder changes detected")
            return []
        
        self.status_updated.emit(f"🔄 Scanning files in {len(changed_folders)} changed folders...")
        
        for folder_path in changed_folders:
            if self.should_cancel:
                return []
                
            folder = Path(folder_path)
            if folder.exists():
                self.status_updated.emit(f"🔄 Scanning changed folder: {folder.name}...")
                
                try:
                    for file_path in folder.rglob('*'):
                        if self.should_cancel:
                            return []
                            
                        if file_path.is_file() and file_path.suffix.lower() in self.music_extensions:
                            modified_files.append(file_path)
                            
                            if len(modified_files) % 100 == 0:  # Update every 100 files
                                self.status_updated.emit(f"🔄 Found {len(modified_files)} files in changed folders...")
                                
                except Exception as e:
                    logger.error(f"Error scanning changed folder {folder_path}: {e}")
                    continue
        
        self.status_updated.emit(f"🔄 Found {len(modified_files)} files in changed folders")
        return modified_files
    
    def _get_modified_albums(self):
        """Get only album folders that have been modified since last scan."""
        if not self.previous_mtimes:
            self.status_updated.emit("📁 No previous scan data - performing full scan")
            return self._get_all_albums()
        
        # Get changed folders using folder modification times
        changed_folders = self._get_changed_folders()
        
        if not changed_folders:
            self.status_updated.emit("✅ No folder changes detected")
            return []
        
        modified_albums = []
        self.status_updated.emit(f"🔄 Checking {len(changed_folders)} changed folders for albums...")
        
        for folder_path in changed_folders:
            if self.should_cancel:
                return []
                
            folder = Path(folder_path)
            if folder.exists():
                self.status_updated.emit(f"🔄 Checking folder: {folder.name}...")
                
                try:
                    # Check if this folder itself is an album folder
                    has_music = any(
                        f.suffix.lower() in self.music_extensions 
                        for f in folder.iterdir() 
                        if f.is_file()
                    )
                    
                    if has_music:
                        modified_albums.append(folder)
                    
                    # Also check subfolders for album folders
                    for subfolder in folder.rglob('*'):
                        if self.should_cancel:
                            return []
                            
                        if subfolder.is_dir():
                            has_music = any(
                                f.suffix.lower() in self.music_extensions 
                                for f in subfolder.iterdir() 
                                if f.is_file()
                            )
                            
                            if has_music:
                                modified_albums.append(subfolder)
                                
                                if len(modified_albums) % 50 == 0:  # Update every 50 albums
                                    self.status_updated.emit(f"🔄 Found {len(modified_albums)} modified albums...")
                                
                except Exception as e:
                    logger.error(f"Error checking changed folder {folder_path}: {e}")
                    continue
        
        self.status_updated.emit(f"🔄 Found {len(modified_albums)} modified album folders")
        return modified_albums
    
    def _extract_metadata(self, file_path: Path) -> Dict[str, Any]:
        """Extract metadata from a music file (optimized for performance)."""
        metadata = {}
        
        try:
            # Fast metadata extraction using mutagen
            from mutagen import File
            
            # Use fast=True for better performance on large libraries
            audio_file = File(str(file_path), easy=True)
            if audio_file is not None:
                # Use easy tags for faster access
                metadata['title'] = self._get_easy_tag(audio_file, 'title')
                metadata['artist'] = self._get_easy_tag(audio_file, 'artist')
                metadata['album'] = self._get_easy_tag(audio_file, 'album')
                metadata['album_artist'] = self._get_easy_tag(audio_file, 'albumartist') or metadata.get('artist')
                metadata['year'] = self._get_easy_tag(audio_file, 'date')
                metadata['track_number'] = self._get_easy_tag(audio_file, 'tracknumber')
                
                # Fast year processing
                if metadata.get('year'):
                    year_str = str(metadata['year'])
                    # Extract first 4 digits as year
                    import re
                    year_match = re.search(r'\d{4}', year_str)
                    metadata['year'] = int(year_match.group()) if year_match else None
                
                # Fast track number processing
                if metadata.get('track_number'):
                    track_str = str(metadata['track_number'])
                    # Extract first number before '/'
                    track_num = track_str.split('/')[0].split(' ')[0]
                    metadata['track_number'] = int(track_num) if track_num.isdigit() else None
                
        except ImportError:
            # Fallback: try to extract from file path structure
            metadata = self._extract_metadata_from_path(file_path)
        except Exception as e:
            # Fast fallback to path-based extraction
            metadata = self._extract_metadata_from_path(file_path)
        
        return metadata
    
    def _get_easy_tag(self, audio_file, tag_name):
        """Get tag value using mutagen's easy interface (faster)."""
        try:
            value = audio_file.get(tag_name)
            if value and isinstance(value, list):
                return value[0]
            return value
        except:
            return None
    
    def _get_tag_value(self, audio_file, tag_keys):
        """Get tag value from audio file, trying multiple possible tag keys."""
        for key in tag_keys:
            if key in audio_file:
                value = audio_file[key]
                if isinstance(value, list) and value:
                    return str(value[0])
                elif value:
                    return str(value)
        return None
    
    def _extract_metadata_from_path(self, file_path: Path) -> Dict[str, Any]:
        """Extract metadata from file path structure as fallback."""
        metadata = {}
        
        try:
            # Assume structure like: Artist/Album/Track.ext or Artist - Album/Track.ext
            parts = file_path.parts
            
            if len(parts) >= 3:
                # Try to extract artist and album from path
                artist_part = parts[-3]  # Third from end (Artist folder)
                album_part = parts[-2]   # Second from end (Album folder)
                
                # Debug: Log path parsing
                if artist_part == "Music":
                    logger.warning(f"DEBUG: Found 'Music' as artist for path: {file_path}")
                    logger.warning(f"DEBUG: Path parts: {parts}")
                    logger.warning(f"DEBUG: Artist part (parts[-3]): {artist_part}")
                    logger.warning(f"DEBUG: Album part (parts[-2]): {album_part}")
                
                # Clean up common patterns
                if ' - ' in artist_part:
                    artist_part = artist_part.split(' - ')[0]
                
                # Filter out common folder names that shouldn't be artists
                invalid_artists = ['Music', 'music', 'MUSIC', 'Various Artists', 'Various', 'Compilation', 'Compilations']
                if artist_part in invalid_artists:
                    logger.warning(f"DEBUG: Filtering out invalid artist '{artist_part}' from path: {file_path}")
                    # Try to use a different part of the path or skip
                    if len(parts) >= 4:
                        # Try the next level up
                        alternative_artist = parts[-4]
                        if alternative_artist not in invalid_artists:
                            artist_part = alternative_artist
                            logger.warning(f"DEBUG: Using alternative artist: {artist_part}")
                        else:
                            # Skip this file or use unknown
                            logger.warning(f"DEBUG: No valid artist found, skipping path-based extraction")
                            return metadata
                    else:
                        logger.warning(f"DEBUG: No alternative artist available, skipping path-based extraction")
                        return metadata
                
                metadata['artist'] = artist_part
                metadata['album'] = album_part
                metadata['album_artist'] = artist_part
            
            # Extract title from filename
            metadata['title'] = file_path.stem
            
            # Try to extract track number from filename
            filename = file_path.stem
            if filename and filename[0].isdigit():
                track_match = filename.split(' ')[0]
                if track_match.replace('.', '').isdigit():
                    metadata['track_number'] = int(track_match.split('.')[0])
            
        except Exception as e:
            logger.warning(f"Error extracting metadata from path {file_path}: {e}")
        
        return metadata
    
    def _parallel_scan(self, all_files, total_files, start_time):
        """High-performance parallel scanning for large libraries."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import multiprocessing
        
        scanned_files = []
        
        # Use optimal number of threads (CPU cores * 2 for I/O bound tasks)
        max_workers = min(multiprocessing.cpu_count() * 2, 16)  # Cap at 16 threads
        
        self.status_updated.emit(f"🚀 High-speed parallel scan using {max_workers} threads...")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all files for processing
            future_to_file = {
                executor.submit(self._extract_file_data, file_path): file_path 
                for file_path in all_files
            }
            
            completed = 0
            for future in as_completed(future_to_file):
                if self.should_cancel:
                    self.status_updated.emit("❌ Scan cancelled")
                    return []
                
                try:
                    file_data = future.result()
                    if file_data:
                        scanned_files.append(file_data)
                    
                    completed += 1
                    
                    # Update progress every 100 files or every 5% for performance
                    if completed % 100 == 0 or completed % max(1, total_files // 20) == 0:
                        progress = int((completed / total_files) * 100)
                        self.progress_updated.emit(progress)
                        self.file_count_updated.emit(completed, total_files)
                        
                        # Calculate speed
                        elapsed_time = time.time() - start_time
                        if elapsed_time > 0:
                            files_per_second = completed / elapsed_time
                            self.speed_updated.emit(f"{files_per_second:.1f} files/sec")
                        
                        # Show current progress
                        self.current_file_updated.emit(f"🚀 Processed {completed}/{total_files} files...")
                
                except Exception as e:
                    logger.warning(f"Error processing file: {e}")
        
        return scanned_files
    
    def _sequential_scan(self, all_files, total_files, start_time):
        """Sequential scanning for smaller libraries."""
        scanned_files = []
        
        for i, file_path in enumerate(all_files):
            if self.should_cancel:
                self.status_updated.emit("❌ Scan cancelled")
                return []
            
            # Update progress
            progress = int((i / total_files) * 100)
            self.progress_updated.emit(progress)
            self.file_count_updated.emit(i + 1, total_files)
            
            # Update current file being scanned
            relative_path = str(file_path.relative_to(file_path.anchor))
            if len(relative_path) > 80:
                display_path = "..." + relative_path[-77:]
            else:
                display_path = relative_path
            
            self.current_file_updated.emit(f"📁 Scanning: {display_path}")
            
            # Calculate and update speed
            elapsed_time = time.time() - start_time
            if elapsed_time > 0:
                files_per_second = (i + 1) / elapsed_time
                if files_per_second > 1:
                    speed_text = f"{files_per_second:.1f} files/sec"
                else:
                    speed_text = f"{1/files_per_second:.1f} sec/file"
                self.speed_updated.emit(speed_text)
            
            # Extract file data
            file_data = self._extract_file_data(file_path)
            if file_data:
                scanned_files.append(file_data)
        
        return scanned_files
    
    def _extract_file_data(self, folder_path):
        """Extract album data from a folder containing music files (thread-safe)."""
        try:
            # This method now processes album folders, not individual files
            if not folder_path.is_dir():
                logger.warning(f"Expected folder but got file: {folder_path}")
                return None
            
            # Find music files in this folder
            music_files = [
                f for f in folder_path.iterdir() 
                if f.is_file() and f.suffix.lower() in self.music_extensions
            ]
            
            if not music_files:
                logger.debug(f"No music files found in folder: {folder_path}")
                return None
            
            # Extract metadata from all music files in the folder
            track_metadatas = []
            for music_file in music_files:
                metadata = self._extract_metadata(music_file)
                if metadata:
                    track_metadatas.append(metadata)
            
            if not track_metadatas:
                logger.warning(f"No valid metadata extracted from folder: {folder_path}")
                return None
            
            # Aggregate metadata to create album-level entry
            # Use the most common values for album_artist and album
            from collections import Counter
            
            album_artists = [m.get('album_artist') or m.get('artist') for m in track_metadatas if m.get('album_artist') or m.get('artist')]
            albums = [m.get('album') for m in track_metadatas if m.get('album')]
            
            # Smart album/artist detection for multi-disc albums
            folder_name = folder_path.name
            parent_folder_name = folder_path.parent.name
            grandparent_folder_name = folder_path.parent.parent.name if folder_path.parent.parent else ""
            
            # Check if this looks like a CD folder (CD1, CD2, Disc 1, etc.)
            is_cd_folder = (
                folder_name.lower().startswith(('cd', 'disc')) or
                folder_name.lower() in ['cd1', 'cd2', 'cd3', 'cd4', 'cd5', 'disc1', 'disc2', 'disc3', 'disc4', 'disc5'] or
                (len(folder_name) <= 3 and folder_name.lower().startswith('cd'))
            )
            
            if is_cd_folder and grandparent_folder_name:
                # Multi-disc album: use grandparent as artist, parent as album
                album_artist = grandparent_folder_name
                album = parent_folder_name
                logger.info(f"Detected multi-disc album: {album_artist} - {album} ({folder_name})")
            else:
                # Regular album: try to get from metadata first, then fall back to folder structure
                if album_artists and albums:
                    # Use album_artist from metadata, but prefer the most consistent one
                    # Filter out obvious guest artists and compilations
                    filtered_artists = []
                    for artist in album_artists:
                        if artist and artist.lower() not in ['various artists', 'various', 'compilation']:
                            # Skip artists that look like guest features (containing "feat", "ft", etc.)
                            if not any(indicator in artist.lower() for indicator in ['feat.', 'ft.', 'featuring', 'with ']):
                                filtered_artists.append(artist)
                    
                    if filtered_artists:
                        # Use the most common album artist from filtered list
                        album_artist = Counter(filtered_artists).most_common(1)[0][0]
                        logger.debug(f"Selected album artist '{album_artist}' from {len(filtered_artists)} filtered candidates")
                    else:
                        # Fall back to folder structure if all artists were filtered out
                        album_artist = parent_folder_name
                        logger.debug(f"All metadata artists filtered out, using folder name: '{album_artist}'")
                    
                    album = Counter(albums).most_common(1)[0][0]
                else:
                    # Fall back to folder structure
                    album_artist = parent_folder_name
                    album = folder_name
            
            # Skip invalid entries
            if not album_artist or not album or album_artist.lower() == 'various artists':
                logger.warning(f"Skipping invalid album: '{album_artist}' - '{album}'")
                return None
            
            # Skip entries where artist is a drive path
            if album_artist.endswith(':\\') or ':\\' in album_artist:
                logger.warning(f"Skipping drive path entry: artist='{album_artist}'")
                return None
            
            # Get additional metadata
            years = [m.get('year') for m in track_metadatas if m.get('year')]
            year = min(years) if years else 0
            
            genres = [m.get('genre') for m in track_metadatas if m.get('genre')]
            genre = Counter(genres).most_common(1)[0][0] if genres else ""
            
            # Return album-level data
            return {
                'album_artist': album_artist,
                'album': album,
                'folder_path': str(folder_path),
                'year': year,
                'genre': genre,
                'num_tracks': len(track_metadatas),
                'total_duration': 0,  # Could calculate if needed
                'file_formats': list(set(f.suffix.lower()[1:] for f in music_files))
            }
            
        except Exception as e:
            logger.warning(f"Error extracting album data from {folder_path}: {e}")
            return None
    
    def _ultra_fast_scan(self, all_files, total_files, start_time):
        """Ultra-fast scanning for very large libraries (10k+ files)."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import multiprocessing
        
        scanned_files = []
        
        # Use maximum threads for ultra-fast processing
        max_workers = min(multiprocessing.cpu_count() * 4, 32)  # Aggressive threading
        batch_size = 500  # Process in batches for memory efficiency
        
        self.status_updated.emit(f"⚡ Ultra-fast scan: {max_workers} threads, {batch_size} files per batch...")
        
        # Process files in batches to manage memory
        for batch_start in range(0, total_files, batch_size):
            if self.should_cancel:
                self.status_updated.emit("❌ Scan cancelled")
                return []
            
            batch_end = min(batch_start + batch_size, total_files)
            batch_files = all_files[batch_start:batch_end]
            
            # Process batch in parallel
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit batch for processing
                futures = [executor.submit(self._extract_file_data, file_path) for file_path in batch_files]
                
                # Collect results
                for future in as_completed(futures):
                    try:
                        file_data = future.result()
                        if file_data:
                            scanned_files.append(file_data)
                    except Exception as e:
                        logger.warning(f"Error in ultra-fast scan: {e}")
            
            # Update progress after each batch
            progress = int((batch_end / total_files) * 100)
            self.progress_updated.emit(progress)
            self.file_count_updated.emit(len(scanned_files), total_files)
            
            # Calculate speed
            elapsed_time = time.time() - start_time
            if elapsed_time > 0:
                files_per_second = len(scanned_files) / elapsed_time
                self.speed_updated.emit(f"⚡ {files_per_second:.0f} files/sec")
            
            self.current_file_updated.emit(f"⚡ Batch {batch_start//batch_size + 1}/{(total_files-1)//batch_size + 1} - {len(scanned_files)} files processed")
        
        return scanned_files
    
    def _is_network_drive(self, file_path):
        """Detect if the path is on a network drive."""
        if not file_path:
            return False
        
        try:
            import os
            path_str = str(file_path)
            
            # Check for UNC paths (\\server\share)
            if path_str.startswith('\\\\'):
                return True
            
            # Check for mapped network drives on Windows
            if os.name == 'nt':
                import subprocess
                try:
                    # Get drive letter
                    drive = os.path.splitdrive(path_str)[0]
                    if drive:
                        # Use net use command to check if it's a network drive
                        result = subprocess.run(['net', 'use', drive], 
                                              capture_output=True, text=True, timeout=5)
                        return 'Remote' in result.stdout or 'Network' in result.stdout
                except:
                    pass
            
            return False
        except:
            return False
    
    def _network_optimized_scan(self, all_files, total_files, start_time):
        """Network-optimized scanning with reduced I/O and intelligent caching."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import multiprocessing
        
        scanned_files = []
        
        # Network-optimized settings based on connection type
        connection_type = self._detect_network_type(all_files[0] if all_files else None)
        
        if connection_type == 'gigabit':
            # Fast network - can handle more threads
            max_workers = min(multiprocessing.cpu_count() * 2, 16)
            batch_size = 300
        elif connection_type == 'wifi':
            # WiFi - moderate threading
            max_workers = min(multiprocessing.cpu_count(), 6)
            batch_size = 150
        else:
            # Conservative settings for slower networks
            max_workers = min(multiprocessing.cpu_count(), 4)
            batch_size = 100
        
        self.status_updated.emit(f"🌐 Network-optimized scan: {max_workers} threads, reduced I/O...")
        
        # Pre-cache directory listings to reduce network round trips
        dir_cache = self._build_directory_cache(all_files)
        
        # Process files in network-optimized batches
        for batch_start in range(0, total_files, batch_size):
            if self.should_cancel:
                self.status_updated.emit("❌ Scan cancelled")
                return []
            
            batch_end = min(batch_start + batch_size, total_files)
            batch_files = all_files[batch_start:batch_end]
            
            # Group files by directory to minimize network traversal
            dir_groups = self._group_files_by_directory(batch_files)
            
            # Process each directory group
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                
                for directory, files in dir_groups.items():
                    # Submit directory-based processing to reduce network I/O
                    futures.append(
                        executor.submit(self._process_directory_batch, directory, files, dir_cache)
                    )
                
                # Collect results
                for future in as_completed(futures):
                    try:
                        batch_results = future.result()
                        if batch_results:
                            scanned_files.extend(batch_results)
                    except Exception as e:
                        logger.warning(f"Error in network scan batch: {e}")
            
            # Update progress
            progress = int((batch_end / total_files) * 100)
            self.progress_updated.emit(progress)
            self.file_count_updated.emit(len(scanned_files), total_files)
            
            # Calculate speed
            elapsed_time = time.time() - start_time
            if elapsed_time > 0:
                files_per_second = len(scanned_files) / elapsed_time
                self.speed_updated.emit(f"🌐 {files_per_second:.0f} files/sec (network)")
            
            self.current_file_updated.emit(f"🌐 Network batch {batch_start//batch_size + 1} - {len(scanned_files)} files processed")
        
        return scanned_files
    
    def _build_directory_cache(self, all_files):
        """Build a cache of directory information to reduce network I/O."""
        dir_cache = {}
        
        try:
            # Group files by directory
            from collections import defaultdict
            dirs = defaultdict(list)
            
            for file_path in all_files:
                directory = file_path.parent
                dirs[directory].append(file_path)
            
            # Cache directory stats (reduces network round trips)
            for directory, files in dirs.items():
                try:
                    if directory.exists():
                        dir_cache[directory] = {
                            'exists': True,
                            'files': files,
                            'mtime': directory.stat().st_mtime
                        }
                except:
                    dir_cache[directory] = {'exists': False, 'files': files}
            
            logger.info(f"Built directory cache for {len(dir_cache)} directories")
            
        except Exception as e:
            logger.warning(f"Error building directory cache: {e}")
        
        return dir_cache
    
    def _group_files_by_directory(self, files):
        """Group files by directory to process them together."""
        from collections import defaultdict
        groups = defaultdict(list)
        
        for file_path in files:
            directory = file_path.parent
            groups[directory].append(file_path)
        
        return groups
    
    def _process_directory_batch(self, directory, files, dir_cache):
        """Process all files in a directory together (network-optimized)."""
        results = []
        
        try:
            # Check directory cache first
            dir_info = dir_cache.get(directory, {})
            if not dir_info.get('exists', True):
                return results
            
            # Process all files in this directory together
            for file_path in files:
                try:
                    # Network-optimized metadata extraction
                    file_data = self._extract_file_data_network_optimized(file_path)
                    if file_data:
                        results.append(file_data)
                except Exception as e:
                    logger.warning(f"Error processing {file_path}: {e}")
            
        except Exception as e:
            logger.warning(f"Error processing directory {directory}: {e}")
        
        return results
    
    def _extract_file_data_network_optimized(self, folder_path):
        """Network-optimized album data extraction from a folder containing music files."""
        try:
            # This method now processes album folders, not individual files (network-optimized)
            if not folder_path.is_dir():
                logger.warning(f"Expected folder but got file: {folder_path}")
                return None
            
            # Find music files in this folder (minimize network I/O)
            music_files = [
                f for f in folder_path.iterdir() 
                if f.is_file() and f.suffix.lower() in self.music_extensions
            ]
            
            if not music_files:
                logger.debug(f"No music files found in folder: {folder_path}")
                return None
            
            # For network drives, use simplified metadata extraction to minimize I/O
            # Extract metadata from a few representative files instead of all files
            sample_files = music_files[:min(3, len(music_files))]  # Sample first 3 files
            track_metadatas = []
            
            for music_file in sample_files:
                metadata = self._extract_metadata_network_optimized(music_file)
                if metadata:
                    track_metadatas.append(metadata)
            
            if not track_metadatas:
                logger.warning(f"No valid metadata extracted from folder: {folder_path}")
                return None
            
            # Aggregate metadata to create album-level entry (network-optimized)
            from collections import Counter
            
            album_artists = [m.get('album_artist') or m.get('artist') for m in track_metadatas if m.get('album_artist') or m.get('artist')]
            albums = [m.get('album') for m in track_metadatas if m.get('album')]
            
            # Smart album/artist detection for multi-disc albums
            folder_name = folder_path.name
            parent_folder_name = folder_path.parent.name
            grandparent_folder_name = folder_path.parent.parent.name if folder_path.parent.parent else ""
            
            # Check if this looks like a CD folder (CD1, CD2, Disc 1, etc.)
            is_cd_folder = (
                folder_name.lower().startswith(('cd', 'disc')) or
                folder_name.lower() in ['cd1', 'cd2', 'cd3', 'cd4', 'cd5', 'disc1', 'disc2', 'disc3', 'disc4', 'disc5'] or
                (len(folder_name) <= 3 and folder_name.lower().startswith('cd'))
            )
            
            if is_cd_folder and grandparent_folder_name:
                # Multi-disc album: use grandparent as artist, parent as album
                album_artist = grandparent_folder_name
                album = parent_folder_name
                logger.info(f"Detected multi-disc album: {album_artist} - {album} ({folder_name})")
            else:
                # Regular album: try to get from metadata first, then fall back to folder structure
                if album_artists and albums:
                    # Use album_artist from metadata, but prefer the most consistent one
                    # Filter out obvious guest artists and compilations
                    filtered_artists = []
                    for artist in album_artists:
                        if artist and artist.lower() not in ['various artists', 'various', 'compilation']:
                            # Skip artists that look like guest features (containing "feat", "ft", etc.)
                            if not any(indicator in artist.lower() for indicator in ['feat.', 'ft.', 'featuring', 'with ']):
                                filtered_artists.append(artist)
                    
                    if filtered_artists:
                        # Use the most common album artist from filtered list
                        album_artist = Counter(filtered_artists).most_common(1)[0][0]
                        logger.debug(f"Selected album artist '{album_artist}' from {len(filtered_artists)} filtered candidates")
                    else:
                        # Fall back to folder structure if all artists were filtered out
                        album_artist = parent_folder_name
                        logger.debug(f"All metadata artists filtered out, using folder name: '{album_artist}'")
                    
                    album = Counter(albums).most_common(1)[0][0]
                else:
                    # Fall back to folder structure
                    album_artist = parent_folder_name
                    album = folder_name
            
            # Skip invalid entries
            if not album_artist or not album or album_artist.lower() == 'various artists':
                logger.warning(f"Skipping invalid album: '{album_artist}' - '{album}'")
                return None
            
            # Skip entries where artist is a drive path
            if album_artist.endswith(':\\') or ':\\' in album_artist:
                logger.warning(f"Skipping drive path entry: artist='{album_artist}'")
                return None
            
            # Get additional metadata (network-optimized)
            years = [m.get('year') for m in track_metadatas if m.get('year')]
            year = min(years) if years else 0
            
            genres = [m.get('genre') for m in track_metadatas if m.get('genre')]
            genre = Counter(genres).most_common(1)[0][0] if genres else ""
            
            # Return album-level data (network-optimized)
            return {
                'album_artist': album_artist,
                'album': album,
                'folder_path': str(folder_path),
                'year': year,
                'genre': genre,
                'num_tracks': len(music_files),  # Count all files, not just sampled ones
                'total_duration': 0,  # Skip duration calculation for network performance
                'file_formats': list(set(f.suffix.lower()[1:] for f in music_files))
            }
            
        except Exception as e:
            logger.warning(f"Error extracting network album data from {folder_path}: {e}")
            return None
    
    def _extract_metadata_network_optimized(self, file_path):
        """Network-optimized metadata extraction with caching and minimal I/O."""
        metadata = {}
        
        try:
            # For network drives, try path-based extraction first (no file I/O)
            path_metadata = self._extract_metadata_from_path(file_path)
            
            # Only read file metadata if path extraction failed
            if (path_metadata.get('artist') == 'Unknown Artist' or 
                path_metadata.get('album') == 'Unknown Album'):
                
                # Network-optimized mutagen reading
                from mutagen import File
                
                # Use minimal metadata reading for network performance
                try:
                    audio_file = File(str(file_path), easy=True)
                    if audio_file is not None:
                        # Only read essential tags to minimize network I/O
                        metadata['artist'] = self._get_easy_tag(audio_file, 'artist') or path_metadata.get('artist')
                        metadata['album'] = self._get_easy_tag(audio_file, 'album') or path_metadata.get('album')
                        metadata['album_artist'] = (self._get_easy_tag(audio_file, 'albumartist') or 
                                                   metadata.get('artist') or path_metadata.get('artist'))
                        metadata['title'] = self._get_easy_tag(audio_file, 'title') or path_metadata.get('title')
                        
                        # Optional tags (skip if network is slow)
                        try:
                            metadata['year'] = self._get_easy_tag(audio_file, 'date')
                            metadata['track_number'] = self._get_easy_tag(audio_file, 'tracknumber')
                        except:
                            pass  # Skip optional tags on network errors
                    else:
                        metadata = path_metadata
                except:
                    # Fall back to path-based extraction on network errors
                    metadata = path_metadata
            else:
                # Use path-based metadata if it's good enough
                metadata = path_metadata
                
        except Exception as e:
            # Ultimate fallback
            metadata = self._extract_metadata_from_path(file_path)
        
        return metadata
    
    def _detect_network_type(self, file_path):
        """Detect network connection type for optimization."""
        if not file_path:
            return 'unknown'
        
        try:
            import time
            
            # Quick network speed test
            start_time = time.time()
            
            # Test file access speed
            try:
                file_path.stat()
                access_time = time.time() - start_time
                
                # Classify based on access time
                if access_time < 0.01:
                    return 'gigabit'  # Very fast network
                elif access_time < 0.05:
                    return 'wifi'     # Moderate speed
                else:
                    return 'slow'     # Slow network
                    
            except:
                return 'unknown'
                
        except:
            return 'unknown'

class ComparisonWorker(QThread):
    """Worker thread for comparing library with Deezer."""
    
    # Signals for progress updates
    progress_updated = pyqtSignal(int)  # Progress percentage (0-100)
    status_updated = pyqtSignal(str)  # Status message
    comparison_completed = pyqtSignal(dict)  # Comparison results
    comparison_error = pyqtSignal(str)  # Error message
    
    def __init__(self, local_albums, config):
        super().__init__()
        self.local_albums = local_albums
        self.config = config
        self.should_cancel = False
        
    def cancel(self):
        """Cancel the comparison process."""
        self.should_cancel = True
        
    def run(self):
        """Run the comparison process."""
        try:
            logger.info("Main DeeMusic ComparisonWorker.run() started")
            self.status_updated.emit("🔍 Initializing comparison with Deezer...")
            
            # Import the comparison engine
            logger.info("Importing comparison engine...")
            try:
                from library_scanner.core.comparison_engine import ComparisonEngine
                from library_scanner.services.deezer_service import DeezerService
                logger.info("Imports successful")
            except ImportError as e:
                logger.error(f"Import error: {e}")
                self.comparison_error.emit(f"Import error: {e}")
                return
            
            # Get ARL token from config
            arl_token = self.config.get_setting('deezer.arl', '') if self.config else ''
            
            if not arl_token:
                self.comparison_error.emit("No Deezer ARL token found. Please configure your ARL token in Settings.")
                return
            
            # Initialize services with ARL token
            deezer_service = DeezerService(arl_token)
            
            # Create a config wrapper that provides threshold methods
            class ConfigWrapper:
                def __init__(self, main_config):
                    self.main_config = main_config
                
                def get_album_match_threshold(self):
                    return self.main_config.get_setting('library_scanner.album_match_threshold', 75)
                
                def get_track_match_threshold(self):
                    return self.main_config.get_setting('library_scanner.track_match_threshold', 80)
            
            config_wrapper = ConfigWrapper(self.config)
            comparison_engine = ComparisonEngine(deezer_service, config_wrapper)
            
            self.status_updated.emit("🎵 Starting comparison with Deezer...")
            self.progress_updated.emit(10)
            
            # Run the comparison
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                results = loop.run_until_complete(self._run_async_comparison(deezer_service, comparison_engine))
                
                self.progress_updated.emit(100)
                self.status_updated.emit("✅ Comparison completed successfully")
                
                # Return results
                self.comparison_completed.emit(results)
                
            finally:
                loop.close()
                
        except Exception as e:
            logger.error(f"Error during comparison: {e}")
            self.comparison_error.emit(str(e))
    
    async def _run_async_comparison(self, deezer_service, comparison_engine):
        """Run the async comparison process."""
        try:
            # Initialize the Deezer service
            await deezer_service.initialize()
            
            # Debug: Log the raw scan data first
            logger.info(f"Raw scan data count: {len(self.local_albums)}")
            if self.local_albums:
                sample_track = self.local_albums[0]
                logger.info(f"Sample raw track data: {sample_track}")
                logger.info(f"Sample track keys: {list(sample_track.keys())}")
                logger.info(f"Sample track artist: {sample_track.get('artist', 'NOT_FOUND')}")
                logger.info(f"Sample track album: {sample_track.get('album', 'NOT_FOUND')}")
                logger.info(f"Sample track album_artist: {sample_track.get('album_artist', 'NOT_FOUND')}")
            
            # Check if data is already in album format or needs grouping
            if self.local_albums and isinstance(self.local_albums[0], dict):
                # Check if this looks like track-level data that needs grouping
                sample = self.local_albums[0]
                has_track_fields = 'path' in sample and 'name' in sample
                has_album_fields = 'album_artist' in sample and 'album' in sample
                
                if has_track_fields and has_album_fields:
                    # This is track-level data from scan results - convert to album format
                    logger.info("Converting track-level scan data to album format for comparison")
                    album_data = self._convert_tracks_to_albums(self.local_albums)
                else:
                    # This might already be album-level data
                    logger.info("Using existing album-level data for comparison")
                    album_data = self.local_albums
            else:
                # Fallback to grouping
                logger.info("Grouping track-level data into albums")
                album_data = self._group_tracks_by_album(self.local_albums)
            
            # Debug: Log the structure of album data
            logger.info(f"Grouped albums count: {len(album_data)}")
            if album_data:
                logger.info(f"Sample album data: {album_data[0]}")
            else:
                # Debug why no albums were found
                logger.error("No albums found after grouping. Analyzing tracks...")
                valid_tracks = 0
                for i, track in enumerate(self.local_albums[:10]):  # Check first 10 tracks
                    album = track.get('album', 'Unknown Album')
                    album_artist = track.get('album_artist') or track.get('artist', 'Unknown Artist')
                    logger.info(f"Track {i}: album='{album}', album_artist='{album_artist}', artist='{track.get('artist', 'NOT_FOUND')}'")
                    if not (album == 'Unknown Album' and album_artist == 'Unknown Artist'):
                        valid_tracks += 1
                logger.info(f"Found {valid_tracks} tracks with valid metadata out of {min(10, len(self.local_albums))} checked")
            
            if not album_data:
                # More detailed error message
                if not self.local_albums:
                    raise Exception("No scan data found. Please run a library scan first.")
                else:
                    raise Exception(f"No albums found after processing {len(self.local_albums)} tracks. Check the logs for detailed track analysis.")
            
            # Run the comparison
            results = await comparison_engine.compare_albums_with_deezer(album_data)
            
            return results
            
        finally:
            # Always close the Deezer service
            try:
                await deezer_service.close()
            except Exception as e:
                logger.warning(f"Error closing Deezer service: {e}")
    
    def _convert_tracks_to_albums(self, tracks):
        """Convert clean track data from scan_results.json to album format for comparison."""
        from collections import defaultdict
        
        albums_dict = defaultdict(lambda: {
            'tracks': [],
            'album_artist': 'Unknown Artist',
            'album': 'Unknown Album',
            'year': None
        })
        
        for track in tracks:
            # Use the clean data directly from scan_results.json
            album = track.get('album', 'Unknown Album')
            album_artist = track.get('album_artist', track.get('artist', 'Unknown Artist'))
            
            # Debug logging for each track - ENHANCED
            print(f"=== PROCESSING TRACK ===")
            print(f"Raw track data: {track}")
            print(f"Extracted album: '{album}'")
            print(f"Extracted album_artist: '{album_artist}'")
            print(f"Track path: '{track.get('path', 'Unknown')}'")
            
            # Skip tracks with no meaningful data
            if album == 'Unknown Album' and album_artist == 'Unknown Artist':
                print(f"=== SKIPPING: No meaningful data ===")
                logger.warning(f"Skipping track with no meaningful data: {track.get('path', 'Unknown')}")
                continue
            
            # Additional validation - skip if artist looks like a path
            if '\\' in album_artist or '/' in album_artist or ':' in album_artist:
                print(f"=== SKIPPING: Path-like artist '{album_artist}' ===")
                logger.warning(f"Skipping track with path-like artist '{album_artist}': {track.get('path', 'Unknown')}")
                continue
            
            album_key = (album_artist, album)
            print(f"=== CREATING ALBUM KEY: {album_key} ===")
            
            albums_dict[album_key]['album_artist'] = album_artist
            albums_dict[album_key]['album'] = album
            albums_dict[album_key]['tracks'].append(track)
            print(f"=== ADDED TO ALBUM: '{album}' by '{album_artist}' (total tracks: {len(albums_dict[album_key]['tracks'])}) ===")
            
            # Use year from track if available
            if track.get('year') and not albums_dict[album_key]['year']:
                albums_dict[album_key]['year'] = track.get('year')
        
        # Convert to list format expected by comparison engine
        album_list = []
        for (artist, album), data in albums_dict.items():
            album_list.append({
                'album_artist': data['album_artist'],
                'album': data['album'],
                'year': data['year'],
                'num_tracks': len(data['tracks'])
            })
        
        logger.info(f"Converted {len(tracks)} tracks to {len(album_list)} albums")
        
        # Debug: Log the albums that were created
        for album in album_list:
            logger.info(f"Created album: '{album['album_artist']}' - '{album['album']}' ({album['num_tracks']} tracks)")
        
        return album_list
    
    def _group_tracks_by_album(self, tracks):
        """Group track-level data into album-level data for comparison."""
        from collections import defaultdict
        
        albums_dict = defaultdict(lambda: {
            'tracks': [],
            'album_artist': 'Unknown Artist',
            'album': 'Unknown Album',
            'year': None
        })
        
        for track in tracks:
            # Get album and artist info, using fallbacks
            album = track.get('album', 'Unknown Album')
            album_artist = track.get('album_artist') or track.get('artist', 'Unknown Artist')
            
            # Filter out invalid album artists (common folder names)
            invalid_artists = ['Music', 'music', 'MUSIC', 'Various Artists', 'Various', 'Compilation', 'Compilations']
            if album_artist in invalid_artists:
                logger.warning(f"DEBUG: Filtering out invalid album_artist '{album_artist}' for track: {track.get('path', 'Unknown')}")
                # Try to use the regular artist field instead
                fallback_artist = track.get('artist', 'Unknown Artist')
                if fallback_artist not in invalid_artists:
                    album_artist = fallback_artist
                    logger.warning(f"DEBUG: Using fallback artist: {album_artist}")
                else:
                    # Skip this track entirely
                    logger.warning(f"DEBUG: No valid artist found, skipping track")
                    continue
            
            # Skip only if both album and artist are completely missing/unknown
            if album == 'Unknown Album' and album_artist == 'Unknown Artist':
                logger.debug(f"Skipping track with no metadata: {track.get('path', 'Unknown')}")
                continue
            
            album_key = (album_artist, album)
            
            albums_dict[album_key]['album_artist'] = album_artist
            albums_dict[album_key]['album'] = album
            albums_dict[album_key]['tracks'].append(track)
            
            # Use the most recent year if multiple tracks have different years
            if track.get('year') and (not albums_dict[album_key]['year'] or track['year'] > albums_dict[album_key]['year']):
                albums_dict[album_key]['year'] = track['year']
        
        # Convert to list format expected by comparison engine
        album_list = []
        for (artist, album), data in albums_dict.items():
            album_list.append({
                'album_artist': data['album_artist'],
                'album': data['album'],
                'year': data['year'],
                'track_count': len(data['tracks']),
                'tracks': data['tracks']
            })
        
        return album_list

class LibraryScannerWidget(QWidget):
    """Minimal Library Scanner widget for testing integration."""
    
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self._checkbox_change_in_progress = False
        self.local_albums = []
        self.fast_comparison_results = {}
        # Track selected albums across all artists
        self.selected_albums_global = set()  # Set of (artist_name, album_title) tuples
        
        self.setup_ui()
        self.apply_deemusic_styling()
        
        # Initialize paths list
        self.update_paths_list()
        
        # Set initial UI state first
        self.initialize_ui_state()
        
        # Don't load previous results during initialization - use lazy loading
        # self.load_previous_results()  # Moved to lazy loading
        self._results_loaded = False
    
    def get_appdata_path(self) -> Path:
        """Get the DeeMusic AppData directory path."""
        import sys
        app_name = "DeeMusic"
        
        if sys.platform == "win32":
            appdata = os.getenv('APPDATA')
            if appdata:
                return Path(appdata) / app_name
            else:
                return Path.home() / app_name
        elif sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / app_name
        else:
            xdg_config_home = os.getenv('XDG_CONFIG_HOME')
            if xdg_config_home:
                return Path(xdg_config_home) / app_name
            else:
                return Path.home() / ".config" / app_name
    
    def load_previous_results(self):
        """Load previous scan and comparison results from AppData."""
        if self._results_loaded:
            return  # Already loaded
            
        try:
            logger.info("Loading previous results...")
            appdata_path = self.get_appdata_path()
            logger.info(f"AppData path: {appdata_path}")
            
            # Load scan results
            scan_results_path = appdata_path / "scan_results.json"
            logger.info(f"Scan results path: {scan_results_path}")
            logger.info(f"Scan results file exists: {scan_results_path.exists()}")
            if scan_results_path.exists():
                self.load_scan_results(scan_results_path)
            else:
                logger.info("No scan results file found")
            
            # Load comparison results
            comparison_results_path = appdata_path / "fast_comparison_results.json"
            if comparison_results_path.exists():
                self.load_comparison_results(comparison_results_path)
            
            self._results_loaded = True
                
        except Exception as e:
            logger.error(f"Error loading previous results: {e}")
    
    def showEvent(self, event):
        """Override showEvent to load data when widget is actually shown."""
        super().showEvent(event)
        if not self._results_loaded:
            logger.info("Library scanner widget shown, loading previous results...")
            self.load_previous_results()
    
    def load_scan_results(self, scan_results_path: Path):
        """Load scan results from file."""
        try:
            logger.info(f"Loading scan results from: {scan_results_path}")
            with open(scan_results_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            print(f"DEBUG: Loaded scan_results.json keys: {list(data.keys())}")
            print(f"DEBUG: File size: {scan_results_path.stat().st_size} bytes")
            
            scan_timestamp = data.get('scan_timestamp', 'Unknown')
            total_files = data.get('total_files', 0)
            track_count = data.get('track_count', 0)
            scan_time = data.get('scan_time', 0)
            
            # Handle different JSON structures - prioritize 'albums' format
            files_data = []
            if 'albums' in data:
                # New album-based format (preferred)
                albums_data = data.get('albums', [])
                files_data = albums_data  # Use album data directly
                total_files = len(albums_data)
                print(f"DEBUG: Found {len(albums_data)} albums in scan_results.json")
            elif 'files' in data:
                # Legacy files format
                files_data = data.get('files', [])
                total_files = len(files_data) if total_files == 0 else total_files
                print(f"DEBUG: Found {len(files_data)} files in legacy format")
            elif 'tracks' in data:
                # Old format with tracks structure
                tracks_data = data.get('tracks', {})
                if isinstance(tracks_data, dict):
                    # Convert tracks structure to files format for compatibility
                    albums = tracks_data.get('albums', [])
                    for album in albums:
                        # Create file entries from album data
                        album_path = album.get('folder_path', album.get('path', ''))
                        if album_path:
                            files_data.append({
                                'path': album_path,
                                'name': album.get('album', 'Unknown'),
                                'artist': album.get('album_artist', 'Unknown'),
                                'modified': 0  # Will be updated during scan
                            })
                    # Count the actual albums instead of using track_count
                    album_count = len(albums)
                    total_files = album_count
                    print(f"DEBUG: Converted {len(albums)} tracks to album format")
            
            # Update status display with loaded scan info
            if scan_timestamp != 'Unknown':
                # Format timestamp for display
                try:
                    from datetime import datetime
                    if 'T' in scan_timestamp:
                        dt = datetime.fromisoformat(scan_timestamp.replace('T', ' '))
                        formatted_date = dt.strftime('%Y-%m-%d')
                    else:
                        formatted_date = scan_timestamp.split(' ')[0] if ' ' in scan_timestamp else scan_timestamp
                    
                    self.status_label.setText(f"📂 Loaded scan from {formatted_date} - {total_files:,} files")
                    logger.info(f"Loaded scan results: {total_files} files from {formatted_date}")
                except Exception as e:
                    logger.error(f"Error formatting scan timestamp: {e}")
                    self.status_label.setText(f"📂 Loaded previous scan - {total_files:,} files")
            
            # Store the scan data for use by Update Scan and comparison
            self.local_albums = files_data
            logger.info(f"Set self.local_albums to {len(files_data)} albums")
            print(f"DEBUG: local_albums populated with {len(files_data)} items")
            if files_data:
                print(f"DEBUG: First album sample: {files_data[0]}")
            
            # Debug logging
            logger.info(f"Loaded scan data: {len(files_data)} files from scan_results.json")
            logger.info(f"Total files from JSON: {total_files}")
            logger.info(f"Track count from JSON: {track_count}")
            
            # The status has already been set above with the correct total_files count
            
            # Enable Update Scan button if we have scan data (check multiple indicators)
            has_scan_data = (len(files_data) > 0) or (track_count > 0) or (total_files > 0)
            
            if has_scan_data:
                self.update_scan_btn.setEnabled(True)
                self.clear_results_btn.setEnabled(True)
                self.compare_btn.setEnabled(True)
                
                # Enable incremental comparison if we have previous comparison results
                if hasattr(self, 'fast_comparison_results') and self.fast_comparison_results:
                    self.incremental_compare_btn.setEnabled(True)
                
                logger.info(f"Update Scan button enabled - scan data available ({total_files} files)")
            else:
                logger.warning("No scan data found - Update Scan disabled")
            
        except Exception as e:
            logger.error(f"Error loading scan results: {e}")
    
    def load_comparison_results(self, comparison_results_path: Path):
        """Load comparison results from file."""
        try:
            with open(comparison_results_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            results = data.get('results', {})
            self.fast_comparison_results = results
            
            # Populate UI
            self.populate_comparison_ui(results)
            
            # Count missing albums
            total_missing = 0
            for artist_data in results.get('artists', {}).values():
                missing_albums = artist_data.get('missing_albums', [])
                total_missing += len(missing_albums)
            
            if total_missing > 0:
                self.import_btn.setEnabled(True)
                logger.info(f"Loaded comparison results: {total_missing} missing albums")
            
            # Enable incremental comparison button since we have comparison results
            if hasattr(self, 'incremental_compare_btn'):
                self.incremental_compare_btn.setEnabled(True)
            
        except Exception as e:
            logger.error(f"Error loading comparison results: {e}")
    
    def populate_comparison_ui(self, results: Dict[str, Any]):
        """Populate the comparison UI with loaded results."""
        try:
            # Store results for filtering
            self.fast_comparison_results = results
            
            # Use the filtered version
            self.populate_comparison_ui_with_filters(results)
            
        except Exception as e:
            logger.error(f"Error populating comparison UI: {e}")
    
    def setup_ui(self):
        """Setup the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # Header
        header_layout = QHBoxLayout()
        
        # Back button
        self.back_btn = QPushButton("← Back to DeeMusic")
        self.back_btn.setObjectName("BackButton")
        self.back_btn.clicked.connect(self.go_back_to_deemusic)
        self.back_btn.setToolTip("Return to main DeeMusic interface")
        header_layout.addWidget(self.back_btn)
        
        # Spacer
        header_layout.addSpacing(20)
        
        title_label = QLabel("Library Scanner")
        title_label.setObjectName("LibraryScannerTitle")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        self.status_label = QLabel("Loading previous results...")
        self.status_label.setObjectName("StatusLabel")
        header_layout.addWidget(self.status_label)
        
        layout.addLayout(header_layout)
        
        # Tab widget
        self.tab_widget = QTabWidget()
        
        # Scan tab with full functionality
        scan_tab = QWidget()
        scan_layout = QVBoxLayout(scan_tab)
        scan_layout.setSpacing(15)
        
        # Library paths section
        paths_group = QGroupBox("Library Paths")
        paths_group.setObjectName("LibraryPathsGroup")
        paths_layout = QVBoxLayout(paths_group)
        
        # Path controls
        path_controls = QHBoxLayout()
        
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Enter library path...")
        self.path_input.setObjectName("PathInput")
        
        browse_btn = QPushButton("Browse")
        browse_btn.setObjectName("BrowseButton")
        browse_btn.clicked.connect(self.browse_library_path)
        
        add_path_btn = QPushButton("Add Path")
        add_path_btn.setObjectName("AddPathButton")
        add_path_btn.clicked.connect(self.add_library_path)
        
        path_controls.addWidget(self.path_input, 1)
        path_controls.addWidget(browse_btn)
        path_controls.addWidget(add_path_btn)
        
        paths_layout.addLayout(path_controls)
        
        # Paths list
        self.paths_list = QTreeWidget()
        self.paths_list.setHeaderLabel("Configured Library Paths")
        self.paths_list.setObjectName("PathsList")
        paths_layout.addWidget(self.paths_list)
        
        # Remove path button
        remove_path_btn = QPushButton("Remove Selected Path")
        remove_path_btn.setObjectName("RemovePathButton")
        remove_path_btn.clicked.connect(self.remove_library_path)
        paths_layout.addWidget(remove_path_btn)
        
        scan_layout.addWidget(paths_group)
        
        # Scan section
        scan_group = QGroupBox("Library Scan")
        scan_group.setObjectName("ScanGroup")
        scan_group_layout = QVBoxLayout(scan_group)
        
        # Scan buttons
        scan_buttons_layout = QHBoxLayout()
        
        self.scan_btn = QPushButton("🔍 Full Scan")
        self.scan_btn.setObjectName("ScanButton")
        self.scan_btn.clicked.connect(self.scan_library)
        scan_buttons_layout.addWidget(self.scan_btn)
        
        self.update_scan_btn = QPushButton("🔄 Update Scan")
        self.update_scan_btn.setObjectName("UpdateScanButton")
        self.update_scan_btn.clicked.connect(self.update_scan_library)
        self.update_scan_btn.setEnabled(False)
        scan_buttons_layout.addWidget(self.update_scan_btn)
        
        self.clear_results_btn = QPushButton("🗑️ Clear Results")
        self.clear_results_btn.setObjectName("ClearResultsButton")
        self.clear_results_btn.clicked.connect(self.clear_scan_results)
        self.clear_results_btn.setEnabled(False)
        scan_buttons_layout.addWidget(self.clear_results_btn)
        
        scan_buttons_layout.addStretch()
        scan_group_layout.addLayout(scan_buttons_layout)
        
        # Comparison section
        comparison_buttons_layout = QHBoxLayout()
        
        self.compare_btn = QPushButton("🎵 Compare with Deezer")
        self.compare_btn.setObjectName("CompareButton")
        self.compare_btn.clicked.connect(self.compare_with_deezer)
        self.compare_btn.setEnabled(False)
        self.compare_btn.setToolTip("Compare your library with Deezer to find missing albums")
        comparison_buttons_layout.addWidget(self.compare_btn)
        
        self.incremental_compare_btn = QPushButton("🔄 Update Comparison")
        self.incremental_compare_btn.setObjectName("IncrementalCompareButton")
        self.incremental_compare_btn.clicked.connect(self.incremental_compare_with_deezer)
        self.incremental_compare_btn.setEnabled(False)
        self.incremental_compare_btn.setToolTip("Compare only new/updated albums since last scan")
        comparison_buttons_layout.addWidget(self.incremental_compare_btn)
        
        comparison_buttons_layout.addStretch()
        scan_group_layout.addLayout(comparison_buttons_layout)
        
        # Progress section
        self.scan_progress = QProgressBar()
        self.scan_progress.setVisible(False)
        self.scan_progress.setObjectName("ScanProgress")
        self.scan_progress.setMinimum(0)
        self.scan_progress.setMaximum(100)
        scan_group_layout.addWidget(self.scan_progress)
        
        # Current scanning item display
        self.current_scan_label = QLabel("")
        self.current_scan_label.setVisible(False)
        self.current_scan_label.setObjectName("CurrentScanLabel")
        self.current_scan_label.setWordWrap(True)
        scan_group_layout.addWidget(self.current_scan_label)
        
        # Progress info
        progress_info_layout = QHBoxLayout()
        
        self.progress_percentage = QLabel("")
        self.progress_percentage.setVisible(False)
        self.progress_percentage.setObjectName("ProgressPercentage")
        progress_info_layout.addWidget(self.progress_percentage)
        
        progress_info_layout.addStretch()
        
        self.file_count_label = QLabel("")
        self.file_count_label.setVisible(False)
        self.file_count_label.setObjectName("FileCountLabel")
        progress_info_layout.addWidget(self.file_count_label)
        
        self.scan_speed_label = QLabel("")
        self.scan_speed_label.setVisible(False)
        self.scan_speed_label.setObjectName("ScanSpeedLabel")
        progress_info_layout.addWidget(self.scan_speed_label)
        
        self.cancel_scan_btn = QPushButton("❌ Cancel")
        self.cancel_scan_btn.setObjectName("CancelScanButton")
        self.cancel_scan_btn.clicked.connect(self.cancel_scan)
        self.cancel_scan_btn.setVisible(False)
        progress_info_layout.addWidget(self.cancel_scan_btn)
        
        scan_group_layout.addLayout(progress_info_layout)
        
        # Scan status
        self.scan_status = QLabel("Ready to scan - Add library paths above")
        self.scan_status.setObjectName("ScanStatus")
        scan_group_layout.addWidget(self.scan_status)
        
        scan_layout.addWidget(scan_group)
        
        self.tab_widget.addTab(scan_tab, "📁 Library Scan")
        
        # Comparison tab
        comparison_tab = QWidget()
        comparison_layout = QVBoxLayout(comparison_tab)
        
        # Results section
        results_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Filter controls
        filter_layout = QHBoxLayout()
        
        self.filter_live_checkbox = QCheckBox("Filter out Live albums")
        self.filter_live_checkbox.setChecked(True)
        self.filter_live_checkbox.stateChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.filter_live_checkbox)
        
        self.filter_duplicates_checkbox = QCheckBox("Filter out Deluxe, Remaster etc duplicates")
        self.filter_duplicates_checkbox.setChecked(True)
        self.filter_duplicates_checkbox.stateChanged.connect(self.apply_filters)
        filter_layout.addWidget(self.filter_duplicates_checkbox)
        
        filter_layout.addStretch()
        comparison_layout.addLayout(filter_layout)
        
        # Results section
        results_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Artists tree with wider columns
        self.artists_tree = QTreeWidget()
        self.artists_tree.setHeaderLabels(["Artist", "Missing Albums"])
        self.artists_tree.itemClicked.connect(self.on_artist_selected)
        self.artists_tree.itemChanged.connect(self.on_artist_checkbox_changed)
        # Enable selection mode
        self.artists_tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        # Connect selection change signal
        self.artists_tree.itemSelectionChanged.connect(self.on_artist_selection_changed)
        # Set wider column widths
        self.artists_tree.setColumnWidth(0, 300)  # Artist column
        self.artists_tree.setColumnWidth(1, 150)  # Missing Albums column
        results_splitter.addWidget(self.artists_tree)
        
        # Albums tree with wider columns
        self.albums_tree = QTreeWidget()
        self.albums_tree.setHeaderLabels(["Album", "Artist", "Type"])
        # Connect the itemChanged signal to handle checkbox changes
        self.albums_tree.itemChanged.connect(self.on_album_checkbox_changed)
        # Set wider column widths
        self.albums_tree.setColumnWidth(0, 350)  # Album column
        self.albums_tree.setColumnWidth(1, 200)  # Artist column
        self.albums_tree.setColumnWidth(2, 100)  # Type column
        results_splitter.addWidget(self.albums_tree)
        
        results_splitter.setSizes([400, 600])
        comparison_layout.addWidget(results_splitter)
        
        # Import button
        self.import_btn = QPushButton("📤 Import Selected to DeeMusic")
        self.import_btn.setEnabled(False)
        self.import_btn.clicked.connect(self.import_selected)
        comparison_layout.addWidget(self.import_btn)
        
        self.tab_widget.addTab(comparison_tab, "🔍 Comparison")
        
        layout.addWidget(self.tab_widget)
    
    def apply_deemusic_styling(self):
        """Apply DeeMusic styling with light backgrounds and dark text."""
        # Check if parent has theme manager to detect dark mode
        is_dark_mode = self.is_dark_mode()
        
        if is_dark_mode:
            # Dark mode - keep existing dark theme
            self.setStyleSheet("""
                /* Dark mode styling */
                LibraryScannerWidget {
                    background-color: #1a1a1a;
                    color: #FFFFFF;
                }
                
                QTabWidget {
                    background-color: #1a1a1a;
                    color: #FFFFFF;
                }
                
                QTabWidget::pane {
                    border: 1px solid #333333;
                    background-color: #1a1a1a;
                }
                
                QTabBar::tab {
                    background-color: #2a2a2a;
                    color: #FFFFFF;
                    padding: 10px 20px;
                    margin-right: 2px;
                    border-top-left-radius: 5px;
                    border-top-right-radius: 5px;
                    font-weight: bold;
                }
                
                QTabBar::tab:selected {
                    background-color: #6C2BD9;
                    color: #FFFFFF;
                }
                
                QPushButton {
                    background-color: #6C2BD9;
                    color: #FFFFFF;
                    border: none;
                    padding: 10px 20px;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 14px;
                }
                
                QTreeWidget {
                    background-color: #2a2a2a;
                    border: 1px solid #333333;
                    border-radius: 6px;
                    color: #FFFFFF;
                    selection-background-color: #6C2BD9;
                    font-size: 14px;
                }
                
                QLineEdit {
                    background-color: #2a2a2a;
                    border: 1px solid #333333;
                    border-radius: 6px;
                    padding: 8px;
                    color: #FFFFFF;
                    font-size: 14px;
                }
                
                QGroupBox {
                    color: #FFFFFF;
                    font-weight: bold;
                    font-size: 16px;
                    border: 2px solid #333333;
                    border-radius: 8px;
                    margin-top: 10px;
                    padding-top: 10px;
                }
                
                QLabel {
                    color: #FFFFFF;
                    font-size: 14px;
                    font-weight: bold;
                }
                
                QLabel#StatusLabel {
                    color: #000000;
                    background-color: #E8E8E8;
                    padding: 8px 12px;
                    border-radius: 6px;
                    border: 1px solid #CCCCCC;
                }
            """)
        else:
            # Light mode - light backgrounds with dark text
            self.setStyleSheet("""
                /* Light mode styling */
                LibraryScannerWidget {
                    background-color: #FFFFFF;
                    color: #000000;
                }
                
                QTabWidget {
                    background-color: #FFFFFF;
                    color: #000000;
                }
                
                QTabWidget::pane {
                    border: 1px solid #CCCCCC;
                    background-color: #FFFFFF;
                }
                
                QTabBar::tab {
                    background-color: #F5F5F5;
                    color: #000000;
                    padding: 10px 20px;
                    margin-right: 2px;
                    border-top-left-radius: 5px;
                    border-top-right-radius: 5px;
                    font-weight: bold;
                    border: 1px solid #CCCCCC;
                }
                
                QTabBar::tab:selected {
                    background-color: #6C2BD9;
                    color: #FFFFFF;
                    border-color: #6C2BD9;
                }
                
                QTabBar::tab:hover {
                    background-color: #E8E8E8;
                }
                
                QPushButton {
                    background-color: #6C2BD9;
                    color: #FFFFFF;
                    border: none;
                    padding: 10px 20px;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 14px;
                }
                
                QPushButton:hover {
                    background-color: #7C3BE9;
                }
                
                QPushButton:pressed {
                    background-color: #5C1BC9;
                }
                
                QPushButton:disabled {
                    background-color: #CCCCCC;
                    color: #666666;
                }
                
                QPushButton#BackButton {
                    background-color: #F5F5F5;
                    color: #000000;
                    border: 1px solid #CCCCCC;
                    padding: 8px 16px;
                    border-radius: 6px;
                    font-weight: bold;
                    font-size: 14px;
                }
                
                QPushButton#BackButton:hover {
                    background-color: #E8E8E8;
                    border-color: #AAAAAA;
                }
                
                QTreeWidget {
                    background-color: #FFFFFF;
                    border: 1px solid #CCCCCC;
                    border-radius: 6px;
                    color: #000000;
                    selection-background-color: #6C2BD9;
                    selection-color: #FFFFFF;
                    font-size: 14px;
                    alternate-background-color: #F9F9F9;
                }
                
                QTreeWidget::item {
                    padding: 8px;
                    border-bottom: 1px solid #EEEEEE;
                    color: #000000;
                }
                
                QTreeWidget::item:selected {
                    background-color: #6C2BD9;
                    color: #FFFFFF;
                }
                
                QTreeWidget::item:hover {
                    background-color: #F0F0F0;
                    color: #000000;
                }
                
                QHeaderView::section {
                    background-color: #F5F5F5;
                    color: #000000;
                    padding: 8px;
                    border: 1px solid #CCCCCC;
                    font-weight: bold;
                }
                
                QLineEdit {
                    background-color: #FFFFFF;
                    border: 1px solid #CCCCCC;
                    border-radius: 6px;
                    padding: 8px;
                    color: #000000;
                    font-size: 14px;
                }
                
                QLineEdit:focus {
                    border-color: #6C2BD9;
                    border-width: 2px;
                }
                
                QGroupBox {
                    color: #000000;
                    font-weight: bold;
                    font-size: 16px;
                    border: 2px solid #CCCCCC;
                    border-radius: 8px;
                    margin-top: 10px;
                    padding-top: 10px;
                    background-color: #FAFAFA;
                }
                
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 8px 0 8px;
                    color: #000000;
                    background-color: #FFFFFF;
                }
                
                QProgressBar {
                    border: 1px solid #CCCCCC;
                    border-radius: 6px;
                    text-align: center;
                    background-color: #F5F5F5;
                    color: #000000;
                    font-weight: bold;
                }
                
                QProgressBar::chunk {
                    background-color: #6C2BD9;
                    border-radius: 5px;
                }
                
                QLabel {
                    color: #000000;
                    font-size: 14px;
                    font-weight: bold;
                    background-color: transparent;
                }
                
                QLabel#LibraryScannerTitle {
                    color: #000000;
                    background-color: transparent;
                    font-size: 24px;
                    font-weight: bold;
                }
                
                QLabel#StatusLabel {
                    color: #000000;
                    background-color: #E8F4FD;
                    font-size: 14px;
                    padding: 8px 12px;
                    border-radius: 6px;
                    font-weight: bold;
                    border: 1px solid #B3D9F2;
                }
                
                QLabel#CurrentScanLabel {
                    color: #000000;
                    background-color: #F9F9F9;
                    font-size: 13px;
                    font-weight: normal;
                    padding: 8px;
                    border-radius: 4px;
                    border: 1px solid #DDDDDD;
                }
                
                QWidget {
                    color: #000000;
                    background-color: #FFFFFF;
                }
            """)
    
    def is_dark_mode(self):
        """Check if the application is in dark mode."""
        try:
            # Try to get theme from parent main window
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'theme_manager'):
                main_window = main_window.parent()
            
            if main_window and hasattr(main_window, 'theme_manager'):
                return main_window.theme_manager.current_theme == 'dark'
            
            # Default to light mode if can't determine
            return False
        except Exception:
            return False
    
    def on_artist_selected(self, item, column):
        """Handle artist selection."""
        try:
            artist_name = item.text(0)
            artist_info = item.data(0, Qt.ItemDataRole.UserRole)
            
            if not artist_info:
                return
            
            self.albums_tree.clear()
            missing_albums = artist_info.get('missing_albums', [])
            
            for album_data in missing_albums:
                if isinstance(album_data, dict):
                    # Handle both Deezer format ('title', 'artist') and local format ('album', 'album_artist')
                    album_title = album_data.get('title') or album_data.get('album', 'Unknown Album')
                    album_artist = album_data.get('artist') or album_data.get('album_artist', artist_name)
                else:
                    album_title = str(album_data)
                    album_artist = artist_name
                
                album_item = QTreeWidgetItem([album_title, album_artist])
                album_item.setCheckState(0, Qt.CheckState.Unchecked)
                album_item.setData(0, Qt.ItemDataRole.UserRole, album_data)
                self.albums_tree.addTopLevelItem(album_item)
            
            self.albums_tree.sortItems(0, Qt.SortOrder.AscendingOrder)
            
        except Exception as e:
            logger.error(f"Error handling artist selection: {e}")
    
    def go_back_to_deemusic(self):
        """Navigate back to the main DeeMusic interface."""
        try:
            # Get the main window from the parent hierarchy
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'content_stack'):
                main_window = main_window.parent()
            
            if main_window and hasattr(main_window, 'content_stack'):
                # Switch back to the home page (index 0)
                home_page_index = 0
                main_window._switch_to_view(home_page_index)
                logger.info("Navigated back to DeeMusic home page")
            else:
                logger.error("Could not find main window to navigate back")
                QMessageBox.information(self, "Navigation", "Unable to navigate back to main DeeMusic interface.")
                
        except Exception as e:
            logger.error(f"Error navigating back to DeeMusic: {e}")
            QMessageBox.critical(self, "Navigation Error", f"Error navigating back:\n\n{str(e)}")
    
    def browse_library_path(self):
        """Browse for library path."""
        path = QFileDialog.getExistingDirectory(self, "Select Library Path")
        if path:
            self.path_input.setText(path)
    
    def add_library_path(self):
        """Add library path."""
        path = self.path_input.text().strip()
        if path and os.path.exists(path):
            # Add to config and update UI
            paths = self.config.get_setting('library_scanner.library_paths', [])
            if path not in paths:
                paths.append(path)
                self.config.set_setting('library_scanner.library_paths', paths)
                self.update_paths_list()
                self.path_input.clear()
                self.scan_btn.setEnabled(True)
                self.status_label.setText(f"Ready - {len(paths)} path(s) configured")
        else:
            QMessageBox.warning(self, "Invalid Path", "Please enter a valid directory path.")
    
    def remove_library_path(self):
        """Remove selected library path."""
        current_item = self.paths_list.currentItem()
        if current_item:
            path = current_item.text(0)
            paths = self.config.get_setting('library_scanner.library_paths', [])
            if path in paths:
                paths.remove(path)
                self.config.set_setting('library_scanner.library_paths', paths)
                self.update_paths_list()
                if len(paths) == 0:
                    self.scan_btn.setEnabled(False)
                    self.status_label.setText("Add library paths to get started")
                else:
                    self.status_label.setText(f"Ready - {len(paths)} path(s) configured")
    
    def update_paths_list(self):
        """Update the paths list widget."""
        self.paths_list.clear()
        paths = self.config.get_setting('library_scanner.library_paths', [])
        for path in paths:
            item = QTreeWidgetItem([path])
            self.paths_list.addTopLevelItem(item)
    
    def load_folder_mtimes(self) -> Dict[str, float]:
        """Load folder modification times from AppData."""
        try:
            appdata_path = self.get_appdata_path()
            mtimes_path = appdata_path / "folder_mtimes.json"
            
            if mtimes_path.exists():
                with open(mtimes_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Error loading folder mtimes: {e}")
            return {}
    
    def save_folder_mtimes(self, mtimes: Dict[str, float]):
        """Save folder modification times to AppData."""
        try:
            appdata_path = self.get_appdata_path()
            appdata_path.mkdir(parents=True, exist_ok=True)
            mtimes_path = appdata_path / "folder_mtimes.json"
            
            with open(mtimes_path, 'w', encoding='utf-8') as f:
                json.dump(mtimes, f, indent=2)
            logger.info(f"Saved folder mtimes for {len(mtimes)} folders")
        except Exception as e:
            logger.error(f"Error saving folder mtimes: {e}")
    
    def save_file_mtimes(self, mtimes: Dict[str, float]):
        """Save file modification times to AppData (for incremental scans)."""
        try:
            appdata_path = self.get_appdata_path()
            appdata_path.mkdir(parents=True, exist_ok=True)
            mtimes_path = appdata_path / "folder_mtimes.json"  # Use same file as folder mtimes
            
            with open(mtimes_path, 'w', encoding='utf-8') as f:
                json.dump(mtimes, f, indent=2)
            logger.info(f"Saved file mtimes for {len(mtimes)} files")
        except Exception as e:
            logger.error(f"Error saving file mtimes: {e}")
    
    def get_folder_mtime(self, folder_path: Path) -> float:
        """Get the modification time of a folder."""
        try:
            return folder_path.stat().st_mtime
        except Exception:
            return 0.0
    
    def scan_library(self):
        """Start full library scan with detailed progress tracking."""
        library_paths = self.config.get_setting('library_scanner.library_paths', [])
        if not library_paths:
            QMessageBox.warning(self, "No Library Paths", "Please add library paths before scanning.")
            return
        
        # Show progress UI
        self.show_progress_ui()
        
        # Create and start scan worker
        print(f"DEBUG: Creating scan worker with paths: {library_paths}")
        self.scan_worker = ScanWorker(library_paths, scan_type="full")
        self.connect_scan_worker_signals()
        print(f"DEBUG: Starting scan worker...")
        self.scan_worker.start()
        print(f"DEBUG: Scan worker started, is running: {self.scan_worker.isRunning()}")
    
    def show_progress_ui(self):
        """Show the progress tracking UI elements."""
        self.scan_btn.setEnabled(False)
        self.update_scan_btn.setEnabled(False)
        
        # Show progress elements
        self.scan_progress.setVisible(True)
        self.scan_progress.setValue(0)
        self.current_scan_label.setVisible(True)
        self.progress_percentage.setVisible(True)
        self.file_count_label.setVisible(True)
        self.scan_speed_label.setVisible(True)
        self.cancel_scan_btn.setVisible(True)
        
        # Initialize labels
        self.progress_percentage.setText("0%")
        self.file_count_label.setText("0 / 0 files")
        self.scan_speed_label.setText("Calculating...")
        self.current_scan_label.setText("🔍 Initializing scan...")
    
    def hide_progress_ui(self):
        """Hide the progress tracking UI elements."""
        self.scan_progress.setVisible(False)
        self.current_scan_label.setVisible(False)
        self.progress_percentage.setVisible(False)
        self.file_count_label.setVisible(False)
        self.scan_speed_label.setVisible(False)
        self.cancel_scan_btn.setVisible(False)
        
        # Re-enable buttons
        self.scan_btn.setEnabled(True)
        self.update_scan_btn.setEnabled(True)
    
    def connect_scan_worker_signals(self):
        """Connect all scan worker signals to UI update methods."""
        self.scan_worker.progress_updated.connect(self.update_progress)
        self.scan_worker.current_file_updated.connect(self.update_current_file)
        self.scan_worker.status_updated.connect(self.update_scan_status)
        self.scan_worker.file_count_updated.connect(self.update_file_count)
        self.scan_worker.speed_updated.connect(self.update_scan_speed)
        self.scan_worker.scan_completed.connect(self.on_scan_completed)
        self.scan_worker.scan_error.connect(self.on_scan_error)
    
    def update_progress(self, percentage):
        """Update the progress bar and percentage label."""
        self.scan_progress.setValue(percentage)
        self.progress_percentage.setText(f"{percentage}%")
    
    def update_current_file(self, file_info):
        """Update the current file being scanned."""
        self.current_scan_label.setText(file_info)
    
    def update_scan_status(self, status):
        """Update the scan status label."""
        self.scan_status.setText(status)
    
    def update_file_count(self, current, total):
        """Update the file count display."""
        self.file_count_label.setText(f"{current:,} / {total:,} files")
    
    def update_scan_speed(self, speed):
        """Update the scanning speed display."""
        self.scan_speed_label.setText(speed)
    
    def on_scan_completed(self, results):
        """Handle scan completion."""
        try:
            self.hide_progress_ui()
            
            # Debug logging
            logger.info(f"DEBUG: Scan completed with results type: {results.get('type', 'unknown')}")
            logger.info(f"DEBUG: Results keys: {list(results.keys())}")
            logger.info(f"DEBUG: Scanned files count: {len(results.get('scanned_files', []))}")
            
            if results["type"] == "success":
                total_files = results["total_files"]
                scan_time = results["scan_time"]
                scanned_files = results.get("scanned_files", [])
                
                # Debug: Log first few scanned files
                if scanned_files:
                    logger.info(f"DEBUG: First scanned file sample: {scanned_files[0]}")
                else:
                    logger.warning("DEBUG: No scanned files found in results!")
                
                # Update status
                self.status_label.setText(f"✅ Scan completed - {total_files:,} files in {scan_time:.1f}s")
                self.scan_status.setText(f"✅ Full scan completed successfully\n"
                                       f"Found {total_files:,} music files in {scan_time:.1f} seconds")
                
                # Enable buttons
                self.update_scan_btn.setEnabled(True)
                self.clear_results_btn.setEnabled(True)
                self.compare_btn.setEnabled(True)
                
                # Save results to AppData
                self.save_scan_results(results)
                
                # Reload the scan results into local_albums for comparison
                logger.info("Reloading scan results into local_albums...")
                self.local_albums = results.get("scanned_files", [])
                logger.info(f"Loaded {len(self.local_albums)} files into local_albums")
                
                logger.info(f"Scan completed: {total_files} files in {scan_time:.1f}s")
                
            elif results["type"] == "no_files":
                self.status_label.setText("⚠️ No music files found")
                self.scan_status.setText("⚠️ No music files found in configured paths")
                
            elif results["type"] == "no_changes":
                self.status_label.setText("✅ No changes detected")
                self.scan_status.setText("✅ No changes detected - Library is up to date")
                
        except Exception as e:
            logger.error(f"Error handling scan completion: {e}")
            self.on_scan_error(str(e))
    
    def on_scan_error(self, error_message):
        """Handle scan errors."""
        self.hide_progress_ui()
        self.status_label.setText("❌ Scan failed")
        self.scan_status.setText(f"❌ Scan failed: {error_message}")
        
        QMessageBox.critical(self, "Scan Error", 
                           f"An error occurred during scanning:\n\n{error_message}")
        
        logger.error(f"Scan error: {error_message}")
    
    def save_scan_results(self, results):
        """Save scan results to AppData in proper album format."""
        try:
            appdata_path = self.get_appdata_path()
            appdata_path.mkdir(parents=True, exist_ok=True)
            
            # Save scan results in album format (compatible with library scanner)
            scan_results_path = appdata_path / "scan_results.json"
            library_paths = self.config.get_setting('library_scanner.library_paths', [])
            
            # Debug logging
            logger.info(f"Saving scan results: {len(results.get('scanned_files', []))} albums")
            logger.info(f"Results keys: {list(results.keys())}")
            
            # Debug: Print the actual results structure
            print(f"DEBUG SAVE: Results type: {results.get('type')}")
            print(f"DEBUG SAVE: Scanned files count: {len(results.get('scanned_files', []))}")
            print(f"DEBUG SAVE: Library paths: {library_paths}")
            if results.get('scanned_files'):
                print(f"DEBUG SAVE: First scanned file: {results['scanned_files'][0]}")
            
            with open(scan_results_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'scan_timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
                    'scan_time': results['scan_time'],
                    'scan_type': results['scan_type'],
                    'library_paths': library_paths,
                    'albums': results['scanned_files'],  # Now contains album data, not file data
                    'album_count': len(results['scanned_files'])
                }, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved {len(results['scanned_files'])} albums to {scan_results_path}")
            
            # Also save folder modification times for future incremental scans
            self.save_current_folder_mtimes()
            
        except Exception as e:
            logger.error(f"Error saving scan results: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            print(f"ERROR SAVING: {e}")
            print(f"ERROR TRACEBACK: {traceback.format_exc()}")
    
    def save_current_folder_mtimes(self):
        """Save current folder modification times for incremental scans."""
        try:
            library_paths = self.config.get_setting('library_scanner.library_paths', [])
            folder_mtimes = {}
            
            print(f"DEBUG MTIMES: Library paths: {library_paths}")
            
            for lib_path in library_paths:
                try:
                    path = Path(lib_path)
                    if path.exists():
                        folder_mtimes[str(path)] = path.stat().st_mtime
                        
                        # Also save mtimes for subdirectories (for more granular change detection)
                        for subfolder in path.rglob('*'):
                            if subfolder.is_dir():
                                try:
                                    folder_mtimes[str(subfolder)] = subfolder.stat().st_mtime
                                except Exception:
                                    pass  # Skip folders we can't access
                except Exception as e:
                    logger.warning(f"Could not get mtime for {lib_path}: {e}")
            
            if folder_mtimes:
                print(f"DEBUG MTIMES: Saving {len(folder_mtimes)} folder mtimes")
                self.save_folder_mtimes(folder_mtimes)
                logger.info(f"Saved modification times for {len(folder_mtimes)} folders")
            else:
                print("DEBUG MTIMES: No folder mtimes to save")
            
        except Exception as e:
            logger.error(f"Error saving current folder mtimes: {e}")
            print(f"ERROR MTIMES: {e}")

    def cancel_scan(self):
        """Cancel the current scan."""
        if hasattr(self, 'scan_worker') and self.scan_worker.isRunning():
            self.scan_worker.cancel()
            self.scan_worker.wait(3000)  # Wait up to 3 seconds for thread to finish
            
        self.hide_progress_ui()
        self.status_label.setText("❌ Scan cancelled")
        self.scan_status.setText("❌ Scan was cancelled by user")
    
    def clear_scan_results(self):
        """Clear scan results."""
        reply = QMessageBox.question(self, "Clear Results", 
                                   "Are you sure you want to clear all scan and comparison results?\n\n"
                                   "This will remove all cached data and you'll need to scan again.",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                   QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            # Clear local data
            self.local_albums = []
            self.fast_comparison_results = {}
            
            # Clear UI
            self.artists_tree.clear()
            self.albums_tree.clear()
            
            # Reset buttons
            self.import_btn.setEnabled(False)
            self.clear_results_btn.setEnabled(False)
            self.update_scan_btn.setEnabled(False)
            
            self.status_label.setText("Results cleared")
            self.scan_status.setText("Ready to scan - Add library paths above")
            
            # Optionally clear AppData files
            try:
                appdata_path = self.get_appdata_path()
                scan_results_path = appdata_path / "scan_results.json"
                comparison_results_path = appdata_path / "fast_comparison_results.json"
                mtimes_path = appdata_path / "folder_mtimes.json"
                
                for file_path in [scan_results_path, comparison_results_path, mtimes_path]:
                    if file_path.exists():
                        file_path.unlink()
                
                logger.info("Cleared all cached scan and comparison data")
            except Exception as e:
                logger.error(f"Error clearing cached data: {e}")
    
    def import_selected(self):
        """Import selected albums to DeeMusic download queue."""
        logger.info("=== IMPORT SELECTED BUTTON CLICKED ===")
        try:
            # Check if QueueIntegration is available
            if not QUEUE_INTEGRATION_AVAILABLE:
                QMessageBox.warning(
                    self, 
                    "Import Unavailable", 
                    "Queue integration is not available. Please ensure the library scanner module is properly installed."
                )
                return
            
            # DEBUG: Log current global selection state
            logger.info(f"DEBUG: Global selection state: {self.selected_albums_global}")
            logger.info(f"DEBUG: Global selection count: {len(self.selected_albums_global)}")
            
            # Collect selected albums from ALL artists, not just currently visible ones
            selected_albums = []
            selected_count = 0
            
            # Go through all artists and their albums
            for artist_index in range(self.artists_tree.topLevelItemCount()):
                artist_item = self.artists_tree.topLevelItem(artist_index)
                artist_data = artist_item.data(0, Qt.ItemDataRole.UserRole)
                artist_name = artist_item.text(0)
                
                logger.info(f"DEBUG: Checking artist {artist_name}")
                
                if artist_data and 'missing_albums' in artist_data:
                    logger.info(f"DEBUG: Found {len(artist_data['missing_albums'])} missing albums for {artist_name}")
                    # Check each album for this artist
                    for album_data in artist_data['missing_albums']:
                        album_title = album_data.get('title', 'Unknown') if isinstance(album_data, dict) else str(album_data)
                        is_selected = self._is_album_selected(artist_name, album_data)
                        logger.info(f"DEBUG: Album '{album_title}' by '{artist_name}' - Selected: {is_selected}")
                        logger.info(f"DEBUG: Album data type: {type(album_data)}, content: {album_data}")
                        
                        # Check if this album is selected
                        if is_selected:
                            selected_count += 1
                            logger.info(f"DEBUG: Adding selected album to import list: {album_title} by {artist_name}")
                            
                            # Convert album data to MissingAlbum format for QueueIntegration
                            if isinstance(album_data, dict):
                                # Handle full Deezer album object
                                album_id = album_data.get('id', 0)
                                if album_id == 0:
                                    # Try to get ID from other possible fields
                                    album_id = album_data.get('album_id', album_data.get('deezer_id', 0))
                                
                                deezer_album = DeezerAlbum(
                                    id=album_id,
                                    title=album_data.get('title', 'Unknown Album'),
                                    artist=album_data.get('artist', artist_name),
                                    year=album_data.get('release_date', album_data.get('year')),
                                    track_count=album_data.get('nb_tracks', album_data.get('track_count', 0)),
                                    cover_url=album_data.get('cover_medium', album_data.get('cover_url'))
                                )
                                
                                # For Library Scanner albums, we assume all tracks are missing since the album is not in the library
                                # Create placeholder missing tracks based on track count
                                track_count = deezer_album.track_count or 1  # At least 1 track
                                missing_tracks = [f"track_{i}" for i in range(track_count)]  # Placeholder track list
                                
                                missing_album = MissingAlbum(
                                    deezer_album=deezer_album,
                                    local_album=None,
                                    missing_tracks=missing_tracks
                                )
                                
                                selected_albums.append(missing_album)
                            else:
                                # Handle simple string format
                                album_title = str(album_data)
                                
                                # Create a basic DeezerAlbum from available info
                                deezer_album = DeezerAlbum(
                                    id=0,  # Will need to be resolved later
                                    title=album_title,
                                    artist=artist_name,
                                    year=None,
                                    track_count=1  # Assume at least 1 track
                                )
                                
                                # For Library Scanner albums, assume at least 1 missing track
                                missing_tracks = ["track_1"]  # Placeholder track
                                
                                missing_album = MissingAlbum(
                                    deezer_album=deezer_album,
                                    local_album=None,
                                    missing_tracks=missing_tracks
                                )
                                
                                selected_albums.append(missing_album)
            
            if selected_count == 0:
                QMessageBox.information(self, "No Selection", "Please select albums to import.")
                return
            
            # Initialize QueueIntegration with download service if available
            download_service = None
            try:
                # Try to get the download service from the main window
                main_window = self.window()
                if main_window and hasattr(main_window, 'download_service'):
                    download_service = main_window.download_service
                    logger.info(f"[LibraryScanner] Found download service: {download_service is not None}")
                else:
                    logger.info(f"[LibraryScanner] No download service found, using fallback")
            except Exception as e:
                logger.warning(f"[LibraryScanner] Error getting download service: {e}")
            
            queue_integration = QueueIntegration(self.config, download_service)
            
            # Check if DeeMusic queue is accessible
            if not queue_integration.is_deemusic_queue_accessible():
                reply = QMessageBox.question(
                    self,
                    "Queue Not Accessible",
                    "DeeMusic's download queue is not accessible. This might be because:\n\n"
                    "• DeeMusic hasn't been run yet\n"
                    "• DeeMusic is not installed in the expected location\n\n"
                    "Would you like to continue anyway? The albums will be saved and can be imported later.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                
                if reply != QMessageBox.StandardButton.Yes:
                    return
            
            # Show confirmation dialog
            reply = QMessageBox.question(
                self,
                "Confirm Import",
                f"Import {selected_count} selected albums to DeeMusic download queue?\n\n"
                f"These albums will be added to DeeMusic's download queue and can be downloaded when you open DeeMusic.\n\n"
                f"Continue with import?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
            
            # Import albums directly to DeeMusic queue (skip intermediate file)
            # Create and show progress dialog
            progress_dialog = QProgressDialog("Preparing import...", "Cancel", 0, 100, self)
            progress_dialog.setWindowTitle("Importing Albums")
            progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            progress_dialog.setMinimumDuration(0)
            progress_dialog.show()
            
            # Create and start import worker
            self.import_worker = ImportWorker(selected_albums, queue_integration)
            
            # Connect signals
            self.import_worker.progress_updated.connect(progress_dialog.setValue)
            self.import_worker.current_album_updated.connect(progress_dialog.setLabelText)
            self.import_worker.import_completed.connect(lambda success, count: self._on_import_completed(success, count, selected_count, progress_dialog))
            
            # Handle cancel button
            progress_dialog.canceled.connect(lambda: self._cancel_import(progress_dialog))
            
            # Start import
            self.import_worker.start()
                
        except Exception as e:
            logger.error(f"Error during import: {e}")
            QMessageBox.critical(
                self,
                "Import Error",
                f"An error occurred during import:\n\n{str(e)}\n\nPlease try again or check the logs for more details."
            )
                
    def _on_import_completed(self, success, imported_count, total_count, progress_dialog):
        """Handle import completion."""
        try:
            # Close progress dialog
            progress_dialog.close()
            
            if success and imported_count > 0:
                # Show updated success message
                QMessageBox.information(
                    self,
                    "Import Successful",
                    f"🎵 Successfully imported {imported_count} of {total_count} albums to DeeMusic!\n\n"
                    f"✅ Albums have been added to the download queue and downloads will start automatically.\n\n"
                    f"💡 You can monitor progress in the Download Queue tab."
                )
                
                # Uncheck all selected items
                for i in range(self.albums_tree.topLevelItemCount()):
                    album_item = self.albums_tree.topLevelItem(i)
                    if album_item.checkState(0) == Qt.CheckState.Checked:
                        album_item.setCheckState(0, Qt.CheckState.Unchecked)
                
                # Update the import button state
                self.update_import_button_state()
                
            else:
                QMessageBox.warning(
                    self,
                    "Import Failed",
                    f"Failed to import albums to DeeMusic queue.\n\n"
                    f"Imported: {imported_count} of {total_count} albums\n\n"
                    f"Please check the logs for more details and try again."
                )
                
        except Exception as e:
            logger.error(f"Error handling import completion: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"An error occurred while completing the import: {e}"
            )
    
    def _cancel_import(self, progress_dialog):
        """Handle import cancellation."""
        try:
            if hasattr(self, 'import_worker') and self.import_worker.isRunning():
                self.import_worker.terminate()
                self.import_worker.wait()
            progress_dialog.close()
            QMessageBox.information(
                self,
                "Import Cancelled",
                "Album import has been cancelled."
            )
        except Exception as e:
            logger.error(f"Error cancelling import: {e}")
    
    def compare_with_deezer(self):
        """Compare the library scan results with Deezer to find missing albums."""
        try:
            logger.info("Compare with Deezer button clicked!")
            logger.info(f"Local albums count: {len(self.local_albums) if self.local_albums else 0}")
            logger.info(f"Local albums type: {type(self.local_albums)}")
            if self.local_albums:
                logger.info(f"First few albums: {self.local_albums[:3]}")
            
            if not self.local_albums:
                QMessageBox.information(
                    self, 
                    "No Scan Data", 
                    "Please perform a library scan first before comparing with Deezer."
                )
                return
            
            # Check if the scan data has metadata (new format)
            logger.info("Checking if scan data has metadata...")
            has_metadata = any(track.get('artist') or track.get('album') for track in self.local_albums[:5])
            logger.info(f"Has metadata: {has_metadata}")
            
            if not has_metadata:
                reply = QMessageBox.question(
                    self,
                    "Rescan Required",
                    "Your current scan data is from before metadata extraction was added.\n\n"
                    "A new scan with metadata extraction is required for comparison to work.\n\n"
                    "Run a new scan now? (This will take a few minutes)",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                
                if reply == QMessageBox.StandardButton.Yes:
                    # Clear old data and start a new scan
                    self.clear_scan_results()
                    # Automatically start a new scan
                    self.scan_library()
                    return
                else:
                    return
            
            # Show confirmation dialog
            logger.info("Showing confirmation dialog...")
            reply = QMessageBox.question(
                self,
                "Compare with Deezer",
                "This will compare your library with Deezer to find missing albums.\n\n"
                "This process may take several minutes depending on your library size.\n\n"
                "Continue with comparison?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            logger.info(f"User reply: {reply}")
            if reply != QMessageBox.StandardButton.Yes:
                logger.info("User cancelled comparison")
                return
            
            # Start the comparison process
            logger.info("Starting comparison process...")
            self.start_comparison()
            
        except Exception as e:
            logger.error(f"Error starting comparison: {e}")
            QMessageBox.critical(
                self,
                "Comparison Error",
                f"An error occurred while starting the comparison:\n\n{str(e)}"
            )
    
    def start_comparison(self):
        """Start the comparison process in a separate thread."""
        try:
            logger.info("Main DeeMusic start_comparison() called")
            # Disable the compare button during comparison
            self.compare_btn.setEnabled(False)
            self.compare_btn.setText("🔄 Comparing...")
            
            # Show progress
            self.scan_progress.setVisible(True)
            self.scan_progress.setValue(0)
            self.current_scan_label.setVisible(True)
            self.current_scan_label.setText("Starting comparison with Deezer...")
            
            # Create and start the comparison worker
            logger.info("Creating comparison worker...")
            self.comparison_worker = ComparisonWorker(self.local_albums, self.config)
            logger.info("Connecting signals...")
            self.comparison_worker.progress_updated.connect(self.scan_progress.setValue)
            self.comparison_worker.status_updated.connect(self.current_scan_label.setText)
            self.comparison_worker.comparison_completed.connect(self.on_comparison_completed)
            self.comparison_worker.comparison_error.connect(self.on_comparison_error)
            
            logger.info("Starting comparison worker...")
            self.comparison_worker.start()
            logger.info("Comparison worker started")
            
        except Exception as e:
            logger.error(f"Error starting comparison worker: {e}")
            self.on_comparison_error(str(e))
    
    def on_comparison_completed(self, results):
        """Handle completion of the comparison process."""
        try:
            # Hide progress
            self.scan_progress.setVisible(False)
            self.current_scan_label.setVisible(False)
            
            # Re-enable the compare button
            self.compare_btn.setEnabled(True)
            self.compare_btn.setText("🎵 Compare with Deezer")
            
            # Store and display results
            self.fast_comparison_results = results
            self.populate_comparison_ui(results)
            
            # Save results to cache
            self.save_comparison_results(results)
            
            # Show completion message
            total_missing = sum(len(artist_data.get('missing_albums', [])) 
                              for artist_data in results.get('artists', {}).values())
            
            QMessageBox.information(
                self,
                "Comparison Complete",
                f"Comparison completed successfully!\n\n"
                f"Found {total_missing} missing albums across {len(results.get('artists', {}))} artists.\n\n"
                f"Check the Comparison tab to see the results."
            )
            
            # Switch to comparison tab
            self.tab_widget.setCurrentIndex(1)
            
        except Exception as e:
            logger.error(f"Error handling comparison completion: {e}")
            self.on_comparison_error(str(e))
    
    def on_comparison_error(self, error_message):
        """Handle comparison errors."""
        try:
            # Hide progress
            self.scan_progress.setVisible(False)
            self.current_scan_label.setVisible(False)
            
            # Re-enable the compare button
            self.compare_btn.setEnabled(True)
            self.compare_btn.setText("🎵 Compare with Deezer")
            
            # Show error message
            QMessageBox.critical(
                self,
                "Comparison Error",
                f"An error occurred during comparison:\n\n{error_message}\n\n"
                f"Please check your internet connection and try again."
            )
            
        except Exception as e:
            logger.error(f"Error handling comparison error: {e}")
    
    def save_comparison_results(self, results):
        """Save comparison results to cache file."""
        try:
            appdata_path = self.get_appdata_path()
            comparison_results_path = appdata_path / "fast_comparison_results.json"
            
            # Ensure directory exists
            appdata_path.mkdir(parents=True, exist_ok=True)
            
            # Save results
            with open(comparison_results_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'results': results,
                    'timestamp': time.time(),
                    'version': '1.0'
                }, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved comparison results to {comparison_results_path}")
            
        except Exception as e:
            logger.error(f"Error saving comparison results: {e}")

    def update_import_button_state(self):
        """Update the import button state based on selected albums."""
        try:
            # Use global selection count instead of just visible albums
            selected_count = len(self.selected_albums_global)
            self.import_btn.setEnabled(selected_count > 0)
            
        except Exception as e:
            logger.error(f"Error updating import button state: {e}")
    
    def _is_album_selected(self, artist_name, album_data):
        """Check if an album is selected globally."""
        if isinstance(album_data, dict):
            # Handle both Deezer format ('title', 'artist') and local format ('album', 'album_artist')
            album_title = album_data.get('title') or album_data.get('album', 'Unknown')
        else:
            album_title = str(album_data)
        lookup_key = (artist_name, album_title)
        is_selected = lookup_key in self.selected_albums_global
        logger.debug(f"DEBUG: _is_album_selected - Looking for {lookup_key}, found: {is_selected}")
        return is_selected
    
    def _add_album_selection(self, artist_name, album_title):
        """Add an album to the global selection."""
        self.selected_albums_global.add((artist_name, album_title))
    
    def _remove_album_selection(self, artist_name, album_title):
        """Remove an album from the global selection."""
        self.selected_albums_global.discard((artist_name, album_title))
    
    def incremental_compare_with_deezer(self):
        """Compare only new/updated albums with Deezer."""
        try:
            # Check if we have previous comparison results
            if not hasattr(self, 'fast_comparison_results') or not self.fast_comparison_results:
                QMessageBox.information(
                    self,
                    "No Previous Comparison",
                    "No previous comparison results found. Please run a full comparison first."
                )
                return
            
            # Check if we have scan results
            if not self.local_albums:
                QMessageBox.warning(
                    self,
                    "No Scan Results",
                    "Please scan your library first before comparing."
                )
                return
            
            # Ask for confirmation
            reply = QMessageBox.question(
                self,
                "Incremental Comparison",
                "This will compare only new or updated albums since the last comparison.\n\n"
                "This is much faster than a full comparison.\n\n"
                "Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
            
            # Implement incremental comparison logic
            self.start_incremental_comparison()
            
        except Exception as e:
            logger.error(f"Error in incremental comparison: {e}")
            QMessageBox.critical(self, "Error", f"Failed to start incremental comparison: {str(e)}")
    
    def start_incremental_comparison(self):
        """Start incremental comparison with Deezer."""
        try:
            logger.info("Starting incremental comparison with Deezer...")
            
            # Get the timestamp of the last comparison
            last_comparison_time = self.fast_comparison_results.get('timestamp', 0)
            logger.info(f"Last comparison timestamp: {last_comparison_time}")
            
            # Get albums that have been modified since the last comparison
            new_or_updated_albums = self.get_albums_modified_since(last_comparison_time)
            
            if not new_or_updated_albums:
                QMessageBox.information(
                    self,
                    "No Changes Found",
                    "No new or updated albums found since the last comparison.\n\n"
                    "Your comparison results are up to date."
                )
                return
            
            logger.info(f"Found {len(new_or_updated_albums)} new/updated albums for incremental comparison")
            
            # Show progress and start comparison
            self.status_label.setText(f"🔄 Comparing {len(new_or_updated_albums)} updated albums...")
            
            # Start the comparison worker with only the new/updated albums
            self.start_comparison_worker(new_or_updated_albums, incremental=True)
            
        except Exception as e:
            logger.error(f"Error starting incremental comparison: {e}")
            QMessageBox.critical(self, "Error", f"Failed to start incremental comparison: {str(e)}")
    
    def get_albums_modified_since(self, timestamp):
        """Get albums that have been modified since the given timestamp."""
        try:
            if not self.local_albums:
                return []
            
            # Load folder modification times to check for changes
            appdata_path = self.get_appdata_path()
            folder_mtimes_path = appdata_path / "folder_mtimes.json"
            
            folder_mtimes = {}
            if folder_mtimes_path.exists():
                try:
                    with open(folder_mtimes_path, 'r', encoding='utf-8') as f:
                        folder_mtimes = json.load(f)
                except Exception as e:
                    logger.warning(f"Could not load folder mtimes: {e}")
            
            # Get albums from folders that have been modified since the last comparison
            modified_albums = []
            
            for album in self.local_albums:
                album_folder = album.get('folder_path', '')
                if not album_folder:
                    continue
                
                # Check if this album's folder has been modified since last comparison
                folder_mtime = folder_mtimes.get(album_folder, 0)
                
                # If folder was modified after the last comparison, include it
                if folder_mtime > timestamp:
                    modified_albums.append(album)
                    logger.debug(f"Including modified album: {album.get('album_artist', 'Unknown')} - {album.get('album', 'Unknown')}")
            
            # If we don't have folder mtimes, fall back to checking scan timestamp
            if not modified_albums and not folder_mtimes:
                # Check if the scan results are newer than the last comparison
                scan_results_path = appdata_path / "scan_results.json"
                if scan_results_path.exists():
                    scan_mtime = scan_results_path.stat().st_mtime
                    if scan_mtime > timestamp:
                        # If scan is newer, include all albums (full comparison)
                        logger.info("Scan results are newer than last comparison, including all albums")
                        modified_albums = self.local_albums
                    else:
                        logger.info("No changes detected since last comparison")
            
            return modified_albums
            
        except Exception as e:
            logger.error(f"Error getting modified albums: {e}")
            return []
    
    def start_comparison_worker(self, albums_to_compare, incremental=False):
        """Start the comparison worker with specified albums."""
        try:
            logger.info(f"Starting comparison worker with {len(albums_to_compare)} albums (incremental: {incremental})")
            
            # Create and start comparison worker
            self.comparison_worker = ComparisonWorker(albums_to_compare, self.config)
            
            # Connect signals
            self.comparison_worker.progress_updated.connect(self.update_comparison_progress)
            self.comparison_worker.status_updated.connect(self.update_comparison_status)
            self.comparison_worker.comparison_completed.connect(
                lambda results: self.on_incremental_comparison_completed(results) if incremental 
                else self.on_comparison_completed(results)
            )
            self.comparison_worker.comparison_error.connect(self.on_comparison_error)
            
            # Start the worker
            self.comparison_worker.start()
            
        except Exception as e:
            logger.error(f"Error starting comparison worker: {e}")
            QMessageBox.critical(self, "Error", f"Failed to start comparison: {str(e)}")
    
    def on_incremental_comparison_completed(self, results):
        """Handle incremental comparison completion."""
        try:
            logger.info("Incremental comparison completed")
            
            # Merge the new results with existing results
            if hasattr(self, 'fast_comparison_results') and self.fast_comparison_results:
                # Update existing results with new data
                existing_results = self.fast_comparison_results.get('results', {})
                new_results = results.get('results', {})
                
                # Merge artist data
                existing_artists = existing_results.get('artists', {})
                new_artists = new_results.get('artists', {})
                
                for artist_name, artist_data in new_artists.items():
                    existing_artists[artist_name] = artist_data
                
                # Update statistics
                existing_stats = existing_results.get('statistics', {})
                new_stats = new_results.get('statistics', {})
                
                # Recalculate totals
                total_missing = sum(len(artist_data.get('missing_albums', [])) 
                                  for artist_data in existing_artists.values())
                
                existing_stats.update({
                    'total_missing_albums': total_missing,
                    'last_incremental_update': time.time()
                })
                
                # Update the complete results
                merged_results = {
                    'results': {
                        'artists': existing_artists,
                        'statistics': existing_stats
                    },
                    'timestamp': time.time(),
                    'version': '1.0'
                }
                
                self.fast_comparison_results = merged_results
            else:
                # No existing results, treat as full comparison
                self.fast_comparison_results = {
                    'results': results,
                    'timestamp': time.time(),
                    'version': '1.0'
                }
            
            # Save the updated results
            self.save_comparison_results(self.fast_comparison_results)
            
            # Update UI
            self.populate_comparison_ui(self.fast_comparison_results.get('results', {}))
            
            # Update status
            total_missing = sum(len(artist_data.get('missing_albums', [])) 
                              for artist_data in self.fast_comparison_results.get('results', {}).get('artists', {}).values())
            
            self.status_label.setText(f"✅ Incremental comparison completed - {total_missing} missing albums found")
            
            logger.info(f"Incremental comparison completed with {total_missing} missing albums")
            
        except Exception as e:
            logger.error(f"Error handling incremental comparison completion: {e}")
            self.on_comparison_error(str(e))
    
    def initialize_ui_state(self):
        """Initialize the UI state based on current configuration."""
        try:
            # Check if library paths are configured
            paths = self.config.get_setting('library_scanner.library_paths', [])
            
            if len(paths) == 0:
                self.scan_btn.setEnabled(False)
                self.status_label.setText("Add library paths to get started")
                self.scan_status.setText("Ready to scan - Add library paths above")
            else:
                self.scan_btn.setEnabled(True)
                self.status_label.setText(f"Ready - {len(paths)} path(s) configured")
                self.scan_status.setText(f"Ready to scan {len(paths)} library path(s)")
            
            # Check if previous results exist
            appdata_path = self.get_appdata_path()
            scan_results_path = appdata_path / "scan_results.json"
            
            if scan_results_path.exists():
                self.update_scan_btn.setEnabled(True)
                self.clear_results_btn.setEnabled(True)
            else:
                self.update_scan_btn.setEnabled(False)
                self.clear_results_btn.setEnabled(False)
                
        except Exception as e:
            logger.error(f"Error initializing UI state: {e}")
    
    def on_artist_checkbox_changed(self, item, column):
        """Handle artist checkbox changes - auto-select all albums for checked artists."""
        # Only handle checkbox in first column and prevent recursive calls
        if column != 0 or (hasattr(self, '_checkbox_change_in_progress') and self._checkbox_change_in_progress):
            return
            
        # Set flag to prevent recursive calls
        self._checkbox_change_in_progress = True
        
        try:
            artist_name = item.text(0)
            is_checked = item.checkState(0) == Qt.CheckState.Checked
            
            logger.info(f"Artist checkbox changed: {artist_name} -> {'checked' if is_checked else 'unchecked'}")
            
            # Update global selection for ALL albums of this artist
            artist_data = item.data(0, Qt.ItemDataRole.UserRole)
            if artist_data and 'missing_albums' in artist_data:
                albums_updated = 0
                for album_data in artist_data['missing_albums']:
                    album_title = album_data.get('title', 'Unknown') if isinstance(album_data, dict) else str(album_data)
                    
                    if is_checked:
                        # Add to global selection
                        self._add_album_selection(artist_name, album_title)
                    else:
                        # Remove from global selection
                        self._remove_album_selection(artist_name, album_title)
                    
                    albums_updated += 1
                
                logger.info(f"Updated global selection for {albums_updated} albums from artist {artist_name}")
            
            # Also update visible albums if this artist is currently displayed
            if self.artists_tree.currentItem() == item:
                for i in range(self.albums_tree.topLevelItemCount()):
                    album_item = self.albums_tree.topLevelItem(i)
                    album_item.setCheckState(0, Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
                
                logger.info(f"Also updated {self.albums_tree.topLevelItemCount()} visible albums for artist {artist_name}")
            
            # Update import button state (this will use the global selection count)
            self.update_import_button_state()
            
        except Exception as e:
            logger.error(f"Error in on_artist_checkbox_changed: {e}")
        finally:
            # Always clear the flag, even if an exception occurs
            self._checkbox_change_in_progress = False
    
    def apply_filters(self):
        """Apply filters to the comparison results."""
        if not hasattr(self, 'fast_comparison_results') or not self.fast_comparison_results:
            logger.debug("FILTER_DEBUG: No comparison results to filter")
            return
        
        filter_live = self.filter_live_checkbox.isChecked()
        filter_duplicates = self.filter_duplicates_checkbox.isChecked()
        logger.info(f"FILTER_DEBUG: Applying filters - Live: {filter_live}, Duplicates: {filter_duplicates}")
        
        # Re-populate with filters applied
        self.populate_comparison_ui_with_filters(self.fast_comparison_results)
    
    def populate_comparison_ui_with_filters(self, results: Dict[str, Any]):
        """Populate the comparison UI with filters applied."""
        try:
            self.artists_tree.clear()
            self.albums_tree.clear()
            
            artists_data = results.get('artists', {})
            filter_live = self.filter_live_checkbox.isChecked()
            filter_duplicates = self.filter_duplicates_checkbox.isChecked()
            
            for artist_name, artist_info in artists_data.items():
                missing_albums = artist_info.get('missing_albums', [])
                
                # Apply filters
                filtered_albums = []
                for album in missing_albums:
                    album_title = album.get('title', '') if isinstance(album, dict) else str(album)
                    
                    # Filter out live albums
                    if filter_live and self.is_live_album(album_title):
                        continue
                    
                    # Filter out duplicates (deluxe/remaster)
                    local_albums = artist_info.get('local_albums', [])
                    if filter_duplicates:
                        is_duplicate = self.is_duplicate_album(album_title, missing_albums, local_albums)
                        logger.debug(f"FILTER_DEBUG: '{album_title}' -> duplicate: {is_duplicate}, local_albums: {local_albums}")
                        if is_duplicate:
                            logger.info(f"FILTERING OUT: '{album_title}' (duplicate/deluxe edition)")
                            continue
                    
                    # Special handling for self-titled albums (like "311" by 311)
                    # Check if this album is actually in the local library but wasn't matched correctly
                    if self.is_self_titled_album(album_title, artist_name):
                        # Check if this album is actually in the local library
                        local_albums = artist_info.get('local_albums', [])
                        if any(self.is_self_titled_album(local_album, artist_name) for local_album in local_albums):
                            logger.info(f"Skipping self-titled album '{album_title}' by '{artist_name}' - found in local library")
                            continue
                    
                    filtered_albums.append(album)
                
                if filtered_albums:
                    artist_item = QTreeWidgetItem([artist_name, f"{len(filtered_albums)} albums"])
                    artist_item.setCheckState(0, Qt.CheckState.Unchecked)
                    artist_item.setData(0, Qt.ItemDataRole.UserRole, {'missing_albums': filtered_albums})
                    self.artists_tree.addTopLevelItem(artist_item)
            
            self.artists_tree.sortItems(0, Qt.SortOrder.AscendingOrder)
            logger.info(f"Populated filtered comparison UI with {self.artists_tree.topLevelItemCount()} artists")
            
        except Exception as e:
            logger.error(f"Error populating filtered comparison UI: {e}")
    
    def is_live_album(self, album_title: str) -> bool:
        """Check if album is a live album."""
        live_keywords = ['live', 'concert', 'tour', 'unplugged', 'acoustic', 'session']
        album_lower = album_title.lower()
        return any(keyword in album_lower for keyword in live_keywords)
    
    def is_duplicate_album(self, album_title: str, all_albums: List, local_albums: List = None) -> bool:
        """Check if album is a duplicate (deluxe/remaster when normal version exists)."""
        duplicate_keywords = [
            'deluxe', 'remaster', 'remastered', 'expanded', 'special edition', 
            'anniversary', 'collector', 'limited edition', 'extended', 'bonus',
            'super deluxe', 'platinum edition', 'gold edition', 'ultimate',
            'complete edition', 'director\'s cut', 'enhanced', 'redux'
        ]
        album_lower = album_title.lower()
        
        # If this album has duplicate keywords
        if any(keyword in album_lower for keyword in duplicate_keywords):
            # Check if a "normal" version exists
            base_title = album_lower
            for keyword in duplicate_keywords:
                # Remove the keyword and common patterns around it
                base_title = base_title.replace(f'({keyword})', '').replace(f'[{keyword}]', '')
                base_title = base_title.replace(f' {keyword}', '').replace(f'{keyword} ', '')
                base_title = base_title.replace(keyword, '')
            
            # Clean up extra spaces and punctuation
            base_title = ' '.join(base_title.split())  # Remove extra whitespace
            base_title = base_title.strip('()[]- ,.')
            
            # First check local albums (albums you already have) - this is the primary check
            if local_albums:
                for local_album in local_albums:
                    local_title = local_album if isinstance(local_album, str) else str(local_album)
                    local_lower = local_title.lower().strip()
                    
                    # If we find a similar title in local albums without duplicate keywords
                    if (base_title and len(base_title) > 2 and 
                        (base_title in local_lower or local_lower in base_title) and 
                        not any(keyword in local_lower for keyword in duplicate_keywords)):
                        logger.debug(f"DUPLICATE_FILTER: Found duplicate - '{album_title}' (base: '{base_title}') matches local album '{local_title}'")
                        return True  # This is a duplicate - you already have the normal version
            
            # Also check in the missing albums list (secondary check)
            for other_album in all_albums:
                other_title = other_album.get('title', '') if isinstance(other_album, dict) else str(other_album)
                other_lower = other_title.lower().strip()
                
                # If we find a similar title without duplicate keywords
                if (base_title and len(base_title) > 2 and 
                    (base_title in other_lower or other_lower in base_title) and 
                    not any(keyword in other_lower for keyword in duplicate_keywords)):
                    logger.debug(f"DUPLICATE_FILTER: Found duplicate - '{album_title}' (base: '{base_title}') matches normal version '{other_title}'")
                    return True  # This is a duplicate
        
        return False  # Not a duplicate
                    
    def is_self_titled_album(self, album_title: str, artist_name: str) -> bool:
        """Check if album is self-titled (album name equals artist name)."""
        # Direct comparison (case-insensitive)
        if album_title.lower() == artist_name.lower():
            return True
            
        # Special handling for numeric album titles (like "311")
        if album_title.isdigit() and artist_name.isdigit() and album_title == artist_name:
            return True
            
        return False
    
    def _parse_album_data(self, album_data, fallback_artist_name):
        """Parse album data handling both Deezer and local formats."""
        if isinstance(album_data, dict):
            # Handle both Deezer format ('title', 'artist') and local format ('album', 'album_artist')
            album_title = album_data.get('title') or album_data.get('album', 'Unknown Album')
            album_artist = album_data.get('artist') or album_data.get('album_artist', fallback_artist_name)
            return album_title, album_artist
        else:
            return str(album_data), fallback_artist_name
    
    def on_artist_selected(self, item, column):
        """Handle artist selection."""
        try:
            artist_name = item.text(0)
            artist_info = item.data(0, Qt.ItemDataRole.UserRole)
            
            if not artist_info:
                return
            
            self.albums_tree.clear()
            missing_albums = artist_info.get('missing_albums', [])
            
            # Get artist data from fast_comparison_results to check local albums
            artist_data = None
            if hasattr(self, 'fast_comparison_results') and self.fast_comparison_results:
                artist_data = self.fast_comparison_results.get('artists', {}).get(artist_name, {})
            
            # Check if the artist is checked in the artists tree
            is_artist_checked = item.checkState(0) == Qt.CheckState.Checked
            
            for album_data in missing_albums:
                album_title, album_artist = self._parse_album_data(album_data, artist_name)
                album_type = self.get_album_type(album_title)
                
                # Special handling for self-titled albums (like "311" by 311)
                is_self_titled = self.is_self_titled_album(album_title, artist_name)
                if is_self_titled:
                    album_type = "Self-Titled"
                    
                    # Check if this album is actually in the local library
                    if artist_data:
                        local_albums = artist_data.get('local_albums', [])
                        if any(self.is_self_titled_album(local_album, artist_name) for local_album in local_albums):
                            # This is likely a false positive - the album is actually in the local library
                            # but wasn't matched correctly. Add a visual indicator.
                            album_title = f"{album_title} ⚠️ (May be in library)"
                
                album_item = QTreeWidgetItem([album_title, album_artist, album_type])
                
                # Set the checkbox state based on the artist's checkbox state
                check_state = Qt.CheckState.Checked if is_artist_checked else Qt.CheckState.Unchecked
                album_item.setCheckState(0, check_state)
                
                album_item.setData(0, Qt.ItemDataRole.UserRole, album_data)
                self.albums_tree.addTopLevelItem(album_item)
            
            self.albums_tree.sortItems(0, Qt.SortOrder.AscendingOrder)
            
            # We've already set the album checkboxes based on the artist's checkbox state
            # in the loop above, so we don't need to do anything else here
            logger.info(f"Loaded albums for artist: {artist_name} with checkbox state: {is_artist_checked}")
            
        except Exception as e:
            logger.error(f"Error handling artist selection: {e}")
    
    def get_album_type(self, album_title: str) -> str:
        """Get the type of album (Normal, Live, Deluxe, etc.)."""
        album_lower = album_title.lower()
        
        # Check for numeric-only album titles (like "311")
        if album_title.isdigit() or album_lower.isdigit():
            return "Self-Titled"
            
        if self.is_live_album(album_title):
            return "Live"
        elif any(keyword in album_lower for keyword in ['deluxe', 'expanded', 'special edition']):
            return "Deluxe"
        elif any(keyword in album_lower for keyword in ['remaster', 'remastered']):
            return "Remaster"
        elif any(keyword in album_lower for keyword in ['anniversary', 'collector']):
            return "Special"
        else:
            return "Normal"
    
    def is_dark_mode(self):
        """Check if the application is in dark mode."""
        try:
            # Try to get theme from parent main window
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'theme_manager'):
                main_window = main_window.parent()
            
            if main_window and hasattr(main_window, 'theme_manager'):
                return main_window.theme_manager.current_theme == 'dark'
            
            # Default to light mode if can't determine
            return False
        except Exception:
            return False
    
    def go_back_to_deemusic(self):
        """Navigate back to the main DeeMusic interface."""
        try:
            # Get the main window from the parent hierarchy
            main_window = self.parent()
            while main_window and not hasattr(main_window, 'content_stack'):
                main_window = main_window.parent()
            
            if main_window and hasattr(main_window, 'content_stack'):
                # Switch back to the home page (index 0)
                home_page_index = 0
                main_window._switch_to_view(home_page_index)
                logger.info("Navigated back to DeeMusic home page")
            else:
                logger.error("Could not find main window to navigate back")
                QMessageBox.information(self, "Navigation", "Unable to navigate back to main DeeMusic interface.")
                
        except Exception as e:
            logger.error(f"Error navigating back to DeeMusic: {e}")
            QMessageBox.critical(self, "Navigation Error", f"Error navigating back:\n\n{str(e)}")
    
    def browse_library_path(self):
        """Browse for library path."""
        path = QFileDialog.getExistingDirectory(self, "Select Library Path")
        if path:
            self.path_input.setText(path)
    
    def add_library_path(self):
        """Add library path."""
        path = self.path_input.text().strip()
        if path and os.path.exists(path):
            # Add to config and update UI
            paths = self.config.get_setting('library_scanner.library_paths', [])
            if path not in paths:
                paths.append(path)
                self.config.set_setting('library_scanner.library_paths', paths)
                self.update_paths_list()
                self.path_input.clear()
                self.scan_btn.setEnabled(True)
                self.status_label.setText(f"Ready - {len(paths)} path(s) configured")
        else:
            QMessageBox.warning(self, "Invalid Path", "Please enter a valid directory path.")
    
    def remove_library_path(self):
        """Remove selected library path."""
        current_item = self.paths_list.currentItem()
        if current_item:
            path = current_item.text(0)
            paths = self.config.get_setting('library_scanner.library_paths', [])
            if path in paths:
                paths.remove(path)
                self.config.set_setting('library_scanner.library_paths', paths)
                self.update_paths_list()
                if len(paths) == 0:
                    self.scan_btn.setEnabled(False)
                    self.status_label.setText("Add library paths to get started")
                else:
                    self.status_label.setText(f"Ready - {len(paths)} path(s) configured")
    
    def update_paths_list(self):
        """Update the paths list widget."""
        self.paths_list.clear()
        paths = self.config.get_setting('library_scanner.library_paths', [])
        for path in paths:
            item = QTreeWidgetItem([path])
            self.paths_list.addTopLevelItem(item)
    
    def scan_library(self):
        """Start full library scan with detailed progress tracking."""
        library_paths = self.config.get_setting('library_scanner.library_paths', [])
        if not library_paths:
            QMessageBox.warning(self, "No Library Paths", "Please add library paths before scanning.")
            return
        
        # Show progress UI
        self.show_progress_ui()
        
        # Create and start scan worker
        self.scan_worker = ScanWorker(library_paths, scan_type="full")
        self.connect_scan_worker_signals()
        self.scan_worker.start()
    
    def update_scan_library(self):
        """Start incremental library scan - only scan modified files."""
        library_paths = self.config.get_setting('library_scanner.library_paths', [])
        if not library_paths:
            QMessageBox.warning(self, "No Library Paths", "Please add library paths before scanning.")
            return
        
        # Check for scan data in AppData/DeeMusic folder
        appdata_path = self.get_appdata_path()
        folder_mtimes_path = appdata_path / "folder_mtimes.json"
        scan_results_path = appdata_path / "scan_results.json"
        
        # Debug logging
        print(f"DEBUG: AppData path: {appdata_path}")
        print(f"DEBUG: scan_results.json path: {scan_results_path}")
        print(f"DEBUG: scan_results.json exists: {scan_results_path.exists()}")
        print(f"DEBUG: folder_mtimes.json exists: {folder_mtimes_path.exists()}")
        
        if scan_results_path.exists():
            try:
                file_size = scan_results_path.stat().st_size
                print(f"DEBUG: scan_results.json size: {file_size} bytes")
            except Exception as e:
                print(f"DEBUG: Error getting file size: {e}")
        
        previous_mtimes = {}
        
        # Try to load folder modification times (preferred method)
        if folder_mtimes_path.exists():
            previous_mtimes = self.load_folder_mtimes()
            print(f"DEBUG: Loaded {len(previous_mtimes)} folder mtimes from folder_mtimes.json")
        elif scan_results_path.exists():
            # Extract file mtimes from existing scan_results.json
            print("DEBUG: Attempting to read scan_results.json")
            try:
                with open(scan_results_path, 'r', encoding='utf-8') as f:
                    scan_data = json.load(f)
                
                print(f"DEBUG: Loaded scan_data keys: {list(scan_data.keys())}")
                
                # Try different possible structures
                files_data = scan_data.get('files', [])
                if not files_data:
                    # Try 'tracks' structure
                    tracks_data = scan_data.get('tracks', {})
                    if isinstance(tracks_data, dict):
                        files_data = tracks_data.get('files', [])
                        if not files_data:
                            # Try direct tracks list
                            files_data = tracks_data.get('tracks', [])
                
                print(f"DEBUG: Found {len(files_data)} files in scan_results.json")
                
                for file_data in files_data:
                    if isinstance(file_data, dict):
                        file_path = file_data.get('path', file_data.get('file_path', ''))
                        file_mtime = file_data.get('modified', file_data.get('mtime', 0))
                        if file_path and file_mtime:
                            previous_mtimes[file_path] = file_mtime
                
                print(f"DEBUG: Extracted {len(previous_mtimes)} file mtimes")
                
                # Save extracted mtimes for future incremental scans
                if previous_mtimes:
                    self.save_file_mtimes(previous_mtimes)
                    print("DEBUG: Saved file_mtimes.json for future use")
                
            except Exception as e:
                print(f"DEBUG: Error reading scan_results.json: {e}")
                logger.error(f"Error reading scan_results.json: {e}")
        else:
            print("DEBUG: scan_results.json not found")
        
        # Check if we have any scan data loaded (either file mtimes or local albums)
        has_scan_data = bool(previous_mtimes) or bool(self.local_albums)
        
        # Additional check: if scan_results.json exists but we couldn't parse it properly
        if not has_scan_data and scan_results_path.exists():
            logger.warning("scan_results.json exists but couldn't extract scan data properly")
            # Try to force-load the scan data
            try:
                with open(scan_results_path, 'r', encoding='utf-8') as f:
                    scan_data = json.load(f)
                
                # If we have any data structure, consider it valid scan data
                if scan_data and (scan_data.get('files') or scan_data.get('albums') or scan_data.get('tracks')):
                    has_scan_data = True
                    logger.info("Found valid scan data structure in scan_results.json")
                    
                    # Create dummy mtimes based on current time for incremental scan
                    import time
                    current_time = time.time()
                    for path in library_paths:
                        previous_mtimes[path] = current_time - 86400  # 1 day ago
                    
                    logger.info(f"Created dummy mtimes for {len(previous_mtimes)} library paths")
            except Exception as e:
                logger.error(f"Error force-loading scan data: {e}")
        
        if not has_scan_data:
            # No previous data at all, suggest full scan
            reply = QMessageBox.question(self, "No Previous Scan", 
                                       "No previous scan data found. Would you like to perform a Full Scan instead?\n\n"
                                       "Update Scan requires previous scan data to compare against.",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                       QMessageBox.StandardButton.Yes)
            
            if reply == QMessageBox.StandardButton.Yes:
                self.scan_library()  # Do full scan instead
            return
        
        # If we have local albums but no file mtimes, create them from the scan data
        if self.local_albums and not previous_mtimes:
            logger.info("Creating file modification times from loaded scan data")
            for file_data in self.local_albums:
                file_path = file_data.get('path', '')
                file_mtime = file_data.get('modified', 0)
                if file_path and file_mtime:
                    previous_mtimes[file_path] = file_mtime
            
            # If we still don't have mtimes, create them based on current folder times
            if not previous_mtimes:
                logger.info("No file mtimes found, creating from current folder modification times")
                import time
                current_time = time.time()
                
                for lib_path in library_paths:
                    try:
                        path = Path(lib_path)
                        if path.exists():
                            # Use the folder's actual modification time
                            folder_mtime = path.stat().st_mtime
                            previous_mtimes[str(path)] = folder_mtime
                            logger.debug(f"Added mtime for {lib_path}: {folder_mtime}")
                    except Exception as e:
                        logger.warning(f"Could not get mtime for {lib_path}: {e}")
                        # Fallback to current time minus 1 day
                        previous_mtimes[str(path)] = current_time - 86400
            
            # Save the extracted mtimes for future use
            if previous_mtimes:
                self.save_file_mtimes(previous_mtimes)
                logger.info(f"Created file_mtimes.json from loaded scan data with {len(previous_mtimes)} files")
        
        # Show progress UI
        self.show_progress_ui()
        
        # Create and start incremental scan worker with previous mtimes
        self.scan_worker = ScanWorker(library_paths, scan_type="incremental", previous_mtimes=previous_mtimes)
        self.connect_scan_worker_signals()
        self.scan_worker.start()
    
    def show_progress_ui(self):
        """Show the progress tracking UI elements."""
        self.scan_btn.setEnabled(False)
        self.update_scan_btn.setEnabled(False)
        
        # Show progress elements
        self.scan_progress.setVisible(True)
        self.scan_progress.setValue(0)
        self.current_scan_label.setVisible(True)
        self.progress_percentage.setVisible(True)
        self.file_count_label.setVisible(True)
        self.scan_speed_label.setVisible(True)
        self.cancel_scan_btn.setVisible(True)
        
        # Initialize labels
        self.progress_percentage.setText("0%")
        self.file_count_label.setText("0 / 0 files")
        self.scan_speed_label.setText("Calculating...")
        self.current_scan_label.setText("🔍 Initializing scan...")
    
    def hide_progress_ui(self):
        """Hide the progress tracking UI elements."""
        self.scan_progress.setVisible(False)
        self.current_scan_label.setVisible(False)
        self.progress_percentage.setVisible(False)
        self.file_count_label.setVisible(False)
        self.scan_speed_label.setVisible(False)
        self.cancel_scan_btn.setVisible(False)
        
        # Re-enable buttons
        self.scan_btn.setEnabled(True)
        self.update_scan_btn.setEnabled(True)
    
    def connect_scan_worker_signals(self):
        """Connect all scan worker signals to UI update methods."""
        self.scan_worker.progress_updated.connect(self.update_progress)
        self.scan_worker.current_file_updated.connect(self.update_current_file)
        self.scan_worker.status_updated.connect(self.update_scan_status)
        self.scan_worker.file_count_updated.connect(self.update_file_count)
        self.scan_worker.speed_updated.connect(self.update_scan_speed)
        self.scan_worker.scan_completed.connect(self.on_scan_completed)
        self.scan_worker.scan_error.connect(self.on_scan_error)
    
    def update_progress(self, percentage):
        """Update the progress bar and percentage label."""
        self.scan_progress.setValue(percentage)
        self.progress_percentage.setText(f"{percentage}%")
    
    def update_current_file(self, file_info):
        """Update the current file being scanned."""
        self.current_scan_label.setText(file_info)
    
    def update_scan_status(self, status):
        """Update the scan status label."""
        self.scan_status.setText(status)
    
    def update_file_count(self, current, total):
        """Update the file count display."""
        self.file_count_label.setText(f"{current:,} / {total:,} files")
    
    def update_scan_speed(self, speed):
        """Update the scanning speed display."""
        self.scan_speed_label.setText(speed)
    
    def on_scan_completed(self, results):
        """Handle scan completion."""
        try:
            self.hide_progress_ui()
            
            if results["type"] == "success":
                total_files = results["total_files"]
                scan_time = results["scan_time"]
                
                # Update status
                self.status_label.setText(f"✅ Scan completed - {total_files:,} files in {scan_time:.1f}s")
                self.scan_status.setText(f"✅ {results['scan_type'].title()} scan completed successfully\n"
                                       f"Found {total_files:,} music files in {scan_time:.1f} seconds")
                
                # Enable buttons
                self.update_scan_btn.setEnabled(True)
                self.clear_results_btn.setEnabled(True)
                self.compare_btn.setEnabled(True)
                
                # Save results to AppData
                self.save_scan_results(results)
                
                # Reload the scan results into local_albums for comparison
                logger.info("Reloading scan results into local_albums...")
                logger.info(f"DEBUG: Results keys: {list(results.keys())}")
                self.local_albums = results.get("scanned_files", [])
                logger.info(f"Loaded {len(self.local_albums)} files into local_albums")
                
                logger.info(f"Scan completed: {total_files} files in {scan_time:.1f}s")
                
            elif results["type"] == "no_files":
                self.status_label.setText("⚠️ No music files found")
                self.scan_status.setText("⚠️ No music files found in configured paths")
                
            elif results["type"] == "no_changes":
                self.status_label.setText("✅ No changes detected")
                self.scan_status.setText("✅ No changes detected - Library is up to date")
                
        except Exception as e:
            logger.error(f"Error handling scan completion: {e}")
            self.on_scan_error(str(e))
    
    def on_scan_error(self, error_message):
        """Handle scan errors."""
        self.hide_progress_ui()
        self.status_label.setText("❌ Scan failed")
        self.scan_status.setText(f"❌ Scan failed: {error_message}")
        
        QMessageBox.critical(self, "Scan Error", 
                           f"An error occurred during scanning:\n\n{error_message}")
        
        logger.error(f"Scan error: {error_message}")
    
    def save_scan_results(self, results):
        """Save scan results to AppData in proper album format."""
        try:
            appdata_path = self.get_appdata_path()
            appdata_path.mkdir(parents=True, exist_ok=True)
            
            # Save scan results in album format (compatible with library scanner)
            scan_results_path = appdata_path / "scan_results.json"
            library_paths = self.config.get_setting('library_scanner.library_paths', [])
            
            # Debug logging
            logger.info(f"Saving scan results: {len(results.get('scanned_files', []))} albums")
            logger.info(f"Results keys: {list(results.keys())}")
            
            with open(scan_results_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'scan_timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
                    'scan_time': results['scan_time'],
                    'scan_type': results['scan_type'],
                    'library_paths': library_paths,
                    'albums': results['scanned_files'],  # Now contains album data, not file data
                    'album_count': len(results['scanned_files'])
                }, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved {len(results['scanned_files'])} albums to {scan_results_path}")
            
            # Also save folder modification times for future incremental scans
            self.save_current_folder_mtimes()
            
        except Exception as e:
            logger.error(f"Error saving scan results: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    def cancel_scan(self):
        """Cancel the current scan."""
        if hasattr(self, 'scan_worker') and self.scan_worker.isRunning():
            self.scan_worker.cancel()
            self.scan_worker.wait(3000)  # Wait up to 3 seconds for thread to finish
            
        self.hide_progress_ui()
        self.status_label.setText("❌ Scan cancelled")
        self.scan_status.setText("❌ Scan was cancelled by user")
    
    def clear_scan_results(self):
        """Clear scan results."""
        reply = QMessageBox.question(self, "Clear Results", 
                                   "Are you sure you want to clear all scan and comparison results?\n\n"
                                   "This will remove all cached data and you'll need to scan again.",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                   QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            # Clear local data
            self.local_albums = []
            self.fast_comparison_results = {}
            
            # Clear UI
            self.artists_tree.clear()
            self.albums_tree.clear()
            
            # Reset buttons
            self.import_btn.setEnabled(False)
            self.clear_results_btn.setEnabled(False)
            self.update_scan_btn.setEnabled(False)
            
            self.status_label.setText("Results cleared")
            self.scan_status.setText("Ready to scan - Add library paths above")
            
            # Clear AppData files
            try:
                appdata_path = self.get_appdata_path()
                scan_results_path = appdata_path / "scan_results.json"
                comparison_results_path = appdata_path / "fast_comparison_results.json"
                mtimes_path = appdata_path / "folder_mtimes.json"
                
                for file_path in [scan_results_path, comparison_results_path, mtimes_path]:
                    if file_path.exists():
                        file_path.unlink()
                
                logger.info("Cleared all cached scan and comparison data")
            except Exception as e:
                logger.error(f"Error clearing cached data: {e}")
    
    def initialize_ui_state(self):
        """Initialize the UI state based on current configuration."""
        try:
            # Check if library paths are configured
            paths = self.config.get_setting('library_scanner.library_paths', [])
            
            if len(paths) == 0:
                self.scan_btn.setEnabled(False)
                self.status_label.setText("Add library paths to get started")
                self.scan_status.setText("Ready to scan - Add library paths above")
            else:
                self.scan_btn.setEnabled(True)
                self.status_label.setText(f"Ready - {len(paths)} path(s) configured")
                self.scan_status.setText(f"Ready to scan {len(paths)} library path(s)")
            
            # Check if previous results exist
            appdata_path = self.get_appdata_path()
            scan_results_path = appdata_path / "scan_results.json"
            
            if scan_results_path.exists():
                self.update_scan_btn.setEnabled(True)
                self.clear_results_btn.setEnabled(True)
            else:
                self.update_scan_btn.setEnabled(False)
                self.clear_results_btn.setEnabled(False)
                
        except Exception as e:
            logger.error(f"Error initializing UI state: {e}")
            
    def normalize_artist_name(self, artist_name: str) -> str:
        """Normalize artist name for case-insensitive comparison."""
        if not artist_name:
            return ""
        return artist_name.lower().strip()
        
    def check_all_albums_for_selected_artist(self):
        """Check all albums for the currently selected artist."""
        selected_items = self.artists_tree.selectedItems()
        if not selected_items:
            return
        
        artist_item = selected_items[0]
        artist_name = artist_item.text(0)
        
        # Only check albums if the artist checkbox is checked
        is_artist_checked = artist_item.checkState(0) == Qt.CheckState.Checked
        
        if is_artist_checked:
            # Check all albums for this artist
            for i in range(self.albums_tree.topLevelItemCount()):
                item = self.albums_tree.topLevelItem(i)
                item.setCheckState(0, Qt.CheckState.Checked)
            
            logger.info(f"Checked all albums for selected artist: {artist_name}")
        else:
            # Uncheck all albums for this artist
            for i in range(self.albums_tree.topLevelItemCount()):
                item = self.albums_tree.topLevelItem(i)
                item.setCheckState(0, Qt.CheckState.Unchecked)
            
            logger.info(f"Unchecked all albums for selected artist: {artist_name}")
        
    def on_artist_selection_changed(self):
        """Handle artist selection change event."""
        selected_items = self.artists_tree.selectedItems()
        if not selected_items:
            return
        
        # Only check all albums if the artist checkbox is checked
        artist_item = selected_items[0]
        is_checked = artist_item.checkState(0) == Qt.CheckState.Checked
        
        if is_checked:
            # Check all albums for the selected artist
            self.check_all_albums_for_selected_artist()
        else:
            # Load albums but respect the unchecked state
            artist_name = artist_item.text(0)
            artist_info = artist_item.data(0, Qt.ItemDataRole.UserRole)
            
            if artist_info:
                # Trigger album loading without checking
                self._load_albums_without_checking(artist_item)
                
    def _load_albums_without_checking(self, item):
        """Load albums for an artist without checking them."""
        try:
            artist_name = item.text(0)
            artist_info = item.data(0, Qt.ItemDataRole.UserRole)
            
            if not artist_info:
                return
            
            self.albums_tree.clear()
            missing_albums = artist_info.get('missing_albums', [])
            
            # Get artist data from fast_comparison_results to check local albums
            artist_data = None
            if hasattr(self, 'fast_comparison_results') and self.fast_comparison_results:
                artist_data = self.fast_comparison_results.get('artists', {}).get(artist_name, {})
            
            # Check if the artist is checked in the artists tree
            is_artist_checked = item.checkState(0) == Qt.CheckState.Checked
            
            for album_data in missing_albums:
                album_title, album_artist = self._parse_album_data(album_data, artist_name)
                album_type = self.get_album_type(album_title)
                
                # Special handling for self-titled albums (like "311" by 311)
                is_self_titled = self.is_self_titled_album(album_title, artist_name)
                if is_self_titled:
                    album_type = "Self-Titled"
                    
                    # Check if this album is actually in the local library
                    if artist_data:
                        local_albums = artist_data.get('local_albums', [])
                        if any(self.is_self_titled_album(local_album, artist_name) for local_album in local_albums):
                            # This is likely a false positive - the album is actually in the local library
                            # but wasn't matched correctly. Add a visual indicator.
                            album_title = f"{album_title} ⚠️ (May be in library)"
                
                album_item = QTreeWidgetItem([album_title, album_artist, album_type])
                
                # Set the checkbox state based on the artist's checkbox state
                check_state = Qt.CheckState.Checked if is_artist_checked else Qt.CheckState.Unchecked
                album_item.setCheckState(0, check_state)
                
                album_item.setData(0, Qt.ItemDataRole.UserRole, album_data)
                self.albums_tree.addTopLevelItem(album_item)
            
            self.albums_tree.sortItems(0, Qt.SortOrder.AscendingOrder)
            
            logger.info(f"Loaded albums for artist {artist_name} without checking")
            
        except Exception as e:
            logger.error(f"Error loading albums without checking: {e}")
            
    def on_album_checkbox_changed(self, item, column):
        """Handle album checkbox changes - update artist checkbox state."""
        # Only handle checkbox in first column and prevent recursive calls
        if column != 0 or (hasattr(self, '_checkbox_change_in_progress') and self._checkbox_change_in_progress):
            return
            
        # Set flag to prevent recursive calls
        self._checkbox_change_in_progress = True
        
        try:
            album_title = item.text(0)
            album_artist = item.text(1)  # Artist column in albums tree
            is_checked = item.checkState(0) == Qt.CheckState.Checked
            
            logger.info(f"Album checkbox changed: {album_title} by {album_artist} -> {'checked' if is_checked else 'unchecked'}")
            
            # Update global selection tracking
            if is_checked:
                self._add_album_selection(album_artist, album_title)
                logger.info(f"DEBUG: Added to global selection: ({album_artist}, {album_title})")
            else:
                self._remove_album_selection(album_artist, album_title)
                logger.info(f"DEBUG: Removed from global selection: ({album_artist}, {album_title})")
            
            logger.info(f"DEBUG: Global selection now contains {len(self.selected_albums_global)} albums: {self.selected_albums_global}")
            
            # Update import button state
            self.update_import_button_state()
            
            # Find the artist in the artists tree
            artist_item = None
            for i in range(self.artists_tree.topLevelItemCount()):
                current_item = self.artists_tree.topLevelItem(i)
                if self.normalize_artist_name(current_item.text(0)) == self.normalize_artist_name(album_artist):
                    artist_item = current_item
                    break
            
            if artist_item:
                # Count checked and total albums for this artist
                checked_count = 0
                total_count = 0
                
                for i in range(self.albums_tree.topLevelItemCount()):
                    album_item = self.albums_tree.topLevelItem(i)
                    if self.normalize_artist_name(album_item.text(1)) == self.normalize_artist_name(album_artist):
                        total_count += 1
                        if album_item.checkState(0) == Qt.CheckState.Checked:
                            checked_count += 1
                
                # Update artist checkbox state
                self.artists_tree.blockSignals(True)
                if checked_count == 0:
                    artist_item.setCheckState(0, Qt.CheckState.Unchecked)
                elif checked_count == total_count:
                    artist_item.setCheckState(0, Qt.CheckState.Checked)
                else:
                    artist_item.setCheckState(0, Qt.CheckState.PartiallyChecked)
                self.artists_tree.blockSignals(False)
                
                logger.info(f"Updated artist checkbox: {album_artist} -> {checked_count}/{total_count} albums checked")
            
            # Update import button state
            self.update_import_button_state()
            
        except Exception as e:
            logger.error(f"Error in on_album_checkbox_changed: {e}")
        finally:
            # Always clear the flag, even if an exception occurs
            self._checkbox_change_in_progress = False