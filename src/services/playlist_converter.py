"""Service for converting Spotify playlists to Deezer search results."""

import logging
import asyncio
from typing import Dict, List, Optional, Tuple
from fuzzywuzzy import fuzz
from services.spotify_api import SpotifyAPI
from services.deezer_api import DeezerAPI

logger = logging.getLogger(__name__)

class PlaylistConverter:
    """Service for converting Spotify playlists to Deezer tracks."""
    
    def __init__(self, spotify_api: SpotifyAPI, deezer_api: DeezerAPI):
        """Initialize the playlist converter.
        
        Args:
            spotify_api (SpotifyAPI): Spotify API service
            deezer_api (DeezerAPI): Deezer API service
        """
        self.spotify_api = spotify_api
        self.deezer_api = deezer_api
    
    def calculate_match_score(self, spotify_track: Dict, deezer_track: Dict) -> float:
        """Calculate how well a Deezer track matches a Spotify track.
        
        Args:
            spotify_track (Dict): Spotify track information
            deezer_track (Dict): Deezer track information
            
        Returns:
            float: Match score between 0 and 100
        """
        scores = []
        
        # Compare track titles
        spotify_title = spotify_track.get('name', '').lower().strip()
        deezer_title = deezer_track.get('title', '').lower().strip()
        if spotify_title and deezer_title:
            title_score = fuzz.ratio(spotify_title, deezer_title)
            scores.append(title_score * 0.4)  # 40% weight for title
        
        # Compare artists
        spotify_artist = spotify_track.get('artist', '').lower().strip()
        deezer_artist = deezer_track.get('artist', {}).get('name', '').lower().strip()
        if spotify_artist and deezer_artist:
            artist_score = fuzz.ratio(spotify_artist, deezer_artist)
            scores.append(artist_score * 0.3)  # 30% weight for artist
        
        # Compare albums
        spotify_album = spotify_track.get('album', '').lower().strip()
        deezer_album = deezer_track.get('album', {}).get('title', '').lower().strip()
        if spotify_album and deezer_album:
            album_score = fuzz.ratio(spotify_album, deezer_album)
            scores.append(album_score * 0.2)  # 20% weight for album
        
        # Compare duration (if available)
        spotify_duration = spotify_track.get('duration_ms', 0) / 1000  # Convert to seconds
        deezer_duration = deezer_track.get('duration', 0)
        if spotify_duration > 0 and deezer_duration > 0:
            duration_diff = abs(spotify_duration - deezer_duration)
            # Perfect match if within 3 seconds, decreasing score for larger differences
            if duration_diff <= 3:
                duration_score = 100
            elif duration_diff <= 10:
                duration_score = 80
            elif duration_diff <= 30:
                duration_score = 60
            else:
                duration_score = 30
            scores.append(duration_score * 0.1)  # 10% weight for duration
        
        # Return average score
        return sum(scores) / len(scores) if scores else 0
    
    async def search_deezer_for_track(self, spotify_track: Dict) -> Optional[List[Dict]]:
        """Search Deezer for a Spotify track.
        
        Args:
            spotify_track (Dict): Spotify track information
            
        Returns:
            Optional[List[Dict]]: List of Deezer search results or None
        """
        try:
            # Format search query
            query = self.spotify_api.format_search_query(spotify_track)
            if not query:
                logger.warning(f"Could not format search query for track: {spotify_track}")
                return None
            
            logger.debug(f"Searching Deezer for: '{query}'")
            
            # Search Deezer for tracks
            search_results = await self.deezer_api.search(query, search_type='track', limit=10)
            
            if not search_results:
                logger.debug(f"No Deezer results found for: '{query}'")
                return None
            
            # Calculate match scores and sort by best match
            scored_results = []
            for deezer_track in search_results:
                match_score = self.calculate_match_score(spotify_track, deezer_track)
                scored_results.append({
                    'track': deezer_track,
                    'match_score': match_score,
                    'spotify_track': spotify_track
                })
            
            # Sort by match score (highest first)
            scored_results.sort(key=lambda x: x['match_score'], reverse=True)
            
            logger.debug(f"Found {len(scored_results)} Deezer matches for '{query}', best match score: {scored_results[0]['match_score']:.1f}")
            
            return scored_results
            
        except Exception as e:
            logger.error(f"Error searching Deezer for track '{spotify_track.get('name', 'Unknown')}': {e}")
            return None
    
    def get_spotify_playlist_data(self, spotify_url: str) -> Optional[Dict]:
        """Get Spotify playlist data only (synchronous, for worker threads).
        
        Args:
            spotify_url (str): Spotify playlist URL
            
        Returns:
            Optional[Dict]: Spotify playlist data or None if failed
        """
        try:
            logger.info(f"Fetching Spotify playlist data for: {spotify_url}")
            
            # Get playlist data from Spotify (synchronous)
            playlist_data = self.spotify_api.get_playlist_tracks_sync(spotify_url)
            if not playlist_data:
                logger.error("Failed to fetch playlist data from Spotify")
                return None
            
            logger.info(f"Retrieved {len(playlist_data['tracks'])} tracks from Spotify playlist '{playlist_data['playlist_info'].get('name', 'Unknown')}'")
            
            return playlist_data
            
        except Exception as e:
            logger.error(f"Error fetching Spotify playlist: {e}")
            return None
    
    async def convert_tracks_to_deezer(self, spotify_tracks: List[Dict], progress_callback=None) -> List[Dict]:
        """Convert Spotify tracks to Deezer matches (async, for main thread).
        
        Args:
            spotify_tracks (List[Dict]): List of Spotify track data
            progress_callback (callable): Optional callback for progress updates
            
        Returns:
            List[Dict]: List of conversion results
        """
        try:
            total_tracks = len(spotify_tracks)
            logger.info(f"Converting {total_tracks} tracks to Deezer matches")
            
            converted_tracks = []
            
            for i, spotify_track in enumerate(spotify_tracks):
                try:
                    # Update progress
                    if progress_callback:
                        progress = (i / total_tracks) * 100
                        progress_callback(progress, f"Searching for: {spotify_track.get('name', 'Unknown')}")
                    
                    # Search Deezer for this track
                    deezer_matches = await self.search_deezer_for_track(spotify_track)
                    
                    if deezer_matches and len(deezer_matches) > 0:
                        # Use the best match
                        best_match = deezer_matches[0]
                        converted_tracks.append({
                            'spotify_track': spotify_track,
                            'deezer_track': best_match['track'],
                            'match_confidence': best_match['match_score'],
                            'all_matches': deezer_matches[:5]  # Keep top 5 matches
                        })
                        
                        logger.debug(f"Match found for '{spotify_track.get('name')}': {best_match['match_score']:.1f}% similarity")
                    else:
                        # No matches found
                        converted_tracks.append({
                            'spotify_track': spotify_track,
                            'deezer_track': None,
                            'match_confidence': 0,
                            'all_matches': []
                        })
                        
                        logger.warning(f"No Deezer match found for: '{spotify_track.get('name')}' by {spotify_track.get('artist')}")
                    
                    # Small delay to avoid overwhelming the API
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logger.error(f"Error processing track '{spotify_track.get('name', 'Unknown')}': {e}")
                    converted_tracks.append({
                        'spotify_track': spotify_track,
                        'deezer_track': None,
                        'match_confidence': 0,
                        'all_matches': [],
                        'error': str(e)
                    })
            
            # Final progress update
            if progress_callback:
                progress_callback(100, "Conversion complete!")
            
            successful_matches = sum(1 for track in converted_tracks if track.get('deezer_track'))
            logger.info(f"Track conversion complete: {successful_matches}/{total_tracks} tracks found")
            
            return converted_tracks
            
        except Exception as e:
            logger.error(f"Error converting tracks to Deezer: {e}")
            return []
    
    def format_for_display(self, conversion_results: Dict) -> List[Dict]:
        """Format conversion results for display in the UI.
        
        Args:
            conversion_results (Dict): Results from convert_tracks_to_deezer()
            
        Returns:
            List[Dict]: List of tracks formatted for SearchResultCard display
        """
        formatted_tracks = []
        
        # Handle new format from convert_tracks_to_deezer
        if 'tracks' in conversion_results:
            # New format
            tracks = conversion_results['tracks']
        else:
            # Old format compatibility
            tracks = conversion_results.get('matches', [])
        
        for track_match in tracks:
            deezer_track = track_match.get('deezer_track')
            spotify_track = track_match.get('spotify_track')
            match_score = track_match.get('match_confidence', track_match.get('match_score', 0))
            
            if deezer_track:
                # Add match score and Spotify info to the Deezer track data
                track_data = dict(deezer_track)  # Copy the original track data
                track_data['spotify_info'] = spotify_track
                track_data['match_score'] = match_score
                track_data['conversion_source'] = 'spotify_playlist'
                formatted_tracks.append(track_data)
            else:
                # Create a placeholder entry for failed matches
                placeholder_track = {
                    'id': f"spotify_{spotify_track.get('spotify_id', 'unknown')}",
                    'type': 'track',
                    'title': spotify_track.get('name', 'Unknown Track'),
                    'artist': {'name': spotify_track.get('artist', 'Unknown Artist')},
                    'album': {'title': spotify_track.get('album', 'Unknown Album')},
                    'duration': spotify_track.get('duration_ms', 0) // 1000,
                    'spotify_info': spotify_track,
                    'match_score': 0,
                    'conversion_source': 'spotify_playlist',
                    'match_failed': True,
                    'preview': None,
                    'readable': False
                }
                formatted_tracks.append(placeholder_track)
        
        return formatted_tracks 