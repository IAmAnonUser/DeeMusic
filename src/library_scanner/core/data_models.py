"""
Data Models for DeeMusic Library Scanner
"""

from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path

@dataclass
class DeezerAlbum:
    """Represents an album from Deezer."""
    id: int
    title: str
    artist: str
    year: Optional[int] = None
    track_count: int = 0
    cover_url: Optional[str] = None
    
    def __str__(self):
        return f"{self.title} by {self.artist} ({self.year})"

@dataclass
class DeezerTrack:
    """Represents a track from Deezer."""
    id: int
    title: str
    artist: str
    album: str
    duration: int = 0
    track_number: int = 0
    
    def __str__(self):
        return f"{self.title} by {self.artist}"

@dataclass
class LocalAlbum:
    """Represents a local album in the user's library."""
    path: Path
    artist: str
    title: str
    year: Optional[int] = None
    track_count: int = 0
    
    def __str__(self):
        return f"{self.title} by {self.artist} (Local: {self.path})"

@dataclass
class LocalTrack:
    """Represents a local track in the user's library."""
    file_path: Path
    title: str
    artist: str
    album: str
    track_number: int = 0
    duration: int = 0
    
    def __str__(self):
        return f"{self.title} by {self.artist} ({self.file_path.name})"

@dataclass
class MissingTrack:
    """Represents a track that's missing from the local library."""
    deezer_track: DeezerTrack
    local_album: Optional[LocalAlbum] = None
    
    def __str__(self):
        return f"Missing: {self.deezer_track}"

@dataclass
class MissingAlbum:
    """Represents an album that's missing from the local library."""
    deezer_album: DeezerAlbum
    local_album: Optional[LocalAlbum] = None
    missing_tracks: List[MissingTrack] = None
    
    def __post_init__(self):
        if self.missing_tracks is None:
            self.missing_tracks = []
    
    def __str__(self):
        return f"Missing: {self.deezer_album} ({len(self.missing_tracks)} tracks)"