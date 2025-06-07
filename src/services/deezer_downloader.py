import os
import asyncio
import logging
from typing import Optional, Callable, Dict, Any
import aiohttp
from tqdm import tqdm
from pathvalidate import sanitize_filename
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC
from ..deemusic.deezer_api import DeezerAPI, AudioQuality
from ..deemusic.config_manager import ConfigManager

class DeezerDownloader:
    def __init__(self, download_dir: str, config: ConfigManager):
        self.download_dir = download_dir
        self.config = config
        self.api = DeezerAPI(config)
        self.logger = logging.getLogger(__name__)
        self._session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        self._session = aiohttp.ClientSession()
        await self.api.initialize()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
            await self.api.close()
            
    async def download_track(
        self,
        track_id: str,
        progress_callback: Optional[Callable[[int, Optional[int]], None]] = None,
        resume_info: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Download a track from Deezer.
        
        Args:
            track_id: The Deezer track ID
            progress_callback: Optional callback for download progress (current_size, total_size)
            resume_info: Optional dict with resume information:
                - temp_filepath: Path to partial download
                - downloaded_size: Number of bytes already downloaded
                - etag: ETag from previous download attempt
            
        Returns:
            Dict containing track info and download path
        """
        try:
            # Get track info
            track_data = await self.api._get_track_info(track_id)
            if not track_data:
                raise ValueError(f"Track {track_id} not found")
                
            # Create sanitized filename
            filename = sanitize_filename(
                f"{track_data['ART_NAME']} - {track_data['SNG_TITLE']}.mp3"
            )
            filepath = os.path.join(self.download_dir, filename)
            
            # Get download URL with highest quality available
            for quality in [AudioQuality.FLAC, AudioQuality.MP3_320, AudioQuality.MP3_128]:
                try:
                    download_url = await self.api._get_track_url(track_data, quality)
                    if download_url:
                        break
                except Exception:
                    continue
            
            if not download_url:
                raise ValueError("Could not get download URL for any quality")
            
            # Download the file
            if self._session:
                headers = {}
                temp_filepath = resume_info and resume_info.get('temp_filepath')
                downloaded_size = resume_info and resume_info.get('downloaded_size', 0)
                etag = resume_info and resume_info.get('etag')
                
                # Check if we can resume
                if temp_filepath and os.path.exists(temp_filepath) and downloaded_size > 0:
                    headers['Range'] = f'bytes={downloaded_size}-'
                    if etag:
                        headers['If-Match'] = etag
                
                async with self._session.get(download_url, headers=headers) as response:
                    can_resume = response.status == 206  # Partial content
                    if not can_resume and response.status != 200:
                        raise ValueError(
                            f"Failed to download track: {response.status}"
                        )
                        
                    # Get total size and check if resume was successful
                    total_size = int(response.headers.get('content-length', 0))
                    if can_resume:
                        total_size += downloaded_size
                    else:
                        # Reset if we can't resume
                        downloaded_size = 0
                        temp_filepath = None
                        
                    # Store ETag for future resume attempts
                    etag = response.headers.get('etag')
                    
                    if progress_callback:
                        progress_callback(downloaded_size, total_size)
                        
                    # Open file in append mode if resuming, write mode if not
                    mode = 'ab' if can_resume else 'wb'
                    output_file = temp_filepath if temp_filepath else filepath
                    
                    chunk_size = 1024 * 8  # 8KB chunks
                    current_size = downloaded_size
                    
                    with open(output_file, mode) as f:
                        async for chunk in response.content.iter_chunked(chunk_size):
                            f.write(chunk)
                            current_size += len(chunk)
                            if progress_callback:
                                progress_callback(current_size, total_size)
                                
                    # If we were using a temp file, move it to final location
                    if temp_filepath and os.path.exists(temp_filepath):
                        os.replace(temp_filepath, filepath)
                                
            # Add metadata
            await self._add_metadata(filepath, {
                'title': track_data['SNG_TITLE'],
                'artist': {'name': track_data['ART_NAME']},
                'album': {'title': track_data['ALB_TITLE']}
            })
            
            return {
                'track_id': track_id,
                'title': track_data['SNG_TITLE'],
                'artist': track_data['ART_NAME'],
                'album': track_data['ALB_TITLE'],
                'filepath': filepath,
                'etag': etag
            }
            
        except Exception as e:
            self.logger.error(f"Error downloading track {track_id}: {str(e)}")
            raise
            
    async def _add_metadata(self, filepath: str, track_info: Dict[str, Any]):
        """Add ID3 metadata to the downloaded MP3 file."""
        try:
            audio = MP3(filepath)
            if audio.tags is None:
                audio.add_tags()
                
            # Add basic metadata
            audio.tags.add(TIT2(encoding=3, text=track_info['title']))
            audio.tags.add(TPE1(encoding=3, text=track_info['artist']['name']))
            audio.tags.add(TALB(encoding=3, text=track_info['album']['title']))
            
            # Add album art if available
            if self._session and track_info['album'].get('cover_xl'):
                async with self._session.get(track_info['album']['cover_xl']) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        audio.tags.add(
                            APIC(
                                encoding=3,
                                mime='image/jpeg',
                                type=3,  # Cover (front)
                                desc='Cover',
                                data=image_data
                            )
                        )
                        
            audio.save()
            
        except Exception as e:
            self.logger.error(f"Error adding metadata to {filepath}: {str(e)}")
            # Don't raise - metadata failure shouldn't fail the download 

    async def download_playlist(
        self,
        playlist_id: str,
        progress_callback: Optional[Callable[[int, Optional[int]], None]] = None,
    ) -> Dict[str, Any]:
        """
        Download all tracks from a playlist.
        
        Args:
            playlist_id: The Deezer playlist ID
            progress_callback: Optional callback for download progress
            
        Returns:
            Dict containing playlist info and download results
        """
        try:
            # Get playlist info and tracks
            playlist_data = await self.api._get_playlist_info(playlist_id)
            if not playlist_data:
                raise ValueError(f"Playlist {playlist_id} not found")
                
            tracks = playlist_data.get('tracks', {}).get('data', [])
            if not tracks:
                raise ValueError(f"No tracks found in playlist {playlist_id}")
                
            # Create playlist directory
            playlist_dir = os.path.join(
                self.download_dir,
                sanitize_filename(playlist_data['title'])
            )
            os.makedirs(playlist_dir, exist_ok=True)
            
            # Download each track
            results = []
            total_tracks = len(tracks)
            
            for i, track in enumerate(tracks, 1):
                try:
                    track_result = await self.download_track(
                        str(track['id']),
                        lambda current, total: progress_callback(
                            current,
                            total,
                            i,
                            total_tracks
                        ) if progress_callback else None
                    )
                    
                    # Move the downloaded file to playlist directory
                    if track_result and track_result.get('filepath'):
                        new_filepath = os.path.join(
                            playlist_dir,
                            os.path.basename(track_result['filepath'])
                        )
                        os.rename(track_result['filepath'], new_filepath)
                        track_result['filepath'] = new_filepath
                        results.append(track_result)
                        
                except Exception as e:
                    self.logger.error(f"Error downloading track {track['id']}: {str(e)}")
                    results.append({
                        'track_id': str(track['id']),
                        'error': str(e)
                    })
                    
            return {
                'playlist_id': playlist_id,
                'title': playlist_data['title'],
                'tracks': results,
                'directory': playlist_dir
            }
            
        except Exception as e:
            self.logger.error(f"Error downloading playlist {playlist_id}: {str(e)}")
            raise 