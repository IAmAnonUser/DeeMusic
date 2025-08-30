"""
Core data models for the new download queue system.

This module defines immutable queue items and mutable state objects
that form the foundation of the reliable download system.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime
import json


class DownloadState(Enum):
    """States a download item can be in"""
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class ItemType(Enum):
    """Types of downloadable items"""
    ALBUM = "album"
    PLAYLIST = "playlist"
    TRACK = "track"


@dataclass(frozen=True)
class TrackInfo:
    """Immutable track information"""
    track_id: int
    title: str
    artist: str
    duration: int
    track_number: Optional[int] = None
    disc_number: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'track_id': self.track_id,
            'title': self.title,
            'artist': self.artist,
            'duration': self.duration,
            'track_number': self.track_number,
            'disc_number': self.disc_number
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TrackInfo':
        """Create from dictionary"""
        return cls(
            track_id=data['track_id'],
            title=data['title'],
            artist=data['artist'],
            duration=data['duration'],
            track_number=data.get('track_number'),
            disc_number=data.get('disc_number')
        )


@dataclass(frozen=True)
class QueueItem:
    """
    Immutable queue item representing a download unit (album/playlist/track).
    
    This is the core data structure that represents what the user wants to download.
    It's immutable to prevent corruption and make the system predictable.
    """
    id: str
    item_type: ItemType
    deezer_id: int  # Album/Playlist/Track ID from Deezer
    title: str
    artist: str
    total_tracks: int
    tracks: List[TrackInfo]
    created_at: datetime
    album_cover_url: Optional[str] = None
    
    def __post_init__(self):
        """Generate UUID if not provided"""
        if not self.id:
            object.__setattr__(self, 'id', str(uuid.uuid4()))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'id': self.id,
            'item_type': self.item_type.value,
            'deezer_id': self.deezer_id,
            'title': self.title,
            'artist': self.artist,
            'total_tracks': self.total_tracks,
            'tracks': [track.to_dict() for track in self.tracks],
            'created_at': self.created_at.isoformat(),
            'album_cover_url': self.album_cover_url
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueueItem':
        """Create from dictionary"""
        return cls(
            id=data['id'],
            item_type=ItemType(data['item_type']),
            deezer_id=data['deezer_id'],
            title=data['title'],
            artist=data['artist'],
            total_tracks=data['total_tracks'],
            tracks=[TrackInfo.from_dict(track) for track in data['tracks']],
            created_at=datetime.fromisoformat(data['created_at']),
            album_cover_url=data.get('album_cover_url')
        )
    
    @classmethod
    def create_album(cls, deezer_id: int, title: str, artist: str, 
                    tracks: List[TrackInfo], album_cover_url: str = None) -> 'QueueItem':
        """Factory method for creating album queue items"""
        return cls(
            id=str(uuid.uuid4()),
            item_type=ItemType.ALBUM,
            deezer_id=deezer_id,
            title=title,
            artist=artist,
            total_tracks=len(tracks),
            tracks=tracks,
            created_at=datetime.now(),
            album_cover_url=album_cover_url
        )
    
    @classmethod
    def create_track(cls, deezer_id: int, title: str, artist: str, 
                    track_info: TrackInfo) -> 'QueueItem':
        """Factory method for creating single track queue items"""
        return cls(
            id=str(uuid.uuid4()),
            item_type=ItemType.TRACK,
            deezer_id=deezer_id,
            title=title,
            artist=artist,
            total_tracks=1,
            tracks=[track_info],
            created_at=datetime.now()
        )


@dataclass
class QueueItemState:
    """
    Mutable state for a queue item.
    
    This tracks the current status, progress, and any errors for a queue item.
    Separated from QueueItem to allow state changes while keeping core data immutable.
    """
    item_id: str
    state: DownloadState
    progress: float = 0.0  # 0.0 to 1.0
    completed_tracks: int = 0
    failed_tracks: int = 0
    error_message: Optional[str] = None
    updated_at: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    
    def update(self, **kwargs):
        """Update state fields and timestamp"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'item_id': self.item_id,
            'state': self.state.value,
            'progress': self.progress,
            'completed_tracks': self.completed_tracks,
            'failed_tracks': self.failed_tracks,
            'error_message': self.error_message,
            'updated_at': self.updated_at.isoformat(),
            'retry_count': self.retry_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueueItemState':
        """Create from dictionary"""
        return cls(
            item_id=data['item_id'],
            state=DownloadState(data['state']),
            progress=data['progress'],
            completed_tracks=data['completed_tracks'],
            failed_tracks=data['failed_tracks'],
            error_message=data.get('error_message'),
            updated_at=datetime.fromisoformat(data['updated_at']),
            retry_count=data.get('retry_count', 0)
        )
    
    @property
    def is_active(self) -> bool:
        """Check if item is currently being processed"""
        return self.state in [DownloadState.DOWNLOADING, DownloadState.QUEUED]
    
    @property
    def is_finished(self) -> bool:
        """Check if item is in a final state"""
        return self.state in [DownloadState.COMPLETED, DownloadState.FAILED, DownloadState.CANCELLED]
    
    @property
    def can_retry(self) -> bool:
        """Check if item can be retried"""
        return self.state == DownloadState.FAILED


@dataclass
class QueueSnapshot:
    """
    Immutable snapshot of the entire queue state.
    
    Used for persistence and atomic operations.
    """
    items: Dict[str, QueueItem]
    states: Dict[str, QueueItemState]
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'items': {k: v.to_dict() for k, v in self.items.items()},
            'states': {k: v.to_dict() for k, v in self.states.items()},
            'created_at': self.created_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueueSnapshot':
        """Create from dictionary"""
        return cls(
            items={k: QueueItem.from_dict(v) for k, v in data['items'].items()},
            states={k: QueueItemState.from_dict(v) for k, v in data['states'].items()},
            created_at=datetime.fromisoformat(data['created_at'])
        )
    
    def save_to_file(self, file_path: str):
        """Save snapshot to JSON file"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load_from_file(cls, file_path: str) -> Optional['QueueSnapshot']:
        """Load snapshot from JSON file"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.debug(f"Loaded queue data with {len(data.get('items', {}))} items")
            return cls.from_dict(data)
        except FileNotFoundError:
            logger.debug(f"Queue file not found: {file_path}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in queue file {file_path}: {e}")
            return None
        except KeyError as e:
            logger.error(f"Missing required key in queue file {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error loading queue file {file_path}: {e}", exc_info=True)
            return None


# Factory functions for common operations
def create_album_from_deezer_data(album_data: Dict[str, Any]) -> QueueItem:
    """Create a QueueItem from Deezer album API response"""
    tracks = []
    track_list = album_data.get('tracks', {}).get('data', [])
    
    # Check if we have the full track list or need to fetch more
    total_tracks_in_album = album_data.get('nb_tracks', len(track_list))
    tracks_in_response = len(track_list)
    
    import logging
    logger = logging.getLogger(__name__)
    
    if tracks_in_response < total_tracks_in_album:
        logger.warning(f"Album '{album_data.get('title', 'Unknown')}' has {total_tracks_in_album} tracks but only {tracks_in_response} were provided in the API response. Some tracks may be missing from the download.")
        logger.info(f"To fix this, the album fetching code should use pagination to get all tracks via get_album_tracks() method.")
    
    for index, track_data in enumerate(track_list, 1):
        # Use API track position if available, otherwise use enumerated position
        api_track_number = track_data.get('track_position') or track_data.get('track_number')
        track_number = api_track_number if api_track_number else index
        
        track_info = TrackInfo(
            track_id=track_data['id'],
            title=track_data['title'],
            artist=track_data['artist']['name'],
            duration=track_data['duration'],
            track_number=track_number,
            disc_number=track_data.get('disk_number') or track_data.get('disc_number') or 1
        )
        tracks.append(track_info)
    
    return QueueItem.create_album(
        deezer_id=album_data['id'],
        title=album_data['title'],
        artist=album_data['artist']['name'],
        tracks=tracks,
        album_cover_url=album_data.get('cover_xl')
    )


def create_track_from_deezer_data(track_data: Dict[str, Any]) -> QueueItem:
    """Create a QueueItem from Deezer track API response"""
    track_info = TrackInfo(
        track_id=track_data['id'],
        title=track_data['title'],
        artist=track_data['artist']['name'],
        duration=track_data['duration'],
        track_number=track_data.get('track_position') or track_data.get('track_number') or 1,
        disc_number=track_data.get('disk_number') or track_data.get('disc_number') or 1
    )
    
    return QueueItem.create_track(
        deezer_id=track_data['id'],
        title=track_data['title'],
        artist=track_data['artist']['name'],
        track_info=track_info
    )


async def create_album_from_deezer_data_complete(album_data: Dict[str, Any], deezer_api) -> QueueItem:
    """
    Create a QueueItem from Deezer album API response with complete track fetching.
    
    This function ensures all tracks are fetched for albums with many tracks by using
    pagination if necessary.
    
    Args:
        album_data: Basic album data from Deezer API
        deezer_api: DeezerAPI instance for fetching additional tracks
        
    Returns:
        QueueItem with all album tracks
    """
    import logging
    logger = logging.getLogger(__name__)
    
    tracks = []
    track_list = album_data.get('tracks', {}).get('data', [])
    total_tracks_in_album = album_data.get('nb_tracks', len(track_list))
    tracks_in_response = len(track_list)
    
    album_id = album_data['id']
    album_title = album_data.get('title', 'Unknown Album')
    
    logger.info(f"Creating album queue item for '{album_title}' - API reports {total_tracks_in_album} tracks, response contains {tracks_in_response} tracks")
    
    # If we have fewer tracks than expected, fetch all tracks using pagination
    if tracks_in_response < total_tracks_in_album and deezer_api:
        logger.info(f"Fetching complete track list for album '{album_title}' using pagination")
        try:
            # Fetch all tracks using pagination
            all_tracks = []
            index = 0
            limit = 100  # Fetch in batches of 100
            
            while len(all_tracks) < total_tracks_in_album:
                batch_tracks = await deezer_api.get_album_tracks(album_id, limit=limit, index=index)
                if not batch_tracks:
                    logger.warning(f"No more tracks returned for album '{album_title}' at index {index}")
                    break
                
                all_tracks.extend(batch_tracks)
                logger.debug(f"Fetched {len(batch_tracks)} tracks for album '{album_title}' (total: {len(all_tracks)})")
                
                # If we got fewer tracks than requested, we've reached the end
                if len(batch_tracks) < limit:
                    break
                    
                index += limit
            
            if len(all_tracks) > tracks_in_response:
                logger.info(f"Successfully fetched {len(all_tracks)} tracks for album '{album_title}' (was {tracks_in_response})")
                track_list = all_tracks
            else:
                logger.warning(f"Pagination didn't return more tracks for album '{album_title}' - using original {tracks_in_response} tracks")
                
        except Exception as e:
            logger.error(f"Error fetching complete track list for album '{album_title}': {e}")
            logger.info(f"Falling back to original {tracks_in_response} tracks")
    
    # Process all tracks
    for index, track_data in enumerate(track_list, 1):
        # Use API track position if available, otherwise use enumerated position
        api_track_number = track_data.get('track_position') or track_data.get('track_number')
        track_number = api_track_number if api_track_number else index
        
        track_info = TrackInfo(
            track_id=track_data['id'],
            title=track_data['title'],
            artist=track_data['artist']['name'],
            duration=track_data['duration'],
            track_number=track_number,
            disc_number=track_data.get('disk_number') or track_data.get('disc_number') or 1
        )
        tracks.append(track_info)
    
    logger.info(f"Created album queue item for '{album_title}' with {len(tracks)} tracks")
    
    return QueueItem.create_album(
        deezer_id=album_data['id'],
        title=album_data['title'],
        artist=album_data['artist']['name'],
        tracks=tracks,
        album_cover_url=album_data.get('cover_xl')
    )


def create_album_from_deezer_data_complete_sync(album_data: Dict[str, Any], deezer_api) -> QueueItem:
    """
    Synchronous version of create_album_from_deezer_data_complete.
    
    This function ensures all tracks are fetched for albums with many tracks by using
    pagination if necessary, but uses synchronous API calls to avoid async context issues.
    
    Args:
        album_data: Basic album data from Deezer API
        deezer_api: DeezerAPI instance for fetching additional tracks
        
    Returns:
        QueueItem with all album tracks
    """
    import logging
    logger = logging.getLogger(__name__)
    
    tracks = []
    track_list = album_data.get('tracks', {}).get('data', [])
    total_tracks_in_album = album_data.get('nb_tracks', len(track_list))
    tracks_in_response = len(track_list)
    
    album_id = album_data['id']
    album_title = album_data.get('title', 'Unknown Album')
    
    logger.info(f"Creating album queue item for '{album_title}' (sync) - API reports {total_tracks_in_album} tracks, response contains {tracks_in_response} tracks")
    
    # If we have fewer tracks than expected, fetch all tracks using pagination
    if tracks_in_response < total_tracks_in_album and deezer_api:
        logger.info(f"Fetching complete track list for album '{album_title}' using synchronous pagination")
        try:
            # Fetch all tracks using synchronous pagination
            all_tracks = []
            index = 0
            limit = 100  # Fetch in batches of 100
            
            while len(all_tracks) < total_tracks_in_album:
                batch_tracks = deezer_api.get_album_tracks_sync(album_id, limit=limit, index=index)
                if not batch_tracks:
                    logger.warning(f"No more tracks returned for album '{album_title}' at index {index}")
                    break
                
                all_tracks.extend(batch_tracks)
                logger.debug(f"Fetched {len(batch_tracks)} tracks for album '{album_title}' (total: {len(all_tracks)})")
                
                # If we got fewer tracks than requested, we've reached the end
                if len(batch_tracks) < limit:
                    break
                    
                index += limit
            
            if len(all_tracks) > tracks_in_response:
                logger.info(f"Successfully fetched {len(all_tracks)} tracks for album '{album_title}' (was {tracks_in_response})")
                track_list = all_tracks
            else:
                logger.warning(f"Synchronous pagination didn't return more tracks for album '{album_title}' - using original {tracks_in_response} tracks")
                
        except Exception as e:
            logger.error(f"Error fetching complete track list for album '{album_title}': {e}")
            logger.info(f"Falling back to original {tracks_in_response} tracks")
    
    # Process all tracks
    for index, track_data in enumerate(track_list, 1):
        # Use API track position if available, otherwise use enumerated position
        api_track_number = track_data.get('track_position') or track_data.get('track_number')
        track_number = api_track_number if api_track_number else index
        
        track_info = TrackInfo(
            track_id=track_data['id'],
            title=track_data['title'],
            artist=track_data['artist']['name'],
            duration=track_data['duration'],
            track_number=track_number,
            disc_number=track_data.get('disk_number') or track_data.get('disc_number') or 1
        )
        tracks.append(track_info)
    
    logger.info(f"Created album queue item for '{album_title}' (sync) with {len(tracks)} tracks")
    
    return QueueItem.create_album(
        deezer_id=album_data['id'],
        title=album_data['title'],
        artist=album_data['artist']['name'],
        tracks=tracks,
        album_cover_url=album_data.get('cover_xl')
    )