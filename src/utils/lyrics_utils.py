"""Utilities for handling lyrics processing and LRC file creation."""

import os
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
import re

logger = logging.getLogger(__name__)

class LyricsProcessor:
    """Class for processing and formatting lyrics data."""
    
    @staticmethod
    def parse_deezer_lyrics(lyrics_data: Dict) -> Dict[str, Any]:
        """
        Parse Deezer lyrics response into usable format.
        
        Args:
            lyrics_data (Dict): Raw lyrics data from Deezer API
            
        Returns:
            Dict: Processed lyrics containing sync_lyrics, plain_text, and metadata
        """
        result = {
            'sync_lyrics': [],
            'plain_text': '',
            'has_sync': False,
            'language': None,
            'copyright': None
        }
        
        if not lyrics_data or not isinstance(lyrics_data, dict):
            return result
        
        try:
            # Get synchronized lyrics
            sync_json = lyrics_data.get('LYRICS_SYNC_JSON', [])
            if sync_json and isinstance(sync_json, list):
                result['has_sync'] = True
                for sync_line in sync_json:
                    if isinstance(sync_line, dict):
                        timestamp = sync_line.get('lrc_timestamp', '')
                        text = sync_line.get('line', '').strip()
                        if timestamp and text:
                            result['sync_lyrics'].append({
                                'timestamp': timestamp,
                                'text': text
                            })
        except Exception as e:
            logger.warning(f"Error parsing synchronized lyrics: {e}")
        
        try:
            # Get plain text lyrics as fallback
            plain_lyrics = lyrics_data.get('LYRICS_TEXT', '')
            if plain_lyrics and isinstance(plain_lyrics, str):
                result['plain_text'] = plain_lyrics.strip()
        except Exception as e:
            logger.warning(f"Error parsing plain text lyrics: {e}")
        
        # If no plain text but we have sync lyrics, create plain text from sync
        if not result['plain_text'] and result['sync_lyrics']:
            try:
                result['plain_text'] = '\n'.join([line['text'] for line in result['sync_lyrics']])
            except Exception as e:
                logger.warning(f"Error creating plain text from sync lyrics: {e}")
        
        # Get metadata
        try:
            result['language'] = lyrics_data.get('LYRICS_LANG', None)
            result['copyright'] = lyrics_data.get('LYRICS_COPYRIGHTS', None)
        except Exception as e:
            logger.warning(f"Error parsing lyrics metadata: {e}")
        
        return result
    
    @staticmethod
    def create_lrc_content(sync_lyrics: List[Dict], track_info: Dict, sync_offset: int = 0) -> str:
        """
        Create LRC file content from synchronized lyrics.
        
        Args:
            sync_lyrics (List[Dict]): List of synchronized lyrics with timestamp and text
            track_info (Dict): Track metadata for LRC headers
            sync_offset (int): Offset in milliseconds to adjust timing
            
        Returns:
            str: LRC file content
        """
        if not sync_lyrics:
            return ""
        
        lrc_lines = []
        
        # Add LRC headers
        title = track_info.get('title', track_info.get('SNG_TITLE', 'Unknown Title'))
        artist = LyricsProcessor._get_artist_name(track_info)
        album = track_info.get('alb_title', track_info.get('album', {}).get('title', 'Unknown Album'))
        
        lrc_lines.append(f"[ti:{title}]")
        lrc_lines.append(f"[ar:{artist}]")
        lrc_lines.append(f"[al:{album}]")
        
        # Add offset if provided
        if sync_offset != 0:
            lrc_lines.append(f"[offset:{sync_offset}]")
        
        lrc_lines.append("[by:DeeMusic]")
        lrc_lines.append("")  # Empty line before lyrics
        
        # Add synchronized lyrics
        for line in sync_lyrics:
            timestamp = line.get('timestamp', '')
            text = line.get('text', '')
            if timestamp and text:
                # Apply offset to timestamp if needed
                if sync_offset != 0:
                    timestamp = LyricsProcessor._adjust_timestamp(timestamp, sync_offset)
                lrc_lines.append(f"{timestamp} {text}")
        
        return '\n'.join(lrc_lines)
    
    @staticmethod
    def _get_artist_name(track_info: Dict) -> str:
        """Extract artist name from track info."""
        artist_data = track_info.get('artist')
        if isinstance(artist_data, dict):
            return artist_data.get('name', 'Unknown Artist')
        elif isinstance(artist_data, str):
            return artist_data
        
        # Fallback to ART_NAME
        return track_info.get('ART_NAME', 'Unknown Artist')
    
    @staticmethod
    def _adjust_timestamp(timestamp: str, offset_ms: int) -> str:
        """
        Adjust LRC timestamp by offset in milliseconds.
        
        Args:
            timestamp (str): Original timestamp in [mm:ss.xx] format
            offset_ms (int): Offset in milliseconds
            
        Returns:
            str: Adjusted timestamp
        """
        try:
            # Parse timestamp [mm:ss.xx]
            match = re.match(r'\[(\d{2}):(\d{2})\.(\d{2})\]', timestamp)
            if not match:
                return timestamp
            
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            centiseconds = int(match.group(3))
            
            # Convert to total milliseconds
            total_ms = (minutes * 60 * 1000) + (seconds * 1000) + (centiseconds * 10)
            
            # Apply offset
            total_ms += offset_ms
            
            # Ensure non-negative
            if total_ms < 0:
                total_ms = 0
            
            # Convert back to timestamp format
            new_minutes = total_ms // (60 * 1000)
            remaining_ms = total_ms % (60 * 1000)
            new_seconds = remaining_ms // 1000
            new_centiseconds = (remaining_ms % 1000) // 10
            
            return f"[{new_minutes:02d}:{new_seconds:02d}.{new_centiseconds:02d}]"
            
        except Exception as e:
            logger.warning(f"Failed to adjust timestamp {timestamp}: {e}")
            return timestamp
    
    @staticmethod
    def save_lrc_file(lrc_content: str, file_path: Path, encoding: str = 'utf-8') -> bool:
        """
        Save LRC content to file.
        
        Args:
            lrc_content (str): LRC file content
            file_path (Path): Path where to save the LRC file
            encoding (str): File encoding (default: utf-8)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Validate inputs
            if not lrc_content or not isinstance(lrc_content, str):
                logger.warning("No valid LRC content provided")
                return False
                
            if not file_path:
                logger.error("No file path provided for LRC save")
                return False
            
            # Ensure directory exists
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"Failed to create directory for LRC file {file_path.parent}: {e}")
                return False
            
            # Write LRC file
            with open(file_path, 'w', encoding=encoding, errors='replace') as f:
                f.write(lrc_content)
            
            logger.info(f"Successfully saved LRC file: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save LRC file {file_path}: {e}")
            return False
    
    @staticmethod
    def save_plain_lyrics(lyrics_text: str, file_path: Path, encoding: str = 'utf-8') -> bool:
        """
        Save plain text lyrics to file.
        
        Args:
            lyrics_text (str): Plain text lyrics
            file_path (Path): Path where to save the lyrics file
            encoding (str): File encoding (default: utf-8)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Validate inputs
            if not lyrics_text or not isinstance(lyrics_text, str):
                logger.warning("No valid lyrics text provided")
                return False
                
            if not file_path:
                logger.error("No file path provided for lyrics save")
                return False
            
            # Ensure directory exists
            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"Failed to create directory for lyrics file {file_path.parent}: {e}")
                return False
            
            # Write text file
            with open(file_path, 'w', encoding=encoding, errors='replace') as f:
                f.write(lyrics_text)
            
            logger.info(f"Successfully saved lyrics file: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save lyrics file {file_path}: {e}")
            return False
    
    @staticmethod
    def get_lyrics_file_path(audio_file_path: Path, lyrics_location: str, 
                            custom_path: str = "", file_extension: str = "lrc") -> Path:
        """
        Determine the path for lyrics file based on settings.
        
        Args:
            audio_file_path (Path): Path to the audio file
            lyrics_location (str): "With Audio Files" or "Separate Folder"
            custom_path (str): Custom lyrics folder path
            file_extension (str): File extension (lrc, txt)
            
        Returns:
            Path: Path where lyrics file should be saved
        """
        base_name = audio_file_path.stem  # Filename without extension
        
        if lyrics_location == "Separate Folder" and custom_path:
            lyrics_dir = Path(custom_path)
            return lyrics_dir / f"{base_name}.{file_extension}"
        else:
            # Save with audio files
            return audio_file_path.parent / f"{base_name}.{file_extension}" 