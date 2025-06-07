from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtCore import QUrl
from pathlib import Path
from typing import Optional, Tuple

class PlayerManager(QObject):
    playback_state_changed = pyqtSignal(bool)  # True for playing, False for paused
    track_changed = pyqtSignal(str, str)  # title, artist
    error_occurred = pyqtSignal(str)  # Error message
    
    def __init__(self, download_path: Optional[Path] = None):
        super().__init__()
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        
        # Connect signals
        self.media_player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.media_player.errorOccurred.connect(self._on_error)
        
        # Initialize state
        self.current_track = None
        self.is_playing = False
        self.download_path = download_path or Path.home() / "Music" / "DeeMusic"
        
        # Set default volume
        self.audio_output.setVolume(0.7)
    
    def _find_track_file(self, artist: str, title: str) -> Optional[Path]:
        """Find the downloaded track file."""
        try:
            # Search in artist directories
            for artist_dir in self.download_path.glob("*"):
                if not artist_dir.is_dir():
                    continue
                    
                # Check if artist name matches (case insensitive)
                if artist.lower() not in artist_dir.name.lower():
                    continue
                    
                # Search in album directories
                for album_dir in artist_dir.glob("*"):
                    if not album_dir.is_dir():
                        continue
                        
                    # Search for track file
                    for ext in ['.mp3', '.flac']:
                        # Try exact match first
                        track_file = album_dir / f"{title}{ext}"
                        if track_file.exists():
                            return track_file
                            
                        # Try case-insensitive search
                        for file in album_dir.glob(f"*{ext}"):
                            if title.lower() in file.stem.lower():
                                return file
                                
            return None
            
        except Exception as e:
            self.error_occurred.emit(f"Error finding track file: {str(e)}")
            return None
    
    def play_track(self, title: str, artist: str, audio_url: str = None):
        """Play a track. If no audio_url is provided, search in downloads."""
        self.current_track = (title, artist)
        
        try:
            # If audio_url is provided, use it
            if audio_url:
                url = QUrl(audio_url)
            else:
                # Search for downloaded file
                track_file = self._find_track_file(artist, title)
                if not track_file:
                    self.error_occurred.emit(f"Track not found: {title} by {artist}")
                    return
                    
                url = QUrl.fromLocalFile(str(track_file))
            
            # Set the media source and play
            self.media_player.setSource(url)
            self.media_player.play()
            self.is_playing = True
            self.track_changed.emit(title, artist)
            self.playback_state_changed.emit(True)
            
        except Exception as e:
            self.error_occurred.emit(f"Error playing track: {str(e)}")
    
    def toggle_play_pause(self):
        """Toggle between play and pause states."""
        if self.current_track is None:
            return
            
        if self.is_playing:
            self.media_player.pause()
        else:
            self.media_player.play()
    
    def stop(self):
        """Stop playback."""
        self.media_player.stop()
        self.is_playing = False
        self.playback_state_changed.emit(False)
    
    def set_volume(self, volume: float):
        """Set the volume level (0.0 to 1.0)."""
        self.audio_output.setVolume(volume)
    
    def _on_playback_state_changed(self, state):
        """Handle playback state changes."""
        self.is_playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.playback_state_changed.emit(self.is_playing)
        
    def _on_error(self, error):
        """Handle media player errors."""
        error_msg = f"Media player error: {error}"
        self.error_occurred.emit(error_msg)
        self.is_playing = False
        self.playback_state_changed.emit(False) 