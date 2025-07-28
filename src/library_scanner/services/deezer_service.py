"""
Deezer API Service
Handles all interactions with the Deezer API for searching and fetching music data
"""

import aiohttp
import asyncio
import hashlib
import json
from typing import Dict, List, Optional, Any
from urllib.parse import quote
import logging

logger = logging.getLogger(__name__)


class DeezerService:
    """Service for interacting with Deezer API"""
    
    def __init__(self, arl_token: Optional[str] = None):
        self.arl_token = arl_token
        self.session = None
        self.api_base = "https://api.deezer.com"
        self.private_api_base = "https://www.deezer.com/ajax/gw-light.php"
        self.api_token = None
        self.sid = None
        
    async def __aenter__(self):
        """Async context manager entry"""
        await self.initialize()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()
        
    async def initialize(self):
        """Initialize the session and authenticate if ARL token is provided"""
        self.session = aiohttp.ClientSession()
        if self.arl_token:
            await self._authenticate()
            
    async def close(self):
        """Close the session"""
        if self.session:
            await self.session.close()
            
    async def _authenticate(self):
        """Authenticate using ARL token"""
        try:
            # Set cookie
            self.session.cookie_jar.update_cookies({"arl": self.arl_token})
            
            # Get API token
            async with self.session.get(f"{self.private_api_base}?method=deezer.getUserData&api_version=1.0&api_token=") as resp:
                data = await resp.json()
                if data.get("results"):
                    self.api_token = data["results"].get("checkForm")
                    self.sid = data["results"].get("SESSION_ID")
                    logger.info("Successfully authenticated with Deezer")
                else:
                    logger.warning("Failed to authenticate with Deezer")
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            
    async def search_artist(self, artist_name: str) -> Optional[Dict[str, Any]]:
        """Search for an artist by name"""
        try:
            url = f"{self.api_base}/search/artist"
            params = {"q": artist_name, "limit": 10}
            
            async with self.session.get(url, params=params) as resp:
                data = await resp.json()
                if data.get("data"):
                    # Return the first/best match
                    return data["data"][0]
                return None
        except Exception as e:
            logger.error(f"Error searching artist {artist_name}: {e}")
            return None
            
    async def get_artist_albums(self, artist_id: int) -> List[Dict[str, Any]]:
        """Get all albums for an artist"""
        albums = []
        try:
            url = f"{self.api_base}/artist/{artist_id}/albums"
            params = {"limit": 100}
            
            while url:
                async with self.session.get(url, params=params if url == f"{self.api_base}/artist/{artist_id}/albums" else None) as resp:
                    data = await resp.json()
                    if data.get("data"):
                        albums.extend(data["data"])
                    
                    # Check for next page
                    url = data.get("next")
                    
            return albums
        except Exception as e:
            logger.error(f"Error getting albums for artist {artist_id}: {e}")
            return albums
            
    async def get_album_tracks(self, album_id: int) -> List[Dict[str, Any]]:
        """Get all tracks for an album"""
        tracks = []
        try:
            url = f"{self.api_base}/album/{album_id}/tracks"
            params = {"limit": 100}
            
            while url:
                async with self.session.get(url, params=params if url == f"{self.api_base}/album/{album_id}/tracks" else None) as resp:
                    data = await resp.json()
                    if data.get("data"):
                        tracks.extend(data["data"])
                    
                    # Check for next page
                    url = data.get("next")
                    
            return tracks
        except Exception as e:
            logger.error(f"Error getting tracks for album {album_id}: {e}")
            return tracks
            
    async def search_track(self, title: str, artist: str = "", album: str = "") -> Optional[Dict[str, Any]]:
        """Search for a specific track"""
        try:
            # Build search query
            query_parts = [f'track:"{title}"']
            if artist:
                query_parts.append(f'artist:"{artist}"')
            if album:
                query_parts.append(f'album:"{album}"')
                
            query = " ".join(query_parts)
            
            url = f"{self.api_base}/search/track"
            params = {"q": query, "limit": 10}
            
            async with self.session.get(url, params=params) as resp:
                data = await resp.json()
                if data.get("data"):
                    # Return the first/best match
                    return data["data"][0]
                return None
        except Exception as e:
            logger.error(f"Error searching track {title}: {e}")
            return None
            
    async def get_artist_discography(self, artist_name: str) -> Dict[str, Any]:
        """Get complete discography for an artist"""
        try:
            # First search for the artist
            artist = await self.search_artist(artist_name)
            if not artist:
                return {"artist": None, "albums": [], "tracks": []}
                
            # Get all albums
            albums = await self.get_artist_albums(artist["id"])
            
            # Get all tracks for each album
            all_tracks = []
            for album in albums:
                tracks = await self.get_album_tracks(album["id"])
                for track in tracks:
                    track["album_info"] = {
                        "id": album["id"],
                        "title": album["title"],
                        "cover": album.get("cover_medium"),
                        "release_date": album.get("release_date")
                    }
                all_tracks.extend(tracks)
                
            return {
                "artist": artist,
                "albums": albums,
                "tracks": all_tracks
            }
        except Exception as e:
            logger.error(f"Error getting discography for {artist_name}: {e}")
            return {"artist": None, "albums": [], "tracks": []}
            
    async def search_album(self, album_title: str, artist: str = "") -> Optional[Dict[str, Any]]:
        """Search for a specific album"""
        try:
            query = f'album:"{album_title}"'
            if artist:
                query += f' artist:"{artist}"'
                
            url = f"{self.api_base}/search/album"
            params = {"q": query, "limit": 10}
            
            async with self.session.get(url, params=params) as resp:
                data = await resp.json()
                if data.get("data"):
                    return data["data"][0]
                return None
        except Exception as e:
            logger.error(f"Error searching album {album_title}: {e}")
            return None 