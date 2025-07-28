"""
Comparison Engine
Compares local music library with Deezer's catalog to identify missing tracks
"""

import asyncio
import logging
from typing import Dict, List, Set, Tuple, Optional, Any
from fuzzywuzzy import fuzz
from collections import defaultdict
import re

from ..services.deezer_service import DeezerService

logger = logging.getLogger(__name__)


class ComparisonEngine:
    """Engine for comparing local library with Deezer catalog"""
    
    def __init__(self, deezer_service: DeezerService, config=None):
        self.deezer_service = deezer_service
        self.config = config
        # Use configurable thresholds if config is provided, otherwise use defaults
        if config:
            self.track_match_threshold = config.get_track_match_threshold()
            self.album_match_threshold = config.get_album_match_threshold()
        else:
            self.track_match_threshold = 80  # Default track match threshold
            self.album_match_threshold = 70  # Default album match threshold (more lenient)
        
    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison"""
        if not text:
            return ""
        # Remove special characters and convert to lowercase
        text = re.sub(r'[^\w\s]', '', text.lower())
        # Remove extra whitespace
        text = ' '.join(text.split())
        return text
        
    def normalize_album_title(self, album_title: str) -> str:
        """Improved album title normalization with better handling of edge cases"""
        if not album_title:
            return ""
        
        # Store original for special cases
        original = album_title.strip()
        normalized = original.lower()
        
        # Handle numeric-only titles (like "311") - keep them as-is
        if re.match(r'^\d+$', normalized):
            return normalized
        
        # Handle Roman numerals (I, II, III, IV, V, etc.)
        if re.match(r'^[ivxlcdm]+$', normalized):
            return normalized
            
        # Replace common separators with spaces
        normalized = re.sub(r'[&+]', ' and ', normalized)
        normalized = re.sub(r'[-_/]', ' ', normalized)
        
        # Remove edition/version indicators but be more conservative
        edition_patterns = [
            r'\s*\(.*?remaster.*?\)',
            r'\s*\(.*?deluxe.*?\)',
            r'\s*\(.*?expanded.*?\)',
            r'\s*\(.*?special.*?edition.*?\)',
            r'\s*\(.*?anniversary.*?\)',
            r'\s*\(.*?bonus.*?\)',
            r'\s*\(.*?collector.*?\)',
            r'\s*\(.*?limited.*?\)',
        ]
        
        for pattern in edition_patterns:
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)
        
        # Remove extra punctuation but preserve important characters
        normalized = re.sub(r'[^\w\s\']', ' ', normalized)
        
        # Clean up multiple spaces
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
        
    def deduplicate_similar_albums(self, albums: List[Dict], artist_name: str = "") -> List[Dict]:
        """Remove duplicate/similar albums, keeping the best version of each."""
        if not albums:
            return albums
            
        print(f"=== DEDUPLICATION CALLED FOR {len(albums)} ALBUMS FOR ARTIST: {artist_name} ===")
        logger.info(f"DEBUG: Starting deduplication for {len(albums)} albums for artist: {artist_name}")
        
        # Group albums by similarity
        groups = []
        similarity_threshold = 85  # Higher threshold for more precise deduplication
        
        for album in albums:
            album_title = album.get('title', '')
            
            # Find if this album belongs to an existing group
            added_to_group = False
            for group in groups:
                # Check similarity with the first album in each group
                representative = group[0]
                representative_title = representative.get('title', '')
                
                # Use improved fuzzy matching with artist name
                similarity = self.fuzzy_match_albums(album_title, representative_title, artist_name)
                
                logger.debug(f"DEBUG: Comparing '{album_title}' vs '{representative_title}' = {similarity}%")
                
                if similarity >= similarity_threshold:
                    logger.info(f"DEBUG: Found similar albums: '{album_title}' matches '{representative_title}' ({similarity}%)")
                    group.append(album)
                    added_to_group = True
                    break
            
            if not added_to_group:
                # Create new group
                groups.append([album])
        
        # From each group, select the best album (prefer original over remasters/expanded)
        deduplicated = []
        for group in groups:
            if len(group) == 1:
                deduplicated.append(group[0])
            else:
                # Select the best album from the group
                best_album = self.select_best_album_from_group(group, artist_name)
                deduplicated.append(best_album)
                
                # Log deduplication for debugging
                titles = [a.get('title', 'Unknown') for a in group]
                logger.info(f"Deduplicated {len(group)} similar albums: {titles} -> Selected: {best_album.get('title', 'Unknown')}")
        
        logger.info(f"DEBUG: Deduplication complete - {len(albums)} albums -> {len(deduplicated)} albums")
        return deduplicated
    
    def select_best_album_from_group(self, albums: List[Dict], artist_name: str = "") -> Dict:
        """Select the best album from a group with improved scoring"""
        if len(albums) == 1:
            return albums[0]
        
        def score_album(album):
            title = album.get('title', '').lower()
            score = 0
            
            # Prefer self-titled albums (they're usually the main release)
            if artist_name and self.is_self_titled_album(title, artist_name):
                score -= 20  # Big bonus for self-titled
            
            # Penalize remasters and special editions
            penalty_terms = [
                ('remaster', 10), ('remastered', 10),
                ('deluxe', 8), ('expanded', 8),
                ('special edition', 12), ('anniversary', 12),
                ('bonus', 6), ('collector', 8),
                ('limited', 6), ('extended', 6),
                ('greatest hits', 15), ('best of', 15),
                ('compilation', 15)
            ]
            
            for term, penalty in penalty_terms:
                if term in title:
                    score += penalty
            
            # Prefer albums with more tracks (usually more complete)
            track_count = album.get('nb_tracks', 0)
            if track_count > 0:
                score -= min(track_count * 0.2, 10)  # Bonus for more tracks, capped
            
            # Prefer more popular albums
            fans = album.get('fans', 0)
            if fans > 0:
                score -= min(fans / 2000, 8)  # Popularity bonus, capped
            
            # Prefer earlier release dates (original releases)
            release_date = album.get('release_date', '')
            if release_date:
                try:
                    year = int(release_date[:4])
                    if year < 2000:  # Older releases get bonus
                        score -= 5
                except:
                    pass
            
            return score
        
        # Sort by score and return the best
        albums_with_scores = [(album, score_album(album)) for album in albums]
        albums_with_scores.sort(key=lambda x: x[1])
        
        best_album = albums_with_scores[0][0]
        logger.debug(f"Selected best album: {best_album.get('title')} (score: {albums_with_scores[0][1]})")
        
        return best_album
        # Remove content in parentheses or brackets
        normalized = re.sub(r'\(.*?\)|\[.*?\]', '', normalized)
        # Remove common suffixes/words
        suffixes = [
            'deluxe edition', 'deluxe', 'remastered', 'remaster', 'expanded edition', 'expanded',
            'anniversary edition', 'anniversary', 'bonus tracks', 'bonus track', 'extended',
            'special edition', 'special', 'limited edition', 'limited', 'collector edition',
            'collector', 'complete edition', 'complete', 'definitive edition', 'definitive',
            'ultimate edition', 'ultimate', 'super deluxe', 'super deluxe edition', 'digital deluxe',
            'digital deluxe edition', 'remix', 'mix', 'edit', 'version'
        ]
        for suffix in sorted(suffixes, key=len, reverse=True):
            normalized = re.sub(r'\b' + re.escape(suffix) + r'\b', '', normalized)
        # Remove punctuation
        normalized = re.sub(r'[\W_]+', ' ', normalized)
        # Remove extra spaces
        normalized = ' '.join(normalized.split())
        # Special handling for numeric-only album titles (like "311")
        # These are often self-titled albums and need special care
        if normalized.isdigit() or re.match(r'^\d+$', normalized):
            # Keep numeric titles as is - they're often self-titled albums
            pass
        return normalized.strip()
        
    def is_self_titled_album(self, album_title: str, artist_name: str) -> bool:
        """Check if an album is self-titled (album name matches artist name)"""
        if not album_title or not artist_name:
            return False
            
        # Direct match
        if album_title.lower().strip() == artist_name.lower().strip():
            return True
            
        # Normalized match
        norm_album = self.normalize_album_title(album_title)
        norm_artist = self.normalize_album_title(artist_name)
        
        if norm_album == norm_artist:
            return True
            
        # Handle cases where album has extra words but is essentially self-titled
        # e.g., "Aerosmith (Remastered)" vs "Aerosmith"
        if norm_artist in norm_album or norm_album in norm_artist:
            return True
            
        return False

    def fuzzy_match_albums(self, album1: str, album2: str, artist_name: str = "") -> int:
        """Enhanced fuzzy matching with special handling for self-titled albums"""
        if not album1 or not album2:
            return 0
            
        # Check for exact match first
        if album1.lower().strip() == album2.lower().strip():
            return 100
        
        # Special handling for self-titled albums
        if artist_name:
            is_self1 = self.is_self_titled_album(album1, artist_name)
            is_self2 = self.is_self_titled_album(album2, artist_name)
            
            if is_self1 and is_self2:
                return 100  # Both are self-titled
        
        # Handle numeric albums (like "311")
        if album1.isdigit() and album2.isdigit():
            return 100 if album1 == album2 else 0
            
        # Normalize and compare
        norm1 = self.normalize_album_title(album1)
        norm2 = self.normalize_album_title(album2)
        
        if norm1 == norm2:
            return 100
            
        # Use multiple fuzzy matching algorithms and take the best score
        scores = [
            fuzz.ratio(norm1, norm2),
            fuzz.partial_ratio(norm1, norm2),
            fuzz.token_sort_ratio(norm1, norm2),
            fuzz.token_set_ratio(norm1, norm2)
        ]
        
        # Also try with original strings
        scores.extend([
            fuzz.ratio(album1.lower(), album2.lower()),
            fuzz.token_sort_ratio(album1.lower(), album2.lower())
        ])
        
        return max(scores)
        
    def fuzzy_match(self, str1: str, str2: str) -> int:
        """Calculate fuzzy match score between two strings"""
        # Normalize both strings
        norm1 = self.normalize_text(str1)
        norm2 = self.normalize_text(str2)
        
        # Use token sort ratio for better matching of reordered words
        return fuzz.token_sort_ratio(norm1, norm2)
        
    async def compare_with_deezer(self, local_tracks: List[Dict]) -> Dict[str, Any]:
        """
        Compare local tracks with Deezer catalog
        
        Returns:
            Dict with comparison results including:
            - matched_tracks: Tracks found in both local and Deezer
            - missing_from_local: Tracks in Deezer but not local
            - not_on_deezer: Local tracks not found on Deezer
            - statistics: Comparison statistics
        """
        results = {
            "matched_tracks": [],
            "missing_from_local": [],
            "not_on_deezer": [],
            "artists_analyzed": {},
            "statistics": {
                "total_local_tracks": len(local_tracks),
                "total_deezer_tracks": 0,
                "matched_count": 0,
                "missing_count": 0,
                "not_found_count": 0
            }
        }
        
        # Group local tracks by artist
        tracks_by_artist = defaultdict(list)
        for track in local_tracks:
            artist = track.get("artist", "Unknown Artist")
            tracks_by_artist[artist].append(track)
            
        # Process each artist
        for artist_name, artist_tracks in tracks_by_artist.items():
            if artist_name == "Unknown Artist":
                # Skip unknown artists
                for track in artist_tracks:
                    results["not_on_deezer"].append({
                        "local_track": track,
                        "reason": "Unknown artist"
                    })
                continue
                
            logger.info(f"Analyzing artist: {artist_name}")
            
            # Get Deezer discography for artist
            discography = await self.deezer_service.get_artist_discography(artist_name)
            
            if not discography["artist"]:
                # Artist not found on Deezer
                for track in artist_tracks:
                    results["not_on_deezer"].append({
                        "local_track": track,
                        "reason": "Artist not found on Deezer"
                    })
                results["artists_analyzed"][artist_name] = {
                    "status": "not_found",
                    "local_tracks": len(artist_tracks),
                    "deezer_tracks": 0
                }
                continue
                
            # Store artist analysis info
            deezer_tracks = discography["tracks"]
            results["statistics"]["total_deezer_tracks"] += len(deezer_tracks)
            
            results["artists_analyzed"][artist_name] = {
                "status": "found",
                "deezer_id": discography["artist"]["id"],
                "deezer_name": discography["artist"]["name"],
                "local_tracks": len(artist_tracks),
                "deezer_tracks": len(deezer_tracks),
                "matched": 0,
                "missing": 0,
                "not_found": 0
            }
            
            # Create lookup for local tracks
            local_track_set = set()
            local_track_map = {}
            for track in artist_tracks:
                key = self._create_track_key(track)
                local_track_set.add(key)
                local_track_map[key] = track
                
            # Create lookup for Deezer tracks
            deezer_track_set = set()
            deezer_track_map = {}
            for track in deezer_tracks:
                key = self._create_deezer_track_key(track)
                deezer_track_set.add(key)
                deezer_track_map[key] = track
                
            # Find matches using fuzzy matching
            matched_local = set()
            matched_deezer = set()
            
            for local_key in local_track_set:
                local_track = local_track_map[local_key]
                best_match = None
                best_score = 0
                
                for deezer_key in deezer_track_set:
                    if deezer_key in matched_deezer:
                        continue
                        
                    deezer_track = deezer_track_map[deezer_key]
                    
                    # Calculate match score
                    score = self._calculate_match_score(local_track, deezer_track)
                    
                    if score > best_score and score >= self.track_match_threshold:
                        best_score = score
                        best_match = deezer_key
                        
                if best_match:
                    # Found a match
                    matched_local.add(local_key)
                    matched_deezer.add(best_match)
                    
                    results["matched_tracks"].append({
                        "local_track": local_track,
                        "deezer_track": deezer_track_map[best_match],
                        "match_score": best_score
                    })
                    
                    results["artists_analyzed"][artist_name]["matched"] += 1
                    results["statistics"]["matched_count"] += 1
                    
            # Find tracks not matched
            for local_key in local_track_set - matched_local:
                results["not_on_deezer"].append({
                    "local_track": local_track_map[local_key],
                    "reason": "No match found on Deezer"
                })
                results["artists_analyzed"][artist_name]["not_found"] += 1
                results["statistics"]["not_found_count"] += 1
                
            # Find Deezer tracks missing from local
            for deezer_key in deezer_track_set - matched_deezer:
                deezer_track = deezer_track_map[deezer_key]
                results["missing_from_local"].append({
                    "deezer_track": deezer_track,
                    "artist": discography["artist"]["name"],
                    "album": deezer_track.get("album_info", {}).get("title", "Unknown Album"),
                    "downloadable": True  # Can be downloaded via DeeMusic
                })
                results["artists_analyzed"][artist_name]["missing"] += 1
                results["statistics"]["missing_count"] += 1
                
        return results
        
    async def compare_albums_with_deezer(self, local_albums: List[dict], progress_callback=None) -> Dict[str, Any]:
        """
        Fast comparison: For each album_artist, fetch their albums from Deezer, compare album titles,
        and return a list of missing albums per artist. Does not fetch tracklists.
        Optionally calls progress_callback(album_artist, idx, total, album_name) after each artist/album.
        Expects local_albums to be a list of album dicts (not tracks).
        """
        results = {
            'artists': {},
            'statistics': {
                'total_artists': 0,
                'total_local_albums': 0,
                'total_deezer_albums': 0,
                'total_missing_albums': 0
            }
        }
        from collections import defaultdict
        albums_by_artist = defaultdict(set)
        for album in local_albums:
            album_artist = album.get('album_artist', 'Unknown Artist')
            album_title = album.get('album', 'Unknown Album')
            if album_artist != 'Unknown Artist' and album_title != 'Unknown Album':
                albums_by_artist[album_artist].add(album_title)
        artist_list = list(albums_by_artist.items())
        total = len(artist_list)
        for idx, (artist_name, local_albums_set) in enumerate(artist_list, 1):
            current_album = None
            if local_albums_set:
                current_album = sorted(local_albums_set)[0]
            if progress_callback:
                progress_callback(artist_name, idx, total, current_album)
            deezer_artist = await self.deezer_service.search_artist(artist_name)
            if not deezer_artist:
                results['artists'][artist_name] = {
                    'deezer_id': None,
                    'deezer_name': None,
                    'local_albums': list(local_albums_set),
                    'deezer_albums': [],
                    'missing_albums': list(local_albums_set),
                    'status': 'not_found'
                }
                continue
            deezer_albums = await self.deezer_service.get_artist_albums(deezer_artist['id'])
            deezer_album_titles = set(a['title'] for a in deezer_albums)
            # Use fuzzy matching to find missing albums instead of exact matching
            missing_albums = []
            missing_albums_titles = set()  # Track titles to prevent duplicates
            matched_local_albums = set()
            
            # Debug: Show what we're working with
            print(f"=== COMPARING ARTIST: {artist_name} ===")
            print(f"=== LOCAL ALBUMS ({len(local_albums_set)}): {sorted(local_albums_set)} ===")
            print(f"=== DEEZER ALBUMS ({len(deezer_albums)}): {[a['title'] for a in deezer_albums]} ===")
            
            # CRITICAL FIX: Check for exact matches first before fuzzy matching
            # This should catch albums that are named exactly the same
            for local_album in local_albums_set:
                for deezer_album_obj in deezer_albums:
                    deezer_album = deezer_album_obj['title']
                    if local_album.strip().lower() == deezer_album.strip().lower():
                        print(f"=== EXACT MATCH FOUND: '{local_album}' == '{deezer_album}' ===")
                        matched_local_albums.add(local_album)
                        break
            
            print(f"=== AFTER EXACT MATCHING: {len(matched_local_albums)} albums matched ===")
            print(f"=== MATCHED ALBUMS: {sorted(matched_local_albums)} ===")
            
            # Special handling for self-titled albums (where album name equals artist name)
            # This is especially important for numeric artist names like "311"
            for deezer_album_obj in deezer_albums:
                deezer_album = deezer_album_obj['title']
                print(f"=== PROCESSING DEEZER ALBUM: '{deezer_album}' ===")
                
                # Skip if already matched in exact matching phase
                already_matched = False
                for matched_local in matched_local_albums:
                    if matched_local.strip().lower() == deezer_album.strip().lower():
                        already_matched = True
                        print(f"=== SKIPPING '{deezer_album}' - ALREADY EXACTLY MATCHED ===")
                        break
                
                if already_matched:
                    continue
                
                # Check if this is a self-titled album (album name = artist name)
                is_self_titled = deezer_album.lower() == artist_name.lower()
                
                best_match = None
                best_score = 0
                for local_album in local_albums_set:
                    if local_album in matched_local_albums:
                        continue  # Already matched
                    
                    # Enhanced matching for self-titled albums
                    if is_self_titled and local_album.lower() == artist_name.lower():
                        # Direct match for self-titled albums
                        best_score = 100
                        best_match = local_album
                        break
                    
                    # Special handling for numeric album titles (like "311")
                    if deezer_album.isdigit() and local_album.isdigit() and deezer_album == local_album:
                        best_score = 100
                        best_match = local_album
                        break
                        
                    # Regular fuzzy matching with artist name for better self-titled album detection
                    score = self.fuzzy_match_albums(deezer_album, local_album, artist_name)
                    print(f"=== FUZZY MATCHING: '{deezer_album}' vs '{local_album}' = {score}% (threshold: {self.album_match_threshold}%) ===")
                    logger.debug(f"DEBUG: Matching '{deezer_album}' vs local '{local_album}' = {score}% (threshold: {self.album_match_threshold}%)")
                    if score > best_score and score >= self.album_match_threshold:
                        best_score = score
                        best_match = local_album
                        print(f"=== NEW BEST FUZZY MATCH: '{local_album}' with {score}% ===")
                        
                if best_match:
                    matched_local_albums.add(best_match)
                    print(f"=== FUZZY MATCHED: '{deezer_album}' with local '{best_match}' (score: {best_score}%) ===")
                    logger.debug(f"DEBUG: MATCHED '{deezer_album}' with local '{best_match}' (score: {best_score}%)")
                else:
                    # Check for duplicates before adding (using fuzzy matching)
                    normalized_title = self.normalize_album_title(deezer_album)
                    is_duplicate = False
                    
                    # Check against already added albums using fuzzy matching
                    for existing_title in missing_albums_titles:
                        similarity = fuzz.ratio(normalized_title, existing_title)
                        print(f"=== CHECKING DUPLICATE: '{deezer_album}' vs existing '{existing_title}' = {similarity}% ===")
                        if similarity >= 90:  # High threshold for duplicate detection
                            is_duplicate = True
                            print(f"=== DUPLICATE FOUND: '{deezer_album}' is {similarity}% similar ===")
                            logger.debug(f"DEBUG: DUPLICATE DETECTED - '{deezer_album}' is {similarity}% similar to existing album")
                            break
                    
                    if not is_duplicate:
                        # Store the full album object instead of just the title
                        print(f"=== ADDING AS MISSING: '{deezer_album}' (normalized: '{normalized_title}') ===")
                        print(f"=== REASON: No match found in local albums: {sorted(local_albums_set)} ===")
                        logger.debug(f"DEBUG: NO MATCH for '{deezer_album}' - adding as missing")
                        missing_albums.append(deezer_album_obj)
                        missing_albums_titles.add(normalized_title)
                    else:
                        print(f"=== SKIPPING DUPLICATE: '{deezer_album}' ===")
                        logger.debug(f"DEBUG: SKIPPING DUPLICATE - '{deezer_album}'")
            # Deduplicate similar albums before adding to results
            missing_albums = self.deduplicate_similar_albums(missing_albums, artist_name)
            
            # Sort missing albums by title
            missing_albums.sort(key=lambda x: x.get('title', ''))
            self.log_album_comparison_details(artist_name, local_albums_set, deezer_album_titles, missing_albums, matched_local_albums)
            results['artists'][artist_name] = {
                'deezer_id': deezer_artist['id'],
                'deezer_name': deezer_artist['name'],
                'local_albums': list(sorted(local_albums_set)),
                'deezer_albums': list(sorted(deezer_album_titles)),
                'missing_albums': missing_albums,
                'status': 'found'
            }
            results['statistics']['total_artists'] += 1
            results['statistics']['total_local_albums'] += len(local_albums_set)
            results['statistics']['total_deezer_albums'] += len(deezer_album_titles)
            results['statistics']['total_missing_albums'] += len(missing_albums)
        return results
        
    def log_album_comparison_details(self, artist_name: str, local_albums: set, deezer_albums: set, missing_albums: list, matched_albums: set):
        """Log detailed information about album comparison for debugging"""
        logger.info(f"=== Album Comparison Details for {artist_name} ===")
        logger.info(f"Local albums ({len(local_albums)}): {sorted(local_albums)}")
        logger.info(f"Deezer albums ({len(deezer_albums)}): {sorted(deezer_albums)}")
        logger.info(f"Matched albums ({len(matched_albums)}): {sorted(matched_albums)}")
        logger.info(f"Missing albums ({len(missing_albums)}): {missing_albums}")
        
        # Special debug for self-titled albums
        if artist_name in local_albums or artist_name in deezer_albums:
            logger.info(f"⚠️ Self-titled album detected for artist '{artist_name}'")
            # Check if it was properly matched
            if artist_name in matched_albums:
                logger.info(f"✅ Self-titled album was correctly matched")
            elif artist_name in missing_albums:
                logger.info(f"❌ Self-titled album was incorrectly marked as missing")
                
        # Special debug for numeric album titles (like "311")
        numeric_albums_local = [album for album in local_albums if album.isdigit()]
        numeric_albums_deezer = [album for album in deezer_albums if album.isdigit()]
        if numeric_albums_local or numeric_albums_deezer:
            logger.info(f"⚠️ Numeric album titles detected: Local={numeric_albums_local}, Deezer={numeric_albums_deezer}")
            
        logger.info("=" * 50)
        
    def _create_track_key(self, track: Dict) -> str:
        """Create a normalized key for a local track"""
        title = self.normalize_text(track.get("title", ""))
        album = self.normalize_text(track.get("album", ""))
        return f"{title}|{album}"
        
    def _create_deezer_track_key(self, track: Dict) -> str:
        """Create a normalized key for a Deezer track"""
        title = self.normalize_text(track.get("title", ""))
        album_info = track.get("album_info", {})
        album = self.normalize_text(album_info.get("title", track.get("album", {}).get("title", "")))
        return f"{title}|{album}"
        
    def _calculate_match_score(self, local_track: Dict, deezer_track: Dict) -> int:
        """Calculate match score between local and Deezer track"""
        # Title match (60% weight)
        title_score = self.fuzzy_match(
            local_track.get("title", ""),
            deezer_track.get("title", "")
        )
        
        # Album match (30% weight)
        local_album = local_track.get("album", "")
        album_info = deezer_track.get("album_info", {})
        deezer_album = album_info.get("title", deezer_track.get("album", {}).get("title", ""))
        album_score = self.fuzzy_match(local_album, deezer_album)
        
        # Track number match (10% weight)
        track_num_score = 0
        local_track_num = local_track.get("track_number")
        deezer_track_num = deezer_track.get("track_position")
        
        if local_track_num and deezer_track_num:
            if str(local_track_num) == str(deezer_track_num):
                track_num_score = 100
            else:
                track_num_score = 0
        else:
            # If track numbers are missing, give partial credit
            track_num_score = 50
            
        # Calculate weighted score
        total_score = (title_score * 0.6) + (album_score * 0.3) + (track_num_score * 0.1)
        
        return int(total_score)
        
    def group_missing_by_album(self, missing_tracks: List[Dict]) -> Dict[str, List[Dict]]:
        """Group missing tracks by album for easier browsing"""
        albums = defaultdict(list)
        
        for item in missing_tracks:
            track = item["deezer_track"]
            album_info = track.get("album_info", {})
            album_key = f"{item['artist']}|{album_info.get('title', 'Unknown Album')}"
            
            albums[album_key].append(item)
            
        # Sort tracks within each album by track position
        for album_key in albums:
            albums[album_key].sort(
                key=lambda x: x["deezer_track"].get("track_position", 0)
            )
            
        return dict(albums)
        
    def filter_missing_tracks(self, missing_tracks: List[Dict], 
                            album_filter: Optional[str] = None,
                            min_duration: Optional[int] = None) -> List[Dict]:
        """Filter missing tracks based on criteria"""
        filtered = missing_tracks
        
        if album_filter:
            filtered = [
                track for track in filtered
                if album_filter.lower() in track.get("album", "").lower()
            ]
            
        if min_duration:
            filtered = [
                track for track in filtered
                if track["deezer_track"].get("duration", 0) >= min_duration
            ]
            
        return filtered 