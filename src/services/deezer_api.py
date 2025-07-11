"""Service for interacting with the Deezer API."""

import os
import logging
import json
import requests
import aiohttp
import asyncio
import time
from typing import Dict, List, Optional, Any
import deezer  # Import the deezer-python module correctly
from pathlib import Path
from yarl import URL
from src.config_manager import ConfigManager
import random

logger = logging.getLogger(__name__)

class DeezerAPI:
    """Service for interacting with the Deezer API."""
    
    # API Base URLs
    PUBLIC_API_BASE = "https://api.deezer.com"
    PRIVATE_API_BASE = "https://www.deezer.com/ajax/gw-light.php"
    
    # Cache settings
    CACHE_DIR = Path.home() / ".config" / "deemusic" / "cache"
    CACHE_DURATION = 86400  # 24 hours
    
    def __init__(self, config: ConfigManager, loop: asyncio.AbstractEventLoop = None):
        """Initialize the DeezerAPI service."""
        self.config = config
        # Store the passed loop, MUST exist for threadsafe calls
        self.loop = loop 
        if not self.loop:
            # This should ideally not happen if called correctly from MainWindow
            logger.warning("DeezerAPI initialized without an explicit event loop. Trying to get current.")
            try:
                self.loop = asyncio.get_event_loop()
            except RuntimeError:
                logger.error("Could not get event loop during DeezerAPI init!")
                # This is problematic, subsequent calls might fail
                self.loop = None 
                
        self.arl = config.get_setting('deezer.arl', '')
        self.session: Optional[aiohttp.ClientSession] = None
        self.initialized = False
        self.api_token = None
        self.csrf_token = None
        self.license_token: Optional[str] = None
        self.user_id = None
        self.user_info: Optional[Dict] = None
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._proxy_url: Optional[str] = None  # Store proxy URL for requests
        
    async def _ensure_session_and_tokens(self) -> bool:
        """Ensure that a valid session and API tokens are available."""
        session = await self._get_session()
        if not session:
            logger.error("Failed to get session in _ensure_session_and_tokens.")
            return False
        if not self.api_token or not self.csrf_token: # Or just self.user_id if that's a good proxy
            logger.debug("API token or CSRF token missing, attempting to fetch tokens.")
            if not await self._get_tokens():
                logger.error("Failed to get tokens in _ensure_session_and_tokens.")
                return False
        return True

    async def initialize(self) -> bool:
        """Initialize the API service (setting basic state)."""
        if self.initialized:
            return True
            
        try:
            # --- Remove session creation --- 
            
            # Mark as initialized, session and tokens will be created/fetched on demand
            logger.info("DeezerAPI initialized (session/tokens deferred).")
            self.initialized = True
            return True
            
        except Exception as e:
            logger.error(f"Error during basic API init: {e}")
            return False
            
    async def close(self) -> None:
        """Close the API service's session if it exists."""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.debug("Closed aiohttp ClientSession")
        self.session = None
        self.initialized = False
            
    async def _get_session(self) -> Optional[aiohttp.ClientSession]:
        """Get the existing session or create a new one on demand."""
        if self.session and not self.session.closed:
            return self.session
            
        # Create session if it doesn't exist or is closed
        if not self.loop:
            logger.error("Cannot create session: DeezerAPI has no event loop instance.")
            return None
            
        try:
            # Use the stored self.loop explicitly
            logger.debug(f"Creating new aiohttp ClientSession on stored loop {self.loop} (running={self.loop.is_running()})")
            
            # Get proxy configuration
            proxy_config = self.config.get_setting('network.proxy', {})
            session_kwargs = {
                'loop': self.loop,  # Use stored loop
                'headers': {
                    'User-Agent': self.config.get_setting('network.user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36'),
                    'Accept': '*/*',
                    'Accept-Language': 'en-US,en;q=0.9'
                }
            }
            
            # Add proxy configuration if enabled
            if proxy_config.get('enabled', False) and proxy_config.get('use_for_api', True):
                proxy_host = proxy_config.get('host', '')
                proxy_port = proxy_config.get('port', '')
                proxy_type = proxy_config.get('type', 'http')
                proxy_username = proxy_config.get('username', '')
                proxy_password = proxy_config.get('password', '')
                
                if proxy_host and proxy_port:
                    # Build proxy URL
                    if proxy_username and proxy_password:
                        proxy_url = f"{proxy_type}://{proxy_username}:{proxy_password}@{proxy_host}:{proxy_port}"
                    else:
                        proxy_url = f"{proxy_type}://{proxy_host}:{proxy_port}"
                    
                    session_kwargs['connector'] = aiohttp.TCPConnector(
                        limit=100,
                        limit_per_host=30,
                        ttl_dns_cache=300,
                        use_dns_cache=True,
                    )
                    session_kwargs['trust_env'] = True  # Allow proxy environment variables
                    
                    logger.info(f"Using proxy for API requests: {proxy_type}://{proxy_host}:{proxy_port}")
                    # Note: For aiohttp, proxy is set per request, not per session
                    # We'll store the proxy URL for use in requests
                    self._proxy_url = proxy_url
                else:
                    logger.warning("Proxy enabled but host/port not configured properly")
            
            self.session = aiohttp.ClientSession(**session_kwargs)
            
            # If ARL exists, set the cookie on the new session
            if self.arl:
                 await self._set_cookie() # _set_cookie assumes self.session exists now
                 
            return self.session
        except RuntimeError as e:
             # Handle cases where loop isn't running when get_event_loop is called
             logger.error(f"Failed to get running event loop for session creation: {e}")
             return None
        except Exception as e:
            logger.error(f"Failed to create aiohttp ClientSession: {e}")
            self.session = None # Ensure session is None if creation fails
            return None

    async def _set_cookie(self) -> None:
        """Set the ARL cookie for Deezer authentication."""
        if not self.session or self.session.closed:
             logger.error("_set_cookie called but session is invalid!")
             return
        if not self.arl:
             logger.warning("_set_cookie called but no ARL token is set.")
             return
             
        cookies = {'arl': self.arl}
        self.session.cookie_jar.update_cookies(cookies, URL('https://www.deezer.com'))
        logger.debug("ARL cookie set on session")
        
    async def _make_request(self, method: str, url: str, **kwargs):
        """Make HTTP request with proxy support if configured."""
        session = await self._get_session()
        if not session:
            return None
            
        # Add proxy to request if configured
        if hasattr(self, '_proxy_url') and self._proxy_url:
            kwargs['proxy'] = self._proxy_url
            
        # Make the request
        async with session.request(method, url, **kwargs) as response:
            return response

    async def _get_tokens(self) -> bool:
        """Get API tokens from Deezer (Requires session)."""
        try:
            params = {
                'method': 'deezer.getUserData',
                'input': '3',
                'api_version': '1.0',
                'api_token': ''
            }
            
            # Use proxy-aware request method
            response = await self._make_request('GET', self.PRIVATE_API_BASE, params=params)
            if not response:
                logger.error("Failed to create session for token request")
                return False
                
            if response.status != 200:
                logger.error(f"Failed to get tokens: HTTP {response.status}")
                return False
                
            data = await response.json()
            if data is None:
                logger.error("Token response body was empty or non-JSON")
                return False
                
            if (data.get('error') and len(data['error']) > 0) or 'results' not in data:
                logger.error(f"Invalid token response (error or missing results): {data}")
                return False
                
            result = data.get('results', {})
            self.api_token = result.get('checkForm', '')
            self.csrf_token = result.get('checkForm', '')
            
            # Safely get USER dict and then USER_ID
            user_dict = result.get('USER')
            self.user_id = user_dict.get('USER_ID', None) if isinstance(user_dict, dict) else None
            
            # Get license token
            await self._get_license_token()
            
            return bool(self.api_token and self.csrf_token)
                
        except Exception as e:
            logger.error(f"Error getting tokens: {e}")
            return False
            
    async def _get_license_token(self) -> Optional[str]:
        """Get Deezer license token required for downloads.
        
        Returns:
            Optional[str]: License token or None if not available
        """
        session = await self._get_session()
        if not session: return None
        # Ensure tokens are fetched first (which also ensures session)
        if not self.api_token:
             if not await self._get_tokens(): return None # Propagate failure
        if not self.api_token: return None # Check again
        try:
            params = {
                'method': 'deezer.getUserData',
                'input': '3',
                'api_version': '1.0',
                'api_token': self.api_token or ''
            }
            
            async with session.get(self.PRIVATE_API_BASE, params=params) as response:
                if response.status != 200:
                    return None
                    
                data = await response.json()
                if data is None:
                    logger.error("License token response body was empty or non-JSON")
                    return None
                    
                # Check for non-empty error list or missing results
                if (data.get('error') and len(data['error']) > 0) or 'results' not in data:
                    logger.error(f"Invalid license token response (error or missing results): {data}")
                    return None
                    
                user_data_results = data.get('results', {})
                # Safely get license token with nested checks
                user_dict = user_data_results.get('USER')
                options_dict = user_dict.get('OPTIONS') if isinstance(user_dict, dict) else None
                self.license_token = options_dict.get('license_token', '') if isinstance(options_dict, dict) else ''
                
                logger.debug(f"License token: {self.license_token}")
                return self.license_token
                
        except Exception as e:
            logger.error(f"Error getting license token: {e}")
            return None
            
    async def _get_user_info(self) -> Optional[Dict]:
        """Get user information.
        
        Returns:
            Optional[Dict]: User information or None if not available
        """
        session = await self._get_session()
        if not session: return None
        # Ensure tokens/user_id are fetched first
        if not self.user_id:
             if not await self._get_tokens(): return None # Propagate failure
        if not self.user_id: return None # Check again
        try:
            async with session.get(f"{self.PUBLIC_API_BASE}/user/{self.user_id}") as response:
                if response.status != 200:
                    return None
                    
                data = await response.json()
                if 'error' in data:
                    return None
                    
                self.user_info = data
                return data
                
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return None
            
    async def login_via_arl(self, arl_token: str) -> bool:
        """Login to Deezer using ARL token.
        
        Args:
            arl_token (str): ARL authentication token
            
        Returns:
            bool: True if login successful, False otherwise
        """
        self.arl = arl_token
        self.config.set_setting('deezer.arl', arl_token)
        
        # Reset session
        if self.session:
            await self.session.close()
            self.session = None
        
        # Get tokens (will call _get_session)
        if not await self._get_tokens(): return False
        
        # Get user info (will call _get_session indirectly)
        user_info = await self._get_user_info()
        if not user_info:
            logger.error("Failed to get user info after login")
            return False
            
        logger.info(f"Successfully authenticated with Deezer as {user_info.get('name', 'Unknown')}")
        self.initialized = True
        return True
        
    def _get_cache_path(self, key: str) -> Path:
        """Get cache file path for a key.
        
        Args:
            key (str): Cache key
            
        Returns:
            Path: Path to cache file
        """
        # Create a safe filename from the key
        safe_key = "".join(c if c.isalnum() else "_" for c in key)
        return self.CACHE_DIR / f"{safe_key}.json"
        
    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cache is valid and not expired.
        
        Args:
            cache_path (Path): Path to cache file
            
        Returns:
            bool: True if cache is valid, False otherwise
        """
        if not cache_path.exists():
            return False
            
        # Check if cache is expired
        modified_time = cache_path.stat().st_mtime
        current_time = time.time()
        return (current_time - modified_time) < self.CACHE_DURATION
        
    def _load_from_cache(self, key: str) -> Optional[Dict]:
        """Load data from cache.
        
        Args:
            key (str): Cache key
            
        Returns:
            Optional[Dict]: Cached data or None if not available
        """
        cache_path = self._get_cache_path(key)
        if not self._is_cache_valid(cache_path):
            return None
            
        try:
            with open(cache_path, 'r') as f:
                return json.load(f)
        except Exception:
            return None
            
    def _save_to_cache(self, key: str, data: Dict) -> None:
        """Save data to cache.
        
        Args:
            key (str): Cache key
            data (Dict): Data to cache
        """
        cache_path = self._get_cache_path(key)
        try:
            with open(cache_path, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            logger.error(f"Error saving to cache: {e}")
            
    async def get_track(self, track_id: int) -> Optional[Dict]:
        """Get track information from the Deezer API.
        
        Args:
            track_id (int): Track ID
            
        Returns:
            Optional[Dict]: Track information or None if not available
        """
        # Check cache first
        cache_key = f"track_{track_id}"
        cached = self._load_from_cache(cache_key)
        if cached:
            return cached
            
        session = await self._get_session()
        if not session: return None
        try:
            async with session.get(f"{self.PUBLIC_API_BASE}/track/{track_id}") as response:
                if response.status != 200:
                    logger.error(f"Failed to get track {track_id}: HTTP {response.status}")
                    return None
                    
                data = await response.json()
                if 'error' in data:
                    logger.error(f"Failed to get track {track_id}: {data['error']}")
                    return None
                    
                # Cache the result
                self._save_to_cache(cache_key, data)
                return data
                
        except Exception as e:
            logger.error(f"Error getting track {track_id}: {e}")
            return None
            
    async def get_album(self, album_id: int) -> Optional[Dict]:
        """Get album information from the Deezer API.
        
        Args:
            album_id (int): Album ID
            
        Returns:
            Optional[Dict]: Album information or None if not available
        """
        # Check cache first
        cache_key = f"album_{album_id}"
        cached = self._load_from_cache(cache_key)
        if cached:
            return cached
            
        session = await self._get_session()
        if not session: return None
        try:
            async with session.get(f"{self.PUBLIC_API_BASE}/album/{album_id}") as response:
                if response.status != 200:
                    logger.error(f"Failed to get album {album_id}: HTTP {response.status}")
                    return None
                    
                data = await response.json()
                if 'error' in data:
                    logger.error(f"Failed to get album {album_id}: {data['error']}")
                    return None
                    
                # Cache the result
                self._save_to_cache(cache_key, data)
                return data
                
        except Exception as e:
            logger.error(f"Error getting album {album_id}: {e}")
            return None
            
    async def search(self, query: str, search_type: Optional[str] = None, limit: int = 20) -> List[Dict]:
        """Search Deezer using the public API.

        Args:
            query (str): Search query.
            search_type (Optional[str]): Type of search (e.g., 'track', 'album', 'artist'). 
                                         Defaults to general search if None.
            limit (int): Maximum number of results.

        Returns:
            List[Dict]: List of search results.
        """
        cache_key = f"search_{search_type or 'all'}_{query}_{limit}"
        cached_data = self._load_from_cache(cache_key)
        if cached_data:
            logger.debug(f"Returning cached search results for '{query}' ({search_type or 'all'})')")
            return cached_data

        session = await self._get_session()
        if not session:
            logger.error("Cannot search: Session unavailable.")
            return []
            
        try:
            # Determine endpoint based on search_type
            endpoint = f"{self.PUBLIC_API_BASE}/search"
            if search_type and search_type in ['track', 'album', 'artist', 'playlist', 'user']:
                endpoint += f"/{search_type}"
            
            params = {'q': query, 'limit': limit}
            logger.debug(f"Searching Deezer API: {endpoint} with params: {params}")
            loop_state = f"running={session.loop.is_running() if session.loop else 'N/A'}"
            logger.debug(f"Using session: {session} on loop: {getattr(session, 'loop', 'N/A')} ({loop_state})")

            async with session.get(endpoint, params=params) as response:
                if response.status != 200:
                    logger.error(f"Search failed: HTTP {response.status} - {await response.text()}")
                    return []
                
                data = await response.json() # This is the full API response dictionary
                
                if 'error' in data:
                    logger.error(f"Search API error: {data['error']}")
                    return []
                
                # Added detailed logging for general search raw results
                if search_type is None: # For general search (when search_type is not specified)
                    raw_data_items = data.get('data', [])
                    if raw_data_items:
                        logger.debug(f"DeezerAPI.search general query '{query}': Raw first 5 item types from API: {[item.get('type') for item in raw_data_items[:5]]}")
                        logger.debug(f"DeezerAPI.search general query '{query}': Raw first item example from API: {raw_data_items[0] if raw_data_items else 'None'}")
                    results = raw_data_items # Use the already fetched list
                else: # Existing logic for when search_type is specified
                    results = data.get('data', [])
                
                self._save_to_cache(cache_key, results) # Caches the list of items
                return results

        except Exception as e:
            logger.error(f"Error during search: {e}", exc_info=True)
            return []

    async def get_chart_playlists(self, limit: int = 10) -> Optional[List[Dict]]:
        """
        Get the global chart playlists.

        Args:
            limit (int): Number of playlists to retrieve.

        Returns:
            Optional[List[Dict]]: A list of playlist details, or None on error.
        """
        session = await self._get_session()
        if not session:
            logger.error("Cannot get chart playlists: no session.")
            return None

        request_url = f"{self.PUBLIC_API_BASE}/chart/0/playlists?limit={limit}"
        
        try:
            logger.info(f"Fetching chart playlists from: {request_url}")
            async with session.get(request_url) as response:
                if response.status != 200:
                    logger.error(f"Failed to get chart playlists: HTTP {response.status} - {await response.text()}")
                    return None
                
                data = await response.json()
                if not data or 'data' not in data:
                    logger.error(f"Invalid chart playlists response: 'data' field missing. Response: {data}")
                    return None

                playlists_data = data.get('data', [])
                
                parsed_playlists = []
                for playlist in playlists_data:
                    if not all(k in playlist for k in ['id', 'title', 'picture_medium', 'user']):
                        logger.warning(f"Skipping playlist due to missing keys: {playlist.get('title', 'N/A')}")
                        continue
                    
                    parsed_playlists.append({
                        'id': playlist.get('id'),
                        'title': playlist.get('title'),
                        'description': playlist.get('description', playlist['user'].get('name', 'Various Artists')), # Use description or user name
                        'picture_url': playlist.get('picture_medium'), 
                        'type': 'playlist'
                    })
                
                logger.info(f"Successfully fetched and parsed {len(parsed_playlists)} chart playlists.")
                return parsed_playlists

        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching chart playlists: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for chart playlists: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching chart playlists: {e}")
            return None

    async def get_chart_artists(self, limit: int = 10) -> Optional[List[Dict]]:
        """
        Get the global chart artists.

        Args:
            limit (int): Number of artists to retrieve.

        Returns:
            Optional[List[Dict]]: A list of artist details, or None on error.
        """
        session = await self._get_session()
        if not session:
            logger.error("Cannot get chart artists: no session.")
            return None

        request_url = f"{self.PUBLIC_API_BASE}/chart/0/artists?limit={limit}"
        
        try:
            logger.info(f"Fetching chart artists from: {request_url}")
            async with session.get(request_url) as response:
                if response.status != 200:
                    logger.error(f"Failed to get chart artists: HTTP {response.status} - {await response.text()}")
                    return None
                
                data = await response.json()
                if not data or 'data' not in data:
                    logger.error(f"Invalid chart artists response: 'data' field missing. Response: {data}")
                    return None

                artists_data = data.get('data', [])
                
                parsed_artists = []
                for artist_info in artists_data:
                    if not all(k in artist_info for k in ['id', 'name', 'picture_medium']):
                        logger.warning(f"Skipping artist due to missing keys: {artist_info.get('name', 'N/A')}")
                        continue
                    
                    parsed_artists.append({
                        'id': artist_info.get('id'),
                        'name': artist_info.get('name'),
                        'picture_url': artist_info.get('picture_medium'), 
                        'type': 'artist' # Add type for clarity if needed later
                    })
                
                logger.info(f"Successfully fetched and parsed {len(parsed_artists)} chart artists.")
                return parsed_artists

        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching chart artists: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for chart artists: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching chart artists: {e}")
            return None

    async def get_chart_albums(self, limit: int = 10) -> Optional[List[Dict]]:
        """
        Get the global chart albums.

        Args:
            limit (int): Number of albums to retrieve.

        Returns:
            Optional[List[Dict]]: A list of album details, or None on error.
        """
        session = await self._get_session()
        if not session:
            logger.error("Cannot get chart albums: no session.")
            return None

        request_url = f"{self.PUBLIC_API_BASE}/chart/0/albums?limit={limit}"
        
        try:
            logger.info(f"Fetching chart albums from: {request_url}")
            async with session.get(request_url) as response:
                if response.status != 200:
                    logger.error(f"Failed to get chart albums: HTTP {response.status} - {await response.text()}")
                    return None
                
                data = await response.json()
                if not data or 'data' not in data:
                    logger.error(f"Invalid chart albums response: 'data' field missing. Response: {data}")
                    return None

                albums_data = data.get('data', [])
                
                parsed_albums = []
                for album_info in albums_data:
                    # Ensure essential keys and nested artist object with name are present
                    if not all(k in album_info for k in ['id', 'title', 'cover_medium', 'artist']) or \
                       not isinstance(album_info.get('artist'), dict) or \
                       'name' not in album_info.get('artist', {}):
                        logger.warning(f"Skipping album due to missing keys or invalid artist structure: {album_info.get('title', 'N/A')}")
                        continue
                    
                    parsed_albums.append({
                        'id': album_info.get('id'),
                        'title': album_info.get('title'),
                        'artist_name': album_info['artist'].get('name'),
                        'picture_url': album_info.get('cover_medium'), 
                        'type': 'album'
                    })
                
                logger.info(f"Successfully fetched and parsed {len(parsed_albums)} chart albums.")
                return parsed_albums

        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching chart albums: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for chart albums: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching chart albums: {e}")
            return None

    async def get_editorial_releases(self, limit: int = 10) -> Optional[List[Dict]]:
        """
        Get the editorial new releases from Deezer.

        Args:
            limit (int): Number of releases to retrieve.

        Returns:
            Optional[List[Dict]]: A list of new release album details, or None on error.
        """
        session = await self._get_session()
        if not session:
            logger.error("Cannot get editorial releases: no session.")
            return None

        request_url = f"{self.PUBLIC_API_BASE}/editorial/0/releases?limit={limit}"
        
        try:
            logger.info(f"Fetching editorial releases from: {request_url}")
            async with session.get(request_url) as response:
                if response.status != 200:
                    logger.error(f"Failed to get editorial releases: HTTP {response.status} - {await response.text()}")
                    return None
                
                data = await response.json()
                if not data or 'data' not in data:
                    logger.error(f"Invalid editorial releases response: 'data' field missing. Response: {data}")
                    return None

                releases_data = data.get('data', [])
                
                parsed_releases = []
                for release_info in releases_data:
                    # Ensure essential keys and nested artist object with name are present
                    if not all(k in release_info for k in ['id', 'title', 'cover_medium', 'artist']) or \
                       not isinstance(release_info.get('artist'), dict) or \
                       'name' not in release_info.get('artist', {}):
                        logger.warning(f"Skipping release due to missing keys or invalid artist structure: {release_info.get('title', 'N/A')}")
                        continue
                    
                    parsed_releases.append({
                        'id': release_info.get('id'),
                        'title': release_info.get('title'),
                        'artist_name': release_info['artist'].get('name'),
                        'picture_url': release_info.get('cover_medium'), 
                        'type': 'album'
                    })
                
                logger.info(f"Successfully fetched and parsed {len(parsed_releases)} editorial releases.")
                return parsed_releases

        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching editorial releases: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for editorial releases: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching editorial releases: {e}")
            return None

    async def _get_track_info(self, track_id: str) -> Optional[Dict]:
        """Get additional track information including tokens.
        
        Args:
            track_id (str): Track ID
            
        Returns:
            Optional[Dict]: Track information or None if not found
        """
        session = await self._get_session()
        if not session: return None
        if not self.api_token or not self.csrf_token:
             await self._get_tokens()
        try:
            params = {
                'method': 'deezer.pageTrack',
                'input': '3',
                'api_version': '1.0',
                'api_token': self.csrf_token or '',
                'sng_id': track_id
            }
            logger.debug(f"Calling deezer.pageTrack with params: {params}")
            async with session.get(self.PRIVATE_API_BASE, params=params) as response:
                if response.status != 200:
                    logger.error(f"Failed to get track info: HTTP {response.status}")
                    return None
                data = await response.json()
                logger.debug(f"Private API response for {track_id}: {data}")
                if 'error' in data and data['error']:
                    if 'VALID_TOKEN_REQUIRED' in data['error']:
                        logger.debug("Token invalid, refreshing tokens...")
                        if await self._get_tokens():
                            return await self._get_track_info(track_id)
                    logger.error(f"API error: {data['error']}")
                    return None
                if 'results' not in data or not data['results']:
                    logger.error(f"No results in API response")
                    return None
                results = data.get('results', {})
                track_data = results.get('DATA')
                lyrics_data = results.get('LYRICS')
                if not track_data:
                    logger.warning(f"No 'DATA' found in pageTrack results for track {track_id}")
                    return None
                if lyrics_data:
                    track_data['LYRICS'] = lyrics_data
                return track_data
        except Exception as e:
            logger.exception(f"Error getting track info for {track_id}: {e}", exc_info=True)
            return None
            
    async def _get_track_url(self, track_data: Dict, quality: str = 'MP3_320') -> Optional[str]:
        """Generate download URL for a track using the /v1/get_url endpoint.
        
        Args:
            track_data (Dict): Track data from _get_track_info (needs SNG_ID and TRACK_TOKEN).
            quality (str, optional): Quality - MP3_128, MP3_320, or FLAC. Defaults to 'MP3_320'.
            
        Returns:
            Optional[str]: Download URL or None if not available
        """
        session = await self._get_session()
        if not session: return None
        # Ensure license token is fetched
        if not self.license_token:
             if not await self._get_license_token(): return None # Propagate failure
        if not self.license_token: return None # Check again
        try:
            track_token = track_data.get('TRACK_TOKEN')
            if not track_token:
                 logger.error("No track token available in track_data for URL retrieval")
                 return None
                 
            # Map quality string to API format string
            quality_format_map = {
                'MP3_128': 'MP3_128',
                'MP3_320': 'MP3_320',
                'FLAC': 'FLAC'
            }
            api_format = quality_format_map.get(quality, 'MP3_320')
            
            # Construct the payload
            payload = {
                "license_token": self.license_token,
                "media": [
                    {
                        "type": "FULL",
                        "formats": [
                            {"cipher": "BF_CBC_STRIPE", "format": api_format}
                        ]
                    }
                ],
                "track_tokens": [track_token]
            }
            
            media_url = "https://media.deezer.com/v1/get_url"
            logger.debug(f"Calling {media_url} with payload: {payload}")
            
            # Restore the indented block for the async with statement
            async with session.post(media_url, json=payload) as response:
                if response.status != 200:
                    logger.error(f"Failed to get download URL via {media_url}: HTTP {response.status} - {await response.text()}")
                    return None
                    
                data = await response.json()
                logger.debug(f"{media_url} response: {data}")
                
                if 'error' in data and data['error']:
                    logger.error(f"API error from {media_url}: {data['error']}")
                    return None
                    
                if 'data' in data and data['data'] and 'media' in data['data'][0] and data['data'][0]['media'] and 'sources' in data['data'][0]['media'][0] and data['data'][0]['media'][0]['sources']:
                    sources = data['data'][0]['media'][0]['sources']
                    if sources:
                        track_url = sources[0].get('url')
                        if track_url:
                             logger.debug(f"Got download URL: {track_url[:50]}...")
                             return track_url
                        else:
                             logger.error("No URL found in sources array")
                             return None
                    else:
                        logger.error("Empty sources array in response")
                        return None
                else:
                    logger.error(f"Unexpected response structure from {media_url}: {data}")
                    return None
                    
        except Exception as e:
            logger.exception(f"Error getting track URL via {media_url}: {e}", exc_info=True)
            return None
            
    def _generate_legacy_url(self, track_data: Dict, quality: int) -> Optional[str]:
        """Generate legacy download URL for a track.
        
        This is a fallback method for when the API doesn't return a URL.
        
        Args:
            track_data (Dict): Track data from _get_track_info
            quality (int): Quality - 1 for MP3_128, 3 for MP3_320, 9 for FLAC
            
        Returns:
            Optional[str]: Download URL or None if not available
        """
        try:
            md5 = track_data.get('MD5_ORIGIN')
            media_version = track_data.get('MEDIA_VERSION')
            sng_id = track_data.get('SNG_ID')
            
            if not md5 or not media_version or not sng_id:
                logger.error("Missing required data for legacy URL generation")
                return None
                
            # Generate URL based on the first character of MD5
            cdn = md5[0]
            
            return f"https://e-cdns-proxy-{cdn}.dzcdn.net/mobile/1/{md5}/{quality}/{media_version}/{sng_id}"
            
        except Exception as e:
            logger.error(f"Error generating legacy URL: {e}")
            return None
            
    async def get_track_download_url(self, track_id: int, quality: str = 'MP3_320') -> Optional[str]:
        """Get track download URL.
        
        Args:
            track_id (int): Track ID.
            quality (str, optional): Quality - MP3_128, MP3_320, or FLAC. Defaults to 'MP3_320'.
            
        Returns:
            Optional[str]: Download URL or None if not available.
        """
        if not self.is_authenticated():
            logger.warning("Not authenticated. Cannot get download URL.")
            return None
            
        try:
            # Get track tokens and info
            track_data = await self._get_track_info(str(track_id))
            if not track_data:
                logger.error(f"Could not get track info for {track_id}")
                return None
                
            # Get download URL
            url = await self._get_track_url(track_data, quality)
            if not url:
                logger.error(f"Could not get download URL for track {track_id}")
                return None
                
            return url
            
        except Exception as e:
            logger.error(f"Failed to get download URL for track {track_id}: {e}")
            return None
            
    def is_authenticated(self) -> bool:
        """Check if the API is authenticated.
        
        Returns:
            bool: True if authenticated, False otherwise.
        """
        # For sync operations, we only need ARL and API token
        # The initialized flag is only set through async login_via_arl()
        has_credentials = self.arl is not None and self.api_token is not None
        
        # Log the state of each component for debugging
        logger.debug(f"is_authenticated check: initialized={self.initialized}, arl_is_not_none={self.arl is not None} (len={len(self.arl) if self.arl else 0}), api_token_is_not_none={self.api_token is not None} (token_val='{self.api_token[:10] if self.api_token else None}...'")
        
        # Return True if we have credentials (allows sync operations to work)
        # OR if we're fully initialized (async operations)
        return has_credentials or self.initialized

    async def get_track_details(self, track_id: int) -> Optional[Dict]:
        """Get detailed track information.
        
        Args:
            track_id (int): The track ID to get details for
            
        Returns:
            Optional[Dict]: Track details or None if not available
        """
        logger.debug(f"Getting track details for {track_id}")
        
        # First try to get from public API (more details)
        try:
            session = await self._get_session()
            if not session:
                return None
                
            cache_key = f"track_{track_id}"
            cached = self._load_from_cache(cache_key)
            if cached:
                logger.debug(f"Using cached track details for {track_id}")
                return cached
                
            async with session.get(f"{self.PUBLIC_API_BASE}/track/{track_id}") as response:
                if response.status != 200:
                    logger.error(f"Failed to get track details: HTTP {response.status}")
                    return None
                    
                data = await response.json()
                if 'error' in data:
                    logger.error(f"Error in track details response: {data.get('error')}")
                    return None
                    
                # Cache the results
                self._save_to_cache(cache_key, data)
                return data
                
        except Exception as e:
            logger.error(f"Error getting track details: {e}")
            return None
            
    async def get_album_details(self, album_id: int) -> Optional[Dict]:
        """Get detailed information for a specific album using public API."""
        session = await self._get_session()
        if not session: return None

        cache_key = f"album_details_{album_id}"
        cached_data = self._load_from_cache(cache_key)
        if cached_data: return cached_data

        try:
            async with session.get(f"{self.PUBLIC_API_BASE}/album/{album_id}") as response:
                response.raise_for_status() # Raise an exception for bad status codes
                data = await response.json()
                if 'error' in data:
                    logger.warning(f"Error fetching album details for {album_id} from public API: {data['error']}")
                    return None
                self._save_to_cache(cache_key, data)
                return data
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching album details for {album_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching album details for {album_id}: {e}")
            return None

    def get_track_details_sync(self, track_id: int) -> Optional[Dict]:
        """Synchronous version of get_track_details.
        
        This method is used by the DownloadWorker class to get track details
        in a synchronous way, avoiding asyncio context issues.
        
        Args:
            track_id (int): The ID of the track
            
        Returns:
            Optional[Dict]: Track details or None if not available
        """
        try:
            url = f"{self.PUBLIC_API_BASE}/track/{track_id}"
            logger.debug(f"Getting track details for {track_id} (sync)")
            
            # Use requests library for synchronous request
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            track_data = response.json()
            if 'error' in track_data:
                logger.error(f"Error getting track details: {track_data['error']}")
                return None
                
            return track_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error getting track details: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting track details: {e}")
            return None
            
    def get_album_details_sync(self, album_id: int) -> Optional[Dict]:
        """Synchronous version of get_album_details.
        
        This method is used by the DownloadWorker class to get album details
        in a synchronous way, avoiding asyncio context issues.
        
        Args:
            album_id (int): The ID of the album
            
        Returns:
            Optional[Dict]: Album details or None if not available
        """
        try:
            url = f"{self.PUBLIC_API_BASE}/album/{album_id}"
            logger.debug(f"Getting album details for {album_id} (sync)")
            
            # Use requests library for synchronous request
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            album_data = response.json()
            if 'error' in album_data:
                logger.error(f"Error getting album details: {album_data['error']}")
                return None
                
            return album_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error getting album details: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting album details: {e}")
            return None

    async def _get_track_info_private(self, track_id: str) -> Optional[Dict]:
        """Get detailed track information from Deezer's private API.
        
        This method addresses the 'track_token_expire' issue by using Deezer's
        private API endpoints which include additional fields needed by deemix.
        
        Args:
            track_id (str): Deezer track ID
            
        Returns:
            Optional[Dict]: Detailed track info including all deemix required fields or None if failed
        """
        session = await self._get_session()
        if not session:
            return None
            
        # Ensure tokens are fetched
        if not self.api_token:
            if not await self._get_tokens():
                logger.error("Failed to get API tokens for private track info")
                return None
                
        try:
            # Prepare request parameters for the private API
            params = {
                'method': 'deezer.pageTrack',
                'api_version': '1.0',
                'api_token': self.api_token,
                'input': '3',
                'cid': int(time.time())
            }
            
            json_data = {
                'sng_id': track_id
            }
            
            # Make the request to the private API
            async with session.post(
                self.PRIVATE_API_BASE,
                params=params,
                json=json_data
            ) as response:
                if response.status != 200:
                    logger.error(f"Error fetching track from private API: HTTP {response.status}")
                    return None
                    
                data = await response.json()
                
                # Check for errors in response
                if 'error' in data and data['error']:
                    logger.error(f"Error in private API response: {data['error']}")
                    return None
                    
                # Extract track data from results
                if 'results' not in data:
                    logger.error("No results in private API response")
                    return None
                    
                track_data = data['results']['DATA']
                
                # TEMPORARY DEBUG LOGGING:
                logger.debug(f"ASYNC Raw DATA for track {track_id}: {track_data}")
                logger.debug(f"ASYNC Keys in raw DATA for track {track_id}: {list(track_data.keys())}")

                # Check if track_token_expire exists, which is what deemix needs
                if 'TRACK_TOKEN_EXPIRE' in track_data:
                    # Convert to lowercase keys to match what deemix expects
                    result = {}
                    for key, value in track_data.items():
                        result[key.lower()] = value
                        
                    # Ensure the key is explicitly set to avoid future issues
                    result['track_token_expire'] = track_data['TRACK_TOKEN_EXPIRE']
                    
                    # Add additional fields required by deemix
                    if 'track_token' not in result and 'TRACK_TOKEN' in track_data:
                        result['track_token'] = track_data['TRACK_TOKEN']
                        
                    # Convert any nested structures too
                    if 'ALBUM' in track_data:
                        result['album'] = {}
                        for key, value in track_data['ALBUM'].items():
                            result['album'][key.lower()] = value
                            
                    if 'ARTIST' in track_data:
                        result['artist'] = {}
                        for key, value in track_data['ARTIST'].items():
                            result['artist'][key.lower()] = value
                    
                    # Ensure 'artist' dictionary exists and has a 'name' key for deemix
                    if not isinstance(result.get('artist'), dict) or 'name' not in result.get('artist', {}):
                        logger.debug(f"Artist dictionary missing or incomplete for track {track_id}. Attempting fallback.")
                        artist_name_fallback = result.get('art_name') or track_data.get('ART_NAME')
                        if artist_name_fallback:
                            logger.debug(f"Using fallback artist name: {artist_name_fallback}")
                            # Ensure result['artist'] is a dictionary before assigning name
                            if not isinstance(result.get('artist'), dict):
                                result['artist'] = {}
                            result['artist']['name'] = artist_name_fallback
                        else:
                            logger.warning(f"Could not find artist name for track {track_id}. Setting to 'Unknown Artist'.")
                            result['artist'] = {'name': 'Unknown Artist'}
                    
                    # Ensure 'filesizes' dictionary is present for deemix
                    result['filesizes'] = {}
                    filesize_keys_map = {
                        'FILESIZE_MP3_128': 'MP3_128',
                        'FILESIZE_MP3_256': 'MP3_256', # Might exist
                        'FILESIZE_MP3_320': 'MP3_320',
                        'FILESIZE_FLAC': 'FLAC',
                        # Add mappings for other potential qualities if needed
                    }
                    for api_key, deemix_key in filesize_keys_map.items():
                        if api_key in track_data:
                            try:
                                result['filesizes'][deemix_key] = int(track_data[api_key])
                            except (ValueError, TypeError):
                                logger.warning(f"Could not convert {api_key} value '{track_data[api_key]}' to int for track {track_id}")
                        # Check lowercase version as well, just in case
                        elif api_key.lower() in result: 
                            try:
                                result['filesizes'][deemix_key] = int(result[api_key.lower()])
                            except (ValueError, TypeError):
                                logger.warning(f"Could not convert {api_key.lower()} value '{result[api_key.lower()]}' to int for track {track_id}")

                    if not result['filesizes']:
                         logger.warning(f"No filesize information found in track_data for track {track_id}. Deemix might fail.")

                    # Ensure 'release_date' is present for deemix
                    if 'release_date' not in result:
                        release_date_fallback = result.get('physical_release_date') # Check lowercase primary first
                        if not release_date_fallback and isinstance(result.get('album'), dict):
                            release_date_fallback = result['album'].get('release_date') # Check lowercase album dict
                        if not release_date_fallback:
                             release_date_fallback = track_data.get('PHYSICAL_RELEASE_DATE') # Check original uppercase
                             if not release_date_fallback and isinstance(track_data.get('ALBUM'), dict):
                                  release_date_fallback = track_data['ALBUM'].get('release_date') # Check original album dict
                        
                        if release_date_fallback:
                            result['release_date'] = release_date_fallback
                            logger.debug(f"Copied release date ({release_date_fallback}) to 'release_date' for track {track_id}")
                        else:
                            logger.warning(f"Could not find release date for track {track_id}. Using '1970-01-01'. Deemix might have issues.")
                            result['release_date'] = "1970-01-01" # Provide a default to prevent KeyError

                    # TEMPORARY DEBUG LOGGING FOR PROCESSED INFO (ASYNC):
                    logger.debug(f"ASYNC Processed result for track {track_id}: {result}")
                    logger.debug(f"ASYNC Keys in processed result for track {track_id}: {list(result.keys())}")
                    # Specifically check for disk_number
                    logger.debug(f"ASYNC disk_number in processed result: {result.get('disk_number')}")


                    logger.debug(f"Successfully fetched track data from private API with track_token_expire")
                    return result
                else:
                    logger.error("track_token_expire field missing from private API response")
                    return None
                    
        except Exception as e:
            logger.error(f"Error getting track info from private API: {e}", exc_info=True)
            return None
            
    def get_track_details_sync_private(self, track_id: int) -> Optional[Dict]:
        """Get track details synchronously using the private API.
        
        This is a synchronous version of the private API track getter,
        suitable for use in background threads where the asyncio event loop
        is not available.
        
        Args:
            track_id (int): Deezer track ID
            
        Returns:
            Optional[Dict]: Track details or None if not found/error
        """
        # Use a single session for the entire synchronous operation
        with requests.Session() as sync_session:
            # Configure proxy for requests session if enabled
            proxy_config = self.config.get_setting('network.proxy', {})
            if proxy_config.get('enabled', False) and proxy_config.get('use_for_api', True):
                proxy_host = proxy_config.get('host', '')
                proxy_port = proxy_config.get('port', '')
                proxy_type = proxy_config.get('type', 'http')
                proxy_username = proxy_config.get('username', '')
                proxy_password = proxy_config.get('password', '')
                
                if proxy_host and proxy_port:
                    # Build proxy URL for requests
                    if proxy_username and proxy_password:
                        proxy_url = f"{proxy_type}://{proxy_username}:{proxy_password}@{proxy_host}:{proxy_port}"
                    else:
                        proxy_url = f"{proxy_type}://{proxy_host}:{proxy_port}"
                    
                    # Set proxies for requests session
                    sync_session.proxies = {
                        'http': proxy_url,
                        'https': proxy_url
                    }
                    logger.info(f"[SYNC_URL_FETCH] Using proxy for sync requests: {proxy_type}://{proxy_host}:{proxy_port}")
                else:
                    logger.warning("[SYNC_URL_FETCH] Proxy enabled but host/port not configured properly")
            
            try:
                # Ensure ARL cookie is set on the session
                if self.arl:
                    sync_session.cookies.set('arl', self.arl, domain='.deezer.com')
                else:
                    logger.error("ARL token is missing. Cannot get private track details.")
                    return None

                # Ensure API token is available before making the request
                current_api_token = self.api_token # Work with a local variable
                if not current_api_token:
                    logger.info("API token not found, attempting synchronous fetch within session...")
                    init_token_params = {
                        'method': 'deezer.getUserData', 'input': '3', 
                        'api_version': '1.0', 'api_token': ''
                    }
                    try:
                        # Use the single session to fetch the token
                        init_token_response = sync_session.get(
                            self.PRIVATE_API_BASE, params=init_token_params, timeout=10
                        )
                        init_token_response.raise_for_status()
                        init_token_data = init_token_response.json()
                        
                        if (init_token_data.get('error') and len(init_token_data['error']) > 0) or 'results' not in init_token_data:
                            logger.error(f"Failed to get initial token: Invalid response {init_token_data}")
                            return None # Cannot proceed without token
                            
                        initial_api_token = init_token_data.get('results', {}).get('checkForm', '')
                        if initial_api_token:
                            logger.info(f"Successfully obtained initial API token: {initial_api_token[:5]}...")
                            current_api_token = initial_api_token
                            self.api_token = initial_api_token # Update the instance variable as well
                            self.csrf_token = initial_api_token
                        else:
                            logger.error("Failed to get initial token: 'checkForm' missing.")
                            return None # Cannot proceed without token
                            
                    except requests.exceptions.RequestException as init_token_err:
                         logger.error(f"HTTP error during nested token fetch: {init_token_err}")
                         return None # Network or HTTP error
                    except Exception as init_inner_e:
                         logger.error(f"Unexpected error during nested token fetch: {init_inner_e}")
                         return None # Other error

                # If after attempting fetch, token is still missing, abort.
                if not current_api_token:
                     logger.error("API token is missing after fetch attempt. Cannot get private track details.")
                     return None

                # --- Inner function remains similar but uses the outer session --- 
                def make_api_request(api_token_to_use, retry=True):
                    # Use the existing sync_session 
                    params = {
                        'method': 'deezer.pageTrack',
                        'api_version': '1.0',
                        'api_token': api_token_to_use, # Use the token passed to this attempt
                        'input': '3',
                        'cid': int(time.time())
                    }
                    json_data = {'sng_id': str(track_id)}
                    
                    logger.debug(f"Making sync private API request (pageTrack) for track {track_id} with token {api_token_to_use[:5]}... (Retry={retry})")
                    
                    try:
                        response = sync_session.post(
                            self.PRIVATE_API_BASE,
                            params=params,
                            json=json_data,
                            timeout=10
                        )
                        response.raise_for_status()
                        track_data_response = response.json()

                        if 'error' in track_data_response and track_data_response['error']:
                            logger.warning(f"pageTrack returned error for {track_id}: {track_data_response['error']}. Retrying: {retry}")
                            # Specific handling for "VALID_TOKEN_REQUIRED"
                            # Check if the error dictionary ITSELF contains VALID_TOKEN_REQUIRED as a key
                            if isinstance(track_data_response['error'], dict) and 'VALID_TOKEN_REQUIRED' in track_data_response['error']:
                                if retry: # Only retry once for token issues
                                    logger.info("Attempting sync token refresh within session (VALID_TOKEN_REQUIRED found)...")
                                    # Refresh token using the same sync_session
                                    refreshed_token = self._refresh_token_sync(sync_session)
                                    if refreshed_token:
                                        return make_api_request(refreshed_token, retry=False) 
                                    else:
                                        logger.error("Token refresh failed. Cannot get private track details.")
                                        return None 
                                else:
                                    logger.error("Token still invalid after refresh attempt.")
                                    return None # Failed after retry
                            # For other errors, don't retry or handle as needed
                            return None 

                        if 'results' not in track_data_response or 'DATA' not in track_data_response['results']:
                            logger.error(f"Invalid response structure from pageTrack for {track_id}: {track_data_response}")
                            return None

                        raw_track_data_from_api = track_data_response.get('results', {}).get('DATA', {})
                        
                        # TEMPORARY DEBUG LOGGING:
                        logger.debug(f"SYNC Raw DATA for track {track_id}: {raw_track_data_from_api}") 
                        logger.debug(f"SYNC Keys in raw DATA for track {track_id}: {list(raw_track_data_from_api.keys())}")

                        # Process data (this function should handle key conversion, etc.)
                        processed_track_info = self._process_track_data_private(raw_track_data_from_api, str(track_id))
                        
                        if processed_track_info:
                             # TEMPORARY DEBUG LOGGING FOR PROCESSED INFO:
                            logger.debug(f"SYNC Processed track_info for {track_id}: {processed_track_info}")
                            logger.debug(f"SYNC Keys in processed track_info for {track_id}: {list(processed_track_info.keys())}")
                            # Specifically check for disk_number
                            logger.debug(f"SYNC disk_number in processed_track_info: {processed_track_info.get('disk_number')}")


                        return processed_track_info

                    except requests.exceptions.RequestException as http_err:
                        logger.error(f"HTTP error during pageTrack call: {http_err}")
                        return None
                
                # Initial call to make_api_request - This should be the last line before the except
                result = make_api_request(current_api_token, retry=True) 
                return result

            except Exception as e:
                logger.error(f"Outer exception in get_track_details_sync_private for {track_id}: {e}", exc_info=True)
                return None
                
    def _process_track_data_private(self, raw_data: Dict[str, Any], track_id_str: str) -> Optional[Dict[str, Any]]:
        """Helper to consistently process raw track data from pageTrack into a standardized dict."""
        if not raw_data:
            logger.warning(f"_process_track_data_private called with empty raw_data for {track_id_str}")
            return None

        processed_info = {}
        for key, value in raw_data.items():
            processed_info[key.lower()] = value # General lowercase conversion

        # Ensure SNG_ID is present and correct
        if 'sng_id' not in processed_info:
            logger.warning(f"\'sng_id\' missing in processed_info for {track_id_str} after lowercase conversion. Raw keys: {list(raw_data.keys())}")
            # Attempt to get it from original raw_data if SNG_ID was the key
            if 'SNG_ID' in raw_data:
                 processed_info['sng_id'] = raw_data['SNG_ID']
            else: # Still not found, this is an issue.
                 logger.error(f"CRITICAL: SNG_ID is missing for track {track_id_str}. Cannot proceed with this track.")
                 return None # Or handle error appropriately

        # Ensure 'id' is present (copy from 'sng_id')
        processed_info['id'] = processed_info['sng_id'] 
        logger.debug(f"Copied sng_id to id for track {track_id_str}")

        # Ensure 'title' is present (copy from 'sng_title')
        if 'sng_title' in processed_info:
            processed_info['title'] = processed_info['sng_title']
            logger.debug(f"Copied sng_title to title for track {track_id_str}")
        elif 'SNG_TITLE' in raw_data: # Fallback to original casing if needed
            processed_info['title'] = raw_data['SNG_TITLE']
            logger.debug(f"Copied SNG_TITLE (original case) to title for track {track_id_str}")
        else:
            logger.warning(f"Title (sng_title) not found for track {track_id_str}")
            processed_info['title'] = f"Track {track_id_str}"

        # Handle VERSION field for track versions (remixes, extended mixes, etc.)
        version = None
        if 'VERSION' in raw_data and raw_data['VERSION']:
            version = raw_data['VERSION'].strip()
        elif 'version' in processed_info and processed_info['version']:
            version = processed_info['version'].strip()
        
        # Combine title with version if version exists and is not already in title
        if version and processed_info['title']:
            current_title = processed_info['title']
            # Only add version if it's not already included in the title
            if version not in current_title:
                processed_info['title'] = f"{current_title} {version}".strip()
                logger.debug(f"Added version '{version}' to title for track {track_id_str}: '{processed_info['title']}'")
            else:
                logger.debug(f"Version '{version}' already present in title for track {track_id_str}")
        elif version:
            logger.debug(f"Found version '{version}' but no title for track {track_id_str}")

        # Store the original version info for potential future use
        processed_info['version'] = version

        # Artist Info (ensure 'artist' key with at least 'name')
        artist_data_lc = processed_info.get('artist', {}) # from ARTIST if it was there
        artist_data_uc = raw_data.get('ARTIST', {})       # from original ARTIST
        
        final_artist_info = {}
        # Populate from lowercase version first
        if isinstance(artist_data_lc, dict):
            for k,v in artist_data_lc.items():
                final_artist_info[k.lower()] = v
        # Overlay/add from uppercase version if keys were different or missing
        if isinstance(artist_data_uc, dict):
            for k,v in artist_data_uc.items():
                if k.lower() not in final_artist_info: # only add if not already there from lc version
                    final_artist_info[k.lower()] = v
        
        if 'name' not in final_artist_info:
            # Try ART_NAME from main raw_data level
            if raw_data.get('ART_NAME'):
                final_artist_info['name'] = raw_data['ART_NAME']
            elif processed_info.get('art_name'): # from main processed_info level (lowercase)
                final_artist_info['name'] = processed_info['art_name']
            else:
                logger.warning(f"Artist name not found for {track_id_str}. Using 'Unknown Artist'.")
                final_artist_info['name'] = "Unknown Artist"
        
        # Ensure 'id' is in artist if possible
        if 'id' not in final_artist_info:
            if 'art_id' in final_artist_info: # from ARTIST.art_id (lc)
                final_artist_info['id'] = final_artist_info['art_id']
            elif raw_data.get('ART_ID'): # from main ART_ID
                final_artist_info['id'] = raw_data['ART_ID']
            elif processed_info.get('art_id'): # from main art_id (lc)
                final_artist_info['id'] = processed_info['art_id']

        processed_info['artist'] = final_artist_info
        logger.debug(f"Processed artist info for {track_id_str}: {processed_info['artist']}")


        # Album Info (ensure 'album' key with at least 'title')
        album_data_lc = processed_info.get('album', {}) # from ALBUM if it was there
        album_data_uc = raw_data.get('ALBUM', {})       # from original ALBUM

        final_album_info = {}
        if isinstance(album_data_lc, dict):
            for k,v in album_data_lc.items():
                final_album_info[k.lower()] = v
        if isinstance(album_data_uc, dict):
            for k,v in album_data_uc.items():
                if k.lower() not in final_album_info:
                     final_album_info[k.lower()] = v

        if 'title' not in final_album_info:
            if raw_data.get('ALB_TITLE'):
                final_album_info['title'] = raw_data['ALB_TITLE']
            elif processed_info.get('alb_title'):
                final_album_info['title'] = processed_info['alb_title']
            else:
                logger.warning(f"Album title not found for {track_id_str}. Using 'Unknown Album'.")
                final_album_info['title'] = "Unknown Album"
        
        if 'id' not in final_album_info:
            if 'alb_id' in final_album_info: # from ALBUM.alb_id (lc)
                final_album_info['id'] = final_album_info['alb_id']
            elif raw_data.get('ALB_ID'): # from main ALB_ID
                final_album_info['id'] = raw_data['ALB_ID']
            elif processed_info.get('alb_id'): # from main alb_id (lc)
                final_album_info['id'] = processed_info['alb_id']
        
        processed_info['album'] = final_album_info
        logger.debug(f"Processed album info for {track_id_str}: {processed_info['album']}")

        # Standardize other important fields, ensuring they exist at top level of processed_info
        key_mappings_to_ensure = {
            'track_token': 'TRACK_TOKEN',
            'track_token_expire': 'TRACK_TOKEN_EXPIRE',
            'disk_number': 'DISK_NUMBER',
            'track_number': 'TRACK_NUMBER', # often 'track_position' in other contexts
            'duration': 'DURATION',
            'release_date': 'PHYSICAL_RELEASE_DATE', # Or just 'release_date' if that's primary
            'gain': 'GAIN',
            'isrc': 'ISRC',
            'md5_origin': 'MD5_ORIGIN',
            'alb_picture': 'ALB_PICTURE', # For album cover MD5
            'art_picture': 'ART_PICTURE', # For artist picture MD5
            'version': 'VERSION', # Track version (remix, extended, etc.)
        }

        for target_key, source_key_uc in key_mappings_to_ensure.items():
            if target_key not in processed_info: # If not already set by initial lowercase conversion
                if source_key_uc in raw_data:
                    processed_info[target_key] = raw_data[source_key_uc]
                else:
                    logger.debug(f"Key '{target_key}' (from '{source_key_uc}') not found in raw_data for {track_id_str}")
                    # Set a sensible default or leave as None if appropriate
                    if target_key in ['disk_number', 'track_number', 'duration']:
                        processed_info[target_key] = processed_info.get(target_key, 0) # Default to 0 for numerical
                    elif target_key in ['track_token']: # Critical, should log if missing
                        logger.warning(f"Critical key '{target_key}' is missing for {track_id_str}")
                        processed_info[target_key] = None
                    else:
                        processed_info[target_key] = None # Default to None for others

        # Ensure 'track_position' is also populated if 'track_number' exists
        if 'track_number' in processed_info and 'track_position' not in processed_info:
            processed_info['track_position'] = processed_info['track_number']
            logger.debug(f"Copied track_number to track_position for {track_id_str}")


        # --- Filesizes ---
        # Create a 'filesizes' sub-dictionary for consistency
        processed_info['filesizes'] = {}
        filesize_keys_map = {
            'FILESIZE_MP3_128': 'MP3_128', 
            'FILESIZE_MP3_256': 'MP3_256', # Not always present
            'FILESIZE_MP3_320': 'MP3_320', 
            'FILESIZE_FLAC': 'FLAC',
            'FILESIZE_AAC_64': 'AAC_64', # Less common but include for completeness
        }
        for api_key_uc, quality_key in filesize_keys_map.items():
            value_from_raw = raw_data.get(api_key_uc) # Check original uppercase first
            if value_from_raw is not None:
                try:
                    processed_info['filesizes'][quality_key] = int(value_from_raw)
                except (ValueError, TypeError):
                    logger.warning(f"Could not convert {api_key_uc} value '{value_from_raw}' to int for {track_id_str}")
            else: # Fallback to check already lowercased key if direct UC wasn't there
                value_from_lc = processed_info.get(api_key_uc.lower())
                if value_from_lc is not None:
                    try:
                        processed_info['filesizes'][quality_key] = int(value_from_lc)
                    except (ValueError, TypeError):
                         logger.warning(f"Could not convert {api_key_uc.lower()} value '{value_from_lc}' to int for {track_id_str}")
                # else: logger.debug(f"Filesize key {api_key_uc} (and lc) not found for {track_id_str}")
        
        # Some API responses might have a single 'FILESIZE' field for the default quality (often 128kbps MP3)
        # If specific quality filesizes are missing, and a general 'FILESIZE' exists, use it for MP3_128
        if 'MP3_128' not in processed_info['filesizes'] or processed_info['filesizes']['MP3_128'] == 0:
            general_filesize_raw = raw_data.get('FILESIZE')
            if general_filesize_raw is not None:
                try:
                    processed_info['filesizes']['MP3_128'] = int(general_filesize_raw)
                    logger.debug(f"Used general 'FILESIZE' for MP3_128 for track {track_id_str}")
                except (ValueError, TypeError):
                    logger.warning(f"Could not convert general 'FILESIZE' value '{general_filesize_raw}' to int for {track_id_str}")

        logger.debug(f"Final processed_info for {track_id_str} (keys: {list(processed_info.keys())})")
        return processed_info

    def _refresh_token_sync(self, sync_session: requests.Session) -> Optional[str]:
        """Synchronously refreshes the API token (checkForm) using the given session."""
        logger.info("Attempting to refresh API token synchronously...")
        params = {'method': 'deezer.getUserData', 'input': '3', 'api_version': '1.0', 'api_token': ''}
        try:
            response = sync_session.get(self.PRIVATE_API_BASE, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            if 'error' in data and data['error']:
                logger.error(f"Error refreshing token: {data['error']}")
                return None
            if 'results' in data and 'checkForm' in data['results']:
                new_api_token = data['results']['checkForm']
                logger.info(f"Successfully refreshed API token: {new_api_token[:5]}...")
                self.api_token = new_api_token
                self.csrf_token = new_api_token # CSRF token is usually the same as API token
                return new_api_token
            else:
                logger.error(f"Failed to refresh token: 'checkForm' not in response results. Response: {data}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP error during token refresh: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during token refresh: {e}", exc_info=True)
            return None

    def get_track_download_url_sync(self, track_id: int, quality: str = 'MP3_320') -> Optional[str]:
        """Synchronous version to get track download URL.

        Combines getting track info (private) and download URL (media API).

        Args:
            track_id (int): Track ID.
            quality (str, optional): Quality - MP3_128, MP3_320, or FLAC. Defaults to 'MP3_320'.

        Returns:
            Optional[str]: Download URL or None if not available.
        """
        logger.debug(f"[SYNC_URL_FETCH] Enter get_track_download_url_sync for {track_id}. Current self.api_token: '{self.api_token[:10] if self.api_token else None}...' Current self.license_token: '{self.license_token[:10] if self.license_token else None}...' ARL set: {bool(self.arl)}")

        if not self.is_authenticated(): # Check basic auth state first
            logger.warning("[SYNC_URL_FETCH] Not authenticated (is_authenticated failed). Cannot get sync download URL.")
            return None

        # Need a requests.Session for cookie/token handling across calls
        with requests.Session() as sync_session:
            # Configure proxy for requests session if enabled
            proxy_config = self.config.get_setting('network.proxy', {})
            if proxy_config.get('enabled', False) and proxy_config.get('use_for_api', True):
                proxy_host = proxy_config.get('host', '')
                proxy_port = proxy_config.get('port', '')
                proxy_type = proxy_config.get('type', 'http')
                proxy_username = proxy_config.get('username', '')
                proxy_password = proxy_config.get('password', '')
                
                if proxy_host and proxy_port:
                    # Build proxy URL for requests
                    if proxy_username and proxy_password:
                        proxy_url = f"{proxy_type}://{proxy_username}:{proxy_password}@{proxy_host}:{proxy_port}"
                    else:
                        proxy_url = f"{proxy_type}://{proxy_host}:{proxy_port}"
                    
                    # Set proxies for requests session
                    sync_session.proxies = {
                        'http': proxy_url,
                        'https': proxy_url
                    }
                    logger.info(f"[SYNC_URL_FETCH] Using proxy for sync requests: {proxy_type}://{proxy_host}:{proxy_port}")
                else:
                    logger.warning("[SYNC_URL_FETCH] Proxy enabled but host/port not configured properly")
            
            try:
                # --- 1. Set ARL Cookie --- 
                if self.arl:
                    sync_session.cookies.set('arl', self.arl, domain='.deezer.com')
                    logger.debug("[SYNC_URL_FETCH] ARL cookie set for sync_session.")
                else:
                    logger.error("[SYNC_URL_FETCH] ARL token missing. Cannot get sync download URL.")
                    return None

                # --- 2. Ensure API Token and License Token --- 
                current_api_token = self.api_token
                if not current_api_token:
                    logger.info("[SYNC_URL_FETCH] API token not found on instance, attempting nested sync fetch for API token...")
                    init_token_params = {'method': 'deezer.getUserData', 'input': '3',
                                       'api_version': '1.0', 'api_token': ''}
                    try:
                        init_token_response = sync_session.get(
                            self.PRIVATE_API_BASE, params=init_token_params, timeout=10
                        )
                        init_token_response.raise_for_status()
                        init_token_data = init_token_response.json()
                        if (init_token_data.get('error') and len(init_token_data['error']) > 0) or 'results' not in init_token_data:
                            logger.error(f"[SYNC_URL_FETCH] Failed nested API token fetch: Invalid response {init_token_data}")
                            return None
                        initial_api_token = init_token_data.get('results', {}).get('checkForm', '')
                        if initial_api_token:
                            logger.info(f"[SYNC_URL_FETCH] Successfully obtained nested API token: {initial_api_token[:5]}...")
                            current_api_token = initial_api_token
                            self.api_token = initial_api_token # Store on instance
                            self.csrf_token = initial_api_token # Store on instance
                        else:
                            logger.error("[SYNC_URL_FETCH] Nested API token fetch failed: 'checkForm' missing from response.")
                            return None
                    except requests.exceptions.RequestException as init_token_err:
                        logger.error(f"[SYNC_URL_FETCH] HTTP error during nested API token fetch: {init_token_err}")
                        return None
                    except Exception as init_inner_e:
                        logger.error(f"[SYNC_URL_FETCH] Unexpected error during nested API token fetch: {init_inner_e}", exc_info=True)
                        return None
                
                # Now, ensure license_token using the current_api_token
                if not self.license_token: # Check instance's license_token
                    logger.info(f"[SYNC_URL_FETCH] License token not found on instance. Attempting sync fetch for license token using API token {current_api_token[:5] if current_api_token else 'None'}...")
                    if not current_api_token: # Should have been fetched above if was None
                         logger.error("[SYNC_URL_FETCH] Cannot fetch license token: API token is unexpectedly still unavailable.")
                         return None

                    license_params = {
                        'method': 'deezer.getUserData', 'input': '3',
                        'api_version': '1.0', 'api_token': current_api_token
                    }
                    try:
                        lic_response = sync_session.get(self.PRIVATE_API_BASE, params=license_params, timeout=10)
                        lic_response.raise_for_status()
                        lic_data = lic_response.json()

                        if (lic_data.get('error') and len(lic_data['error']) > 0) or 'results' not in lic_data:
                            logger.error(f"[SYNC_URL_FETCH] Failed sync license token fetch: Invalid response {lic_data}")
                            self.license_token = None # Clear any old one
                        else:
                            user_data_results = lic_data.get('results', {})
                            user_dict = user_data_results.get('USER')
                            options_dict = user_dict.get('OPTIONS') if isinstance(user_dict, dict) else None
                            fetched_license_token = options_dict.get('license_token', '') if isinstance(options_dict, dict) else ''
                            if fetched_license_token:
                                self.license_token = fetched_license_token # Store on instance
                                logger.info(f"[SYNC_URL_FETCH] Successfully fetched sync license token: {self.license_token[:10]}...")
                            else:
                                 logger.warning("[SYNC_URL_FETCH] Sync license token fetch succeeded but token was empty in response.")
                                 self.license_token = None # Ensure it's None
                    except requests.exceptions.RequestException as lic_err:
                        logger.error(f"[SYNC_URL_FETCH] HTTP error fetching sync license token: {lic_err}")
                        self.license_token = None 
                    except Exception as lic_inner_e:
                        logger.error(f"[SYNC_URL_FETCH] Unexpected error fetching sync license token: {lic_inner_e}", exc_info=True)
                        self.license_token = None
                
                # Final check for license token
                if not self.license_token:
                    logger.error("[SYNC_URL_FETCH] License token unavailable after all attempts. Cannot get download URL.")
                    return None

                # --- 3. Get Track Info (Private API, handles its own token logic) --- 
                logger.debug("[SYNC_URL_FETCH] Attempting to get track details via get_track_details_sync_private...")
                track_info = self.get_track_details_sync_private(track_id) # This uses its own session and token logic
                if not track_info:
                    logger.error(f"[SYNC_URL_FETCH] Failed to get sync track details for {track_id} via get_track_details_sync_private.")
                    return None

                track_token_from_details = track_info.get('track_token') # Ensure using the correct key from processed data
                if not track_token_from_details:
                     logger.error(f"[SYNC_URL_FETCH] No 'track_token' found in processed track_info for {track_id}. track_info: {track_info.keys() if track_info else 'None'}")
                     return None
                logger.debug(f"[SYNC_URL_FETCH] Obtained track_token from details: {track_token_from_details[:10]}...")


                # --- 4. Get Download URL (Media API) --- 
                quality_format_map = {
                    'MP3_128': 'MP3_128', 'MP3_320': 'MP3_320', 'FLAC': 'FLAC'
                }
                api_format = quality_format_map.get(quality, 'MP3_320')

                payload = {
                    "license_token": self.license_token, # Use the now confirmed license_token
                    "media": [{"type": "FULL", "formats": [{"cipher": "BF_CBC_STRIPE", "format": api_format}]}],
                    "track_tokens": [track_token_from_details]
                }

                media_url = "https://media.deezer.com/v1/get_url"
                logger.debug(f"[SYNC_URL_FETCH] Calling {media_url} with payload: {{license_token: '{self.license_token[:10]}...', ..., track_tokens: ['{track_token_from_details[:10]}...']}}")

                # Use the *same* sync_session for this call to maintain cookies if necessary (though typically token-based)
                media_response = sync_session.post(media_url, json=payload, timeout=15)
                media_response.raise_for_status()
                media_data = media_response.json()
                logger.debug(f"[SYNC_URL_FETCH] {media_url} response: {str(media_data)[:200]}...") # Log snippet

                if 'error' in media_data and media_data['error']: # Check for explicit error array
                    logger.error(f"[SYNC_URL_FETCH] Media API error: {media_data['error']}")
                    return None

                # Check new deezer api response structure
                if 'data' in media_data and isinstance(media_data['data'], list) and media_data['data']:
                    first_item_data = media_data['data'][0]
                    if 'errors' in first_item_data and first_item_data['errors']:
                        errors = first_item_data['errors']
                        logger.error(f"[SYNC_URL_FETCH] Media API returned errors in 'data[0].errors': {errors}")
                        
                        # Check for specific error codes and provide better error messages
                        if errors and isinstance(errors, list) and len(errors) > 0:
                            first_error = errors[0]
                            error_code = first_error.get('code')
                            error_message = first_error.get('message', 'Unknown error')
                            
                            if error_code == 2002:
                                # This is a licensing/rights issue, not a technical problem
                                return f"RIGHTS_ERROR: Track not available - {error_message}"
                            elif error_code in [2001, 4]:  # Other common rights-related errors
                                return f"RIGHTS_ERROR: Geographic restriction or subscription required - {error_message}"
                            else:
                                # Generic error
                                return f"API_ERROR: {error_message} (Code: {error_code})"
                        
                        return None
                    if 'media' in first_item_data and isinstance(first_item_data['media'], list) and first_item_data['media']:
                        media_item = first_item_data['media'][0]
                        if 'sources' in media_item and isinstance(media_item['sources'], list) and media_item['sources']:
                            sources = media_item['sources']
                            final_url = sources[0].get('url')
                            if final_url:
                                 logger.info(f"[SYNC_URL_FETCH] Successfully got sync download URL: {final_url[:70]}...")
                                 return final_url
                            else:
                                 logger.error("[SYNC_URL_FETCH] No 'url' found in media API sources[0].")
                                 return None
                        else:
                            logger.error("[SYNC_URL_FETCH] 'sources' array missing or empty in media_item.")
                            return None
                    else:
                        logger.error("[SYNC_URL_FETCH] 'media' array missing or empty in first_item_data.")
                        return None
                else:
                    logger.error(f"[SYNC_URL_FETCH] Unexpected response structure from {media_url}: 'data' array missing or empty. Response: {str(media_data)[:300]}")
                    return None

            except requests.exceptions.RequestException as e:
                logger.error(f"[SYNC_URL_FETCH] Request error during sync URL retrieval for {track_id}: {e}")
                return None
            except Exception as e:
                logger.error(f"[SYNC_URL_FETCH] Unexpected error during sync URL retrieval for {track_id}: {e}", exc_info=True)
                return None

    async def get_album_tracks(self, album_id: int, limit: int = 50, index: int = 0) -> list:
        """Fetches tracks for a given album ID using limit and index parameters."""
        session = await self._get_session()
        if not session:
            logger.error(f"Cannot get album tracks for {album_id}: no session.")
            return [] # Return empty list on session error

        request_url = f"{self.PUBLIC_API_BASE}/album/{album_id}/tracks"
        params = {"limit": limit, "index": index}
        
        try:
            logger.info(f"Fetching tracks for album {album_id} from: {request_url} with params: {params}")
            async with session.get(request_url, params=params) as response:
                if response.status != 200:
                    logger.error(f"Failed to get album tracks for {album_id}: HTTP {response.status} - {await response.text()}")
                    return [] # Return empty list on HTTP error
                
                data = await response.json()
                if not data or 'data' not in data:
                    logger.error(f"Invalid album tracks response for {album_id}: 'data' field missing. Response: {data}")
                    return [] # Return empty list on invalid data
                
                tracks_data = data.get('data', [])
                logger.info(f"Successfully fetched {len(tracks_data)} tracks for album {album_id}.")
                return tracks_data
        except aiohttp.ClientError as e: # Specific exception for network issues with aiohttp
            logger.error(f"Network error fetching tracks for album {album_id}: {e}")
            return []
        except json.JSONDecodeError as e: # Specific exception for JSON parsing issues
            logger.error(f"JSON decode error fetching tracks for album {album_id}: {e}. Response: {await response.text()[:200]}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching tracks for album {album_id}: {e}", exc_info=True)
            return []

    async def get_artist_details(self, artist_id: int) -> dict | None:
        """
        Fetches detailed information about a specific artist from the Deezer API.

        Args:
            artist_id: The ID of the artist.

        Returns:
            A dictionary containing artist details, or None if an error occurs.
        """
        # For basic artist info, we don't need tokens - just a session
        session = await self._get_session()
        if not session:
             logger.error(f"Session not available for get_artist_details (artist_id: {artist_id}).")
             return None

        url = f"{self.PUBLIC_API_BASE}/artist/{artist_id}"
        extended_url = f"{self.PRIVATE_API_BASE}?method=deezer.getArtistData&input=3&api_version=1.0&api_token={self.api_token or ''}&cid=0&artist_id={artist_id}"
        # It seems the original log was trying to call a method that would use PRIVATE_API_BASE
        # For now, let's assume we want public details first, and can adjust if more private data is needed.
        # Sticking to the public API for general details is usually safer.
        # The error was in load_artist_data calling get_artist_details which then tried to call _ensure_session_and_tokens
        # The actual API call in get_artist_details was not shown in the traceback, but let's assume it's the public one for now.

        cache_key = f"artist_details_{artist_id}"
        cached_data = self._load_from_cache(cache_key)
        if cached_data:
            logger.debug(f"Using cached artist details for {artist_id}.")
            return cached_data

        try:
            logger.info(f"Fetching artist details for {artist_id} from: {url}")
            async with session.get(url) as response:
                response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
                data = await response.json()
                if 'error' in data and data['error']:
                    logger.error(f"API error for artist {artist_id}: {data['error']}")
                    return None
                logger.debug(f"Successfully fetched details for artist {artist_id}.")
                self._save_to_cache(cache_key, data)
                return data
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching artist {artist_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching artist {artist_id}: {e}", exc_info=True)
            return None

    async def get_artist_top_tracks(self, artist_id: int, limit: int = 25, index: int = 0) -> list:
        """
        Get top tracks for a specific artist.
        
        Args:
            artist_id (int): The artist ID to fetch top tracks for
            limit (int): Maximum number of tracks to fetch (default: 25)
            index (int): Starting index for pagination (default: 0)
            
        Returns:
            list: List of track objects or empty list if none found/error
        """
        if not artist_id:
            logger.error("get_artist_top_tracks: artist_id is required.")
            return []
        
        logger.info(f"[DeezerAPI] Getting top tracks for artist {artist_id}, limit={limit}, index={index}")
        
        cache_key = f"artist_{artist_id}_top_tracks_limit{limit}_index{index}"
        cached_data = self._load_from_cache(cache_key)
        if cached_data is not None:
            logger.debug(f"[DeezerAPI] Returning cached top tracks for artist {artist_id}")
            return cached_data.get('data', [])

        session = await self._get_session()
        if not session:
            logger.error(f"[DeezerAPI] Failed to get session for fetching top tracks for artist {artist_id}")
            return []

        url = f"{self.PUBLIC_API_BASE}/artist/{artist_id}/top?limit={limit}&index={index}"
        logger.info(f"[DeezerAPI] Fetching artist top tracks from: {url}")
        
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    response_text = await response.text()
                    try:
                        data = json.loads(response_text)
                        if 'data' in data and isinstance(data['data'], list):
                            tracks = data['data']
                            logger.info(f"[DeezerAPI] Successfully fetched {len(tracks)} top tracks for artist {artist_id}")
                            self._save_to_cache(cache_key, data)
                            return tracks
                        elif 'error' in data:
                            logger.error(f"[DeezerAPI] API error fetching top tracks for artist {artist_id}: {data['error']}")
                            return []
                        else:
                            logger.warning(f"[DeezerAPI] Unexpected data structure for top tracks: {data}")
                            return []
                    except json.JSONDecodeError as e:
                        logger.error(f"[DeezerAPI] JSON decode error for top tracks artist {artist_id}: {e}. Response: {response_text[:200]}")
                        return []
                else:
                    logger.error(f"[DeezerAPI] Failed to fetch top tracks for artist {artist_id}. Status: {response.status}")
                    return []
        except aiohttp.ClientError as e:
            logger.error(f"[DeezerAPI] Network error fetching top tracks for artist {artist_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"[DeezerAPI] Unexpected error fetching top tracks for artist {artist_id}: {e}", exc_info=True)
            return []

    async def get_artist_albums_generic(self, artist_id: int, limit: int = 25, index: int = 0) -> Optional[List[Dict]]:
        """Fetches albums for a given artist from the public Deezer API."""
        if not artist_id:
            logger.error("get_artist_albums_generic: artist_id is required.")
            return None

        cache_key = f"artist_{artist_id}_albums_limit{limit}_index{index}"
        cached_data = self._load_from_cache(cache_key)
        if cached_data is not None:
            logger.debug(f"Returning cached albums for artist {artist_id}")
            return cached_data.get('data')

        session = await self._get_session()
        if not session:
            return None

        url = f"{self.PUBLIC_API_BASE}/artist/{artist_id}/albums?limit={limit}&index={index}"
        logger.info(f"Fetching artist albums from: {url}")
        response_text = ""
        
        try:
            # Use a longer timeout for artist albums requests
            timeout = aiohttp.ClientTimeout(total=20)  # Increase timeout to 20 seconds
            async with session.get(url, timeout=timeout) as response:
                response_text = await response.text()
                if response.status == 200:
                    data = json.loads(response_text)
                    if 'data' in data and isinstance(data['data'], list):
                        self._save_to_cache(cache_key, data)
                        return data['data']
                    elif 'error' in data:
                        logger.error(f"API error fetching albums for artist {artist_id}: {data['error']}")
                        return None
                    else:
                        logger.warning(f"Unexpected data structure for albums: {data}")
                        return None
                else:
                    logger.error(f"Failed to fetch albums for artist {artist_id}. Status: {response.status}, Response: {response_text[:200]}")
                    return None
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching albums for artist {artist_id}")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching albums for artist {artist_id}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for albums artist {artist_id}: {e}. Response: {response_text[:200]}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching albums for artist {artist_id}: {e}", exc_info=True)
            return None

    async def get_playlist_tracks(self, playlist_id: int, limit: int = 500) -> Optional[List[Dict]]:
        """
        Get tracks for a specific playlist.

        Args:
            playlist_id (int): The ID of the playlist.
            limit (int): Maximum number of tracks to retrieve.

        Returns:
            Optional[List[Dict]]: A list of track details, or None on error.
        """
        session = await self._get_session()
        if not session:
            logger.error(f"Cannot get playlist tracks for {playlist_id}: no session.")
            return None

        request_url = f"{self.PUBLIC_API_BASE}/playlist/{playlist_id}/tracks?limit={limit}"
        
        try:
            logger.info(f"Fetching tracks for playlist {playlist_id} from: {request_url}")
            async with session.get(request_url) as response:
                if response.status != 200:
                    logger.error(f"Failed to get playlist tracks for {playlist_id}: HTTP {response.status} - {await response.text()}")
                    return None
                
                data = await response.json()
                if not data or 'data' not in data:
                    logger.error(f"Invalid playlist tracks response for {playlist_id}: 'data' field missing. Response: {data}")
                    return None
                
                tracks_data = data.get('data', [])
                logger.info(f"Successfully fetched {len(tracks_data)} tracks for playlist {playlist_id}.")
                return tracks_data
        except Exception as e:
            logger.error(f"Unexpected error fetching tracks for playlist {playlist_id}: {e}")
            return None 

    async def get_playlist_details(self, playlist_id: int) -> Optional[Dict]:
        """Get detailed information for a specific playlist using public API."""
        session = await self._get_session()
        if not session: 
            logger.error(f"Failed to get session for playlist details {playlist_id}")
            return None

        cache_key = f"playlist_details_{playlist_id}"
        # TODO: Consider cache duration specific to playlists if needed
        cached_data = self._load_from_cache(cache_key)
        if cached_data:
            logger.debug(f"Loaded playlist details for {playlist_id} from cache.")
            return cached_data

        try:
            url = f"{self.PUBLIC_API_BASE}/playlist/{playlist_id}"
            logger.debug(f"Fetching playlist details for {playlist_id} from {url}")
            async with session.get(url) as response:
                # response.raise_for_status() # Raise an exception for bad status codes
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Error fetching playlist details for {playlist_id}: HTTP {response.status} - {error_text}")
                    return None
                
                data = await response.json()
                if 'error' in data:
                    logger.warning(f"API error fetching playlist details for {playlist_id}: {data['error']}")
                    return None
                
                self._save_to_cache(cache_key, data)
                logger.debug(f"Fetched and cached playlist details for {playlist_id}.")
                return data
        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching playlist details for {playlist_id}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error fetching playlist details for {playlist_id}: {e}. Response: {await response.text()[:200]}") # Escaped '''
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching playlist details for {playlist_id}: {e}", exc_info=True)
            return None

    async def get_artist(self, artist_id: int) -> dict | None:
        """
        Get details for a specific artist.
        
        This is an alias for get_artist_details for backward compatibility.
        
        Args:
            artist_id (int): The artist ID to fetch
            
        Returns:
            dict | None: Artist data or None if not found/error
        """
        return await self.get_artist_details(artist_id)

    async def get_track_lyrics(self, track_id: int) -> Optional[Dict]:
        """
        Get synchronized lyrics for a track using Deezer private API.
        
        Args:
            track_id (int): The track ID to fetch lyrics for
            
        Returns:
            Optional[Dict]: Lyrics data containing sync info and plain text, or None if not found/error
        """
        session = await self._get_session()
        if not session:
            logger.error(f"Cannot get lyrics for track {track_id}: no session.")
            return None

        # Ensure tokens are available
        if not await self._ensure_session_and_tokens():
            logger.error(f"Cannot get lyrics for track {track_id}: failed to get tokens.")
            return None

        try:
            params = {
                'method': 'song.getLyrics',
                'api_version': '1.0',
                'api_token': self.api_token,
                'input': '3',
                'cid': int(time.time())
            }
            json_data = {'sng_id': str(track_id)}
            
            # Headers to simulate US region for better lyrics availability
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
                'X-Forwarded-For': '8.8.8.8',  # Google DNS (US)
                'CF-IPCountry': 'US',  # Cloudflare country header
                'X-Real-IP': '8.8.8.8'
            }
            
            logger.debug(f"Fetching lyrics for track {track_id} with US region headers")
            
            async with session.post(
                self.PRIVATE_API_BASE,
                params=params,
                json=json_data,
                headers=headers
            ) as response:
                if response.status != 200:
                    logger.error(f"Failed to get lyrics for track {track_id}: HTTP {response.status}")
                    return None
                    
                data = await response.json()
                
                if 'error' in data and data['error']:
                    logger.warning(f"Lyrics API returned error for track {track_id}: {data['error']}")
                    return None
                
                if 'results' not in data:
                    logger.warning(f"No lyrics results found for track {track_id}")
                    return None
                
                lyrics_data = data['results']
                logger.debug(f"Successfully fetched lyrics for track {track_id} with US region")
                return lyrics_data
                
        except Exception as e:
            logger.error(f"Error fetching lyrics for track {track_id}: {e}", exc_info=True)
            return None

    def get_track_lyrics_sync(self, track_id: int) -> Optional[Dict]:
        """
        Get synchronized lyrics for a track synchronously.
        
        This is a synchronous version suitable for use in background threads
        where the asyncio event loop is not available.
        
        Args:
            track_id (int): The track ID to fetch lyrics for
            
        Returns:
            Optional[Dict]: Lyrics data containing sync info and plain text, or None if not found/error
        """
        with requests.Session() as sync_session:
            try:
                # Set ARL cookie
                if self.arl:
                    sync_session.cookies.set('arl', self.arl, domain='.deezer.com')
                else:
                    logger.error("ARL token is missing. Cannot get lyrics.")
                    return None

                # Enhanced headers to simulate US region for better lyrics availability
                # Using multiple US IP ranges and comprehensive headers
                us_ips = [
                    '173.252.74.22',   # Facebook US server
                    '142.250.191.14',  # Google US server  
                    '23.185.0.2',      # Akamai US CDN
                    '151.101.193.140'  # Reddit US server
                ]
                import random
                us_ip = random.choice(us_ips)
                
                sync_session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'empty',
                    'Sec-Fetch-Mode': 'cors',
                    'Sec-Fetch-Site': 'same-origin',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                    # IP spoofing headers
                    'X-Forwarded-For': us_ip,
                    'X-Real-IP': us_ip,
                    'X-Originating-IP': us_ip,
                    'X-Remote-IP': us_ip,
                    'X-Remote-Addr': us_ip,
                    'X-Client-IP': us_ip,
                    # Cloudflare/CDN headers
                    'CF-IPCountry': 'US',
                    'CF-RAY': '8b8b8b8b8b8b8b8b-ORD',
                    'CF-Visitor': '{"scheme":"https"}',
                    # ISP headers
                    'X-Forwarded-Country': 'US',
                    'X-Country-Code': 'US',
                    'X-GeoIP-Country': 'US'
                })

                # Get API token if not available
                current_api_token = self.api_token
                if not current_api_token:
                    logger.info("API token not found, attempting synchronous fetch for lyrics...")
                    init_token_params = {
                        'method': 'deezer.getUserData', 'input': '3', 
                        'api_version': '1.0', 'api_token': ''
                    }
                    try:
                        init_token_response = sync_session.get(
                            self.PRIVATE_API_BASE, params=init_token_params, timeout=10
                        )
                        init_token_response.raise_for_status()
                        init_token_data = init_token_response.json()
                        
                        if (init_token_data.get('error') and len(init_token_data['error']) > 0) or 'results' not in init_token_data:
                            logger.error(f"Failed to get token for lyrics: {init_token_data}")
                            return None
                            
                        current_api_token = init_token_data.get('results', {}).get('checkForm', '')
                        if current_api_token:
                            self.api_token = current_api_token
                            self.csrf_token = current_api_token
                        else:
                            logger.error("Failed to get token for lyrics: 'checkForm' missing.")
                            return None
                            
                    except requests.exceptions.RequestException as e:
                        logger.error(f"HTTP error during token fetch for lyrics: {e}")
                        return None

                if not current_api_token:
                    logger.error("API token is missing after fetch attempt. Cannot get lyrics.")
                    return None

                # Inner function to make API request with retry logic
                def make_lyrics_request(api_token_to_use, retry=True):
                    params = {
                        'method': 'song.getLyrics',
                        'api_version': '1.0',
                        'api_token': api_token_to_use,
                        'input': '3',
                        'cid': int(time.time())
                    }
                    json_data = {'sng_id': str(track_id)}
                    
                    logger.debug(f"Fetching lyrics for track {track_id} (sync) with enhanced US region spoofing (IP: {us_ip})...")
                    
                    try:
                        response = sync_session.post(
                            self.PRIVATE_API_BASE,
                            params=params,
                            json=json_data,
                            timeout=10
                        )
                        response.raise_for_status()
                        data = response.json()
                        
                        if 'error' in data and data['error']:
                            logger.warning(f"Lyrics API returned error for track {track_id}: {data['error']}")
                            # Check for VALID_TOKEN_REQUIRED error (can be dict or list)
                            if isinstance(data['error'], dict) and 'VALID_TOKEN_REQUIRED' in data['error']:
                                if retry:
                                    logger.info("Attempting sync token refresh for lyrics (VALID_TOKEN_REQUIRED found)...")
                                    refreshed_token = self._refresh_token_sync(sync_session)
                                    if refreshed_token:
                                        return make_lyrics_request(refreshed_token, retry=False)
                                    else:
                                        logger.error("Token refresh failed for lyrics. Cannot get lyrics.")
                                        return None
                                else:
                                    logger.error("Token still invalid after refresh attempt for lyrics.")
                                    return None
                            return None
                        
                        if 'results' not in data:
                            logger.warning(f"No lyrics results found for track {track_id}")
                            return None
                        
                        lyrics_data = data['results']
                        logger.debug(f"Successfully fetched lyrics for track {track_id} (sync) with enhanced US region spoofing")
                        return lyrics_data
                        
                    except requests.exceptions.RequestException as e:
                        logger.error(f"HTTP error during lyrics fetch for track {track_id}: {e}")
                        return None

                # Make the request with retry logic
                return make_lyrics_request(current_api_token)
                
            except Exception as e:
                logger.error(f"Error fetching lyrics for track {track_id} (sync): {e}", exc_info=True)
                return None