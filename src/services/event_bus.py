"""
Simple event bus for decoupled communication between components.

This provides a clean way for the queue manager, download engine, and UI
to communicate without tight coupling or complex signal management.
"""

import threading
import logging
from typing import Dict, List, Callable, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class EventBus:
    """
    Thread-safe event bus for component communication.
    
    This replaces the complex Qt signal/slot system with a simpler,
    more reliable event system that doesn't depend on Qt object lifecycles.
    """
    
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._lock = threading.RLock()
        self._event_count = 0
    
    def subscribe(self, event_type: str, callback: Callable):
        """
        Subscribe to an event type.
        
        Args:
            event_type: The type of event to listen for
            callback: Function to call when event is emitted
        """
        with self._lock:
            self.subscribers[event_type].append(callback)
            logger.debug(f"[EventBus] Subscribed to '{event_type}' (total subscribers: {len(self.subscribers[event_type])})")
    
    def unsubscribe(self, event_type: str, callback: Callable):
        """
        Unsubscribe from an event type.
        
        Args:
            event_type: The type of event to stop listening for
            callback: The callback function to remove
        """
        with self._lock:
            if event_type in self.subscribers:
                try:
                    self.subscribers[event_type].remove(callback)
                    logger.debug(f"[EventBus] Unsubscribed from '{event_type}'")
                except ValueError:
                    logger.warning(f"[EventBus] Callback not found for '{event_type}'")
    
    def emit(self, event_type: str, *args, **kwargs):
        """
        Emit an event to all subscribers.
        
        Args:
            event_type: The type of event to emit
            *args: Positional arguments to pass to callbacks
            **kwargs: Keyword arguments to pass to callbacks
        """
        with self._lock:
            self._event_count += 1
            event_id = self._event_count
            
            if event_type not in self.subscribers:
                logger.debug(f"[EventBus] No subscribers for event '{event_type}' (#{event_id})")
                return
            
            subscribers = self.subscribers[event_type].copy()  # Copy to avoid modification during iteration
        
        # Call subscribers outside the lock to prevent deadlocks
        logger.debug(f"[EventBus] Emitting '{event_type}' to {len(subscribers)} subscribers (#{event_id})")
        
        for callback in subscribers:
            try:
                callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"[EventBus] Error in callback for '{event_type}': {e}", exc_info=True)
    
    def clear_subscribers(self, event_type: str = None):
        """
        Clear subscribers for a specific event type or all events.
        
        Args:
            event_type: Event type to clear, or None to clear all
        """
        with self._lock:
            if event_type:
                if event_type in self.subscribers:
                    count = len(self.subscribers[event_type])
                    del self.subscribers[event_type]
                    logger.info(f"[EventBus] Cleared {count} subscribers for '{event_type}'")
            else:
                total_count = sum(len(subs) for subs in self.subscribers.values())
                self.subscribers.clear()
                logger.info(f"[EventBus] Cleared all {total_count} subscribers")
    
    def get_subscriber_count(self, event_type: str) -> int:
        """Get the number of subscribers for an event type"""
        with self._lock:
            return len(self.subscribers.get(event_type, []))
    
    def get_all_event_types(self) -> List[str]:
        """Get all event types that have subscribers"""
        with self._lock:
            return list(self.subscribers.keys())


# Event type constants for type safety and documentation
class QueueEvents:
    """Constants for queue-related events"""
    ITEM_ADDED = "queue.item_added"
    ITEM_REMOVED = "queue.item_removed"
    ITEM_STATE_CHANGED = "queue.item_state_changed"
    QUEUE_CLEARED = "queue.cleared"
    QUEUE_LOADED = "queue.loaded"


class DownloadEvents:
    """Constants for download-related events"""
    DOWNLOAD_STARTED = "download.started"
    DOWNLOAD_PROGRESS = "download.progress"
    DOWNLOAD_COMPLETED = "download.completed"
    DOWNLOAD_FAILED = "download.failed"
    DOWNLOAD_CANCELLED = "download.cancelled"
    TRACK_COMPLETED = "download.track_completed"
    TRACK_FAILED = "download.track_failed"


class UIEvents:
    """Constants for UI-related events"""
    QUEUE_UI_REFRESH = "ui.queue_refresh"
    PROGRESS_UPDATE = "ui.progress_update"
    STATUS_MESSAGE = "ui.status_message"


# Global event bus instance
# This can be imported and used throughout the application
_global_event_bus = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance"""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus


def reset_event_bus():
    """Reset the global event bus (useful for testing)"""
    global _global_event_bus
    if _global_event_bus:
        _global_event_bus.clear_subscribers()
    _global_event_bus = EventBus()


# Convenience functions for common operations
def subscribe(event_type: str, callback: Callable):
    """Subscribe to an event using the global event bus"""
    get_event_bus().subscribe(event_type, callback)


def unsubscribe(event_type: str, callback: Callable):
    """Unsubscribe from an event using the global event bus"""
    get_event_bus().unsubscribe(event_type, callback)


def emit(event_type: str, *args, **kwargs):
    """Emit an event using the global event bus"""
    get_event_bus().emit(event_type, *args, **kwargs)


# Decorator for automatic event emission
def emits_event(event_type: str):
    """
    Decorator that automatically emits an event when a method completes.
    
    Usage:
        @emits_event(QueueEvents.ITEM_ADDED)
        def add_item(self, item):
            # method implementation
            return item_id
    
    The return value of the method will be passed as the first argument to the event.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            emit(event_type, result)
            return result
        return wrapper
    return decorator


# Context manager for event batching
class EventBatch:
    """
    Context manager for batching events.
    
    Events emitted within the context are collected and emitted
    as a single batch event when the context exits.
    """
    
    def __init__(self, batch_event_type: str):
        self.batch_event_type = batch_event_type
        self.events = []
        self.original_emit = None
    
    def __enter__(self):
        self.original_emit = get_event_bus().emit
        
        def batched_emit(event_type, *args, **kwargs):
            self.events.append((event_type, args, kwargs))
        
        get_event_bus().emit = batched_emit
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        get_event_bus().emit = self.original_emit
        
        if not exc_type:  # Only emit batch if no exception occurred
            get_event_bus().emit(self.batch_event_type, self.events)


# Example usage:
if __name__ == "__main__":
    # Example of how to use the event bus
    bus = EventBus()
    
    def on_item_added(item_id: str):
        print(f"Item added: {item_id}")
    
    def on_progress_update(item_id: str, progress: float):
        print(f"Progress for {item_id}: {progress:.1%}")
    
    # Subscribe to events
    bus.subscribe(QueueEvents.ITEM_ADDED, on_item_added)
    bus.subscribe(DownloadEvents.DOWNLOAD_PROGRESS, on_progress_update)
    
    # Emit events
    bus.emit(QueueEvents.ITEM_ADDED, "item-123")
    bus.emit(DownloadEvents.DOWNLOAD_PROGRESS, "item-123", 0.5)
    
    # Cleanup
    bus.clear_subscribers()