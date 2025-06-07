"""Library management service for DeeMusic."""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import logging
from datetime import datetime
import mutagen
from mutagen.easyid3 import EasyID3
from deemusic.config_manager import ConfigManager
import sqlite3
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class Track:
    """Represents a track in the library."""
    id: str
    title: str
    artist: str
    album: str
    duration: int
    path: str
    artwork_path: Optional[str] = None
    added_date: str = datetime.now().isoformat()
    play_count: int = 0
    last_played: Optional[str] = None

@dataclass
class Playlist:
    """Represents a playlist in the library."""
    id: str
    name: str
    description: str
    tracks: List[str]  # List of track IDs
    created_date: str = datetime.now().isoformat()
    modified_date: str = datetime.now().isoformat()

class LibraryManager:
    """Manages the user's music library."""
    
    def __init__(self, config: ConfigManager):
        self.config = config
        self.library_path = Path(config.get_setting("library.path", "library"))
        self.library_path.mkdir(parents=True, exist_ok=True)
        
        # Load library data
        self.tracks: Dict[str, Track] = {}
        self.playlists: Dict[str, Playlist] = {}
        self.load_library()
        
    def load_library(self):
        """Load library data from disk."""
        try:
            # Load tracks
            tracks_file = self.library_path / "tracks.json"
            if tracks_file.exists():
                with open(tracks_file, "r", encoding="utf-8") as f:
                    tracks_data = json.load(f)
                    self.tracks = {
                        id: Track(**data)
                        for id, data in tracks_data.items()
                    }
                    
            # Load playlists
            playlists_file = self.library_path / "playlists.json"
            if playlists_file.exists():
                with open(playlists_file, "r", encoding="utf-8") as f:
                    playlists_data = json.load(f)
                    self.playlists = {
                        id: Playlist(**data)
                        for id, data in playlists_data.items()
                    }
                    
            logger.info(f"Loaded {len(self.tracks)} tracks and {len(self.playlists)} playlists")
            
        except Exception as e:
            logger.error(f"Failed to load library: {e}")
            
    def save_library(self):
        """Save library data to disk."""
        try:
            # Save tracks
            tracks_file = self.library_path / "tracks.json"
            with open(tracks_file, "w", encoding="utf-8") as f:
                json.dump(
                    {id: asdict(track) for id, track in self.tracks.items()},
                    f,
                    indent=2
                )
                
            # Save playlists
            playlists_file = self.library_path / "playlists.json"
            with open(playlists_file, "w", encoding="utf-8") as f:
                json.dump(
                    {id: asdict(playlist) for id, playlist in self.playlists.items()},
                    f,
                    indent=2
                )
                
            logger.info("Library saved successfully")
            
        except Exception as e:
            logger.error(f"Failed to save library: {e}")
            
    def add_track(self, track_data: Dict, file_path: str) -> Optional[Track]:
        """Add a track to the library."""
        try:
            # Extract metadata from file
            audio = mutagen.File(file_path, easy=True)
            if audio is None:
                logger.error(f"Could not read metadata from {file_path}")
                return None
                
            # Create track object
            track = Track(
                id=str(track_data.get("id")),
                title=audio.get("title", [track_data.get("title", "Unknown")])[0],
                artist=audio.get("artist", [track_data.get("artist", {}).get("name", "Unknown")])[0],
                album=audio.get("album", [track_data.get("album", {}).get("title", "Unknown")])[0],
                duration=int(track_data.get("duration", 0)),
                path=str(file_path),
                artwork_path=None  # Will be set when artwork is downloaded
            )
            
            self.tracks[track.id] = track
            self.save_library()
            logger.info(f"Added track: {track.title} by {track.artist}")
            return track
            
        except Exception as e:
            logger.error(f"Failed to add track: {e}")
            return None
            
    def remove_track(self, track_id: str) -> bool:
        """Remove a track from the library."""
        try:
            if track_id in self.tracks:
                track = self.tracks[track_id]
                
                # Remove file
                if os.path.exists(track.path):
                    os.remove(track.path)
                    
                # Remove artwork if exists
                if track.artwork_path and os.path.exists(track.artwork_path):
                    os.remove(track.artwork_path)
                    
                # Remove from playlists
                for playlist in self.playlists.values():
                    if track_id in playlist.tracks:
                        playlist.tracks.remove(track_id)
                        
                # Remove from library
                del self.tracks[track_id]
                self.save_library()
                logger.info(f"Removed track: {track.title}")
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Failed to remove track: {e}")
            return False
            
    def create_playlist(self, name: str, description: str = "") -> Optional[Playlist]:
        """Create a new playlist."""
        try:
            playlist_id = str(len(self.playlists) + 1)  # Simple ID generation
            playlist = Playlist(
                id=playlist_id,
                name=name,
                description=description,
                tracks=[]
            )
            
            self.playlists[playlist_id] = playlist
            self.save_library()
            logger.info(f"Created playlist: {name}")
            return playlist
            
        except Exception as e:
            logger.error(f"Failed to create playlist: {e}")
            return None
            
    def add_to_playlist(self, playlist_id: str, track_id: str) -> bool:
        """Add a track to a playlist."""
        try:
            if playlist_id in self.playlists and track_id in self.tracks:
                playlist = self.playlists[playlist_id]
                if track_id not in playlist.tracks:
                    playlist.tracks.append(track_id)
                    playlist.modified_date = datetime.now().isoformat()
                    self.save_library()
                    logger.info(f"Added track to playlist: {playlist.name}")
                    return True
            return False
            
        except Exception as e:
            logger.error(f"Failed to add track to playlist: {e}")
            return False
            
    def remove_from_playlist(self, playlist_id: str, track_id: str) -> bool:
        """Remove a track from a playlist."""
        try:
            if playlist_id in self.playlists:
                playlist = self.playlists[playlist_id]
                if track_id in playlist.tracks:
                    playlist.tracks.remove(track_id)
                    playlist.modified_date = datetime.now().isoformat()
                    self.save_library()
                    logger.info(f"Removed track from playlist: {playlist.name}")
                    return True
            return False
            
        except Exception as e:
            logger.error(f"Failed to remove track from playlist: {e}")
            return False
            
    def delete_playlist(self, playlist_id: str) -> bool:
        """Delete a playlist."""
        try:
            if playlist_id in self.playlists:
                playlist = self.playlists[playlist_id]
                del self.playlists[playlist_id]
                self.save_library()
                logger.info(f"Deleted playlist: {playlist.name}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Failed to delete playlist: {e}")
            return False
            
    def update_play_count(self, track_id: str):
        """Update play count for a track."""
        try:
            if track_id in self.tracks:
                track = self.tracks[track_id]
                track.play_count += 1
                track.last_played = datetime.now().isoformat()
                self.save_library()
                logger.debug(f"Updated play count for: {track.title}")
                
        except Exception as e:
            logger.error(f"Failed to update play count: {e}")
            
    def get_recent_tracks(self, limit: int = 10) -> List[Track]:
        """Get recently played tracks."""
        try:
            return sorted(
                [t for t in self.tracks.values() if t.last_played],
                key=lambda t: t.last_played,
                reverse=True
            )[:limit]
            
        except Exception as e:
            logger.error(f"Failed to get recent tracks: {e}")
            return []
            
    def get_most_played(self, limit: int = 10) -> List[Track]:
        """Get most played tracks."""
        try:
            return sorted(
                self.tracks.values(),
                key=lambda t: t.play_count,
                reverse=True
            )[:limit]
            
        except Exception as e:
            logger.error(f"Failed to get most played tracks: {e}")
            return []
            
    def search_library(self, query: str) -> Dict[str, List]:
        """Search the library for tracks, albums, and artists."""
        try:
            query = query.lower()
            results = {
                "tracks": [],
                "albums": set(),
                "artists": set()
            }
            
            for track in self.tracks.values():
                if (query in track.title.lower() or
                    query in track.artist.lower() or
                    query in track.album.lower()):
                    results["tracks"].append(track)
                    results["albums"].add(track.album)
                    results["artists"].add(track.artist)
                    
            # Convert sets to sorted lists
            results["albums"] = sorted(list(results["albums"]))
            results["artists"] = sorted(list(results["artists"]))
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to search library: {e}")
            return {"tracks": [], "albums": [], "artists": []} 