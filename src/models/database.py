"""Database models for DeeMusic."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Table
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

# Association tables for many-to-many relationships
playlist_tracks = Table(
    'playlist_tracks',
    Base.metadata,
    Column('playlist_id', Integer, ForeignKey('playlists.id'), primary_key=True),
    Column('track_id', Integer, ForeignKey('tracks.id'), primary_key=True)
)

album_tracks = Table(
    'album_tracks',
    Base.metadata,
    Column('album_id', Integer, ForeignKey('albums.id'), primary_key=True),
    Column('track_id', Integer, ForeignKey('tracks.id'), primary_key=True)
)

class User(Base):
    """User model for storing Deezer user information."""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    deezer_id = Column(String, unique=True, nullable=False)
    name = Column(String)
    email = Column(String)
    country = Column(String)
    last_sync = Column(DateTime, server_default=func.now())
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    playlists = relationship("Playlist", back_populates="user")
    favorites = relationship("Favorite", back_populates="user")

class Track(Base):
    """Track model for storing song information."""
    __tablename__ = 'tracks'

    id = Column(Integer, primary_key=True)
    deezer_id = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    artist = Column(String, nullable=False)
    album = Column(String, nullable=False)
    duration = Column(Integer)
    track_position = Column(Integer)
    disk_number = Column(Integer)
    release_date = Column(String)
    isrc = Column(String)
    explicit_lyrics = Column(Boolean, default=False)
    preview_url = Column(String)
    local_path = Column(String)
    download_status = Column(String)
    last_played = Column(DateTime)
    play_count = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    playlists = relationship("Playlist", secondary=playlist_tracks, back_populates="tracks")
    albums = relationship("Album", secondary=album_tracks, back_populates="tracks")
    favorites = relationship("Favorite", back_populates="track")

class Album(Base):
    """Album model for storing album information."""
    __tablename__ = 'albums'

    id = Column(Integer, primary_key=True)
    deezer_id = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    artist = Column(String, nullable=False)
    release_date = Column(String)
    total_tracks = Column(Integer)
    duration = Column(Integer)
    genre = Column(String)
    label = Column(String)
    cover_url = Column(String)
    cover_path = Column(String)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    tracks = relationship("Track", secondary=album_tracks, back_populates="albums")

class Playlist(Base):
    """Playlist model for storing playlist information."""
    __tablename__ = 'playlists'

    id = Column(Integer, primary_key=True)
    deezer_id = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String)
    is_public = Column(Boolean, default=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="playlists")
    tracks = relationship("Track", secondary=playlist_tracks, back_populates="playlists")

class Favorite(Base):
    """Favorite model for storing user's favorite tracks."""
    __tablename__ = 'favorites'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    track_id = Column(Integer, ForeignKey('tracks.id'))
    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="favorites")
    track = relationship("Track", back_populates="favorites")

class SyncHistory(Base):
    """Model for tracking synchronization history."""
    __tablename__ = 'sync_history'

    id = Column(Integer, primary_key=True)
    sync_type = Column(String, nullable=False)  # 'full' or 'incremental'
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime)
    status = Column(String)  # 'success', 'failed', 'in_progress'
    error = Column(String)
    tracks_added = Column(Integer, default=0)
    tracks_updated = Column(Integer, default=0)
    tracks_removed = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now()) 