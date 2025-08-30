"""
High-level download service that coordinates the new queue management system.

This service replaces the old download_manager.py and provides a clean interface
for the UI and other components to interact with the download system.
"""

import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime

# Import our new system components
import sys
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from src.models.queue_models import QueueItem, QueueItemState, DownloadState, ItemType, TrackInfo, create_album_from_deezer_data, create_track_from_deezer_data, create_album_from_deezer_data_complete, create_album_from_deezer_data_complete_sync
from src.services.new_queue_manager import QueueManager
from src.services.new_download_engine import DownloadEngine
from src.services.event_bus import EventBus, QueueEvents, DownloadEvents, get_event_bus

logger = logging.getLogger(__name__)


class DownloadService:
    """
    High-level service coordinating queue management and download execution.
    
    This replaces the old DownloadManager and provides a clean, reliable interface
    for downloading music with proper queue management and progress tracking.
    """
    
    def __init__(self, config_manager, deezer_api):
        self.config = config_manager
        self.deezer_api = deezer_api
        self.event_bus = get_event_bus()
        
        # Initialize core components
        self.queue_manager = QueueManager(config_manager, self.event_bus)
        self.download_engine = DownloadEngine(self.queue_manager, deezer_api, config_manager)
        
        # Service state
        self._is_running = False
        
        logger.info("[DownloadService] Initialized new download service")
    
    def start(self):
        """Start the download service."""
        if self._is_running:
            logger.warning("[DownloadService] Service already running")
            return
        
        # Reset cancelled items to queued on startup
        self._reset_cancelled_items_on_startup()
        
        # Fix track numbering in existing queue items
        self._fix_track_numbering_in_queue()
        
        # Validate queue states against actual files
        self._validate_queue_states_on_startup()
        
        # Validate items that are about to be processed
        self._validate_priority_items()
        
        self._is_running = True
        self.download_engine.start()
        
        logger.info("[DownloadService] Download service started")
    
    def _reset_cancelled_items_on_startup(self):
        """Reset cancelled items to queued state on service startup."""
        try:
            cancelled_count = 0
            with self.queue_manager._lock:
                for item_id, state in self.queue_manager.states.items():
                    if state.state == DownloadState.CANCELLED:
                        state.state = DownloadState.QUEUED
                        state.error_message = None
                        state.updated_at = datetime.now()
                        cancelled_count += 1
                        self.event_bus.emit(QueueEvents.ITEM_STATE_CHANGED, item_id, state)
                
                if cancelled_count > 0:
                    self.queue_manager._persist_queue()
                    logger.info(f"[DownloadService] Reset {cancelled_count} cancelled items to queued on startup")
                    
        except Exception as e:
            logger.error(f"[DownloadService] Error resetting cancelled items: {e}")
    
    def _fix_track_numbering_in_queue(self):
        """Fix track numbering in existing queue items where all tracks have number 1."""
        try:
            fixed_count = 0
            with self.queue_manager._lock:
                for item_id, item in self.queue_manager.items.items():
                    if item.item_type == ItemType.ALBUM:
                        # Check if all tracks have track_number = 1 (indicating the bug)
                        all_tracks_are_one = all(track.track_number == 1 for track in item.tracks)
                        if all_tracks_are_one and len(item.tracks) > 1:
                            # Fix track numbering by enumerating
                            fixed_tracks = []
                            for index, track in enumerate(item.tracks, 1):
                                fixed_track = TrackInfo(
                                    track_id=track.track_id,
                                    title=track.title,
                                    artist=track.artist,
                                    duration=track.duration,
                                    track_number=index,  # Use enumerated position
                                    disc_number=track.disc_number
                                )
                                fixed_tracks.append(fixed_track)
                            
                            # Create new item with fixed tracks
                            fixed_item = QueueItem(
                                id=item.id,
                                item_type=item.item_type,
                                deezer_id=item.deezer_id,
                                title=item.title,
                                artist=item.artist,
                                total_tracks=item.total_tracks,
                                tracks=fixed_tracks,
                                created_at=item.created_at,
                                album_cover_url=getattr(item, 'album_cover_url', None)
                            )
                            
                            # Replace the item
                            self.queue_manager.items[item_id] = fixed_item
                            fixed_count += 1
                
                if fixed_count > 0:
                    self.queue_manager._persist_queue()
                    logger.info(f"[DownloadService] Fixed track numbering for {fixed_count} album(s) in queue")
                    
        except Exception as e:
            logger.error(f"[DownloadService] Error fixing track numbering: {e}")
    
    def _validate_queue_states_on_startup(self):
        """Validate queue states against actual files on startup to prevent unnecessary processing."""
        try:
            from pathlib import Path
            import os
            
            logger.info("[DownloadService] Starting queue state validation...")
            validated_count = 0
            queued_count = 0
            completed_count = 0
            with self.queue_manager._lock:
                for item_id, item in self.queue_manager.items.items():
                    state = self.queue_manager.states.get(item_id)
                    if not state:
                        continue
                    
                    if state.state == DownloadState.QUEUED:
                        queued_count += 1
                    elif state.state == DownloadState.COMPLETED:
                        completed_count += 1
                    
                    # Skip items that are currently downloading or failed
                    if state.state in [DownloadState.DOWNLOADING, DownloadState.FAILED, DownloadState.CANCELLED]:
                        continue
                    
                    # Check if all files for this item already exist
                    all_files_exist = True
                    checked_files = 0
                    
                    if item.item_type == ItemType.ALBUM:
                        # Check all tracks in the album
                        for track in item.tracks:
                            file_path = self._get_expected_file_path(item, track)
                            checked_files += 1
                            if not file_path or not file_path.exists():
                                all_files_exist = False
                                break
                    else:
                        # Single track
                        file_path = self._get_expected_file_path(item, item.tracks[0] if item.tracks else None)
                        checked_files += 1
                        if not file_path or not file_path.exists():
                            all_files_exist = False
                    
                    # Debug logging for first few items
                    if queued_count <= 3:
                        logger.info(f"[DownloadService] Validation check: {item.title} - {checked_files} files checked, all exist: {all_files_exist}")
                        if item.item_type == ItemType.ALBUM and item.tracks:
                            first_track_path = self._get_expected_file_path(item, item.tracks[0])
                            logger.info(f"[DownloadService] First track expected path: {first_track_path}")
                            if first_track_path:
                                logger.info(f"[DownloadService] Path exists: {first_track_path.exists()}")
                    
                    # Update state based on file existence
                    if all_files_exist:
                        # All files exist - mark as completed (only if not already completed)
                        if state.state != DownloadState.COMPLETED:
                            state.state = DownloadState.COMPLETED
                            state.progress = 1.0
                            state.completed_tracks = item.total_tracks
                            state.failed_tracks = 0
                            state.status_message = "Files already exist"
                            state.updated_at = datetime.now()
                            validated_count += 1
                    else:
                        # Some files missing - only reset to queued if it was never properly completed
                        # If it was completed before, respect that status even if files are moved/deleted
                        if state.state == DownloadState.COMPLETED:
                            logger.info(f"[DownloadService] Download was completed previously, keeping completed status even though files are missing: {item.title}")
                            # Keep the completed status - user may have moved/deleted files intentionally
                        elif state.state == DownloadState.QUEUED:
                            # This was never completed, so we can validate it
                            logger.info(f"[DownloadService] Queued download has missing files, will need to download: {item.title}")
                        # Don't reset completed items back to queued
                
                if validated_count > 0:
                    self.queue_manager._persist_queue()
                    logger.info(f"[DownloadService] Validated {validated_count} items as completed on startup")
                
                logger.info(f"[DownloadService] Queue state summary: {queued_count} queued, {completed_count} completed, {validated_count} validated")
                    
        except Exception as e:
            logger.error(f"[DownloadService] Error validating queue states: {e}", exc_info=True)
    
    def _validate_priority_items(self):
        """Validate items that are about to be processed by the download engine."""
        try:
            logger.info("[DownloadService] Validating priority items that will be processed...")
            
            # Get the same items that the download engine will process
            queued_items = self.queue_manager.get_next_queued_items(limit=20)
            validated_count = 0
            
            for item in queued_items:
                # Check if all files for this item already exist
                all_files_exist = True
                
                if item.item_type == ItemType.ALBUM:
                    # Check all tracks in the album
                    for track in item.tracks:
                        file_path = self._get_expected_file_path(item, track)
                        if not file_path or not file_path.exists():
                            all_files_exist = False
                            break
                else:
                    # Single track
                    file_path = self._get_expected_file_path(item, item.tracks[0] if item.tracks else None)
                    if not file_path or not file_path.exists():
                        all_files_exist = False
                
                # If all files exist, mark as completed
                if all_files_exist:
                    with self.queue_manager._lock:
                        state = self.queue_manager.states.get(item.id)
                        if state and state.state == DownloadState.QUEUED:
                            state.state = DownloadState.COMPLETED
                            state.progress = 1.0
                            state.status_message = "Files already exist"
                            state.updated_at = datetime.now()
                            validated_count += 1
                            logger.info(f"[DownloadService] Marked as completed: {item.title}")
            
            if validated_count > 0:
                self.queue_manager._persist_queue()
                logger.info(f"[DownloadService] Validated {validated_count} priority items as completed")
            else:
                logger.info("[DownloadService] No priority items needed validation")
                
        except Exception as e:
            logger.error(f"[DownloadService] Error validating priority items: {e}", exc_info=True)
    
    def _get_expected_file_path(self, item, track=None):
        """Get the expected file path for an item/track."""
        try:
            from pathlib import Path
            
            # Get download settings
            downloads_dir = Path(self.config.get_setting('downloads.folder', str(Path.home() / 'Downloads' / 'DeeMusic')))
            quality = self.config.get_setting('downloads.quality', 'MP3_320')
            folder_structure = self.config.get_setting('downloads.folder_structure', {})
            
            # Determine file extension
            if quality == 'FLAC':
                ext = '.flac'
            else:
                ext = '.mp3'
            
            # Build path based on folder structure
            if folder_structure.get('create_artist_folder', True):
                path = downloads_dir / item.artist
                if item.item_type == ItemType.ALBUM and folder_structure.get('create_album_folder', True):
                    path = path / item.title
            else:
                path = downloads_dir
            
            # Generate filename
            if track:
                if folder_structure.get('include_track_number', True):
                    filename = f"{track.track_number:02d} - {item.artist} - {track.title}{ext}"
                else:
                    filename = f"{item.artist} - {track.title}{ext}"
            else:
                filename = f"{item.artist} - {item.title}{ext}"
            
            # Clean filename
            import re
            filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            
            return path / filename
            
        except Exception as e:
            logger.error(f"[DownloadService] Error getting expected file path: {e}")
            return None
    
    def stop(self):
        """Stop the download service."""
        if not self._is_running:
            return
        
        self._is_running = False
        self.download_engine.stop()
        
        logger.info("[DownloadService] Download service stopped")
    
    # Queue Management Methods
    
    def add_album(self, album_data: Dict[str, Any]) -> str:
        """
        Add album to download queue.
        
        Args:
            album_data: Album data from Deezer API
            
        Returns:
            Queue item ID
        """
        try:
            # Create queue item from Deezer data with complete track fetching
            import asyncio
            import concurrent.futures
            
            # Use the synchronous version to avoid async context issues
            try:
                logger.info("[DownloadService] Using synchronous complete album creation")
                queue_item = create_album_from_deezer_data_complete_sync(album_data, self.deezer_api)
            except Exception as e:
                # If complete function fails, fall back to basic function
                logger.warning(f"[DownloadService] Synchronous complete album creation failed ({e}), falling back to basic creation")
                queue_item = create_album_from_deezer_data(album_data)
            
            # Add to queue
            item_id = self.queue_manager.add_item(queue_item)
            
            logger.info(f"[DownloadService] Added album to queue: {queue_item.title} by {queue_item.artist} ({len(queue_item.tracks)} tracks)")
            return item_id
            
        except Exception as e:
            logger.error(f"[DownloadService] Error adding album to queue: {e}")
            raise
    
    async def add_album_async(self, album_data: Dict[str, Any]) -> str:
        """
        Add album to download queue (async version with complete track fetching).
        
        Args:
            album_data: Album data from Deezer API
            
        Returns:
            Queue item ID
        """
        try:
            # Create queue item from Deezer data with complete track fetching
            queue_item = await create_album_from_deezer_data_complete(album_data, self.deezer_api)
            
            # Add to queue
            item_id = self.queue_manager.add_item(queue_item)
            
            logger.info(f"[DownloadService] Added album to queue (async): {queue_item.title} by {queue_item.artist} ({len(queue_item.tracks)} tracks)")
            return item_id
            
        except Exception as e:
            logger.error(f"[DownloadService] Error adding album to queue (async): {e}")
            raise
    
    def add_track(self, track_data: Dict[str, Any]) -> str:
        """
        Add single track to download queue.
        
        Args:
            track_data: Track data from Deezer API
            
        Returns:
            Queue item ID
        """
        try:
            # Create queue item from Deezer data
            queue_item = create_track_from_deezer_data(track_data)
            
            # Add to queue
            item_id = self.queue_manager.add_item(queue_item)
            
            logger.info(f"[DownloadService] Added track to queue: {queue_item.title} by {queue_item.artist}")
            return item_id
            
        except Exception as e:
            logger.error(f"[DownloadService] Error adding track to queue: {e}")
            raise
    
    def add_playlist(self, playlist_data: Dict[str, Any]) -> str:
        """
        Add playlist to download queue.
        
        Args:
            playlist_data: Playlist data from Deezer API (may be basic or full)
            
        Returns:
            Queue item ID
        """
        try:
            # Check if we have full playlist data with tracks, or just basic data
            tracks = []
            if 'tracks' in playlist_data and 'data' in playlist_data['tracks']:
                # Full playlist data - extract tracks directly
                for track_data in playlist_data['tracks']['data']:
                    track_info = TrackInfo(
                        track_id=track_data['id'],
                        title=track_data['title'],
                        artist=track_data['artist']['name'],
                        duration=track_data['duration']
                    )
                    tracks.append(track_info)
            else:
                # Basic playlist data - need to fetch tracks from API
                playlist_id = playlist_data.get('id')
                if playlist_id and self.deezer_api:
                    logger.info(f"[DownloadService] Fetching tracks for playlist {playlist_id}")
                    # Since we're in a sync context but need async, we'll defer the track fetching
                    # to the download worker which can handle async operations properly
                    logger.info(f"[DownloadService] Will fetch playlist tracks during download process")
                else:
                    logger.error(f"[DownloadService] No playlist ID or DeezerAPI available for fetching tracks")
            
            # Create playlist queue item
            queue_item = QueueItem(
                id="",  # Will be generated
                item_type=ItemType.PLAYLIST,
                deezer_id=playlist_data['id'],
                title=playlist_data['title'],
                artist=playlist_data.get('creator', {}).get('name', 'Various Artists'),
                total_tracks=len(tracks),
                tracks=tracks,
                created_at=datetime.now()
            )
            
            # Add to queue
            item_id = self.queue_manager.add_item(queue_item)
            
            logger.info(f"[DownloadService] Added playlist to queue: {queue_item.title} ({len(tracks)} tracks)")
            return item_id
            
        except Exception as e:
            logger.error(f"[DownloadService] Error adding playlist to queue: {e}")
            raise
    
    def remove_item(self, item_id: str) -> bool:
        """
        Remove item from queue.
        
        Args:
            item_id: Queue item ID
            
        Returns:
            True if removed successfully
        """
        try:
            success = self.queue_manager.remove_item(item_id)
            if success:
                logger.info(f"[DownloadService] Removed item from queue: {item_id}")
            return success
            
        except Exception as e:
            logger.error(f"[DownloadService] Error removing item from queue: {e}")
            return False
    
    def cancel_download(self, item_id: str) -> bool:
        """
        Cancel active download.
        
        Args:
            item_id: Queue item ID
            
        Returns:
            True if cancelled successfully
        """
        try:
            success = self.download_engine.cancel_download(item_id)
            if success:
                logger.info(f"[DownloadService] Cancelled download: {item_id}")
            return success
            
        except Exception as e:
            logger.error(f"[DownloadService] Error cancelling download: {e}")
            return False
    
    def pause_download(self, item_id: str) -> bool:
        """
        Pause active download.
        
        Args:
            item_id: Queue item ID
            
        Returns:
            True if paused successfully
        """
        try:
            success = self.download_engine.pause_download(item_id)
            if success:
                logger.info(f"[DownloadService] Paused download: {item_id}")
            return success
            
        except Exception as e:
            logger.error(f"[DownloadService] Error pausing download: {e}")
            return False
    
    def resume_download(self, item_id: str) -> bool:
        """
        Resume paused download.
        
        Args:
            item_id: Queue item ID
            
        Returns:
            True if resumed successfully
        """
        try:
            success = self.download_engine.resume_download(item_id)
            if success:
                logger.info(f"[DownloadService] Resumed download: {item_id}")
            return success
            
        except Exception as e:
            logger.error(f"[DownloadService] Error resuming download: {e}")
            return False
    
    # Queue Operations
    
    def clear_completed(self):
        """Clear completed downloads from queue."""
        try:
            self.queue_manager.clear_by_state([DownloadState.COMPLETED])
            logger.info("[DownloadService] Cleared completed downloads")
            
        except Exception as e:
            logger.error(f"[DownloadService] Error clearing completed downloads: {e}")
    
    def clear_failed(self):
        """Clear failed downloads from queue."""
        try:
            self.queue_manager.clear_by_state([DownloadState.FAILED])
            logger.info("[DownloadService] Cleared failed downloads")
            
        except Exception as e:
            logger.error(f"[DownloadService] Error clearing failed downloads: {e}")
    
    def clear_all(self):
        """Clear all downloads from queue."""
        try:
            # Cancel active downloads first
            active_downloads = self.download_engine.get_active_downloads()
            for item_id in active_downloads:
                self.download_engine.cancel_download(item_id)
            
            # Clear all items
            self.queue_manager.clear_all()
            logger.info("[DownloadService] Cleared all downloads")
            
        except Exception as e:
            logger.error(f"[DownloadService] Error clearing all downloads: {e}")
    
    def retry_failed(self) -> int:
        """
        Retry all failed downloads.
        
        Returns:
            Number of items set to retry
        """
        try:
            count = self.queue_manager.retry_failed_items()
            logger.info(f"[DownloadService] Set {count} failed items to retry")
            return count
            
        except Exception as e:
            logger.error(f"[DownloadService] Error retrying failed downloads: {e}")
            return 0
    
    # Status and Information Methods
    
    def get_queue_items(self) -> List[QueueItem]:
        """Get all queue items."""
        return self.queue_manager.get_all_items()
    
    def get_queue_items_by_state(self, state: DownloadState) -> List[QueueItem]:
        """Get queue items filtered by state."""
        return self.queue_manager.get_items_by_state(state)
    
    def get_queue_items_paginated(self, offset: int = 0, limit: int = 50) -> Dict[str, Any]:
        """Get queue items in pages for large queue handling."""
        try:
            all_items = self.queue_manager.get_all_items()
            total_count = len(all_items)
            
            # Get the requested page
            end_index = min(offset + limit, total_count)
            page_items = all_items[offset:end_index]
            
            # Get state counts for summary
            state_counts = {}
            for state in DownloadState:
                state_counts[state.name.lower()] = len(self.queue_manager.get_items_by_state(state))
            
            return {
                'items': page_items,
                'total_count': total_count,
                'offset': offset,
                'limit': limit,
                'has_more': end_index < total_count,
                'state_counts': state_counts
            }
            
        except Exception as e:
            logger.error(f"[DownloadService] Error getting paginated queue items: {e}")
            return {
                'items': [],
                'total_count': 0,
                'offset': 0,
                'limit': limit,
                'has_more': False,
                'state_counts': {}
            }
    
    def get_queue_item(self, item_id: str) -> Optional[QueueItem]:
        """Get specific queue item."""
        return self.queue_manager.get_item(item_id)
    
    def get_queue_state(self, item_id: str) -> Optional[QueueItemState]:
        """Get queue item state."""
        return self.queue_manager.get_state(item_id)
    
    def get_items_by_state(self, state: DownloadState) -> List[QueueItem]:
        """Get items with specific state."""
        return self.queue_manager.get_items_by_state(state)
    
    def get_queue_summary(self) -> Dict[str, int]:
        """Get summary of queue by state."""
        return self.queue_manager.get_queue_summary()
    
    def get_queue_statistics(self) -> Dict[str, Any]:
        """Get detailed queue statistics."""
        return self.queue_manager.get_statistics()
    
    def get_download_statistics(self) -> Dict[str, Any]:
        """Get download engine statistics."""
        return self.download_engine.get_statistics()
    
    def get_active_downloads(self) -> List[str]:
        """Get list of active download IDs."""
        return self.download_engine.get_active_downloads()
    
    def get_download_count(self) -> int:
        """Get number of active downloads."""
        return self.download_engine.get_download_count()
    
    # Configuration Methods
    
    def update_concurrent_limit(self, new_limit: int):
        """Update maximum concurrent downloads."""
        try:
            self.download_engine.update_concurrent_limit(new_limit)
            logger.info(f"[DownloadService] Updated concurrent limit to {new_limit}")
            
        except Exception as e:
            logger.error(f"[DownloadService] Error updating concurrent limit: {e}")
    
    # Event System Access
    
    def subscribe_to_events(self, event_type: str, callback):
        """Subscribe to download events."""
        self.event_bus.subscribe(event_type, callback)
    
    def unsubscribe_from_events(self, event_type: str, callback):
        """Unsubscribe from download events."""
        self.event_bus.unsubscribe(event_type, callback)
    
    # Legacy Compatibility Methods (for migration)
    
    def download_album(self, album_id: int) -> str:
        """
        Legacy method for downloading album by ID.
        
        Args:
            album_id: Deezer album ID
            
        Returns:
            Queue item ID
        """
        try:
            # Fetch album data from API
            album_data = self.deezer_api.get_album_details_sync(album_id)
            if not album_data:
                raise ValueError(f"Could not fetch album data for ID {album_id}")
            
            return self.add_album(album_data)
            
        except Exception as e:
            logger.error(f"[DownloadService] Error downloading album {album_id}: {e}")
            raise
    
    def download_track(self, track_id: int) -> str:
        """
        Legacy method for downloading track by ID.
        
        Args:
            track_id: Deezer track ID
            
        Returns:
            Queue item ID
        """
        try:
            # Fetch track data from API
            track_data = self.deezer_api.get_track_details_sync(track_id)
            if not track_data:
                raise ValueError(f"Could not fetch track data for ID {track_id}")
            
            return self.add_track(track_data)
            
        except Exception as e:
            logger.error(f"[DownloadService] Error downloading track {track_id}: {e}")
            raise
    
    def download_playlist(self, playlist_id: int) -> str:
        """
        Legacy method for downloading playlist by ID.
        
        Args:
            playlist_id: Deezer playlist ID
            
        Returns:
            Queue item ID
        """
        try:
            # Fetch playlist data from API
            playlist_data = self.deezer_api.get_playlist_details_sync(playlist_id)
            if not playlist_data:
                raise ValueError(f"Could not fetch playlist data for ID {playlist_id}")
            
            return self.add_playlist(playlist_data)
            
        except Exception as e:
            logger.error(f"[DownloadService] Error downloading playlist {playlist_id}: {e}")
            raise


# Factory function for easy creation
def create_download_service(config_manager, deezer_api) -> DownloadService:
    """Create and configure a new download service."""
    service = DownloadService(config_manager, deezer_api)
    service.start()
    return service


# Example usage and testing
if __name__ == "__main__":
    # This would be used for testing the download service
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    
    # Mock config manager for testing
    class MockConfig:
        def get_setting(self, key, default=None):
            settings = {
                'downloads.concurrent_downloads': 3,
                'downloads.quality': 'MP3_320',
                'downloads.path': 'test_downloads'
            }
            return settings.get(key, default)
        
        def get_app_data_dir(self):
            return Path.cwd() / "test_data"
    
    # Mock Deezer API for testing
    class MockDeezerAPI:
        def get_album_details_sync(self, album_id):
            return {
                'id': album_id,
                'title': 'Test Album',
                'artist': {'name': 'Test Artist'},
                'tracks': {
                    'data': [
                        {
                            'id': 123,
                            'title': 'Test Track',
                            'artist': {'name': 'Test Artist'},
                            'duration': 180,
                            'track_position': 1
                        }
                    ]
                }
            }
    
    # Test the download service
    config = MockConfig()
    deezer_api = MockDeezerAPI()
    
    service = DownloadService(config, deezer_api)
    service.start()
    
    # Test adding an album
    item_id = service.download_album(456)
    print(f"Added album with ID: {item_id}")
    
    # Test getting statistics
    stats = service.get_queue_statistics()
    print(f"Queue statistics: {stats}")
    
    service.stop()
    print("Service stopped")