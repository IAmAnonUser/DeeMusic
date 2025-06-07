"""Queue manager for music playback management."""

from typing import List, Dict, Optional, Callable, Any
from dataclasses import dataclass
from enum import Enum
import random
import logging

logger = logging.getLogger(__name__)

@dataclass
class Track:
    """Data class representing a track."""
    id: str
    title: str
    artist: str
    album: str
    duration: int  # In seconds
    url: str
    album_art: str = ""
    artist_id: str = ""
    album_id: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert track to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "duration": self.duration,
            "url": self.url,
            "album_art": self.album_art,
            "artist_id": self.artist_id,
            "album_id": self.album_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Track':
        """Create Track from dictionary."""
        return cls(
            id=data.get("id", ""),
            title=data.get("title", "Unknown"),
            artist=data.get("artist", "Unknown Artist"),
            album=data.get("album", "Unknown Album"),
            duration=data.get("duration", 0),
            url=data.get("url", ""),
            album_art=data.get("album_art", ""),
            artist_id=data.get("artist_id", ""),
            album_id=data.get("album_id", "")
        )

class PlaybackMode(Enum):
    """Playback modes for the queue."""
    NORMAL = 0
    REPEAT_ALL = 1
    REPEAT_ONE = 2
    SHUFFLE = 3

class QueueManager:
    """Manages the playback queue."""
    
    def __init__(self):
        """Initialize the QueueManager."""
        self.queue: List[Track] = []
        self.history: List[Track] = []
        self.current_index: int = -1
        self.playback_mode: PlaybackMode = PlaybackMode.NORMAL
        self.on_queue_changed: Optional[Callable[[], None]] = None
        self.on_current_track_changed: Optional[Callable[[Optional[Track]], None]] = None
        
    def add_track(self, track: Track) -> None:
        """Add a track to the queue."""
        self.queue.append(track)
        if self.on_queue_changed:
            self.on_queue_changed()
            
    def add_tracks(self, tracks: List[Track]) -> None:
        """Add multiple tracks to the queue."""
        self.queue.extend(tracks)
        if self.on_queue_changed:
            self.on_queue_changed()
            
    def clear_queue(self) -> None:
        """Clear the queue."""
        self.queue.clear()
        self.current_index = -1
        if self.on_queue_changed:
            self.on_queue_changed()
        if self.on_current_track_changed:
            self.on_current_track_changed(None)
            
    def remove_track(self, index: int) -> None:
        """Remove a track from the queue."""
        if 0 <= index < len(self.queue):
            # Adjust current_index if needed
            if index < self.current_index:
                self.current_index -= 1
            elif index == self.current_index:
                # Currently playing track is being removed
                self.queue.pop(index)
                if self.current_index >= len(self.queue):
                    self.current_index = len(self.queue) - 1
                if self.on_current_track_changed:
                    self.on_current_track_changed(self.get_current_track())
                if self.on_queue_changed:
                    self.on_queue_changed()
                return
                
            self.queue.pop(index)
            if self.on_queue_changed:
                self.on_queue_changed()
                
    def move_track(self, from_index: int, to_index: int) -> None:
        """Move a track within the queue."""
        if 0 <= from_index < len(self.queue) and 0 <= to_index < len(self.queue):
            track = self.queue.pop(from_index)
            self.queue.insert(to_index, track)
            
            # Update current_index if needed
            if self.current_index == from_index:
                self.current_index = to_index
            elif from_index < self.current_index <= to_index:
                self.current_index -= 1
            elif to_index <= self.current_index < from_index:
                self.current_index += 1
                
            if self.on_queue_changed:
                self.on_queue_changed()
                
    def get_queue(self) -> List[Track]:
        """Get the current queue."""
        return self.queue
        
    def get_current_track(self) -> Optional[Track]:
        """Get the current track."""
        if 0 <= self.current_index < len(self.queue):
            return self.queue[self.current_index]
        return None
        
    def get_current_index(self) -> int:
        """Get the current track index."""
        return self.current_index
        
    def set_current_index(self, index: int) -> None:
        """Set the current track index."""
        if 0 <= index < len(self.queue):
            old_index = self.current_index
            self.current_index = index
            if old_index != index and self.on_current_track_changed:
                self.on_current_track_changed(self.get_current_track())
                
    def next_track(self) -> Optional[Track]:
        """Move to the next track based on playback mode."""
        if not self.queue:
            return None
            
        if self.playback_mode == PlaybackMode.REPEAT_ONE:
            # Stay on the same track
            if self.on_current_track_changed:
                self.on_current_track_changed(self.get_current_track())
            return self.get_current_track()
            
        if self.playback_mode == PlaybackMode.SHUFFLE:
            # Get a random track (not the current one)
            if len(self.queue) > 1:
                available_indices = [i for i in range(len(self.queue)) if i != self.current_index]
                self.current_index = random.choice(available_indices)
            else:
                self.current_index = 0
        else:
            # Normal or repeat all mode
            self.current_index += 1
            if self.current_index >= len(self.queue):
                if self.playback_mode == PlaybackMode.REPEAT_ALL:
                    self.current_index = 0
                else:
                    self.current_index = len(self.queue) - 1
                    return None  # End of queue in normal mode
                    
        if self.on_current_track_changed:
            self.on_current_track_changed(self.get_current_track())
        return self.get_current_track()
        
    def previous_track(self) -> Optional[Track]:
        """Move to the previous track."""
        if not self.queue:
            return None
            
        if self.playback_mode == PlaybackMode.REPEAT_ONE:
            # Stay on the same track
            if self.on_current_track_changed:
                self.on_current_track_changed(self.get_current_track())
            return self.get_current_track()
            
        if self.playback_mode == PlaybackMode.SHUFFLE:
            # Get a random track (not the current one)
            if len(self.queue) > 1:
                available_indices = [i for i in range(len(self.queue)) if i != self.current_index]
                self.current_index = random.choice(available_indices)
            else:
                self.current_index = 0
        else:
            # Normal or repeat all mode
            self.current_index -= 1
            if self.current_index < 0:
                if self.playback_mode == PlaybackMode.REPEAT_ALL:
                    self.current_index = len(self.queue) - 1
                else:
                    self.current_index = 0
                    
        if self.on_current_track_changed:
            self.on_current_track_changed(self.get_current_track())
        return self.get_current_track()
        
    def set_playback_mode(self, mode: PlaybackMode) -> None:
        """Set the playback mode."""
        self.playback_mode = mode
        
    def get_playback_mode(self) -> PlaybackMode:
        """Get the current playback mode."""
        return self.playback_mode
        
    def shuffle_queue(self) -> None:
        """Shuffle the queue (except current track)."""
        if len(self.queue) <= 1:
            return
            
        current_track = self.get_current_track()
        
        # Remove current track
        if current_track:
            self.queue.pop(self.current_index)
            
        # Shuffle remaining tracks
        random.shuffle(self.queue)
        
        # Re-insert current track at the beginning
        if current_track:
            self.queue.insert(0, current_track)
            self.current_index = 0
            
        if self.on_queue_changed:
            self.on_queue_changed() 

class DummyQueueManager:
    """Dummy QueueManager that does nothing, for when play feature is disabled."""
    def __init__(self, music_player_service = None): # music_player_service might be DummyMusicPlayer
        self.queue: List[Track] = []
        self.current_index: int = -1
        self.playback_mode: PlaybackMode = PlaybackMode.NORMAL
        logger.info("DummyQueueManager initialized.")

    def add_track(self, track: Track) -> None:
        logger.debug(f"DummyQueueManager: add_track called with {track.title if track else 'None'}")
        pass
            
    def add_tracks(self, tracks: List[Track]) -> None:
        logger.debug(f"DummyQueueManager: add_tracks called with {len(tracks) if tracks else 0} tracks")
        pass
            
    def clear_queue(self) -> None:
        logger.debug("DummyQueueManager: clear_queue called")
        self.queue.clear()
        self.current_index = -1
            
    def remove_track(self, index: int) -> None:
        logger.debug(f"DummyQueueManager: remove_track called for index {index}")
        pass
                
    def move_track(self, from_index: int, to_index: int) -> None:
        logger.debug(f"DummyQueueManager: move_track called from {from_index} to {to_index}")
        pass
                
    def get_queue(self) -> List[Track]:
        return []
        
    def get_current_track(self) -> Optional[Track]:
        return None
        
    def get_current_index(self) -> int:
        return -1
        
    def set_current_index(self, index: int) -> None:
        logger.debug(f"DummyQueueManager: set_current_index called with {index}")
        pass
                
    def next_track(self) -> Optional[Track]:
        logger.debug("DummyQueueManager: next_track called")
        return None
        
    def previous_track(self) -> Optional[Track]:
        logger.debug("DummyQueueManager: previous_track called")
        return None
        
    def set_playback_mode(self, mode: PlaybackMode) -> None:
        logger.debug(f"DummyQueueManager: set_playback_mode called with {mode}")
        self.playback_mode = mode
        
    def get_playback_mode(self) -> PlaybackMode:
        return self.playback_mode
        
    def shuffle_queue(self) -> None:
        logger.debug("DummyQueueManager: shuffle_queue called")
        pass

    # Add any other methods from the real QueueManager that PlayerControls might try to call
    # For example, from connect_signals in MainWindow:
    def toggle_play_pause(self):
        logger.debug("DummyQueueManager: toggle_play_pause called")
        pass

    def seek_to_position(self, position_ms: int):
        logger.debug(f"DummyQueueManager: seek_to_position called with {position_ms}")
        pass

    def set_volume(self, volume_float: float):
        logger.debug(f"DummyQueueManager: set_volume called with {volume_float}")
        pass

    def toggle_shuffle(self, shuffle_on: bool):
        logger.debug(f"DummyQueueManager: toggle_shuffle called with {shuffle_on}")
        pass

    def toggle_repeat_mode(self, repeat_mode_enum_or_int):
        logger.debug(f"DummyQueueManager: toggle_repeat_mode called with {repeat_mode_enum_or_int}")
        pass

    # Methods that MusicPlayer signals might connect to via QueueManager in MainWindow
    def handle_player_state_change(self, state):
        logger.debug(f"DummyQueueManager: handle_player_state_change called with {state}")
        pass

    def handle_player_position_change(self, position):
        logger.debug(f"DummyQueueManager: handle_player_position_change called with {position}")
        pass

    def handle_player_duration_change(self, duration):
        logger.debug(f"DummyQueueManager: handle_player_duration_change called with {duration}")
        pass

    def handle_track_finished(self):
        logger.debug("DummyQueueManager: handle_track_finished called")
        pass

# Example of how to use (for testing):
# if __name__ == '__main__':
#     qm = QueueManager()
#     track1 = Track(id='1', title='Song A', artist='Artist X', album='Album Y', duration=180, url='http://example.com/a.mp3')
#     track2 = Track(id='2', title='Song B', artist='Artist X', album='Album Y', duration=200, url='http://example.com/b.mp3')
    
#     qm.add_track(track1)
#     qm.add_track(track2)
    
#     print(qm.get_queue())
#     qm.set_current_index(0)
#     print(qm.get_current_track())
#     print(qm.next_track())
#     print(qm.previous_track()) 