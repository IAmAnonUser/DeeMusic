"""
Migration script to convert old download queue data to the new format.

This script helps transition from the old download_manager.py system
to the new queue management system.
"""

import json
import logging
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add src to path for imports
import sys
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from models.queue_models import QueueItem, QueueItemState, QueueSnapshot, DownloadState, ItemType, TrackInfo


class QueueMigrator:
    """Migrates old queue data to new format."""
    
    def __init__(self, app_data_dir: Path):
        self.app_data_dir = Path(app_data_dir)
        self.old_queue_file = self.app_data_dir / "download_queue_state.json"
        self.new_queue_file = self.app_data_dir / "new_queue_state.json"
        self.backup_dir = self.app_data_dir / "migration_backup"
        
    def migrate(self) -> bool:
        """
        Perform the migration.
        
        Returns:
            True if migration was successful
        """
        try:
            logger.info("Starting queue data migration...")
            
            # Check if old queue file exists
            if not self.old_queue_file.exists():
                logger.info("No old queue file found, nothing to migrate")
                return True
            
            # Create backup
            self._create_backup()
            
            # Load old queue data
            old_data = self._load_old_queue_data()
            if not old_data:
                logger.warning("No valid old queue data found")
                return True
            
            # Convert to new format
            new_items, new_states = self._convert_queue_data(old_data)
            
            # Save new format
            self._save_new_queue_data(new_items, new_states)
            
            logger.info(f"Migration completed successfully: {len(new_items)} items migrated")
            return True
            
        except Exception as e:
            logger.error(f"Migration failed: {e}", exc_info=True)
            return False
    
    def _create_backup(self):
        """Create backup of old data."""
        try:
            self.backup_dir.mkdir(exist_ok=True)
            
            # Backup old queue file
            if self.old_queue_file.exists():
                backup_file = self.backup_dir / f"download_queue_state_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                shutil.copy2(self.old_queue_file, backup_file)
                logger.info(f"Created backup: {backup_file}")
            
        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            raise
    
    def _load_old_queue_data(self) -> Optional[Dict[str, Any]]:
        """Load old queue data from file."""
        try:
            with open(self.old_queue_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.info(f"Loaded old queue data with {len(data.get('unfinished_downloads', []))} unfinished downloads")
            return data
            
        except Exception as e:
            logger.error(f"Error loading old queue data: {e}")
            return None
    
    def _convert_queue_data(self, old_data: Dict[str, Any]) -> tuple[Dict[str, QueueItem], Dict[str, QueueItemState]]:
        """Convert old queue data to new format."""
        new_items = {}
        new_states = {}
        
        # Process unfinished downloads
        unfinished_downloads = old_data.get('unfinished_downloads', [])
        
        for old_item in unfinished_downloads:
            try:
                # Skip invalid entries
                if not self._is_valid_old_entry(old_item):
                    continue
                
                # Convert to new format
                queue_item, queue_state = self._convert_single_item(old_item)
                
                if queue_item and queue_state:
                    new_items[queue_item.id] = queue_item
                    new_states[queue_item.id] = queue_state
                
            except Exception as e:
                logger.warning(f"Error converting item: {e}")
                continue
        
        # Process failed downloads
        failed_downloads = old_data.get('failed_downloads', [])
        for failed_item in failed_downloads:
            try:
                # Convert failed item
                queue_item, queue_state = self._convert_failed_item(failed_item)
                
                if queue_item and queue_state:
                    new_items[queue_item.id] = queue_item
                    new_states[queue_item.id] = queue_state
                
            except Exception as e:
                logger.warning(f"Error converting failed item: {e}")
                continue
        
        logger.info(f"Converted {len(new_items)} items to new format")
        return new_items, new_states
    
    def _is_valid_old_entry(self, entry: Dict[str, Any]) -> bool:
        """Check if old entry is valid for conversion."""
        # Skip entries with 'unknown' IDs (corrupted data)
        album_id = entry.get('album_id')
        if album_id == 'unknown' or album_id is None:
            return False
        
        # Check for valid tracks
        queued_tracks = entry.get('queued_tracks', [])
        if not queued_tracks:
            return False
        
        # Check for valid track IDs
        valid_tracks = [
            track for track in queued_tracks 
            if track.get('track_id') != 'unknown' and track.get('track_id') is not None
        ]
        
        return len(valid_tracks) > 0
    
    def _convert_single_item(self, old_item: Dict[str, Any]) -> tuple[Optional[QueueItem], Optional[QueueItemState]]:
        """Convert a single old item to new format."""
        try:
            # Extract basic info
            album_id = old_item.get('album_id')
            album_title = old_item.get('album_title', 'Unknown Album')
            artist_name = old_item.get('artist_name', 'Unknown Artist')
            queued_tracks = old_item.get('queued_tracks', [])
            
            # Convert tracks
            tracks = []
            for track_data in queued_tracks:
                if track_data.get('track_id') == 'unknown':
                    continue
                
                track_info = TrackInfo(
                    track_id=int(track_data.get('track_id', 0)),
                    title=track_data.get('title', 'Unknown Track'),
                    artist=track_data.get('artist', artist_name),
                    duration=int(track_data.get('duration', 0)),
                    track_number=track_data.get('track_number'),
                    disc_number=track_data.get('disc_number')
                )
                tracks.append(track_info)
            
            if not tracks:
                return None, None
            
            # Determine item type
            item_type = ItemType.ALBUM  # Most old items are albums
            if len(tracks) == 1:
                item_type = ItemType.TRACK
            
            # Create queue item
            queue_item = QueueItem(
                id="",  # Will be generated
                item_type=item_type,
                deezer_id=int(album_id),
                title=album_title,
                artist=artist_name,
                total_tracks=len(tracks),
                tracks=tracks,
                created_at=datetime.now()
            )
            
            # Create queue state (assume queued for migration)
            queue_state = QueueItemState(
                item_id=queue_item.id,
                state=DownloadState.QUEUED,
                progress=0.0,
                completed_tracks=0,
                failed_tracks=0
            )
            
            return queue_item, queue_state
            
        except Exception as e:
            logger.error(f"Error converting single item: {e}")
            return None, None
    
    def _convert_failed_item(self, failed_item: Dict[str, Any]) -> tuple[Optional[QueueItem], Optional[QueueItemState]]:
        """Convert a failed item to new format."""
        try:
            # Similar to single item but mark as failed
            queue_item, queue_state = self._convert_single_item(failed_item)
            
            if queue_item and queue_state:
                # Mark as failed
                queue_state.state = DownloadState.FAILED
                queue_state.error_message = failed_item.get('error_message', 'Migration: Previously failed')
            
            return queue_item, queue_state
            
        except Exception as e:
            logger.error(f"Error converting failed item: {e}")
            return None, None
    
    def _save_new_queue_data(self, items: Dict[str, QueueItem], states: Dict[str, QueueItemState]):
        """Save new queue data to file."""
        try:
            # Create snapshot
            snapshot = QueueSnapshot(
                items=items,
                states=states,
                created_at=datetime.now()
            )
            
            # Save to file
            snapshot.save_to_file(str(self.new_queue_file))
            
            logger.info(f"Saved new queue data to: {self.new_queue_file}")
            
        except Exception as e:
            logger.error(f"Error saving new queue data: {e}")
            raise
    
    def verify_migration(self) -> bool:
        """Verify that migration was successful."""
        try:
            if not self.new_queue_file.exists():
                logger.error("New queue file was not created")
                return False
            
            # Try to load new queue data
            snapshot = QueueSnapshot.load_from_file(str(self.new_queue_file))
            if not snapshot:
                logger.error("Could not load new queue data")
                return False
            
            logger.info(f"Migration verification successful: {len(snapshot.items)} items, {len(snapshot.states)} states")
            return True
            
        except Exception as e:
            logger.error(f"Migration verification failed: {e}")
            return False


def main():
    """Main migration function."""
    import os
    
    # Get app data directory
    app_data_dir = Path(os.getenv('APPDATA', Path.home())) / 'DeeMusic'
    
    if not app_data_dir.exists():
        logger.error(f"App data directory not found: {app_data_dir}")
        return False
    
    # Create migrator
    migrator = QueueMigrator(app_data_dir)
    
    # Perform migration
    success = migrator.migrate()
    
    if success:
        # Verify migration
        if migrator.verify_migration():
            logger.info("Migration completed and verified successfully!")
            
            # Ask user if they want to keep old file
            response = input("Migration successful! Keep old queue file as backup? (y/n): ")
            if response.lower() != 'y':
                try:
                    migrator.old_queue_file.unlink()
                    logger.info("Old queue file removed")
                except Exception as e:
                    logger.warning(f"Could not remove old queue file: {e}")
            
            return True
        else:
            logger.error("Migration verification failed")
            return False
    else:
        logger.error("Migration failed")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)