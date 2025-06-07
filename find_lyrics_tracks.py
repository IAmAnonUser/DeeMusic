#!/usr/bin/env python3
"""Find tracks with available lyrics."""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

import logging
from config_manager import ConfigManager
from services.deezer_api import DeezerAPI

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

def find_tracks_with_lyrics():
    """Find tracks that have lyrics available."""
    logger.info("Searching for tracks with available lyrics...")
    
    try:
        # Initialize config and API
        config = ConfigManager()
        api = DeezerAPI(config)
        
        # Set the ARL on the API
        arl = config.get_setting('deezer.arl')
        api.arl = arl
        
        # Test popular tracks that often have lyrics
        test_tracks = [
            {"id": 2769846461, "name": "Miles On It - Marshmello & Kane Brown"},
            {"id": 3135556, "name": "Somebody That I Used to Know - Gotye"},
            {"id": 916424, "name": "Rolling in the Deep - Adele"},
            {"id": 1109731, "name": "Someone Like You - Adele"},
            {"id": 892594, "name": "Payphone - Maroon 5"},
            {"id": 892596, "name": "Moves Like Jagger - Maroon 5"},
            {"id": 465489, "name": "Poker Face - Lady Gaga"},
            {"id": 831856, "name": "Call Me Maybe - Carly Rae Jepsen"},
            {"id": 1275734, "name": "Gangnam Style - Psy"},
            {"id": 4672269, "name": "Happy - Pharrell Williams"}
        ]
        
        tracks_with_lyrics = []
        
        for track in test_tracks:
            track_id = track["id"]
            track_name = track["name"]
            
            logger.info(f"Testing: {track_name}")
            
            try:
                lyrics_data = api.get_track_lyrics_sync(track_id)
                if lyrics_data and 'LYRICS_TEXT' in lyrics_data:
                    lyrics_text = lyrics_data['LYRICS_TEXT']
                    logger.info(f"✅ FOUND lyrics for {track_name} (length: {len(lyrics_text)})")
                    tracks_with_lyrics.append({
                        "id": track_id,
                        "name": track_name,
                        "lyrics_length": len(lyrics_text)
                    })
                    
                    # Show first few lines
                    lines = lyrics_text.split('\n')[:3]
                    for line in lines:
                        if line.strip():
                            logger.info(f"  📝 {line.strip()}")
                else:
                    logger.info(f"❌ No lyrics for {track_name}")
            except Exception as e:
                logger.error(f"Error testing {track_name}: {e}")
        
        logger.info(f"\n🎵 Found {len(tracks_with_lyrics)} tracks with lyrics:")
        for track in tracks_with_lyrics:
            print(f"  - {track['name']} (ID: {track['id']})")
        
        return tracks_with_lyrics
        
    except Exception as e:
        logger.error(f"Error in find_tracks_with_lyrics: {e}", exc_info=True)
        return []

if __name__ == "__main__":
    tracks = find_tracks_with_lyrics()
    if tracks:
        print(f"\n✅ Found {len(tracks)} tracks with available lyrics")
        print("You can search for and download these tracks to test LRC file creation!")
    else:
        print("\n❌ No tracks found with available lyrics")
    sys.exit(0 if tracks else 1) 