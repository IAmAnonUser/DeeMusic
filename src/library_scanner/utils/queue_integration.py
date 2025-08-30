"""
Queue Integration - Handles importing selected albums into DeeMusic's download queue
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import sys

from ..core.data_models import MissingAlbum, MissingTrack

# Import the new queue system models
try:
    # Add src to path for imports
    src_path = Path(__file__).parent.parent.parent
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    
    from src.models.queue_models import QueueItem, ItemType, TrackInfo
    NEW_QUEUE_SYSTEM_AVAILABLE = True
except ImportError as e:
    logging.warning(f"New queue system not available: {e}")
    NEW_QUEUE_SYSTEM_AVAILABLE = False

logger = logging.getLogger(__name__)

class QueueIntegration:
    """Handles integration with DeeMusic's download queue system."""
    
    def __init__(self, config=None, download_service=None):
        """Initialize queue integration."""
        self.config = config
        self.download_service = download_service  # New download service
        self.deemusic_appdata_path = self._get_deemusic_appdata_path()
        
        # Support both old and new queue systems
        self.old_download_queue_path = self.deemusic_appdata_path / "download_queue_state.json"
        self.new_download_queue_path = self.deemusic_appdata_path / "new_queue_state.json"
        self.library_scanner_queue_path = Path(__file__).parent.parent.parent / "download_queue.json"
    
    def _get_deemusic_appdata_path(self) -> Path:
        """Get the DeeMusic AppData directory path."""
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
    
    def is_deemusic_queue_accessible(self) -> bool:
        """Check if DeeMusic's download queue is accessible."""
        try:
            logger.info(f"DEBUG: Checking queue accessibility - AppData path: {self.deemusic_appdata_path}")
            
            # Check if AppData directory exists
            if not self.deemusic_appdata_path.exists():
                logger.info(f"DeeMusic AppData directory not found: {self.deemusic_appdata_path}")
                return False
            
            logger.info(f"DEBUG: AppData directory exists")
            
            # If we have a download service, we can use the new system directly
            if self.download_service and NEW_QUEUE_SYSTEM_AVAILABLE:
                logger.info(f"DEBUG: Using new download service for queue access")
                return True
            
            # Otherwise check for queue files
            new_queue_exists = self.new_download_queue_path.exists()
            old_queue_exists = self.old_download_queue_path.exists()
            
            logger.info(f"DEBUG: New queue file exists: {new_queue_exists}")
            logger.info(f"DEBUG: Old queue file exists: {old_queue_exists}")
            
            # Prefer new queue system if available
            if new_queue_exists or NEW_QUEUE_SYSTEM_AVAILABLE:
                logger.info(f"DEBUG: New queue system available")
                return True
            
            # Fall back to old queue system
            if old_queue_exists:
                logger.info(f"DEBUG: Old queue system available")
                return True
            
            # If no queue files exist, we can create them
            logger.info(f"DEBUG: No queue files exist, but can be created")
            return True
            
        except Exception as e:
            logger.error(f"Error checking DeeMusic queue accessibility: {e}")
            return False
    
    def save_selected_albums(self, selected_albums: List[MissingAlbum]) -> bool:
        """Save selected albums to the Library Scanner's download queue file."""
        try:
            # Create the download queue data
            queue_data = {
                "selected_albums": [],
                "metadata": {
                    "created_at": datetime.now().isoformat(),
                    "total_albums": len(selected_albums),
                    "source": "DeeMusic Library Scanner"
                }
            }
            
            for missing_album in selected_albums:
                album_data = {
                    "deezer_id": missing_album.deezer_album.id,
                    "title": missing_album.deezer_album.title,
                    "artist": missing_album.deezer_album.artist,
                    "year": missing_album.deezer_album.year,
                    "track_count": missing_album.deezer_album.track_count,
                    "url": f"https://www.deezer.com/album/{missing_album.deezer_album.id}",
                    "local_album_path": str(missing_album.local_album.path) if missing_album.local_album else None,
                    "missing_tracks_count": len(missing_album.missing_tracks),
                    "selection_reason": "user_selected"
                }
                queue_data["selected_albums"].append(album_data)
            
            # Ensure directory exists
            self.library_scanner_queue_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save to file
            with open(self.library_scanner_queue_path, 'w', encoding='utf-8') as f:
                json.dump(queue_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved {len(selected_albums)} selected albums to {self.library_scanner_queue_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving selected albums: {e}")
            return False
    
    def load_selected_albums(self) -> List[Dict[str, Any]]:
        """Load selected albums from the Library Scanner's download queue file."""
        try:
            if not self.library_scanner_queue_path.exists():
                logger.info("No selected albums file found")
                return []
            
            with open(self.library_scanner_queue_path, 'r', encoding='utf-8') as f:
                queue_data = json.load(f)
            
            selected_albums = queue_data.get("selected_albums", [])
            logger.info(f"Loaded {len(selected_albums)} selected albums")
            return selected_albums
            
        except Exception as e:
            logger.error(f"Error loading selected albums: {e}")
            return []
    
    def import_to_deemusic_queue(self, selected_albums: Optional[List[Dict[str, Any]]] = None) -> bool:
        """Import selected albums into DeeMusic's download queue as pending downloads."""
        try:
            # Load selected albums if not provided
            if selected_albums is None:
                selected_albums = self.load_selected_albums()
            
            if not selected_albums:
                logger.info("No selected albums to import")
                return True
            
            # Check if DeeMusic queue is accessible
            if not self.is_deemusic_queue_accessible():
                logger.error("DeeMusic download queue is not accessible")
                return False
            
            # Load existing DeeMusic queue state
            queue_state = self._load_deemusic_queue_state()
            
            # Add selected albums as pending downloads
            imported_count = 0
            for album_data in selected_albums:
                if self._add_album_to_queue(queue_state, album_data):
                    imported_count += 1
            
            # Save updated queue state
            if self._save_deemusic_queue_state(queue_state):
                logger.info(f"Successfully imported {imported_count} albums to DeeMusic download queue")
                
                # Clear the Library Scanner's queue file after successful import
                self._clear_selected_albums()
                
                return True
            else:
                logger.error("Failed to save updated DeeMusic queue state")
                return False
                
        except Exception as e:
            logger.error(f"Error importing to DeeMusic queue: {e}")
            return False
    
    def _load_deemusic_queue_state(self) -> Dict[str, Any]:
        """Load DeeMusic's download queue state."""
        try:
            # Try new queue file first, then fall back to old
            queue_file = self.new_download_queue_path if self.new_download_queue_path.exists() else self.old_download_queue_path
            
            if queue_file.exists():
                try:
                    with open(queue_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except UnicodeDecodeError:
                    # Try with utf-8-sig to handle BOM
                    with open(queue_file, 'r', encoding='utf-8-sig') as f:
                        return json.load(f)
            else:
                # Create default structure that matches DeeMusic's expected format
                return {
                    "unfinished_downloads": [],
                    "completed_downloads": [],
                    "failed_downloads": [],
                    "metadata": {
                        "last_updated": datetime.now().isoformat(),
                        "version": "1.0"
                    }
                }
        except Exception as e:
            logger.error(f"Error loading DeeMusic queue state: {e}")
            # Return default structure on error that matches DeeMusic's expected format
            return {
                "unfinished_downloads": [],
                "completed_downloads": [],
                "failed_downloads": [],
                "metadata": {
                    "last_updated": datetime.now().isoformat(),
                    "version": "1.0"
                }
            }
    
    def _save_deemusic_queue_state(self, queue_state: Dict[str, Any]) -> bool:
        """Save DeeMusic's download queue state, preserving existing data."""
        try:
            # Ensure directory exists
            self.deemusic_appdata_path.mkdir(parents=True, exist_ok=True)
            
            # Load existing queue state to preserve other sections
            existing_state = {}
            if self.download_queue_path.exists():
                try:
                    with open(self.download_queue_path, 'r', encoding='utf-8') as f:
                        existing_state = json.load(f)
                except Exception as e:
                    logger.warning(f"Could not load existing queue state: {e}")
            
            # Merge with existing state, preserving failed_downloads and completed_downloads
            merged_state = {
                "unfinished_downloads": queue_state.get("unfinished_downloads", []),
                "completed_downloads": existing_state.get("completed_downloads", []),
                "failed_downloads": existing_state.get("failed_downloads", []),
                "metadata": {
                    "last_updated": datetime.now().isoformat(),
                    "version": "1.0"
                }
            }
            
            # Update metadata from existing state if present
            if "metadata" in existing_state:
                merged_state["metadata"].update(existing_state["metadata"])
                merged_state["metadata"]["last_updated"] = datetime.now().isoformat()
            
            # Save merged state to file (prefer new queue file)
            queue_file = self.new_download_queue_path if NEW_QUEUE_SYSTEM_AVAILABLE else self.old_download_queue_path
            
            with open(queue_file, 'w', encoding='utf-8') as f:
                json.dump(merged_state, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved DeeMusic queue state to {queue_file} (preserved existing failed/completed downloads)")
            return True
            
        except Exception as e:
            logger.error(f"Error saving DeeMusic queue state: {e}")
            return False
    
    def _add_album_to_queue(self, queue_state: Dict[str, Any], album_data: Dict[str, Any]) -> bool:
        """Add an album to the DeeMusic download queue as an unfinished download."""
        try:
            # Ensure unfinished_downloads list exists (this is what DeeMusic expects)
            if "unfinished_downloads" not in queue_state:
                queue_state["unfinished_downloads"] = []
            
            # Skip albums with no missing tracks (they don't need to be downloaded)
            missing_tracks_count = album_data.get("missing_tracks_count", 0)
            if missing_tracks_count == 0:
                logger.info(f"Skipping album '{album_data.get('title', 'Unknown')}' - no missing tracks to download")
                return False
            
            # Validate album ID
            album_id = str(album_data.get("deezer_id"))
            if not album_id or album_id == "None" or album_id == "0" or album_id == "unknown":
                logger.error(f"Invalid album ID: {album_id}. Skipping album: {album_data.get('title', 'Unknown')}")
                return False
            
            # Ensure album ID is numeric
            try:
                int(album_id)
            except ValueError:
                logger.error(f"Non-numeric album ID: {album_id}. Skipping album: {album_data.get('title', 'Unknown')}")
                return False
            
            # Check if album is already in queue (avoid duplicates)
            for existing_item in queue_state["unfinished_downloads"]:
                if (existing_item.get("type") == "album" and 
                    str(existing_item.get("album_id")) == album_id):
                    logger.info(f"Album {album_id} already in queue, skipping")
                    return False
            
            # Get track information for the album if we have a valid album ID
            queued_tracks = []
            if album_id and album_id != "0":
                try:
                    queued_tracks = self._get_album_tracks(album_id)
                except Exception as e:
                    logger.warning(f"Could not fetch tracks for album {album_id}: {e}")
            
            # Create album download entry in the format DeeMusic expects
            album_entry = {
                "album_id": album_id,
                "album_title": album_data.get("title", "Unknown Album"),
                "artist_name": album_data.get("artist", "Unknown Artist"),
                "type": "album",
                "queued_tracks": queued_tracks,
                "added_at": datetime.now().isoformat(),
                "source": "Library Scanner",
                "local_album_path": album_data.get("local_album_path"),
                "missing_tracks_count": missing_tracks_count
            }
            
            # Add to unfinished downloads (this is what DeeMusic reads on startup)
            queue_state["unfinished_downloads"].append(album_entry)
            
            logger.info(f"Added album '{album_entry['album_title']}' by '{album_entry['artist_name']}' to DeeMusic queue with {len(queued_tracks)} tracks ({missing_tracks_count} missing)")
            return True
            
        except Exception as e:
            logger.error(f"Error adding album to queue: {e}")
            return False
    
    def _is_track_removed(self, track_id: str) -> bool:
        """Check if a track was manually removed by user"""
        try:
            removed_tracks_file = self.deemusic_appdata_path / 'removed_tracks.json'
            
            if not removed_tracks_file.exists():
                return False
            
            with open(removed_tracks_file, 'r', encoding='utf-8') as f:
                removed_data = json.load(f)
            
            return str(track_id) in removed_data.get("removed_tracks", [])
        
        except Exception as e:
            logger.error(f"Error checking removed track: {e}")
            return False
    
    def _get_album_tracks(self, album_id: str) -> List[Dict[str, Any]]:
        """Get track information for an album from Deezer API."""
        try:
            import requests
            
            # Use Deezer public API to get album tracks
            url = f"https://api.deezer.com/album/{album_id}/tracks"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                tracks = []
                
                for track in data.get('data', []):
                    track_id = str(track.get('id', ''))
                    # Skip tracks that were manually removed by user
                    if not self._is_track_removed(track_id):
                        tracks.append({
                            'track_id': track_id,
                            'title': track.get('title', 'Unknown Title')
                        })
                    else:
                        logger.info(f"Skipping removed track {track_id}: {track.get('title', 'Unknown')}")
                
                return tracks
            else:
                logger.warning(f"Failed to fetch tracks for album {album_id}: HTTP {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Error fetching album tracks: {e}")
            return []
    
    def _clear_selected_albums(self) -> bool:
        """Clear the Library Scanner's selected albums file after successful import."""
        try:
            if self.library_scanner_queue_path.exists():
                self.library_scanner_queue_path.unlink()
                logger.info("Cleared Library Scanner's selected albums file")
            return True
        except Exception as e:
            logger.error(f"Error clearing selected albums file: {e}")
            return False
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get status information about both queues."""
        status = {
            "deemusic_accessible": self.is_deemusic_queue_accessible(),
            "new_queue_path": str(self.new_download_queue_path),
            "old_queue_path": str(self.old_download_queue_path),
            "library_scanner_queue_path": str(self.library_scanner_queue_path),
            "using_new_system": self.download_service is not None and NEW_QUEUE_SYSTEM_AVAILABLE,
            "selected_albums_count": 0,
            "deemusic_pending_count": 0,
            "deemusic_failed_count": 0,
            "deemusic_completed_count": 0
        }
        
        try:
            # Count selected albums in Library Scanner
            selected_albums = self.load_selected_albums()
            status["selected_albums_count"] = len(selected_albums)
            
            # Count items in DeeMusic queue
            if status["deemusic_accessible"]:
                queue_state = self._load_deemusic_queue_state()
                status["deemusic_pending_count"] = len(queue_state.get("unfinished_downloads", []))
                status["deemusic_failed_count"] = len(queue_state.get("failed_downloads", []))
                status["deemusic_completed_count"] = len(queue_state.get("completed_downloads", []))
                
        except Exception as e:
            logger.error(f"Error getting queue status: {e}")
        
        return status
    
    def import_albums_directly(self, selected_albums: List[MissingAlbum]) -> bool:
        """Import selected albums directly to DeeMusic's download queue without intermediate file."""
        try:
            if not selected_albums:
                logger.info("No selected albums to import")
                return True
            
            # Try new download service first
            if self.download_service and NEW_QUEUE_SYSTEM_AVAILABLE:
                return self._import_albums_with_new_service(selected_albums)
            
            # Fall back to old queue system
            return self._import_albums_with_old_system(selected_albums)
                
        except Exception as e:
            logger.error(f"Error importing albums directly: {e}")
            return False
    
    def _import_albums_with_new_service(self, selected_albums: List[MissingAlbum]) -> bool:
        """Import albums using the new download service with optimized batch processing."""
        try:
            logger.info(f"[QueueIntegration] Using new download service to import {len(selected_albums)} albums")
            
            imported_count = 0
            
            # Process albums in smaller batches for better performance
            batch_size = 10
            for batch_start in range(0, len(selected_albums), batch_size):
                batch_end = min(batch_start + batch_size, len(selected_albums))
                batch = selected_albums[batch_start:batch_end]
                
                for i, missing_album in enumerate(batch):
                    overall_index = batch_start + i
                    
                    # Skip albums with invalid or missing IDs
                    album_id = missing_album.deezer_album.id
                    if not album_id or album_id == 0 or str(album_id) == 'unknown':
                        logger.warning(f"Skipping album '{missing_album.deezer_album.title}' with invalid ID: {album_id}")
                        continue
                    
                    try:
                        logger.info(f"[QueueIntegration] Adding album {overall_index+1}/{len(selected_albums)}: '{missing_album.deezer_album.title}' by '{missing_album.deezer_album.artist}' (ID: {album_id})")
                        
                        # Use the download service to add the album
                        success = self.download_service.download_album(album_id)
                        
                        if success:
                            imported_count += 1
                            logger.info(f"[QueueIntegration] Successfully added album {overall_index+1} to new queue")
                        else:
                            logger.warning(f"[QueueIntegration] Failed to add album {overall_index+1} to new queue")
                            
                    except Exception as e:
                        logger.error(f"[QueueIntegration] Error adding album {overall_index+1} to new queue: {e}")
                
                # Small delay between batches to prevent overwhelming the system
                import time
                time.sleep(0.1)
            
            logger.info(f"[QueueIntegration] New service import summary - {imported_count} out of {len(selected_albums)} albums added to queue")
            return imported_count > 0
            
        except Exception as e:
            logger.error(f"[QueueIntegration] Error importing albums with new service: {e}")
            return False
    
    def _import_albums_with_old_system(self, selected_albums: List[MissingAlbum]) -> bool:
        """Import albums using the old queue system (fallback)."""
        try:
            logger.info(f"[QueueIntegration] Using old queue system to import {len(selected_albums)} albums")
            
            # Check if DeeMusic queue is accessible
            if not self.is_deemusic_queue_accessible():
                logger.error("DeeMusic download queue is not accessible")
                return False
            
            # Load existing DeeMusic queue state
            queue_state = self._load_deemusic_queue_state()
            
            # Convert MissingAlbum objects to album data format
            album_data_list = []
            for missing_album in selected_albums:
                # Skip albums with invalid or missing IDs
                album_id = missing_album.deezer_album.id
                if not album_id or album_id == 0 or str(album_id) == 'unknown':
                    logger.warning(f"Skipping album '{missing_album.deezer_album.title}' with invalid ID: {album_id}")
                    continue
                    
                album_data = {
                    "deezer_id": album_id,
                    "title": missing_album.deezer_album.title,
                    "artist": missing_album.deezer_album.artist,
                    "year": missing_album.deezer_album.year,
                    "track_count": missing_album.deezer_album.track_count,
                    "url": f"https://www.deezer.com/album/{album_id}",
                    "local_album_path": str(missing_album.local_album.path) if missing_album.local_album else None,
                    "missing_tracks_count": len(missing_album.missing_tracks),
                }
                album_data_list.append(album_data)
            
            # Add selected albums directly to DeeMusic queue
            logger.info(f"DEBUG: Processing {len(album_data_list)} albums for import")
            imported_count = 0
            for i, album_data in enumerate(album_data_list):
                logger.info(f"DEBUG: Processing album {i+1}/{len(album_data_list)}: '{album_data.get('title')}' by '{album_data.get('artist')}' (ID: {album_data.get('deezer_id')})")
                if self._add_album_to_queue(queue_state, album_data):
                    imported_count += 1
                    logger.info(f"DEBUG: Successfully added album {i+1} to queue")
                else:
                    logger.warning(f"DEBUG: Failed to add album {i+1} to queue")
            
            logger.info(f"DEBUG: Import summary - {imported_count} out of {len(album_data_list)} albums added to queue")
            
            # Save updated queue state directly to DeeMusic
            if self._save_deemusic_queue_state(queue_state):
                logger.info(f"Successfully imported {imported_count} albums directly to DeeMusic download queue")
                return True
            else:
                logger.error("Failed to save updated DeeMusic queue state")
                return False
                
        except Exception as e:
            logger.error(f"Error importing albums with old system: {e}")
            return False
    
    def create_import_summary(self, selected_albums: List[Dict[str, Any]]) -> str:
        """Create a summary of albums to be imported."""
        if not selected_albums:
            return "No albums selected for import."
        
        summary_lines = [
            f"📋 Import Summary",
            f"=" * 50,
            f"Selected Albums: {len(selected_albums)}",
            f"Destination: DeeMusic Download Queue",
            f"",
            f"Albums to Import:"
        ]
        
        for i, album in enumerate(selected_albums, 1):
            title = album.get("title", "Unknown Album")
            artist = album.get("artist", "Unknown Artist")
            track_count = album.get("track_count", 0)
            missing_count = album.get("missing_tracks_count", 0)
            
            summary_lines.append(
                f"  {i:2d}. {title} - {artist} "
                f"({track_count} tracks, {missing_count} missing)"
            )
        
        queue_system = "New Queue System" if (self.download_service and NEW_QUEUE_SYSTEM_AVAILABLE) else "Legacy Queue System"
        queue_path = self.new_download_queue_path if (self.download_service and NEW_QUEUE_SYSTEM_AVAILABLE) else self.old_download_queue_path
        
        summary_lines.extend([
            f"",
            f"💡 These albums will be added to DeeMusic's download queue",
            f"   and can be downloaded when you open DeeMusic.",
            f"",
            f"🔧 Queue System: {queue_system}",
            f"📁 Queue Location: {queue_path}"
        ])
        
        return "\n".join(summary_lines)