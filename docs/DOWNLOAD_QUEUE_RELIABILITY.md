# Download Queue Reliability & Race Condition Prevention

## Overview

This document details the comprehensive reliability improvements made to DeeMusic's download queue system in versions 1.0.6+. These fixes address critical race conditions, infinite loops, state consistency issues, and the major track numbering problem that were affecting queue operations.

## Problems Addressed

### 1. Race Conditions in Clear Operations

**Problem**: When users pressed "Clear Completed" or "Clear All", the last track from an album would sometimes complete after the clear operation, creating folders and downloading files even though the queue was supposed to be cleared.

**Root Cause**: 
- Workers were stopped but could still complete and emit signals
- No coordination between stopping workers and processing completion signals
- Race condition between clear operation and worker completion

**Solution**: Comprehensive signal management and worker coordination system.

### 2. Persistent Completed Downloads

**Problem**: Completed downloads would persist in the queue state file and be restored on app restart, causing re-downloads when folders were moved or deleted.

**Root Cause**: 
- Albums remained in "unfinished_downloads" even after completion
- No detection of completed albums based on file existence
- Queue state not updated when downloads completed by finding existing files

**Solution**: Automatic completed album detection and removal from unfinished downloads.

### 3. Infinite Queue Loops

**Problem**: Invalid queue entries with "unknown" IDs would cause infinite restoration loops where the same phantom downloads would be restored repeatedly.

**Root Cause**: 
- Invalid entries with album_id="unknown" and track_id="unknown" were being saved
- These entries would fail to process but get saved back as "unfinished"
- File watcher would detect changes and trigger restoration, creating an infinite loop

**Solution**: Robust queue entry validation and automatic filtering of invalid entries.

### 4. Track Numbering Issue (v1.0.6 Critical Fix)

**Problem**: All album tracks were showing "01" in filenames instead of correct sequential numbers (01, 02, 03, etc.).

**Root Cause**: 
- Download worker was using track info from album listing API instead of detailed track API
- Album listing API uses different field names (`TRACK_POSITION`) than individual track API (`SNG_TRACK_NUMBER`)
- Field mapping was incorrect in API processing
- Type conversion was missing for numeric fields

**Solution**: Complete overhaul of track number processing system.

### 5. Stuck Pending Downloads (v1.0.6)

**Problem**: Downloads would appear as "Pending" in the UI even when the queue state file showed empty arrays, with no way to remove them.

**Root Cause**: 
- Albums saved as "unfinished" when app closed without clearing queue
- Completion detection logic didn't properly recognize already-downloaded files
- UI state not properly synchronized with queue state file

**Solution**: Enhanced completion detection and dedicated "Clear Pending" functionality.

## Technical Implementation

### Track Number Fix (v1.0.6)

#### API Field Mapping Correction
```python
# BEFORE (Incorrect mapping):
key_mappings_to_ensure = {
    'track_number': 'TRACK_POSITION',  # Wrong field!
    # ...
}

# AFTER (Correct mapping):
key_mappings_to_ensure = {
    'track_number': 'SNG_TRACK_NUMBER',  # Correct field!
    'disk_number': 'DISK_NUMBER',
    'duration': 'DURATION',
    # ...
}
```

#### Enhanced Type Conversion
```python
for target_key, source_key_uc in key_mappings_to_ensure.items():
    if source_key_uc in raw_data:
        value = raw_data[source_key_uc]
        # Convert numeric fields to int
        if target_key in ['disk_number', 'track_number', 'duration'] and value is not None:
            try:
                processed_info[target_key] = int(value)
            except (ValueError, TypeError):
                processed_info[target_key] = 1 if target_key in ['disk_number', 'track_number'] else 0
        else:
            processed_info[target_key] = value
```

#### Download Worker Enhancement
```python
# Force detailed API call for album tracks
if self.item_type == 'album_track':
    # Always fetch detailed track info instead of using album listing data
    authoritative_track_info = self.download_manager.deezer_api.get_track_details_sync_private(self.item_id)
    logger.info(f"[DownloadWorker:{self.item_id_str}] Fetched detailed track info via API")
```

### Stuck Pending Downloads Fix (v1.0.6)

#### Enhanced Completion Detection
```python
def _are_album_tracks_completed(self, album_entry):
    """Check if all tracks in an album are completed with enhanced logging."""
    queued_tracks = album_entry.get('queued_tracks', [])
    if not queued_tracks:
        return True
    
    completed_count = 0
    total_tracks = len(queued_tracks)
    
    logger.debug(f"[QUEUE_DEBUG] Checking completion for album '{artist_name} - {album_title}' ({total_tracks} tracks)")
    
    for track in queued_tracks:
        track_id = track.get('track_id')
        track_title = track.get('title', 'Unknown Title')
        
        # Check internal completion tracking
        if hasattr(self, 'completed_track_ids') and track_id in self.completed_track_ids:
            completed_count += 1
            logger.debug(f"[QUEUE_DEBUG] Track '{track_title}' found in completed tracking")
            continue
        
        # Additional validation logic...
```

#### Clear Pending Downloads Method
```python
def clear_pending_downloads(self):
    """Clear only stuck pending downloads from previous sessions."""
    try:
        queue_state_path = self._get_queue_state_path()
        
        if not queue_state_path.exists():
            logger.info("[QUEUE_DEBUG] No queue state file exists, nothing to clear")
            return
        
        # Load current queue state
        with open(queue_state_path, 'r', encoding='utf-8') as f:
            queue_state = json.load(f)
        
        # Clear only unfinished downloads, preserve completed/failed
        original_count = len(queue_state.get('unfinished_downloads', []))
        queue_state['unfinished_downloads'] = []
        
        # Save the updated state
        with open(queue_state_path, 'w', encoding='utf-8') as f:
            json.dump(queue_state, f, indent=2)
        
        logger.info(f"[QUEUE_DEBUG] Cleared {original_count} pending downloads from queue state")
        
    except Exception as e:
        logger.error(f"[QUEUE_DEBUG] Error clearing pending downloads: {e}")
```

#### UI Enhancement - Three-Button Layout
```python
# Enhanced download queue widget with three control buttons
self.clear_queue_button = QPushButton("Clear All")
self.clear_pending_button = QPushButton("Clear Pending")  # NEW
self.clear_completed_button = QPushButton("Clear Completed")

# Add tooltips for clarity
self.clear_pending_button.setToolTip("Clear stuck pending downloads from previous sessions")
```

### Race Condition Prevention (Previous Fixes)

#### Signal Disconnection During Clear Operations
```python
def _handle_clear_completed_clicked(self):
    # Step 1: Disconnect signals to prevent race conditions
    self.download_manager.signals.download_finished.disconnect()
    self.download_manager.signals.download_failed.disconnect()
    
    # Step 2: Set clearing flag
    self.download_manager._clearing_queue = True
    
    # Step 3: Stop workers and clear state
    # ... clearing operations ...
    
    # Step 4: Reconnect signals
    self.download_manager.signals.download_finished.connect(self._handle_download_finished)
    self.download_manager.signals.download_failed.connect(self._handle_download_failed)
```

#### Worker Protection
```python
def _handle_worker_finished(self, item_id_str: str):
    # Check if we're in the middle of clearing the queue
    if self._clearing_queue:
        logger.info(f"Ignoring worker finished signal for {item_id_str} - queue is being cleared")
        return
    # ... normal processing ...
```

#### Directory Creation Prevention
```python
def _perform_download_direct(self, track_info):
    # Check if worker is stopping or download manager is clearing
    if self._is_stopping or self.download_manager._clearing_queue:
        logger.info("No directories will be created - operation cancelled")
        return None
    # ... continue with download ...
```

### Completed Album Detection

#### File Existence Validation
```python
def _are_album_tracks_completed(self, album_entry):
    """Check if all tracks in an album are completed by verifying file existence."""
    # Use pattern matching to find files in various folder structures
    # Pattern 1: Artist/Album/Track.mp3
    # Pattern 2: Album/Track.mp3 (no artist folder)
    # Match by track title or track ID in filename
```

#### Queue State Filtering
```python
def _save_queue_state(self):
    # Check completion status before saving albums as "unfinished"
    if self._are_album_tracks_completed(existing_album):
        logger.info(f"Album '{album_title}' tracks are completed, removing from unfinished downloads")
    else:
        unfinished_downloads.append(existing_album)
```

### Invalid Entry Filtering

#### Entry Validation
```python
def _is_valid_queue_entry(self, entry):
    """Check if a queue entry is valid and should be saved/restored."""
    # Check for invalid album_id ("unknown", empty, null)
    # Check for invalid track_id ("unknown", empty, non-numeric)
    # Only keep entries with valid, processable data
```

#### Startup Cleanup
```python
def __init__(self):
    # Clean any invalid queue entries before restoring
    self.clean_invalid_queue_entries()
    
    # Load and restore previous queue state
    self._restore_queue_state()
```

## Testing & Verification

### Test Scripts

1. **test_queue_fixes.py**: General queue state testing
2. **test_clear_completed_race.py**: Race condition testing
3. **test_completed_album_removal.py**: Album completion detection testing
4. **fix_queue_loop.py**: Manual cleanup tool for invalid entries

### Log Indicators

Look for these log entries to verify fixes are working:

```
[DownloadQueueWidget] Set clearing queue flag for clear completed operation
[DownloadQueueWidget] Stopping X workers for completed items
[DownloadWorker:XXXXX] Worker stopped before file operations - no directories will be created
[QUEUE_DEBUG] Ignoring worker finished signal for XXXXX - queue is being cleared
[QUEUE_DEBUG] Album 'Album Title' tracks are completed, removing from unfinished downloads
[QUEUE_DEBUG] Filtering out invalid queue entry: ...
```

## Benefits

### For Users
- ✅ Clear operations work reliably without phantom downloads
- ✅ Moving downloaded folders doesn't trigger re-downloads
- ✅ Queue state accurately reflects actual completion status
- ✅ No more infinite loops or stuck queue items
- ✅ Consistent behavior across app restarts

### For Developers
- ✅ Robust error handling throughout queue operations
- ✅ Comprehensive logging for debugging queue issues
- ✅ Clean, maintainable code with proper separation of concerns
- ✅ Extensive test coverage for queue operations
- ✅ Clear documentation of race condition prevention measures

## Future Considerations

### Potential Enhancements
- Real-time file system monitoring for completion detection
- More sophisticated pattern matching for file detection
- Database-backed queue state for better performance
- Advanced retry mechanisms for failed downloads

### Maintenance
- Regular testing of race condition scenarios
- Monitoring of queue state file sizes and content
- Performance profiling of queue operations
- User feedback collection on queue reliability

This comprehensive reliability system ensures that DeeMusic's download queue operates consistently and predictably, providing users with a smooth and frustration-free experience.