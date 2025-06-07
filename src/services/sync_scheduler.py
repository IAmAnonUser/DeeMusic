"""Scheduler for automatic library synchronization."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict
from dataclasses import dataclass

from .library_sync import LibrarySyncService

@dataclass
class SyncSchedule:
    interval_hours: int
    last_sync: Optional[datetime] = None
    is_enabled: bool = True

class SyncScheduler:
    """Manages automatic library synchronization scheduling."""
    
    def __init__(self, sync_service: LibrarySyncService, config: Dict):
        self.sync_service = sync_service
        self.schedule = SyncSchedule(
            interval_hours=config.get('sync_interval_hours', 24),
            is_enabled=config.get('auto_sync_enabled', True)
        )
        self._scheduler_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Start the sync scheduler."""
        if self.schedule.is_enabled and not self._scheduler_task:
            self._scheduler_task = asyncio.create_task(self._run_scheduler())
            logging.info("Sync scheduler started")
    
    async def stop(self):
        """Stop the sync scheduler."""
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
            self._scheduler_task = None
            logging.info("Sync scheduler stopped")
    
    def set_schedule(self, interval_hours: int, enabled: bool = True):
        """Update the sync schedule."""
        self.schedule.interval_hours = interval_hours
        self.schedule.is_enabled = enabled
        logging.info(f"Sync schedule updated: interval={interval_hours}h, enabled={enabled}")
    
    async def _run_scheduler(self):
        """Run the scheduler loop."""
        while True:
            try:
                # Check if sync is needed
                if self._should_sync():
                    logging.info("Starting scheduled library sync")
                    success = await self.sync_service.sync_library(full_sync=False)
                    if success:
                        self.schedule.last_sync = datetime.utcnow()
                        logging.info("Scheduled sync completed successfully")
                    else:
                        logging.error("Scheduled sync failed")
                
                # Wait for next check
                await asyncio.sleep(60 * 60)  # Check every hour
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in sync scheduler: {str(e)}")
                await asyncio.sleep(60 * 5)  # Wait 5 minutes before retrying
    
    def _should_sync(self) -> bool:
        """Check if sync should be performed."""
        if not self.schedule.is_enabled:
            return False
            
        if not self.schedule.last_sync:
            return True
            
        next_sync = self.schedule.last_sync + timedelta(hours=self.schedule.interval_hours)
        return datetime.utcnow() >= next_sync 