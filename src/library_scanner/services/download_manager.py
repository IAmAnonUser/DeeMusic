"""
Download Manager Service
Manages download queue and integrates with DeeMusic for downloading missing tracks
"""

import json
import logging
import os
import subprocess
import asyncio
from typing import Dict, List, Optional, Set
from pathlib import Path
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class DownloadManager(QObject):
    """Manages downloads and integration with DeeMusic"""
    
    # Signals
    download_queued = pyqtSignal(dict)  # Track queued
    download_started = pyqtSignal(str)  # Track ID
    download_completed = pyqtSignal(str)  # Track ID
    download_failed = pyqtSignal(str, str)  # Track ID, error message
    queue_updated = pyqtSignal(int)  # Queue size
    
    def __init__(self, deemusic_path: Optional[str] = None, config_dir: Optional[Path] = None):
        super().__init__()
        self.deemusic_path = deemusic_path
        
        # Use provided config directory or default to %appdata%/DeeMusic
        if config_dir is None:
            import sys
            app_name = "DeeMusic"
            try:
                home_dir = Path.home()
                if sys.platform == "win32":
                    appdata = os.getenv('APPDATA')
                    if appdata:
                        config_dir = Path(appdata) / app_name
                    else:
                        config_dir = home_dir / app_name
                elif sys.platform == "darwin":
                    config_dir = home_dir / "Library" / "Application Support" / app_name
                else:
                    xdg_config_home = os.getenv('XDG_CONFIG_HOME')
                    if xdg_config_home:
                        config_dir = Path(xdg_config_home) / app_name
                    else:
                        config_dir = home_dir / ".config" / app_name
            except Exception as e:
                logger.error(f"Could not determine config directory: {e}")
                config_dir = Path('.') / 'user_config'
        
        self.config_dir = config_dir
        self.download_queue = []
        self.downloaded_tracks = set()
        self.failed_tracks = {}
        self.queue_file = self.config_dir / "download_queue.json"
        self.history_file = self.config_dir / "download_history.json"
        self._load_state()
        
    def _load_state(self):
        """Load download queue and history from disk"""
        # Load queue
        if self.queue_file.exists():
            try:
                with open(self.queue_file, 'r') as f:
                    data = json.load(f)
                    self.download_queue = data.get("queue", [])
                    logger.info(f"Loaded {len(self.download_queue)} items from queue")
            except Exception as e:
                logger.error(f"Error loading queue: {e}")
                
        # Load history
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    data = json.load(f)
                    self.downloaded_tracks = set(data.get("downloaded", []))
                    self.failed_tracks = data.get("failed", {})
                    logger.info(f"Loaded download history: {len(self.downloaded_tracks)} completed")
            except Exception as e:
                logger.error(f"Error loading history: {e}")
                
    def _save_state(self):
        """Save download queue and history to disk"""
        # Ensure directory exists
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Save queue (legacy)
        try:
            with open(self.queue_file, 'w') as f:
                json.dump({
                    "queue": self.download_queue,
                    "updated": datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving queue: {e}")
        
        # Save history
        try:
            with open(self.history_file, 'w') as f:
                json.dump({
                    "downloaded": list(self.downloaded_tracks),
                    "failed": self.failed_tracks,
                    "updated": datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving history: {e}")
        # Merge queue to DeeMusic's download_queue_state.json
        self.merge_queue_to_deemusic_state()
            
    def merge_queue_to_deemusic_state(self):
        """Merge the current download queue into DeeMusic's download_queue_state.json (unfinished_downloads)."""
        try:
            deemusic_state_path = self.config_dir / "download_queue_state.json"
            # Load existing state or create new
            if deemusic_state_path.exists():
                with open(deemusic_state_path, 'r', encoding='utf-8') as f:
                    state = json.load(f)
            else:
                state = {"unfinished_downloads": [], "completed_downloads": [], "failed_downloads": []}
            # Build set of (album_id, track_id) for deduplication
            existing = set()
            for album in state.get("unfinished_downloads", []):
                for track in album.get("queued_tracks", []):
                    existing.add((album["album_id"], track["track_id"]))
            # Group current queue by album
            albums = {}
            for item in self.download_queue:
                album_id = str(item.get("album_id") or item.get("album") or "unknown")
                album_title = item.get("album") or "Unknown Album"
                artist_name = item.get("artist") or "Unknown Artist"
                track_id = str(item.get("id"))
                track_title = item.get("title")
                if album_id not in albums:
                    albums[album_id] = {
                        "album_id": album_id,
                        "album_title": album_title,
                        "artist_name": artist_name,
                        "type": "album",
                        "queued_tracks": []
                    }
                albums[album_id]["queued_tracks"].append({
                    "track_id": track_id,
                    "title": track_title
                })
            # Merge albums/tracks into state
            for album_id, album_data in albums.items():
                match = next((a for a in state["unfinished_downloads"] if a["album_id"] == album_id), None)
                if match:
                    for track in album_data["queued_tracks"]:
                        if (album_id, track["track_id"]) not in existing:
                            match["queued_tracks"].append(track)
                            existing.add((album_id, track["track_id"]))
                else:
                    state["unfinished_downloads"].append(album_data)
                    for track in album_data["queued_tracks"]:
                        existing.add((album_id, track["track_id"]))
            # Save merged state
            deemusic_state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(deemusic_state_path, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            logger.info(f"Merged queue to DeeMusic download_queue_state.json ({deemusic_state_path})")
        except Exception as e:
            logger.error(f"Error merging queue to DeeMusic state: {e}")
            
    def add_to_queue(self, track_info: Dict):
        """Add a track to the download queue"""
        # Extract Deezer track info
        deezer_track = track_info.get("deezer_track", {})
        
        # Create download item
        download_item = {
            "id": str(deezer_track.get("id")),
            "title": deezer_track.get("title"),
            "artist": track_info.get("artist"),
            "album": track_info.get("album"),
            "duration": deezer_track.get("duration"),
            "track_position": deezer_track.get("track_position"),
            "deezer_url": deezer_track.get("link"),
            "preview_url": deezer_track.get("preview"),
            "added_date": datetime.now().isoformat(),
            "status": "queued"
        }
        
        # Check if already in queue or downloaded
        track_id = download_item["id"]
        if track_id in self.downloaded_tracks:
            logger.info(f"Track {track_id} already downloaded")
            return False
            
        if any(item["id"] == track_id for item in self.download_queue):
            logger.info(f"Track {track_id} already in queue")
            return False
            
        # Add to queue
        self.download_queue.append(download_item)
        self._save_state()
        
        # Emit signals
        self.download_queued.emit(download_item)
        self.queue_updated.emit(len(self.download_queue))
        
        logger.info(f"Added to queue: {download_item['artist']} - {download_item['title']}")
        return True
        
    def add_album_to_queue(self, album_tracks: List[Dict]):
        """Add all tracks from an album to the queue"""
        added_count = 0
        for track_info in album_tracks:
            if self.add_to_queue(track_info):
                added_count += 1
                
        logger.info(f"Added {added_count} tracks from album to queue")
        return added_count
        
    def remove_from_queue(self, track_id: str):
        """Remove a track from the queue"""
        self.download_queue = [
            item for item in self.download_queue 
            if item["id"] != track_id
        ]
        self._save_state()
        self.queue_updated.emit(len(self.download_queue))
        
    def clear_queue(self):
        """Clear the entire download queue"""
        self.download_queue = []
        self._save_state()
        self.queue_updated.emit(0)
        
    def get_queue(self) -> List[Dict]:
        """Get current download queue"""
        return self.download_queue.copy()
        
    def get_queue_size(self) -> int:
        """Get number of items in queue"""
        return len(self.download_queue)
        
    def mark_downloaded(self, track_id: str):
        """Mark a track as successfully downloaded"""
        self.downloaded_tracks.add(track_id)
        self.remove_from_queue(track_id)
        
        # Remove from failed if it was there
        if track_id in self.failed_tracks:
            del self.failed_tracks[track_id]
            
        self._save_state()
        self.download_completed.emit(track_id)
        
    def mark_failed(self, track_id: str, error_message: str):
        """Mark a track as failed to download"""
        self.failed_tracks[track_id] = {
            "error": error_message,
            "timestamp": datetime.now().isoformat()
        }
        self.remove_from_queue(track_id)
        self._save_state()
        self.download_failed.emit(track_id, error_message)
        
    def retry_failed(self, track_id: str):
        """Retry a failed download"""
        if track_id in self.failed_tracks:
            del self.failed_tracks[track_id]
            self._save_state()
            
    def get_download_stats(self) -> Dict:
        """Get download statistics"""
        return {
            "queued": len(self.download_queue),
            "completed": len(self.downloaded_tracks),
            "failed": len(self.failed_tracks),
            "total": len(self.download_queue) + len(self.downloaded_tracks) + len(self.failed_tracks)
        }
        
    def export_queue_to_deemusic(self, output_file: Optional[str] = None) -> str:
        """Export queue to a format DeeMusic can import"""
        if not output_file:
            output_file_path = self.config_dir / "deemusic_import.json"
        else:
            output_file_path = Path(output_file)
            
        output_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Format for DeeMusic
        deemusic_data = {
            "tracks": [
                {
                    "id": item["id"],
                    "title": item["title"],
                    "artist": item["artist"],
                    "album": item["album"],
                    "url": item["deezer_url"]
                }
                for item in self.download_queue
            ],
            "source": "DeeMusic Library Scanner",
            "created": datetime.now().isoformat()
        }
        
        with open(output_file_path, 'w') as f:
            json.dump(deemusic_data, f, indent=2)
            
        logger.info(f"Exported {len(self.download_queue)} tracks to {output_file_path}")
        return str(output_file_path)
        
    def launch_deemusic_with_queue(self) -> bool:
        """Launch DeeMusic with the current queue using --import argument and a temp JSON file."""
        if not self.deemusic_path:
            logger.error("DeeMusic path not configured")
            return False
        
        if not os.path.exists(self.deemusic_path):
            logger.error(f"DeeMusic not found at {self.deemusic_path}")
            return False
        
        if not self.download_queue:
            logger.warning("Download queue is empty")
            return False
        
        try:
            # Export queue to a temp file
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=".json", prefix="deemusic_import_") as tmp:
                import_file = tmp.name
            self.export_queue_to_deemusic(import_file)
            # Launch DeeMusic with import file argument
            subprocess.Popen([self.deemusic_path, "--import", import_file])
            logger.info(f"Launched DeeMusic with {len(self.download_queue)} tracks using import file {import_file}")
            return True
        except Exception as e:
            logger.error(f"Error launching DeeMusic: {e}")
            return False
            
    def create_m3u_playlist(self, output_file: Optional[str] = None) -> str:
        """Create an M3U playlist of tracks to download"""
        if not output_file:
            output_file_path = self.config_dir / "missing_tracks.m3u"
        else:
            output_file_path = Path(output_file)
            
        output_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            
            for item in self.download_queue:
                duration = item.get("duration", 0)
                artist = item.get("artist", "Unknown Artist")
                title = item.get("title", "Unknown Title")
                url = item.get("deezer_url", "")
                
                f.write(f"#EXTINF:{duration},{artist} - {title}\n")
                f.write(f"{url}\n")
                
        logger.info(f"Created M3U playlist with {len(self.download_queue)} tracks")
        return str(output_file_path)
        
    def group_queue_by_album(self) -> Dict[str, List[Dict]]:
        """Group queued tracks by album"""
        albums = {}
        
        for item in self.download_queue:
            album_key = f"{item['artist']}|{item['album']}"
            if album_key not in albums:
                albums[album_key] = []
            albums[album_key].append(item)
            
        # Sort tracks within each album
        for album_key in albums:
            albums[album_key].sort(
                key=lambda x: x.get("track_position", 0)
            )
            
        return albums 