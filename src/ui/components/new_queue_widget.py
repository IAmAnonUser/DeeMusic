"""
New download queue widget using the event-driven architecture.

This widget provides a clean, responsive interface for managing downloads
with automatic updates via the event system.
"""

import logging
from typing import Dict, Optional
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                            QLabel, QScrollArea, QFrame, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot

# Import our new system components
import sys
from pathlib import Path
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from src.models.queue_models import QueueItem, QueueItemState, DownloadState
from src.services.download_service import DownloadService
from src.services.event_bus import EventBus, QueueEvents, DownloadEvents
from src.ui.components.new_queue_item_widget import QueueItemWidget

logger = logging.getLogger(__name__)


class NewQueueWidget(QWidget):
    """
    Modern download queue widget with event-driven updates.
    
    Features:
    - Automatic UI updates via events (no manual refresh needed)
    - Individual item controls (remove, retry, pause)
    - Clean widget lifecycle management
    - Proper handling of large queues
    """
    
    # Signals for communication with main window
    queue_cleared = pyqtSignal()
    item_removed = pyqtSignal(str)  # item_id
    
    # Internal signals for thread-safe GUI updates
    download_started_signal = pyqtSignal(str)
    download_progress_signal = pyqtSignal(str, float, int, int)
    download_completed_signal = pyqtSignal(str)
    download_failed_signal = pyqtSignal(str, str)
    
    def __init__(self, download_service: DownloadService, parent=None):
        super().__init__(parent)
        self.download_service = download_service
        self.event_bus = download_service.event_bus
        
        # Widget tracking
        self.item_widgets: Dict[str, QueueItemWidget] = {}
        self.smart_loading_active = False  # Track if we're using smart loading
        self.loaded_item_count = 0  # Track how many items we've loaded
        
        # Setup UI
        self._setup_ui()
        self._setup_signal_connections()
        self._setup_event_subscriptions()
        self._load_existing_queue()
        
        logger.info("[NewQueueWidget] Initialized new queue widget")
    
    def _setup_signal_connections(self):
        """Connect internal signals to update methods."""
        self.download_started_signal.connect(self._update_download_started)
        self.download_progress_signal.connect(self._update_download_progress)
        self.download_completed_signal.connect(self._update_download_completed)
        self.download_failed_signal.connect(self._update_download_failed)
    
    def _setup_ui(self):
        """Setup the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)  # More padding
        layout.setSpacing(4)  # More spacing between sections
        
        # Header with title and statistics
        self._create_header(layout)
        
        # Action buttons
        self._create_action_buttons(layout)
        
        # Scrollable queue area
        self._create_queue_area(layout)
        
        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("QueueStatusLabel")
        layout.addWidget(self.status_label)
    
    def _create_header(self, layout):
        """Create header with title and statistics."""
        header_layout = QHBoxLayout()
        
        # Title
        title_label = QLabel("Download Queue")
        title_label.setObjectName("QueueTitle")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # Statistics
        self.stats_label = QLabel()
        self.stats_label.setObjectName("QueueStats")
        header_layout.addWidget(self.stats_label)
        
        layout.addLayout(header_layout)
        
        # Update statistics
        self._update_statistics()
    
    def _create_action_buttons(self, layout):
        """Create action buttons for queue management."""
        button_layout = QHBoxLayout()
        
        # Clear All button
        self.clear_all_button = QPushButton("Clear All")
        self.clear_all_button.setObjectName("ClearAllButton")
        self.clear_all_button.clicked.connect(self._handle_clear_all)
        self.clear_all_button.setToolTip("Remove all items from the queue")
        button_layout.addWidget(self.clear_all_button)
        
        # Clear Completed button
        self.clear_completed_button = QPushButton("Clear Completed")
        self.clear_completed_button.setObjectName("ClearCompletedButton")
        self.clear_completed_button.clicked.connect(self._handle_clear_completed)
        self.clear_completed_button.setToolTip("Remove completed downloads")
        button_layout.addWidget(self.clear_completed_button)
        
        # Clear Failed button
        self.clear_failed_button = QPushButton("Clear Failed")
        self.clear_failed_button.setObjectName("ClearFailedButton")
        self.clear_failed_button.clicked.connect(self._handle_clear_failed)
        self.clear_failed_button.setToolTip("Remove failed downloads")
        button_layout.addWidget(self.clear_failed_button)
        
        # Retry Failed button
        self.retry_failed_button = QPushButton("Retry Failed")
        self.retry_failed_button.setObjectName("RetryFailedButton")
        self.retry_failed_button.clicked.connect(self._handle_retry_failed)
        self.retry_failed_button.setToolTip("Retry all failed downloads")
        button_layout.addWidget(self.retry_failed_button)
        
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
    
    def _create_queue_area(self, layout):
        """Create scrollable area for queue items."""
        # Create scroll area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Create container widget for queue items
        self.queue_container = QWidget()
        self.queue_layout = QVBoxLayout(self.queue_container)
        self.queue_layout.setContentsMargins(2, 2, 2, 2)  # Small margins
        self.queue_layout.setSpacing(3)  # More spacing between items
        
        # Set size policy for container to allow proper scrolling
        from PyQt6.QtWidgets import QSizePolicy
        self.queue_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        
        self.queue_layout.addStretch()  # Push items to top
        
        self.scroll_area.setWidget(self.queue_container)
        layout.addWidget(self.scroll_area)
    
    def _setup_event_subscriptions(self):
        """Subscribe to relevant events."""
        # Queue events
        self.event_bus.subscribe(QueueEvents.ITEM_ADDED, self._on_item_added)
        self.event_bus.subscribe(QueueEvents.ITEM_REMOVED, self._on_item_removed)
        self.event_bus.subscribe(QueueEvents.ITEM_STATE_CHANGED, self._on_state_changed)
        self.event_bus.subscribe(QueueEvents.QUEUE_CLEARED, self._on_queue_cleared)
        
        # Download events
        self.event_bus.subscribe(DownloadEvents.DOWNLOAD_STARTED, self._on_download_started)
        self.event_bus.subscribe(DownloadEvents.DOWNLOAD_PROGRESS, self._on_download_progress)
        self.event_bus.subscribe(DownloadEvents.DOWNLOAD_COMPLETED, self._on_download_completed)
        self.event_bus.subscribe(DownloadEvents.DOWNLOAD_FAILED, self._on_download_failed)
        self.event_bus.subscribe(DownloadEvents.TRACK_COMPLETED, self._on_track_completed)
        self.event_bus.subscribe(DownloadEvents.TRACK_FAILED, self._on_track_failed)
    
    def _load_existing_queue(self):
        """Load existing queue items on startup with efficient loading for large queues."""
        try:
            # Get queue info first to check size
            queue_info = self.download_service.get_queue_items_paginated(0, 1)
            total_items = queue_info['total_count']
            
            logger.info(f"[NewQueueWidget] Loading queue with {total_items} items")
            
            if total_items == 0:
                self._update_statistics()
                return
            
            # For large queues, use smart loading strategy
            if total_items > 50:
                logger.info(f"[NewQueueWidget] Large queue detected ({total_items} items), using smart loading")
                self._load_queue_smartly(total_items)
            else:
                # Normal loading for smaller queues
                items = self.download_service.get_queue_items()
                for item in items:
                    self._create_item_widget(item)
            
            self._update_statistics()
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error loading existing queue: {e}")
    
    def _load_queue_smartly(self, total_items):
        """Smart loading strategy for large queues."""
        try:
            # Priority 1: Load active/downloading items first (up to 20)
            active_items = self.download_service.get_queue_items_by_state(DownloadState.DOWNLOADING)
            queued_items = self.download_service.get_queue_items_by_state(DownloadState.QUEUED)
            
            priority_items = (active_items + queued_items)[:20]
            
            for item in priority_items:
                self._create_item_widget(item)
            
            # Priority 2: Load some failed items for user visibility (up to 10)
            failed_items = self.download_service.get_queue_items_by_state(DownloadState.FAILED)[:10]
            for item in failed_items:
                self._create_item_widget(item)
            
            # Add summary for remaining items
            loaded_count = len(priority_items) + len(failed_items)
            remaining_count = total_items - loaded_count
            
            if remaining_count > 0:
                # Get completed count for summary
                completed_items = self.download_service.get_queue_items_by_state(DownloadState.COMPLETED)
                self._add_smart_summary_widget(remaining_count, len(completed_items), total_items)
            
            # Set smart loading flag for automatic progression
            self.smart_loading_active = True
            self.loaded_item_count = loaded_count
            
            logger.info(f"[NewQueueWidget] Smart loading: {loaded_count} priority items loaded, {remaining_count} summarized")
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error in smart loading: {e}")
    
    def _add_smart_summary_widget(self, remaining_count, completed_count, total_items):
        """Add an intelligent summary widget for large queues."""
        try:
            from PyQt6.QtWidgets import QLabel, QFrame, QPushButton, QHBoxLayout
            
            summary_frame = QFrame()
            summary_frame.setFrameStyle(QFrame.Shape.StyledPanel)
            summary_frame.setObjectName("QueueSummaryFrame")
            summary_frame.setStyleSheet("""
                QFrame#QueueSummaryFrame {
                    background-color: rgba(100, 100, 100, 0.1);
                    border: 1px solid rgba(150, 150, 150, 0.3);
                    border-radius: 4px;
                    margin: 2px;
                }
            """)
            
            summary_layout = QVBoxLayout(summary_frame)
            summary_layout.setContentsMargins(8, 6, 8, 6)
            summary_layout.setSpacing(4)
            
            # Main summary text
            summary_text = f"📊 Queue Summary: {total_items} total items"
            summary_label = QLabel(summary_text)
            summary_label.setStyleSheet("font-weight: bold; color: #333; font-size: 11px;")
            summary_layout.addWidget(summary_label)
            
            # Breakdown text
            breakdown_text = f"• {remaining_count} items not shown (including {completed_count} completed)"
            breakdown_label = QLabel(breakdown_text)
            breakdown_label.setStyleSheet("color: #666; font-size: 10px;")
            summary_layout.addWidget(breakdown_label)
            
            # Action buttons layout
            button_layout = QHBoxLayout()
            button_layout.setSpacing(8)
            
            # Helpful action suggestions
            if completed_count > 20:
                suggestion_label = QLabel("💡 Tip: Use 'Clear Completed' to reduce queue size")
                suggestion_label.setStyleSheet("color: #0066CC; font-size: 10px; font-style: italic;")
                summary_layout.addWidget(suggestion_label)
            
            # Insert before stretch
            insert_index = self.queue_layout.count() - 1
            self.queue_layout.insertWidget(insert_index, summary_frame)
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error adding smart summary widget: {e}")
    

    
    def _create_item_widget(self, item: QueueItem):
        """Create widget for queue item."""
        try:
            # Get current state
            state = self.download_service.get_queue_state(item.id)
            if not state:
                logger.warning(f"[NewQueueWidget] No state found for item {item.id}")
                return
            
            # Fix completed_tracks and progress for completed items
            if (state.state == DownloadState.COMPLETED and 
                state.completed_tracks < item.total_tracks):
                state.completed_tracks = item.total_tracks
                state.progress = 1.0  # Ensure progress bar shows 100%
                logger.info(f"[NewQueueWidget] Fixed completed_tracks and progress for loaded item {item.id}: {state.completed_tracks}/{item.total_tracks} (100%)")
 
            # Prevent duplicates: remove any existing widget for this item first
            if item.id in self.item_widgets:
                self._remove_item_widget(item.id)
 
            # Create widget
            widget = QueueItemWidget(
                item=item,
                state=state,
                on_remove=self._handle_item_remove,
                on_retry=self._handle_item_retry,
                on_cancel=self._handle_item_cancel,
                on_pause=self._handle_item_pause,
                on_resume=self._handle_item_resume,
                parent=self
            )
             
            # Add to layout (insert before stretch)
            # The stretch is always the last item, so insert before it
            stretch_index = self.queue_layout.count() - 1
            self.queue_layout.insertWidget(stretch_index, widget)
             
            # Track widget
            self.item_widgets[item.id] = widget
             
            logger.debug(f"[NewQueueWidget] Created widget for: {item.title}")
             
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error creating item widget: {e}")
     
    def _remove_item_widget(self, item_id: str):
        """Remove widget for queue item."""
        try:
            # Remove tracked instance if present
            if item_id in self.item_widgets:
                widget = self.item_widgets.pop(item_id)
 
                # Check if layout still exists before removing widget
                if hasattr(self, 'queue_layout') and self.queue_layout:
                    try:
                        self.queue_layout.removeWidget(widget)
                    except RuntimeError:
                        # Qt object has been deleted
                        pass
 
                widget.deleteLater()
                logger.debug(f"[NewQueueWidget] Removed widget for: {item_id}")
 
            # Also defensively remove any duplicate/orphan widgets with same item_id
            if hasattr(self, 'queue_layout') and self.queue_layout:
                for i in reversed(range(self.queue_layout.count())):
                    item = self.queue_layout.itemAt(i)
                    w = item.widget() if item is not None else None
                    if w and isinstance(w, QueueItemWidget):
                        try:
                            if hasattr(w, 'get_item_id') and w.get_item_id() == item_id:
                                self.queue_layout.removeWidget(w)
                                w.deleteLater()
                                logger.debug(f"[NewQueueWidget] Removed orphan duplicate widget for: {item_id}")
                        except RuntimeError:
                            pass
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error removing item widget: {e}")
 
    def _update_statistics(self):
        """Update statistics display."""
        try:
            stats = self.download_service.get_queue_summary()
             
            total = sum(stats.values())
            queued = stats.get('queued', 0)
            downloading = stats.get('downloading', 0)
            completed = stats.get('completed', 0)
            failed = stats.get('failed', 0)
             
            stats_text = f"Total: {total} | Queued: {queued} | Active: {downloading} | Completed: {completed} | Failed: {failed}"
             
            # Check if stats_label still exists before accessing it
            if hasattr(self, 'stats_label') and self.stats_label:
                try:
                    self.stats_label.setText(stats_text)
                except RuntimeError:
                    # Qt object has been deleted
                    pass
             
            # Update button states (check if buttons exist first)
            if hasattr(self, 'clear_completed_button') and self.clear_completed_button:
                try:
                    self.clear_completed_button.setEnabled(completed > 0)
                except RuntimeError:
                    pass
            if hasattr(self, 'clear_failed_button') and self.clear_failed_button:
                try:
                    self.clear_failed_button.setEnabled(failed > 0)
                except RuntimeError:
                    pass
            if hasattr(self, 'retry_failed_button') and self.retry_failed_button:
                try:
                    self.retry_failed_button.setEnabled(failed > 0)
                except RuntimeError:
                    pass
            if hasattr(self, 'clear_all_button') and self.clear_all_button:
                try:
                    self.clear_all_button.setEnabled(total > 0)
                except RuntimeError:
                    pass
             
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error updating statistics: {e}")
 
    # Event Handlers
 
    def _on_item_added(self, item_id: str):
        """Handle item added to queue."""
        try:
            # Use QTimer.singleShot to ensure UI updates happen on main thread
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._create_item_widget_safe(item_id))
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error handling item added: {e}")
    
    def _create_item_widget_safe(self, item_id: str):
        """Create item widget safely on the main thread."""
        try:
            item = self.download_service.get_queue_item(item_id)
            if item:
                self._create_item_widget(item)
                self._update_statistics()
                if self.status_label:
                    self.status_label.setText(f"Added: {item.title}")
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error creating item widget: {e}")
    
    def _on_item_removed(self, item_id: str):
        """Handle item removed from queue."""
        try:
            # Use QTimer.singleShot to ensure UI updates happen on main thread
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._remove_item_widget_safe(item_id))
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error handling item removed: {e}")
    
    def _remove_item_widget_safe(self, item_id: str):
        """Remove item widget safely on the main thread."""
        try:
            self._remove_item_widget(item_id)
            self._update_statistics()
            if self.status_label:
                self.status_label.setText("Item removed")
            
            # Emit signal for main window
            self.item_removed.emit(item_id)
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error removing item widget: {e}")
    
    def _on_state_changed(self, item_id: str, state: QueueItemState):
        """Handle item state change."""
        try:
            # Use QTimer.singleShot to ensure UI updates happen on main thread
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._update_state_safe(item_id, state))
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error handling state change: {e}")
    
    def _update_state_safe(self, item_id: str, state: QueueItemState):
        """Update item state safely on the main thread."""
        try:
            if item_id in self.item_widgets:
                logger.debug(f"[NewQueueWidget] Updating widget state for {item_id}: {state.state.value}")
                self.item_widgets[item_id].update_state(state)
                self._update_statistics()
            else:
                logger.warning(f"[NewQueueWidget] No widget found for state update: {item_id}")
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error updating state: {e}")
    
    def _on_queue_cleared(self, states, item_ids):
        """Handle queue cleared."""
        try:
            # Clear virtual loading data if it exists
            if hasattr(self, 'all_queue_items'):
                self.all_queue_items = []
            if hasattr(self, 'rendered_items'):
                self.rendered_items.clear()
            
            # Remove all tracked widgets
            for item_id in list(self.item_widgets.keys()):
                self._remove_item_widget(item_id)
 
            # Extra safety: remove ANY remaining widgets from the layout
            if hasattr(self, 'queue_layout') and self.queue_layout:
                for i in reversed(range(self.queue_layout.count())):
                    item = self.queue_layout.itemAt(i)
                    w = item.widget() if item is not None else None
                    if w and (hasattr(w, 'get_item_id') or w.objectName() == "QueueSummaryFrame"):
                        self.queue_layout.removeWidget(w)
                        w.deleteLater()
             
            # Ensure our map is clear
            self.item_widgets.clear()
 
            self._update_statistics()
             
            # Check if status_label still exists before accessing it
            if hasattr(self, 'status_label') and self.status_label:
                try:
                    self.status_label.setText("Queue cleared")
                except RuntimeError:
                    # Qt object has been deleted
                    pass
             
            # Emit signal for main window
            self.queue_cleared.emit()
             
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error handling queue cleared: {e}")
    
    def _on_download_started(self, item_id: str):
        """Handle download started."""
        try:
            # Emit signal to update GUI on main thread
            self.download_started_signal.emit(item_id)
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error handling download started: {e}")
    
    @pyqtSlot(str)
    def _update_download_started(self, item_id: str):
        """Update GUI for download started (called on main thread)."""
        try:
            if item_id in self.item_widgets:
                item = self.download_service.get_queue_item(item_id)
                if item:
                    self.status_label.setText(f"Started: {item.title}")
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error updating download started: {e}")
    
    def _on_download_progress(self, item_id: str, progress: float, completed_tracks: int, failed_tracks: int):
        """Handle download progress update."""
        try:
            # Emit signal to update GUI on main thread
            self.download_progress_signal.emit(item_id, progress, completed_tracks, failed_tracks)
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error handling download progress: {e}")
    
    @pyqtSlot(str, float, int, int)
    def _update_download_progress(self, item_id: str, progress: float, completed_tracks: int, failed_tracks: int):
        """Update GUI for download progress (called on main thread)."""
        try:
            if item_id in self.item_widgets:
                self.item_widgets[item_id].update_progress(progress, completed_tracks, failed_tracks)
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error updating download progress: {e}")
    
    def _on_download_completed(self, item_id: str):
        """Handle download completed."""
        try:
            logger.info(f"[NewQueueWidget] Received download completed event for: {item_id}")
            # Emit signal to update GUI on main thread
            self.download_completed_signal.emit(item_id)
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error handling download completed: {e}")
    
    @pyqtSlot(str)
    def _update_download_completed(self, item_id: str):
        """Update GUI for download completed (called on main thread)."""
        try:
            if item_id in self.item_widgets:
                # Update the individual widget's state
                state = self.download_service.get_queue_state(item_id)
                item = self.download_service.get_queue_item(item_id)
                
                if state and item:
                    # Ensure completed_tracks and progress are set correctly for completed items
                    if (state.state == DownloadState.COMPLETED and 
                        state.completed_tracks < item.total_tracks):
                        state.completed_tracks = item.total_tracks
                        state.progress = 1.0  # Ensure progress bar shows 100%
                        logger.info(f"[NewQueueWidget] Fixed completed_tracks and progress for {item_id}: {state.completed_tracks}/{item.total_tracks} (100%)")
                    
                    self.item_widgets[item_id].update_state(state)
                    logger.debug(f"[NewQueueWidget] Updated widget state for completed item: {item_id}")
                
                # Update status label
                if item and self.status_label:
                    self.status_label.setText(f"Completed: {item.title}")
                    
                self._update_statistics()
            
            # Check if we need to load more items (automatic progression)
            self._check_for_automatic_progression()
            
        except RuntimeError as e:
            if "wrapped C/C++ object" in str(e):
                logger.debug(f"[NewQueueWidget] Widget deleted during completion handling: {e}")
            else:
                logger.error(f"[NewQueueWidget] Runtime error handling download completed: {e}")
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error handling download completed: {e}")
    
    def _check_for_automatic_progression(self):
        """Check if we should automatically load more items from the queue."""
        try:
            if not self.smart_loading_active:
                return
            
            # Count active/queued items currently displayed
            active_count = 0
            for item_id in self.item_widgets.keys():
                state = self.download_service.get_queue_state(item_id)
                if state and state.state in [DownloadState.QUEUED, DownloadState.DOWNLOADING]:
                    active_count += 1
            
            # If we have fewer than 5 active items, load more
            if active_count < 5:
                # Get total queue info
                queue_info = self.download_service.get_queue_items_paginated(0, 1)
                total_items = queue_info['total_count']
                
                # Check if there are more items to load
                if total_items > len(self.item_widgets):
                    logger.info(f"[NewQueueWidget] Auto-progression: Loading more items ({active_count} active, {total_items} total)")
                    # Use QTimer to ensure UI updates happen on main thread
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(0, self._load_next_batch)
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error in automatic progression: {e}")
    
    def _load_next_batch(self):
        """Load the next batch of items from the queue."""
        try:
            # Get next batch of queued items (skip already loaded ones)
            queued_items = self.download_service.get_queue_items_by_state(DownloadState.QUEUED)
            
            # Filter out items we already have widgets for
            new_items = [item for item in queued_items if item.id not in self.item_widgets]
            
            # Load up to 10 more items
            batch_size = min(10, len(new_items))
            
            for i in range(batch_size):
                item = new_items[i]
                self._create_item_widget(item)
            
            if batch_size > 0:
                logger.info(f"[NewQueueWidget] Auto-progression: Loaded {batch_size} more items")
                self._update_statistics()
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error loading next batch: {e}", exc_info=True)
    
    def _on_download_failed(self, item_id: str, error_message: str):
        """Handle download failed."""
        try:
            # Emit signal to update GUI on main thread
            self.download_failed_signal.emit(item_id, error_message)
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error handling download failed: {e}")
    
    @pyqtSlot(str, str)
    def _update_download_failed(self, item_id: str, error_message: str):
        """Update GUI for download failed (called on main thread)."""
        try:
            if item_id in self.item_widgets:
                item = self.download_service.get_queue_item(item_id)
                if item:
                    self.status_label.setText(f"Failed: {item.title}")
                self._update_statistics()
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error updating download failed: {e}")
    
    def _on_track_completed(self, item_id: str, track_id: int):
        """Handle individual track completed."""
        try:
            logger.info(f"[NewQueueWidget] Received track completed event: item_id={item_id}, track_id={track_id}")
            
            # Update the queue manager's state
            if hasattr(self, 'download_service') and self.download_service:
                queue_manager = self.download_service.queue_manager
                if item_id in queue_manager.states:
                    state = queue_manager.states[item_id]
                    # Increment completed tracks count
                    state.completed_tracks = getattr(state, 'completed_tracks', 0) + 1
                    
                    logger.info(f"[NewQueueWidget] Updated completed tracks for {item_id}: {state.completed_tracks}")
                    
                    # Update the widget display
                    if item_id in self.item_widgets:
                        widget = self.item_widgets[item_id]
                        widget.update_progress(
                            state.progress, 
                            state.completed_tracks, 
                            getattr(state, 'failed_tracks', 0)
                        )
                        logger.info(f"[NewQueueWidget] Updated widget display for {item_id}")
                    else:
                        logger.warning(f"[NewQueueWidget] No widget found for item {item_id}")
                else:
                    logger.warning(f"[NewQueueWidget] No state found for item {item_id}")
            else:
                logger.warning(f"[NewQueueWidget] No download service available")
                    
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error handling track completed: {e}")
    
    def _on_track_failed(self, item_id: str, track_id: int, error_message: str):
        """Handle individual track failed."""
        try:
            # Update the queue manager's state
            if hasattr(self, 'download_service') and self.download_service:
                queue_manager = self.download_service.queue_manager
                if item_id in queue_manager.states:
                    state = queue_manager.states[item_id]
                    # Increment failed tracks count
                    state.failed_tracks = getattr(state, 'failed_tracks', 0) + 1
                    
                    # Update the widget display
                    if item_id in self.item_widgets:
                        widget = self.item_widgets[item_id]
                        widget.update_progress(
                            state.progress, 
                            getattr(state, 'completed_tracks', 0), 
                            state.failed_tracks
                        )
                    
                    logger.debug(f"[NewQueueWidget] Track {track_id} failed for item {item_id}. Total failed: {state.failed_tracks}")
                    
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error handling track failed: {e}")
    
    # Button Handlers
    
    def _handle_clear_all(self):
        """Handle clear all button click."""
        try:
            reply = QMessageBox.question(
                self, 
                "Clear All Downloads",
                "Are you sure you want to clear all downloads?\nThis will cancel active downloads and remove all items from the queue.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.download_service.clear_all()
                logger.info("[NewQueueWidget] User cleared all downloads")
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error clearing all downloads: {e}")
    
    def _handle_clear_completed(self):
        """Handle clear completed button click."""
        try:
            # Get count before clearing for user feedback
            completed_items = self.download_service.get_queue_items_by_state(DownloadState.COMPLETED)
            completed_count = len(completed_items)
            
            if completed_count == 0:
                self.status_label.setText("No completed downloads to clear")
                return
            
            # Clear completed items
            self.download_service.clear_completed()
            
            # Update status with count
            self.status_label.setText(f"Cleared {completed_count} completed downloads")
            logger.info(f"[NewQueueWidget] User cleared {completed_count} completed downloads")
            
            # If we had a large queue, reload to show more items
            remaining_items = self.download_service.get_queue_items_paginated(0, 1)['total_count']
            if remaining_items > 0 and completed_count > 10:
                logger.info("[NewQueueWidget] Reloading queue after clearing many completed items")
                # Clear current widgets and reload
                self._clear_all_widgets()
                self._load_existing_queue()
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error clearing completed downloads: {e}")
    
    def _clear_all_widgets(self):
        """Clear all widgets from the queue layout."""
        try:
            # Remove all tracked widgets
            for item_id in list(self.item_widgets.keys()):
                self._remove_item_widget(item_id)
            
            # Remove any summary widgets
            if hasattr(self, 'queue_layout') and self.queue_layout:
                for i in reversed(range(self.queue_layout.count())):
                    item = self.queue_layout.itemAt(i)
                    w = item.widget() if item is not None else None
                    if w and w.objectName() == "QueueSummaryFrame":
                        self.queue_layout.removeWidget(w)
                        w.deleteLater()
            
            self.item_widgets.clear()
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error clearing all widgets: {e}")
    
    def _handle_clear_failed(self):
        """Handle clear failed button click."""
        try:
            self.download_service.clear_failed()
            logger.info("[NewQueueWidget] User cleared failed downloads")
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error clearing failed downloads: {e}")
    
    def _handle_retry_failed(self):
        """Handle retry failed button click."""
        try:
            count = self.download_service.retry_failed()
            self.status_label.setText(f"Retrying {count} failed downloads")
            logger.info(f"[NewQueueWidget] User retried {count} failed downloads")
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error retrying failed downloads: {e}")
    
    # Item Action Handlers
    
    def _handle_item_remove(self, item_id: str):
        """Handle individual item remove."""
        try:
            item = self.download_service.get_queue_item(item_id)
            if not item:
                return
            
            reply = QMessageBox.question(
                self,
                "Remove Download",
                f"Remove '{item.title}' from the queue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.download_service.remove_item(item_id)
                logger.info(f"[NewQueueWidget] User removed item: {item.title}")
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error removing item: {e}")
    
    def _handle_item_retry(self, item_id: str):
        """Handle individual item retry."""
        try:
            # Set state back to queued
            self.download_service.queue_manager.update_state(item_id, state=DownloadState.QUEUED)
            logger.info(f"[NewQueueWidget] User retried item: {item_id}")
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error retrying item: {e}")
    
    def _handle_item_cancel(self, item_id: str):
        """Handle individual item cancel."""
        try:
            self.download_service.cancel_download(item_id)
            logger.info(f"[NewQueueWidget] User cancelled item: {item_id}")
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error cancelling item: {e}")
    
    def _handle_item_pause(self, item_id: str):
        """Handle individual item pause."""
        try:
            self.download_service.pause_download(item_id)
            logger.info(f"[NewQueueWidget] User paused item: {item_id}")
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error pausing item: {e}")
    
    def _handle_item_resume(self, item_id: str):
        """Handle individual item resume."""
        try:
            self.download_service.resume_download(item_id)
            logger.info(f"[NewQueueWidget] User resumed item: {item_id}")
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error resuming item: {e}")
    
    # Public Methods
    
    def load_queue_state(self):
        """Load queue state (for compatibility with main window)."""
        try:
            # This is already handled in _load_existing_queue during initialization
            # But we provide this method for compatibility with the main window
            self._load_existing_queue()
            logger.info("[NewQueueWidget] Queue state loaded")
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error loading queue state: {e}")
    
    # Cleanup
    
    def cleanup(self):
        """Cleanup resources when widget is destroyed."""
        try:
            # Unsubscribe from events
            self.event_bus.clear_subscribers()
            
            # Clear widgets
            for widget in self.item_widgets.values():
                widget.deleteLater()
            self.item_widgets.clear()
            
            logger.info("[NewQueueWidget] Cleaned up queue widget")
            
        except Exception as e:
            logger.error(f"[NewQueueWidget] Error during cleanup: {e}")
    
    def closeEvent(self, event):
        """Handle widget close event."""
        self.cleanup()
        super().closeEvent(event)