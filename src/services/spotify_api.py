"""Service for interacting with Spotify API and parsing playlist URLs."""

import logging
import re
import requests
from typing import Dict, List, Optional, Tuple
from config_manager import ConfigManager

try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
    SPOTIPY_AVAILABLE = True
except ImportError:
    SPOTIPY_AVAILABLE = False
    spotipy = None
    SpotifyClientCredentials = None

logger = logging.getLogger(__name__)

class SpotifyAPI:
    """Service for interacting with Spotify API and parsing playlist URLs."""
    
    def __init__(self, config: ConfigManager):
        """Initialize the SpotifyAPI service."""
        self.config = config
        self.spotify_client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Spotify client with credentials if available."""
        if not SPOTIPY_AVAILABLE:
            logger.error("Spotipy library not available. Please install with: pip install spotipy>=2.22.1")
            self.spotify_client = None
            return
            
        try:
            client_id = self.config.get_setting('spotify.client_id', '')
            client_secret = self.config.get_setting('spotify.client_secret', '')
            
            if client_id and client_secret:
                client_credentials_manager = SpotifyClientCredentials(
                    client_id=client_id,
                    client_secret=client_secret
                )
                self.spotify_client = spotipy.Spotify(
                    client_credentials_manager=client_credentials_manager
                )
                logger.info("Spotify API client initialized successfully")
            else:
                logger.warning("Spotify API credentials not configured. Playlist parsing will use fallback method.")
                self.spotify_client = None
                
        except Exception as e:
            logger.error(f"Failed to initialize Spotify client: {e}")
            self.spotify_client = None
    
    def reinitialize_client(self):
        """Reinitialize the Spotify client with updated credentials."""
        logger.info("Reinitializing Spotify API client with updated credentials")
        self._initialize_client()
    
    def is_spotify_playlist_url(self, url: str) -> bool:
        """Check if the given URL is a Spotify playlist URL.
        
        Args:
            url (str): The URL to check
            
        Returns:
            bool: True if it's a Spotify playlist URL, False otherwise
        """
        spotify_playlist_patterns = [
            r'https?://open\.spotify\.com/playlist/([a-zA-Z0-9]+)',
            r'https?://spotify\.com/playlist/([a-zA-Z0-9]+)',
            r'spotify:playlist:([a-zA-Z0-9]+)'
        ]
        
        for pattern in spotify_playlist_patterns:
            if re.match(pattern, url.strip()):
                return True
        return False
    
    def extract_playlist_id(self, url: str) -> Optional[str]:
        """Extract playlist ID from Spotify URL.
        
        Args:
            url (str): Spotify playlist URL
            
        Returns:
            Optional[str]: Playlist ID or None if not found
        """
        patterns = [
            r'https?://open\.spotify\.com/playlist/([a-zA-Z0-9]+)',
            r'https?://spotify\.com/playlist/([a-zA-Z0-9]+)',
            r'spotify:playlist:([a-zA-Z0-9]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url.strip())
            if match:
                return match.group(1)
        return None
    
    def get_playlist_tracks_api(self, playlist_id: str) -> Optional[List[Dict]]:
        """Get playlist tracks using Spotify API.
        
        Args:
            playlist_id (str): Spotify playlist ID
            
        Returns:
            Optional[List[Dict]]: List of track information or None if failed
        """
        if not self.spotify_client:
            logger.error("Spotify client not initialized")
            return None
            
        try:
            # Get playlist information
            playlist = self.spotify_client.playlist(playlist_id)
            playlist_name = playlist.get('name', 'Unknown Playlist')
            playlist_owner = playlist.get('owner', {}).get('display_name', 'Unknown')
            
            logger.info(f"Fetching tracks from Spotify playlist: '{playlist_name}' by {playlist_owner}")
            
            tracks = []
            results = self.spotify_client.playlist_tracks(playlist_id)
            
            while results:
                for item in results['items']:
                    track = item.get('track')
                    if track and track.get('type') == 'track':
                        # Extract track information
                        track_info = {
                            'name': track.get('name', ''),
                            'artist': ', '.join([artist.get('name', '') for artist in track.get('artists', [])]),
                            'album': track.get('album', {}).get('name', ''),
                            'duration_ms': track.get('duration_ms', 0),
                            'popularity': track.get('popularity', 0),
                            'explicit': track.get('explicit', False),
                            'spotify_id': track.get('id', ''),
                            'spotify_url': track.get('external_urls', {}).get('spotify', ''),
                            'isrc': track.get('external_ids', {}).get('isrc', ''),
                            'preview_url': track.get('preview_url', '')
                        }
                        tracks.append(track_info)
                
                # Get next batch if available
                results = self.spotify_client.next(results) if results['next'] else None
            
            logger.info(f"Successfully extracted {len(tracks)} tracks from Spotify playlist")
            return tracks
            
        except Exception as e:
            logger.error(f"Failed to get playlist tracks from Spotify API: {e}")
            return None
    
    def get_playlist_tracks_fallback(self, playlist_id: str) -> Optional[List[Dict]]:
        """Get playlist tracks using web scraping fallback method.
        
        Args:
            playlist_id (str): Spotify playlist ID
            
        Returns:
            Optional[List[Dict]]: List of track information or None if failed
        """
        logger.info("Attempting to extract playlist tracks using fallback method")
        
        try:
            # This is a simplified fallback - in a real implementation, you might use:
            # 1. Web scraping with BeautifulSoup
            # 2. yt-dlp which has some Spotify support
            # 3. Third-party APIs that don't require authentication
            
            # For now, return None to indicate fallback failed
            # Users will need to set up Spotify API credentials
            logger.warning("Fallback method not implemented. Please configure Spotify API credentials.")
            return None
            
        except Exception as e:
            logger.error(f"Fallback method failed: {e}")
            return None
    
    def get_playlist_tracks(self, url: str) -> Optional[Tuple[List[Dict], Dict]]:
        """Get all tracks from a Spotify playlist URL.
        
        Args:
            url (str): Spotify playlist URL
            
        Returns:
            Optional[Tuple[List[Dict], Dict]]: Tuple of (tracks list, playlist info) or None if failed
        """
        if not self.is_spotify_playlist_url(url):
            logger.error(f"Invalid Spotify playlist URL: {url}")
            return None
        
        playlist_id = self.extract_playlist_id(url)
        if not playlist_id:
            logger.error(f"Could not extract playlist ID from URL: {url}")
            return None
        
        logger.info(f"Extracting tracks from Spotify playlist ID: {playlist_id}")
        
        # Try API method first
        tracks = self.get_playlist_tracks_api(playlist_id)
        
        if tracks is None:
            # Fall back to alternative method if API fails
            tracks = self.get_playlist_tracks_fallback(playlist_id)
        
        if tracks is None:
            logger.error("Failed to extract tracks using all available methods")
            return None
        
        # Get playlist metadata if we have API access
        playlist_info = {}
        if self.spotify_client:
            try:
                playlist = self.spotify_client.playlist(playlist_id)
                playlist_info = {
                    'name': playlist.get('name', 'Unknown Playlist'),
                    'description': playlist.get('description', ''),
                    'owner': playlist.get('owner', {}).get('display_name', 'Unknown'),
                    'total_tracks': playlist.get('tracks', {}).get('total', len(tracks)),
                    'spotify_url': playlist.get('external_urls', {}).get('spotify', url),
                    'image_url': playlist.get('images', [{}])[0].get('url', '') if playlist.get('images') else ''
                }
            except Exception as e:
                logger.warning(f"Could not get playlist metadata: {e}")
                playlist_info = {
                    'name': f'Spotify Playlist ({playlist_id})',
                    'total_tracks': len(tracks)
                }
        else:
            playlist_info = {
                'name': f'Spotify Playlist ({playlist_id})', 
                'total_tracks': len(tracks)
            }
        
        return tracks, playlist_info
    
    def get_playlist_tracks_sync(self, url: str) -> Optional[Dict]:
        """Synchronous version of get_playlist_tracks for worker threads.
        
        Args:
            url (str): Spotify playlist URL
            
        Returns:
            Optional[Dict]: {'tracks': tracks_list, 'playlist_info': playlist_info} or None if failed
        """
        try:
            result = self.get_playlist_tracks(url)
            if result:
                tracks, playlist_info = result
                return {
                    'tracks': tracks,
                    'playlist_info': playlist_info
                }
            return None
        except Exception as e:
            logger.error(f"Error in synchronous playlist extraction: {e}")
            return None
    
    def format_search_query(self, track: Dict) -> str:
        """Format a track for Deezer search.
        
        Args:
            track (Dict): Track information from Spotify
            
        Returns:
            str: Formatted search query for Deezer
        """
        # Create search query with artist and track name
        query_parts = []
        
        if track.get('artist'):
            query_parts.append(track['artist'])
        
        if track.get('name'):
            query_parts.append(track['name'])
        
        # Join with space and clean up
        query = ' '.join(query_parts).strip()
        
        # Remove special characters that might interfere with search
        query = re.sub(r'[^\w\s\-\'\"&]', ' ', query)
        query = re.sub(r'\s+', ' ', query).strip()
        
        return query 