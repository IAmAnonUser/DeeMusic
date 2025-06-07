"""Music player service for DeeMusic."""

from PyQt6.QtCore import QObject, pyqtSignal, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
import logging
from datetime import timedelta
import requests
from pathlib import Path
import os

logger = logging.getLogger(__name__)

class MusicPlayer(QObject):
    """Service for handling music playback."""
    
    # Signals
    playback_state_changed = pyqtSignal(bool)  # True if playing, False if paused
    position_changed = pyqtSignal(int)  # Current position in milliseconds
    duration_changed = pyqtSignal(int)  # Track duration in milliseconds
    track_changed = pyqtSignal(dict)  # Current track info
    volume_changed = pyqtSignal(float)  # Current volume (0.0 to 1.0)
    error_occurred = pyqtSignal(str)  # Error message
    
    def __init__(self):
        super().__init__()
        self.setup_player()
        self.current_track = None
        self.playlist = []
        self.playlist_index = -1
        
    def setup_player(self):
        """Initialize the media player."""
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        # Connect signals
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.positionChanged.connect(self.position_changed.emit)
        self.player.durationChanged.connect(self.duration_changed.emit)
        self.player.errorOccurred.connect(self._on_error)
        
    def _on_playback_state_changed(self, state):
        """Handle playback state changes."""
        is_playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.playback_state_changed.emit(is_playing)
        
    def _on_error(self, error, error_string):
        """Handle media player errors."""
        logger.error(f"Media player error: {error_string}")
        self.error_occurred.emit(error_string)
        
    def play_track(self, track_data):
        """Play a track from Deezer."""
        try:
            # Get track URL (you'll need to implement this based on your Deezer API)
            track_url = self._get_track_url(track_data)
            if not track_url:
                raise Exception("Failed to get track URL")
            
            # Set media source
            self.player.setSource(QUrl(track_url))
            self.player.play()
            
            # Update current track
            self.current_track = track_data
            self.track_changed.emit(track_data)
            
        except Exception as e:
            logger.error(f"Failed to play track: {str(e)}")
            self.error_occurred.emit(f"Failed to play track: {str(e)}")
            
    def _get_track_url(self, track_data):
        """Get playable URL for a track.
        
        This is a placeholder - you'll need to implement this based on your
        Deezer API integration and legal requirements.
        """
        # For now, we'll use a local file if it exists
        track_id = track_data.get('id')
        local_path = Path.home() / ".deemusic" / "cache" / f"{track_id}.mp3"
        
        if local_path.exists():
            return local_path.as_uri()
            
        # TODO: Implement actual Deezer streaming URL retrieval
        return None
        
    def play_pause(self):
        """Toggle between play and pause."""
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()
            
    def stop(self):
        """Stop playback."""
        self.player.stop()
        
    def seek(self, position):
        """Seek to position in milliseconds."""
        self.player.setPosition(position)
        
    def set_volume(self, volume):
        """Set volume level (0.0 to 1.0)."""
        self.audio_output.setVolume(volume)
        self.volume_changed.emit(volume)
        
    def get_position(self):
        """Get current position in milliseconds."""
        return self.player.position()
        
    def get_duration(self):
        """Get track duration in milliseconds."""
        return self.player.duration()
        
    def format_time(self, milliseconds):
        """Format milliseconds as mm:ss."""
        seconds = int(milliseconds / 1000)
        return str(timedelta(seconds=seconds))[2:7]
        
    def set_playlist(self, tracks, start_index=0):
        """Set the current playlist."""
        self.playlist = tracks
        self.playlist_index = start_index
        if tracks:
            self.play_track(tracks[start_index])
            
    def next_track(self):
        """Play next track in playlist."""
        if not self.playlist:
            return
            
        self.playlist_index = (self.playlist_index + 1) % len(self.playlist)
        self.play_track(self.playlist[self.playlist_index])
        
    def previous_track(self):
        """Play previous track in playlist."""
        if not self.playlist:
            return
            
        self.playlist_index = (self.playlist_index - 1) % len(self.playlist)
        self.play_track(self.playlist[self.playlist_index])
        
    def shuffle_playlist(self):
        """Shuffle the current playlist."""
        if not self.playlist:
            return
            
        import random
        current_track = self.playlist[self.playlist_index]
        random.shuffle(self.playlist)
        self.playlist_index = self.playlist.index(current_track)

class DummyMusicPlayer(QObject):
    """A dummy music player that does nothing but provides the necessary signals."""
    playback_state_changed = pyqtSignal(bool)
    position_changed = pyqtSignal(int)
    duration_changed = pyqtSignal(int)
    track_changed = pyqtSignal(dict)
    volume_changed = pyqtSignal(float)
    error_occurred = pyqtSignal(str)
    playback_finished = pyqtSignal() # Added as per summary

    def __init__(self, parent=None):
        super().__init__(parent)
        logger.info("DummyMusicPlayer initialized")

    def play_track(self, track_data):
        logger.debug(f"DummyMusicPlayer: play_track called with {track_data}")
        self.track_changed.emit(track_data if track_data else {})
        self.duration_changed.emit(180000) # Dummy duration 3 mins
        self.playback_state_changed.emit(True)

    def play_pause(self):
        logger.debug("DummyMusicPlayer: play_pause called")
        # In a real scenario, you'd toggle the state
        # For a dummy, let's assume it pauses if it was 'playing' (which it always pretends to be)
        self.playback_state_changed.emit(False)

    def stop(self):
        logger.debug("DummyMusicPlayer: stop called")
        self.playback_state_changed.emit(False)
        self.position_changed.emit(0)

    def seek(self, position):
        logger.debug(f"DummyMusicPlayer: seek called with {position}")
        self.position_changed.emit(position)

    def set_volume(self, volume):
        logger.debug(f"DummyMusicPlayer: set_volume called with {volume}")
        self.volume_changed.emit(volume)

    def get_position(self):
        return 0

    def get_duration(self):
        return 180000 # Dummy duration

    def set_playlist(self, tracks, start_index=0):
        logger.debug(f"DummyMusicPlayer: set_playlist called")
        if tracks:
            self.play_track(tracks[start_index])

    def next_track(self):
        logger.debug("DummyMusicPlayer: next_track called")
        # self.playback_finished.emit() # Or play a dummy next track

    def previous_track(self):
        logger.debug("DummyMusicPlayer: previous_track called")

    def shuffle_playlist(self):
        logger.debug("DummyMusicPlayer: shuffle_playlist called") 