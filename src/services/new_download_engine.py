"""
New download engine for reliable download execution.

This handles the actual download processing, worker management,
and coordination with the queue manager.
"""

import logging
import threading
import time
from typing import Dict, List, Optional, Set
from PyQt6.QtCore import QThreadPool, QTimer
from pathlib import Path

# Import our new models and event system
import sys
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from src.models.queue_models import QueueItem, DownloadState, ItemType
from src.services.event_bus import EventBus, DownloadEvents, QueueEvents, get_event_bus
from src.services.new_download_worker import DownloadWorker

logger = logging.getLogger(__name__)


class DownloadEngine:
    """
    Handles actual download execution and worker management.
    
    This is responsible for:
    - Managing the thread pool and worker lifecycle
    - Coordinating with the queue manager
    - Handling concurrency limits
    - Processing download requests
    """
    
    def __init__(self, queue_manager, deezer_api, config_manager):
        self.queue_manager = queue_manager
        self.deezer_api = deezer_api
        self.config = config_manager
        self.event_bus = get_event_bus()
        
        # Worker management
        self.workers: Dict[str, DownloadWorker] = {}
        self.thread_pool = QThreadPool()
        self.max_concurrent = self.config.get_setting('downloads.concurrent_downloads', 5)
        self.thread_pool.setMaxThreadCount(self.max_concurrent)
        
        # State tracking
        self._lock = threading.RLock()
        self._is_running = False
        self._processing_timer = None
        
        # Subscribe to queue events
        self.event_bus.subscribe(QueueEvents.ITEM_ADDED, self._on_item_added)
        self.event_bus.subscribe(QueueEvents.ITEM_REMOVED, self._on_item_removed)
        self.event_bus.subscribe(DownloadEvents.DOWNLOAD_COMPLETED, self._on_download_completed)
        self.event_bus.subscribe(DownloadEvents.DOWNLOAD_FAILED, self._on_download_failed)
        self.event_bus.subscribe(DownloadEvents.DOWNLOAD_CANCELLED, self._on_download_cancelled)
        
        logger.info(f"[DownloadEngine] Initialized with max {self.max_concurrent} concurrent downloads")
    
    def start(self):
        """Start the download engine"""
        with self._lock:
            if self._is_running:
                logger.warning("[DownloadEngine] Already running")
                return
            
            self._is_running = True
            
            # Start processing timer
            self._processing_timer = QTimer()
            self._processing_timer.timeout.connect(self._process_queue)
            self._processing_timer.start(2000)  # Check every 2 seconds
            
            # Process any existing queued items
            self._process_queue()
            
            logger.info("[DownloadEngine] Started")
    
    def stop(self):
        """Stop the download engine and cancel all downloads"""
        with self._lock:
            if not self._is_running:
                return
            
            self._is_running = False
            
            # Stop processing timer
            if self._processing_timer:
                self._processing_timer.stop()
                self._processing_timer = None
            
            # Cancel all active downloads
            active_workers = list(self.workers.keys())
            for item_id in active_workers:
                self.cancel_download(item_id)
            
            # Wait for thread pool to finish with extremely short timeout
            if not self.thread_pool.waitForDone(50):  # 50ms timeout - extremely aggressive
                logger.warning("[DownloadEngine] Some downloads did not stop gracefully, forcing immediate shutdown")
                # Force terminate any remaining threads immediately
                self.thread_pool.clear()
                # Try to terminate any remaining threads more aggressively
                try:
                    self.thread_pool.waitForDone(1)  # Give 1ms for cleanup
                except:
                    pass
                # Create a new thread pool to ensure clean state
                from PyQt6.QtCore import QThreadPool
                self.thread_pool = QThreadPool()
                self.thread_pool.setMaxThreadCount(4)
            
            logger.info(f"[DownloadEngine] Stopped ({len(active_workers)} downloads cancelled)")
    
    def _process_queue(self):
        """Process queued items and start downloads"""
        if not self._is_running:
            return
        
        with self._lock:
            # Check how many slots are available
            available_slots = self.max_concurrent - len(self.workers)
            if available_slots <= 0:
                return
            
            # Get next queued items
            queued_items = self.queue_manager.get_next_queued_items(limit=available_slots)
            
            if not queued_items:
                return
            
            logger.debug(f"[DownloadEngine] Processing {len(queued_items)} queued items")
            
            # Start downloads for queued items
            for item in queued_items:
                if len(self.workers) >= self.max_concurrent:
                    break
                
                self._start_download(item)
    
    def _start_download(self, item: QueueItem):
        """Start downloading an item"""
        with self._lock:
            if item.id in self.workers:
                logger.warning(f"[DownloadEngine] Item {item.id} already downloading")
                return
            
            if not self._is_running:
                logger.debug(f"[DownloadEngine] Not starting download for {item.id} - engine stopped")
                return
            
            # Create worker
            worker = DownloadWorker(
                item=item,
                deezer_api=self.deezer_api,
                config_manager=self.config,
                event_bus=self.event_bus
            )
            
            # Track worker
            self.workers[item.id] = worker
            
            # Update queue state
            self.queue_manager.update_state(item.id, state=DownloadState.DOWNLOADING)
            
            # Start worker in thread pool
            self.thread_pool.start(worker)
            
            logger.info(f"[DownloadEngine] Started download: {item.title} by {item.artist}")
            
            # Emit event
            self.event_bus.emit(DownloadEvents.DOWNLOAD_STARTED, item.id)
    
    def cancel_download(self, item_id: str) -> bool:
        """Cancel a specific download"""
        with self._lock:
            if item_id not in self.workers:
                logger.warning(f"[DownloadEngine] Cannot cancel unknown download: {item_id}")
                return False
            
            worker = self.workers[item_id]
            worker.cancel()
            
            # Update queue state
            self.queue_manager.update_state(item_id, state=DownloadState.CANCELLED)
            
            logger.info(f"[DownloadEngine] Cancelled download: {item_id}")
            return True
    
    def pause_download(self, item_id: str) -> bool:
        """Pause a specific download"""
        with self._lock:
            if item_id not in self.workers:
                logger.warning(f"[DownloadEngine] Cannot pause unknown download: {item_id}")
                return False
            
            worker = self.workers[item_id]
            worker.pause()
            
            # Update queue state
            self.queue_manager.update_state(item_id, state=DownloadState.PAUSED)
            
            logger.info(f"[DownloadEngine] Paused download: {item_id}")
            return True
    
    def resume_download(self, item_id: str) -> bool:
        """Resume a paused download"""
        with self._lock:
            if item_id not in self.workers:
                logger.warning(f"[DownloadEngine] Cannot resume unknown download: {item_id}")
                return False
            
            worker = self.workers[item_id]
            worker.resume()
            
            # Update queue state
            self.queue_manager.update_state(item_id, state=DownloadState.DOWNLOADING)
            
            logger.info(f"[DownloadEngine] Resumed download: {item_id}")
            return True
    
    def get_active_downloads(self) -> List[str]:
        """Get list of active download IDs"""
        with self._lock:
            return list(self.workers.keys())
    
    def get_download_count(self) -> int:
        """Get number of active downloads"""
        with self._lock:
            return len(self.workers)
    
    def update_concurrent_limit(self, new_limit: int):
        """Update the maximum concurrent downloads"""
        with self._lock:
            old_limit = self.max_concurrent
            self.max_concurrent = max(1, min(new_limit, 10))  # Clamp between 1-10
            self.thread_pool.setMaxThreadCount(self.max_concurrent)
            
            logger.info(f"[DownloadEngine] Updated concurrent limit: {old_limit} → {self.max_concurrent}")
            
            # If we increased the limit, try to start more downloads
            if self.max_concurrent > old_limit:
                self._process_queue()
    
    def get_statistics(self) -> Dict[str, any]:
        """Get download engine statistics"""
        with self._lock:
            return {
                'active_downloads': len(self.workers),
                'max_concurrent': self.max_concurrent,
                'thread_pool_active': self.thread_pool.activeThreadCount(),
                'thread_pool_max': self.thread_pool.maxThreadCount(),
                'is_running': self._is_running,
                'available_slots': self.max_concurrent - len(self.workers)
            }
    
    # Event handlers
    def _on_item_added(self, item_id: str):
        """Handle item added to queue"""
        if self._is_running:
            # Small delay to allow queue state to settle
            QTimer.singleShot(100, self._process_queue)
    
    def _on_item_removed(self, item_id: str):
        """Handle item removed from queue"""
        # Cancel download if it's active
        if item_id in self.workers:
            self.cancel_download(item_id)
    
    def _on_download_completed(self, item_id: str):
        """Handle download completion"""
        with self._lock:
            if item_id in self.workers:
                del self.workers[item_id]
                logger.debug(f"[DownloadEngine] Removed completed worker: {item_id}")
            
            # Update queue state
            self.queue_manager.update_state(item_id, 
                state=DownloadState.COMPLETED, 
                progress=1.0
            )
            
            # Process next items
            if self._is_running:
                QTimer.singleShot(100, self._process_queue)
    
    def _on_download_failed(self, item_id: str, error_message: str):
        """Handle download failure"""
        with self._lock:
            if item_id in self.workers:
                del self.workers[item_id]
                logger.debug(f"[DownloadEngine] Removed failed worker: {item_id}")
            
            # Update queue state
            self.queue_manager.update_state(item_id, 
                state=DownloadState.FAILED,
                error_message=error_message
            )
            
            # Process next items
            if self._is_running:
                QTimer.singleShot(100, self._process_queue)
    
    def _on_download_cancelled(self, item_id: str):
        """Handle download cancellation"""
        with self._lock:
            if item_id in self.workers:
                del self.workers[item_id]
                logger.debug(f"[DownloadEngine] Removed cancelled worker: {item_id}")
            
            # Queue state should already be updated by cancel_download()
            
            # Process next items
            if self._is_running:
                QTimer.singleShot(100, self._process_queue)
    
    def cleanup_orphaned_workers(self):
        """Clean up any orphaned workers (safety method)"""
        with self._lock:
            orphaned = []
            
            for item_id, worker in self.workers.items():
                if worker.is_finished():
                    orphaned.append(item_id)
            
            for item_id in orphaned:
                del self.workers[item_id]
                logger.warning(f"[DownloadEngine] Cleaned up orphaned worker: {item_id}")
            
            if orphaned:
                logger.info(f"[DownloadEngine] Cleaned up {len(orphaned)} orphaned workers")
    
    def __del__(self):
        """Cleanup on destruction"""
        try:
            self.stop()
        except:
            pass