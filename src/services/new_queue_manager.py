"""
New queue manager for reliable download queue management.

This replaces the complex download_manager.py with a clean, thread-safe
queue management system that eliminates race conditions and provides
reliable persistence.
"""

import threading
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set
from datetime import datetime

import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from src.models.queue_models import (
    QueueItem, QueueItemState, QueueSnapshot, DownloadState, ItemType
)
from src.services.event_bus import EventBus, QueueEvents, get_event_bus

logger = logging.getLogger(__name__)


class QueueManager:
    """
    Manages the download queue state and persistence.
    
    This is the single source of truth for all queue operations.
    It provides thread-safe access to queue items and their states,
    and handles persistence to disk.
    """
    
    def __init__(self, config_manager, event_bus: EventBus = None):
        self.config = config_manager
        self.event_bus = event_bus or get_event_bus()
        
        # Thread-safe storage
        self._lock = threading.RLock()
        self.items: Dict[str, QueueItem] = {}
        self.states: Dict[str, QueueItemState] = {}
        
        # Persistence
        self.queue_file = Path(config_manager.config_dir) / "new_queue_state.json"
        
        # Load existing queue on startup
        self._load_queue()
        
        logger.info(f"[QueueManager] Initialized with {len(self.items)} items")
    
    def add_item(self, item: QueueItem) -> str:
        """
        Add item to queue.
        
        Args:
            item: The queue item to add
            
        Returns:
            The item ID
        """
        with self._lock:
            # Check for duplicates
            if self._has_duplicate(item):
                logger.warning(f"[QueueManager] Duplicate item not added: {item.title} by {item.artist}")
                return None
            
            # Add item and initial state
            self.items[item.id] = item
            self.states[item.id] = QueueItemState(
                item_id=item.id,
                state=DownloadState.QUEUED
            )
            
            # Persist and notify
            self._persist_queue()
            self.event_bus.emit(QueueEvents.ITEM_ADDED, item.id)
            
            logger.info(f"[QueueManager] Added {item.item_type.value}: {item.title} by {item.artist}")
            return item.id
    
    def remove_item(self, item_id: str) -> bool:
        """
        Remove item from queue.
        
        Args:
            item_id: ID of item to remove
            
        Returns:
            True if item was removed, False if not found
        """
        with self._lock:
            if item_id not in self.items:
                logger.warning(f"[QueueManager] Cannot remove unknown item: {item_id}")
                return False
            
            item = self.items[item_id]
            state = self.states[item_id]
            
            # If downloading, mark as cancelled first
            if state.state == DownloadState.DOWNLOADING:
                self.update_state(item_id, state=DownloadState.CANCELLED)
            
            # Remove from storage
            del self.items[item_id]
            del self.states[item_id]
            
            # Persist and notify
            self._persist_queue()
            self.event_bus.emit(QueueEvents.ITEM_REMOVED, item_id)
            
            logger.info(f"[QueueManager] Removed {item.item_type.value}: {item.title}")
            return True
    
    def update_state(self, item_id: str, **kwargs):
        """
        Update item state.
        
        Args:
            item_id: ID of item to update
            **kwargs: State fields to update
        """
        with self._lock:
            if item_id not in self.states:
                logger.warning(f"[QueueManager] Cannot update unknown item state: {item_id}")
                return
            
            old_state = self.states[item_id].state
            self.states[item_id].update(**kwargs)
            new_state = self.states[item_id].state
            
            # Always persist when state is updated (not just when state enum changes)
            self._persist_queue()
            
            # Always notify of state changes
            self.event_bus.emit(QueueEvents.ITEM_STATE_CHANGED, item_id, self.states[item_id])
            
            if old_state != new_state:
                logger.debug(f"[QueueManager] State changed for {item_id}: {old_state.value} → {new_state.value}")
            else:
                logger.debug(f"[QueueManager] State updated for {item_id}: {kwargs}")
    
    def get_item(self, item_id: str) -> Optional[QueueItem]:
        """Get queue item by ID"""
        with self._lock:
            return self.items.get(item_id)
    
    def get_state(self, item_id: str) -> Optional[QueueItemState]:
        """Get item state by ID"""
        with self._lock:
            return self.states.get(item_id)
    
    def get_items_by_state(self, state: DownloadState) -> List[QueueItem]:
        """Get all items with specific state"""
        with self._lock:
            return [
                self.items[item_id] 
                for item_id, item_state in self.states.items()
                if item_state.state == state and item_id in self.items
            ]
    
    def get_all_items(self) -> List[QueueItem]:
        """Get all queue items"""
        with self._lock:
            return list(self.items.values())
    
    def get_queue_summary(self) -> Dict[str, int]:
        """Get summary of queue by state"""
        with self._lock:
            summary = {state.value: 0 for state in DownloadState}
            for state in self.states.values():
                summary[state.state.value] += 1
            return summary
    
    def clear_by_state(self, states: List[DownloadState]):
        """
        Clear items with specific states.
        
        Args:
            states: List of states to clear
        """
        with self._lock:
            to_remove = [
                item_id for item_id, state in self.states.items()
                if state.state in states
            ]
            
            if not to_remove:
                logger.info(f"[QueueManager] No items to clear with states: {[s.value for s in states]}")
                return
            
            # Remove items
            for item_id in to_remove:
                item = self.items.get(item_id)
                if item:
                    logger.debug(f"[QueueManager] Clearing {item.item_type.value}: {item.title}")
                del self.items[item_id]
                del self.states[item_id]
            
            # Persist and notify
            self._persist_queue()
            self.event_bus.emit(QueueEvents.QUEUE_CLEARED, states, to_remove)
            
            logger.info(f"[QueueManager] Cleared {len(to_remove)} items with states: {[s.value for s in states]}")
    
    def clear_all(self):
        """Clear all items from queue"""
        with self._lock:
            count = len(self.items)
            
            # Mark downloading items as cancelled
            for item_id, state in self.states.items():
                if state.state == DownloadState.DOWNLOADING:
                    state.update(state=DownloadState.CANCELLED)
            
            # Clear all
            self.items.clear()
            self.states.clear()
            
            # Persist and notify
            self._persist_queue()
            self.event_bus.emit(QueueEvents.QUEUE_CLEARED, list(DownloadState), [])
            
            logger.info(f"[QueueManager] Cleared all {count} items from queue")
    
    def retry_failed_items(self) -> int:
        """
        Retry all failed items.
        
        Returns:
            Number of items set to retry
        """
        with self._lock:
            failed_items = [
                item_id for item_id, state in self.states.items()
                if state.state == DownloadState.FAILED
            ]
            
            for item_id in failed_items:
                self.states[item_id].update(
                    state=DownloadState.QUEUED,
                    error_message=None,
                    retry_count=self.states[item_id].retry_count + 1
                )
                self.event_bus.emit(QueueEvents.ITEM_STATE_CHANGED, item_id, self.states[item_id])
            
            if failed_items:
                self._persist_queue()
                logger.info(f"[QueueManager] Set {len(failed_items)} failed items to retry")
            
            return len(failed_items)
    
    def get_next_queued_items(self, limit: int = None) -> List[QueueItem]:
        """
        Get next queued items for processing.
        
        Args:
            limit: Maximum number of items to return
            
        Returns:
            List of queued items, ordered by creation time
        """
        with self._lock:
            queued_items = []
            
            for item_id, state in self.states.items():
                if state.state == DownloadState.QUEUED and item_id in self.items:
                    queued_items.append(self.items[item_id])
            
            # Sort by creation time (oldest first)
            queued_items.sort(key=lambda x: x.created_at)
            
            if limit:
                queued_items = queued_items[:limit]
            
            return queued_items
    
    def _has_duplicate(self, item: QueueItem) -> bool:
        """Check if item is already in queue"""
        for existing_item in self.items.values():
            if (existing_item.item_type == item.item_type and 
                existing_item.deezer_id == item.deezer_id):
                return True
        return False
    
    def _persist_queue(self):
        """Save queue to disk"""
        try:
            snapshot = QueueSnapshot(
                items=self.items.copy(),
                states=self.states.copy()
            )
            
            # Ensure directory exists
            self.queue_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Save to file
            snapshot.save_to_file(str(self.queue_file))
            
            logger.debug(f"[QueueManager] Persisted queue with {len(self.items)} items")
            
        except Exception as e:
            logger.error(f"[QueueManager] Failed to persist queue: {e}", exc_info=True)
    
    def _load_queue(self):
        """Load queue from disk"""
        try:
            if not self.queue_file.exists():
                logger.info("[QueueManager] No existing queue file found")
                return
            
            logger.info(f"[QueueManager] Loading queue from {self.queue_file}")
            snapshot = QueueSnapshot.load_from_file(str(self.queue_file))
            if snapshot:
                self.items = snapshot.items
                self.states = snapshot.states
                
                # Reset downloading items to queued (they were interrupted)
                reset_count = 0
                for state in self.states.values():
                    if state.state == DownloadState.DOWNLOADING:
                        state.update(state=DownloadState.QUEUED)
                        reset_count += 1
                
                if reset_count > 0:
                    logger.info(f"[QueueManager] Reset {reset_count} interrupted downloads to queued")
                    self._persist_queue()
                
                logger.info(f"[QueueManager] Loaded queue with {len(self.items)} items")
                self.event_bus.emit(QueueEvents.QUEUE_LOADED, len(self.items))
            else:
                logger.warning(f"[QueueManager] Failed to load queue snapshot from {self.queue_file}")
                self._handle_corrupted_queue_file()
            
        except Exception as e:
            logger.error(f"[QueueManager] Failed to load queue: {e}", exc_info=True)
            self._handle_corrupted_queue_file()
    
    def _handle_corrupted_queue_file(self):
        """Handle corrupted queue file by backing it up and starting fresh"""
        try:
            if self.queue_file.exists():
                # Create backup with timestamp
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = self.queue_file.with_suffix(f'.corrupted_{timestamp}.json')
                
                # Move corrupted file to backup
                import shutil
                shutil.move(str(self.queue_file), str(backup_file))
                logger.warning(f"[QueueManager] Corrupted queue file backed up to {backup_file}")
                logger.info("[QueueManager] Starting with empty queue due to corrupted file")
            
        except Exception as e:
            logger.error(f"[QueueManager] Failed to backup corrupted queue file: {e}")
            # If backup fails, just delete the corrupted file
            try:
                self.queue_file.unlink()
                logger.warning("[QueueManager] Deleted corrupted queue file, starting fresh")
            except Exception as delete_error:
                logger.error(f"[QueueManager] Failed to delete corrupted queue file: {delete_error}")
    
    def get_statistics(self) -> Dict[str, any]:
        """Get detailed queue statistics"""
        with self._lock:
            stats = {
                'total_items': len(self.items),
                'by_state': self.get_queue_summary(),
                'by_type': {},
                'total_tracks': 0,
                'completed_tracks': 0,
                'failed_tracks': 0
            }
            
            # Count by type
            for item in self.items.values():
                item_type = item.item_type.value
                stats['by_type'][item_type] = stats['by_type'].get(item_type, 0) + 1
                stats['total_tracks'] += item.total_tracks
            
            # Count track progress
            for state in self.states.values():
                stats['completed_tracks'] += state.completed_tracks
                stats['failed_tracks'] += state.failed_tracks
            
            return stats
    
    def cleanup_orphaned_states(self):
        """Remove states that don't have corresponding items"""
        with self._lock:
            orphaned = [
                state_id for state_id in self.states.keys()
                if state_id not in self.items
            ]
            
            for state_id in orphaned:
                del self.states[state_id]
            
            if orphaned:
                logger.info(f"[QueueManager] Cleaned up {len(orphaned)} orphaned states")
                self._persist_queue()


# Convenience functions for common operations
def create_queue_manager(config_manager) -> QueueManager:
    """Create a new queue manager instance"""
    return QueueManager(config_manager)


# Example usage and testing
if __name__ == "__main__":
    # This would be used for testing the queue manager
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    
    from src.models.queue_models import QueueItem, TrackInfo, ItemType
    
    # Mock config manager for testing
    class MockConfig:
        def get_app_data_dir(self):
            return Path.cwd() / "test_data"
    
    # Test the queue manager
    config = MockConfig()
    queue_manager = QueueManager(config)
    
    # Create test item
    track = TrackInfo(
        track_id=123,
        title="Test Track",
        artist="Test Artist",
        duration=180
    )
    
    item = QueueItem.create_album(
        deezer_id=456,
        title="Test Album",
        artist="Test Artist",
        tracks=[track]
    )
    
    # Test operations
    item_id = queue_manager.add_item(item)
    print(f"Added item: {item_id}")
    
    queue_manager.update_state(item_id, progress=0.5, completed_tracks=1)
    print(f"Updated progress")
    
    stats = queue_manager.get_statistics()
    print(f"Statistics: {stats}")
    
    queue_manager.remove_item(item_id)
    print(f"Removed item")