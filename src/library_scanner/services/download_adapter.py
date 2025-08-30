"""
Download adapter for Library Scanner integration with new download system.

This adapter allows the Library Scanner to work with both the old and new download systems
during the migration period.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class DownloadAdapter:
    """
    Adapter that provides a unified interface for the Library Scanner
    to work with both old and new download systems.
    """
    
    def __init__(self, deemusic_path: str, config_dir: str = None):
        self.deemusic_path = Path(deemusic_path)
        self.config_dir = Path(config_dir) if config_dir else None
        
        # Try to detect and use the new system first
        self.download_service = None
        self.legacy_manager = None
        
        self._initialize_download_system()
    
    def _initialize_download_system(self):
        """Initialize the appropriate download system."""
        try:
            # Check if new system is available
            app_data_dir = self._get_app_data_dir()
            new_queue_file = app_data_dir / "new_queue_state.json"
            
            if new_queue_file.exists():
                logger.info("[DownloadAdapter] New download system detected, attempting to use it")
                self._initialize_new_system()
            else:
                logger.info("[DownloadAdapter] Using legacy download system")
                self._initialize_legacy_system()
                
        except Exception as e:
            logger.error(f"[DownloadAdapter] Error initializing download system: {e}")
            # Fallback to legacy system
            self._initialize_legacy_system()
    
    def _get_app_data_dir(self) -> Path:
        """Get the application data directory."""
        import os
        app_data = os.getenv('APPDATA', Path.home())
        return Path(app_data) / 'DeeMusic'
    
    def _initialize_new_system(self):
        """Initialize the new download system."""
        try:
            import sys
            from pathlib import Path
            
            # Add src to path
            src_path = self.deemusic_path / "src"
            if str(src_path) not in sys.path:
                sys.path.insert(0, str(src_path))
            
            from services.download_service import DownloadService
            from config_manager import ConfigManager
            from services.deezer_api import DeezerAPI
            
            # Initialize config and API
            config = ConfigManager()
            deezer_api = DeezerAPI(config)
            
            # Initialize download service
            self.download_service = DownloadService(config, deezer_api)
            self.download_service.start()
            
            logger.info("[DownloadAdapter] New download system initialized successfully")
            
        except Exception as e:
            logger.error(f"[DownloadAdapter] Failed to initialize new system: {e}")
            self.download_service = None
            self._initialize_legacy_system()
    
    def _initialize_legacy_system(self):
        """Initialize the legacy download system."""
        try:
            import sys
            from pathlib import Path
            
            # Add src to path
            src_path = self.deemusic_path / "src"
            if str(src_path) not in sys.path:
                sys.path.insert(0, str(src_path))
            
            # Try to import from legacy backup location
            try:
                import sys
                legacy_path = str(src_path.parent / "legacy_backup")
                if legacy_path not in sys.path:
                    sys.path.insert(0, legacy_path)
                from services.download_manager import DownloadManager
            except ImportError:
                logger.error("[DownloadAdapter] Legacy download_manager not found - moved to backup")
                raise ImportError("Legacy download system not available")
            
            # Initialize legacy manager
            self.legacy_manager = DownloadManager(str(self.deemusic_path), str(self.config_dir) if self.config_dir else None)
            
            logger.info("[DownloadAdapter] Legacy download system initialized successfully")
            
        except Exception as e:
            logger.error(f"[DownloadAdapter] Failed to initialize legacy system: {e}")
            self.legacy_manager = None
    
    def add_album_to_queue(self, album_tracks: List[Dict[str, Any]]) -> int:
        """
        Add album tracks to download queue.
        
        Args:
            album_tracks: List of track dictionaries
            
        Returns:
            Number of tracks added
        """
        try:
            if self.download_service:
                return self._add_album_to_new_system(album_tracks)
            elif self.legacy_manager:
                return self.legacy_manager.add_album_to_queue(album_tracks)
            else:
                logger.error("[DownloadAdapter] No download system available")
                return 0
                
        except Exception as e:
            logger.error(f"[DownloadAdapter] Error adding album to queue: {e}")
            return 0
    
    def _add_album_to_new_system(self, album_tracks: List[Dict[str, Any]]) -> int:
        """Add album to new download system."""
        if not album_tracks:
            return 0
        
        # Extract album information from first track
        first_track = album_tracks[0]
        album_data = {
            'id': first_track.get('album_id', 0),
            'title': first_track.get('album', 'Unknown Album'),
            'artist': {'name': first_track.get('artist', 'Unknown Artist')},
            'tracks': {
                'data': []
            }
        }
        
        # Convert tracks to Deezer API format
        for track in album_tracks:
            track_data = {
                'id': track.get('track_id', 0),
                'title': track.get('title', 'Unknown Track'),
                'artist': {'name': track.get('artist', 'Unknown Artist')},
                'duration': track.get('duration', 0),
                'track_position': track.get('track_number', 1),
                'disk_number': track.get('disc_number', 1)
            }
            album_data['tracks']['data'].append(track_data)
        
        # Add to new system
        self.download_service.add_album(album_data)
        return len(album_tracks)
    
    def add_to_queue(self, track_data: Dict[str, Any]) -> bool:
        """
        Add individual track to download queue.
        
        Args:
            track_data: Track dictionary
            
        Returns:
            True if added successfully
        """
        try:
            if self.download_service:
                return self._add_track_to_new_system(track_data)
            elif self.legacy_manager:
                return self.legacy_manager.add_to_queue(track_data)
            else:
                logger.error("[DownloadAdapter] No download system available")
                return False
                
        except Exception as e:
            logger.error(f"[DownloadAdapter] Error adding track to queue: {e}")
            return False
    
    def _add_track_to_new_system(self, track_data: Dict[str, Any]) -> bool:
        """Add track to new download system."""
        # Convert to Deezer API format
        deezer_track_data = {
            'id': track_data.get('track_id', 0),
            'title': track_data.get('title', 'Unknown Track'),
            'artist': {'name': track_data.get('artist', 'Unknown Artist')},
            'duration': track_data.get('duration', 0)
        }
        
        # Add to new system
        self.download_service.add_track(deezer_track_data)
        return True
    
    def get_queue_size(self) -> int:
        """Get the current queue size."""
        try:
            if self.download_service:
                stats = self.download_service.get_queue_statistics()
                return stats.get('total_items', 0)
            elif self.legacy_manager:
                return self.legacy_manager.get_queue_size()
            else:
                return 0
                
        except Exception as e:
            logger.error(f"[DownloadAdapter] Error getting queue size: {e}")
            return 0
    
    def get_queue(self) -> List[Dict[str, Any]]:
        """Get the current queue."""
        try:
            if self.download_service:
                items = self.download_service.get_queue_items()
                # Convert to legacy format for compatibility
                queue = []
                for item in items:
                    for track in item.tracks:
                        queue.append({
                            'track_id': track.track_id,
                            'title': track.title,
                            'artist': track.artist,
                            'album': item.title,
                            'album_id': item.deezer_id,
                            'duration': track.duration,
                            'track_number': track.track_number,
                            'disc_number': track.disc_number
                        })
                return queue
            elif self.legacy_manager:
                return self.legacy_manager.get_queue()
            else:
                return []
                
        except Exception as e:
            logger.error(f"[DownloadAdapter] Error getting queue: {e}")
            return []
    
    def get_download_stats(self) -> Dict[str, Any]:
        """Get download statistics."""
        try:
            if self.download_service:
                stats = self.download_service.get_queue_statistics()
                # Convert to legacy format
                return {
                    'total_tracks': stats.get('total_tracks', 0),
                    'completed_tracks': stats.get('completed_tracks', 0),
                    'failed_tracks': stats.get('failed_tracks', 0),
                    'queued_tracks': stats.get('by_state', {}).get('queued', 0)
                }
            elif self.legacy_manager:
                return self.legacy_manager.get_download_stats()
            else:
                return {'total_tracks': 0, 'completed_tracks': 0, 'failed_tracks': 0, 'queued_tracks': 0}
                
        except Exception as e:
            logger.error(f"[DownloadAdapter] Error getting download stats: {e}")
            return {'total_tracks': 0, 'completed_tracks': 0, 'failed_tracks': 0, 'queued_tracks': 0}
    
    def group_queue_by_album(self) -> Dict[str, List[Dict[str, Any]]]:
        """Group queue items by album."""
        try:
            queue = self.get_queue()
            albums = {}
            
            for track in queue:
                artist = track.get('artist', 'Unknown Artist')
                album = track.get('album', 'Unknown Album')
                key = f"{artist}|{album}"
                
                if key not in albums:
                    albums[key] = []
                albums[key].append(track)
            
            return albums
            
        except Exception as e:
            logger.error(f"[DownloadAdapter] Error grouping queue by album: {e}")
            return {}
    
    def _save_state(self):
        """Save the current state."""
        try:
            if self.legacy_manager:
                self.legacy_manager._save_state()
            # New system saves automatically
                
        except Exception as e:
            logger.error(f"[DownloadAdapter] Error saving state: {e}")
    
    def _load_state(self):
        """Load the current state."""
        try:
            if self.legacy_manager:
                self.legacy_manager._load_state()
            # New system loads automatically
                
        except Exception as e:
            logger.error(f"[DownloadAdapter] Error loading state: {e}")
    
    def launch_deemusic_with_queue(self) -> bool:
        """Launch DeeMusic with the current queue."""
        try:
            if self.legacy_manager:
                return self.legacy_manager.launch_deemusic_with_queue()
            else:
                # For new system, just launch DeeMusic - queue is already there
                import subprocess
                import sys
                
                deemusic_exe = self.deemusic_path / "DeeMusic.exe"
                if deemusic_exe.exists():
                    subprocess.Popen([str(deemusic_exe)], cwd=str(self.deemusic_path))
                    return True
                else:
                    # Try running with Python
                    run_py = self.deemusic_path / "run.py"
                    if run_py.exists():
                        subprocess.Popen([sys.executable, str(run_py)], cwd=str(self.deemusic_path))
                        return True
                
                return False
                
        except Exception as e:
            logger.error(f"[DownloadAdapter] Error launching DeeMusic: {e}")
            return False
    
    def export_queue_to_deemusic(self) -> Optional[str]:
        """Export queue to DeeMusic format."""
        try:
            if self.legacy_manager:
                return self.legacy_manager.export_queue_to_deemusic()
            else:
                # For new system, queue is already in DeeMusic
                return None
                
        except Exception as e:
            logger.error(f"[DownloadAdapter] Error exporting queue: {e}")
            return None
    
    def create_m3u_playlist(self) -> Optional[str]:
        """Create M3U playlist from queue."""
        try:
            if self.legacy_manager:
                return self.legacy_manager.create_m3u_playlist()
            else:
                # TODO: Implement M3U creation for new system
                return None
                
        except Exception as e:
            logger.error(f"[DownloadAdapter] Error creating M3U playlist: {e}")
            return None