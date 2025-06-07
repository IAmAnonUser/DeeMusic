"""Library synchronization service for DeeMusic."""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete

from ..models.database import (
    User, Track, Album, Playlist, Favorite, SyncHistory,
    Base
)
from ..deezer_api import (
    DeezerAPI, DeezerTrack, DeezerAlbum, DeezerPlaylist, DeezerUser
)

class SyncStatus:
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"

class LibrarySyncService:
    """Service for synchronizing user's Deezer library with local database."""
    
    def __init__(self, api: DeezerAPI, session: AsyncSession):
        self.api = api
        self.session = session
        self._current_sync: Optional[SyncHistory] = None
        
    async def initialize(self):
        """Initialize the sync service."""
        # Create tables if they don't exist
        async with self.session.begin():
            await self.session.run_sync(Base.metadata.create_all)
    
    async def sync_library(self, full_sync: bool = False) -> bool:
        """Synchronize the user's library.
        
        Args:
            full_sync: Whether to perform a full sync or incremental sync
        
        Returns:
            bool: True if sync was successful
        """
        try:
            # Start sync session
            self._current_sync = SyncHistory(
                sync_type="full" if full_sync else "incremental",
                start_time=datetime.utcnow(),
                status=SyncStatus.IN_PROGRESS
            )
            self.session.add(self._current_sync)
            await self.session.commit()
            
            # Get user info
            user_info = await self.api.get_user_info()
            if not user_info:
                raise Exception("Failed to get user info")
            
            # Sync user
            user = await self._sync_user(user_info)
            
            # Sync library components
            await asyncio.gather(
                self._sync_playlists(user),
                self._sync_favorites(user),
                self._sync_albums()
            )
            
            # Update sync status
            self._current_sync.status = SyncStatus.SUCCESS
            self._current_sync.end_time = datetime.utcnow()
            await self.session.commit()
            
            logging.info(f"Library sync completed successfully: added={self._current_sync.tracks_added}, "
                        f"updated={self._current_sync.tracks_updated}, removed={self._current_sync.tracks_removed}")
            return True
            
        except Exception as e:
            if self._current_sync:
                self._current_sync.status = SyncStatus.FAILED
                self._current_sync.error = str(e)
                self._current_sync.end_time = datetime.utcnow()
                await self.session.commit()
            logging.error(f"Library sync failed: {str(e)}")
            return False
    
    async def _sync_user(self, user_info: DeezerUser) -> User:
        """Sync user information."""
        stmt = select(User).where(User.deezer_id == user_info.id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            # Update existing user
            user.name = user_info.name
            user.email = user_info.email
            user.country = user_info.country
            user.last_sync = datetime.utcnow()
        else:
            # Create new user
            user = User(
                deezer_id=user_info.id,
                name=user_info.name,
                email=user_info.email,
                country=user_info.country
            )
            self.session.add(user)
        
        await self.session.commit()
        return user
    
    async def _sync_playlists(self, user: User):
        """Sync user's playlists."""
        # Get playlists from Deezer
        deezer_playlists = await self.api.get_user_playlists()
        
        # Get existing playlists
        stmt = select(Playlist).where(Playlist.user_id == user.id)
        result = await self.session.execute(stmt)
        existing_playlists = {p.deezer_id: p for p in result.scalars().all()}
        
        for dz_playlist in deezer_playlists:
            playlist = existing_playlists.get(dz_playlist.id)
            
            if playlist:
                # Update existing playlist
                playlist.title = dz_playlist.title
                playlist.description = dz_playlist.description
                playlist.is_public = dz_playlist.is_public
            else:
                # Create new playlist
                playlist = Playlist(
                    deezer_id=dz_playlist.id,
                    title=dz_playlist.title,
                    description=dz_playlist.description,
                    is_public=dz_playlist.is_public,
                    user_id=user.id
                )
                self.session.add(playlist)
            
            # Sync playlist tracks
            await self._sync_playlist_tracks(playlist)
        
        # Remove deleted playlists
        deezer_playlist_ids = {p.id for p in deezer_playlists}
        for playlist_id, playlist in existing_playlists.items():
            if playlist_id not in deezer_playlist_ids:
                await self.session.delete(playlist)
        
        await self.session.commit()
    
    async def _sync_playlist_tracks(self, playlist: Playlist):
        """Sync tracks in a playlist."""
        # Get tracks from Deezer
        deezer_tracks = await self.api.get_playlist_tracks(playlist.deezer_id)
        
        # Get or create tracks
        tracks = []
        for dz_track in deezer_tracks:
            track = await self._get_or_create_track(dz_track)
            if track:
                tracks.append(track)
        
        # Update playlist tracks
        playlist.tracks = tracks
        await self.session.commit()
    
    async def _sync_favorites(self, user: User):
        """Sync user's favorite tracks."""
        # Get favorites from Deezer
        deezer_tracks = await self.api.get_user_favorite_tracks()
        
        # Get existing favorites
        stmt = select(Favorite).where(Favorite.user_id == user.id)
        result = await self.session.execute(stmt)
        existing_favorites = {f.track.deezer_id: f for f in result.scalars().all()}
        
        for dz_track in deezer_tracks:
            track = await self._get_or_create_track(dz_track)
            if not track:
                continue
                
            if track.deezer_id not in existing_favorites:
                # Create new favorite
                favorite = Favorite(user_id=user.id, track_id=track.id)
                self.session.add(favorite)
                if self._current_sync:
                    self._current_sync.tracks_added += 1
        
        # Remove unfavorited tracks
        deezer_track_ids = {t.id for t in deezer_tracks}
        for track_id, favorite in existing_favorites.items():
            if track_id not in deezer_track_ids:
                await self.session.delete(favorite)
                if self._current_sync:
                    self._current_sync.tracks_removed += 1
        
        await self.session.commit()
    
    async def _sync_albums(self):
        """Sync user's albums."""
        # Get albums from Deezer
        deezer_albums = await self.api.get_user_albums()
        
        # Get existing albums
        stmt = select(Album)
        result = await self.session.execute(stmt)
        existing_albums = {a.deezer_id: a for a in result.scalars().all()}
        
        for dz_album in deezer_albums:
            album = existing_albums.get(dz_album.id)
            
            if album:
                # Update existing album
                album.title = dz_album.title
                album.artist = dz_album.artist
                album.release_date = dz_album.release_date
                album.total_tracks = dz_album.total_tracks
                album.duration = dz_album.duration
                album.genre = dz_album.genre
                album.label = dz_album.label
                album.cover_url = dz_album.cover_url
                if self._current_sync:
                    self._current_sync.tracks_updated += 1
            else:
                # Create new album
                album = Album(
                    deezer_id=dz_album.id,
                    title=dz_album.title,
                    artist=dz_album.artist,
                    release_date=dz_album.release_date,
                    total_tracks=dz_album.total_tracks,
                    duration=dz_album.duration,
                    genre=dz_album.genre,
                    label=dz_album.label,
                    cover_url=dz_album.cover_url
                )
                self.session.add(album)
                if self._current_sync:
                    self._current_sync.tracks_added += 1
            
            # Sync album tracks
            await self._sync_album_tracks(album)
        
        await self.session.commit()
    
    async def _sync_album_tracks(self, album: Album):
        """Sync tracks in an album."""
        # Get tracks from Deezer
        deezer_tracks = await self.api.get_album_tracks(album.deezer_id)
        
        # Get or create tracks
        tracks = []
        for dz_track in deezer_tracks:
            track = await self._get_or_create_track(dz_track)
            if track:
                tracks.append(track)
        
        # Update album tracks
        album.tracks = tracks
        await self.session.commit()
    
    async def _get_or_create_track(self, dz_track: DeezerTrack) -> Optional[Track]:
        """Get existing track or create a new one."""
        stmt = select(Track).where(Track.deezer_id == dz_track.id)
        result = await self.session.execute(stmt)
        track = result.scalar_one_or_none()
        
        if track:
            # Update existing track
            track.title = dz_track.title
            track.artist = dz_track.artist
            track.album = dz_track.album
            track.duration = dz_track.duration
            track.track_position = dz_track.track_position
            track.disk_number = dz_track.disk_number
            track.release_date = dz_track.release_date
            track.isrc = dz_track.isrc
            track.explicit_lyrics = dz_track.explicit_lyrics
            track.preview_url = dz_track.preview_url
            if self._current_sync:
                self._current_sync.tracks_updated += 1
        else:
            # Create new track
            track = Track(
                deezer_id=dz_track.id,
                title=dz_track.title,
                artist=dz_track.artist,
                album=dz_track.album,
                duration=dz_track.duration,
                track_position=dz_track.track_position,
                disk_number=dz_track.disk_number,
                release_date=dz_track.release_date,
                isrc=dz_track.isrc,
                explicit_lyrics=dz_track.explicit_lyrics,
                preview_url=dz_track.preview_url
            )
            self.session.add(track)
            if self._current_sync:
                self._current_sync.tracks_added += 1
        
        return track 