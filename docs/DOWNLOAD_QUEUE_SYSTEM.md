# Download Queue System Documentation

## Overview

The DeeMusic download queue system is a sophisticated, persistent queue management system that handles music downloads from Deezer. It provides automatic queue restoration, progress tracking, race condition prevention, and seamless integration with the DeeMusic application's download workflow.

## Recent Major Improvements (v1.0.7+)

### Race Condition Prevention
- **Clear Operations**: Comprehensive fixes prevent last tracks from completing after clear operations
- **Signal Management**: Temporary signal disconnection during clear operations prevents phantom downloads
- **Worker Coordination**: Enhanced worker stopping with proper cleanup and validation

### Queue State Accuracy
- **Completed Album Detection**: Albums are automatically removed from unfinished downloads when all files exist
- **Invalid Entry Filtering**: Automatic filtering of "unknown" entries prevents infinite loops
- **Persistent State Cleanup**: Completed downloads no longer persist across app restarts unnecessarily

### Reliability Enhancements
- **Directory Creation Prevention**: Multiple checkpoints prevent folder creation after clear operations
- **File Existence Validation**: Smart detection of completed downloads by checking file existence
- **Robust Error Handling**: Comprehensive exception handling throughout queue operations

## Architecture

### Core Components

#### 1. **DownloadManager** (`src/services/download_manager.py`)
- **Purpose**: Central coordinator for all download operations
- **Responsibilities**:
  - Queue management and persistence
  - Worker thread coordination
  - Download state tracking
  - Signal emission for UI updates

#### 2. **DownloadWorker** (`src/services/download_manager.py`)
- **Purpose**: Individual download task executor
- **Responsibilities**:
  - Single track/album download execution
  - Progress reporting
  - Error handling and retry logic
  - Metadata application

#### 3. **Queue State Persistence** (`%APPDATA%/DeeMusic/download_queue_state.json`)
- **Purpose**: Persistent storage for download queue state
- **Contents**:
  - Unfinished downloads
  - Completed downloads history
  - Failed downloads tracking

## Queue State File Structure

### Location
```
Windows: %APPDATA%/DeeMusic/download_queue_state.json
macOS: ~/Library/Application Support/DeeMusic/download_queue_state.json
Linux: ~/.config/DeeMusic/download_queue_state.json
```

### File Format
```json
{
  "unfinished_downloads": [
    {
      "album_id": "730000661",
      "album_title": "Album Name",
      "artist_name": "Artist Name",
      "type": "album",
      "queued_tracks": [
        {
          "track_id": "3285890711",
          "title": "Track Title"
        }
      ]
    }
  ],
  "completed_downloads": [
    {
      "album_id": "784193431",
      "album_title": "Completed Album",
      "artist_name": "Artist Name",
      "type": "album",
      "completed_tracks": [
        {
          "track_id": "3448561301",
          "title": "Completed Track"
        }
      ]
    }
  ],
  "failed_downloads": []
}
```

## Queue Management Workflow

### 1. Application Startup

```mermaid
graph TD
    A[Application Start] --> B[Initialize DownloadManager]
    B --> C[Call _restore_queue_state()]
    C --> D[Load download_queue_state.json]
    D --> E{File Exists?}
    E -->|Yes| F[Parse JSON Data]
    E -->|No| G[Initialize Empty Queue]
    F --> H[Restore Unfinished Downloads]
    H --> I[Create Download Tasks]
    I --> J[Queue Ready]
    G --> J
```

#### Restoration Process
1. **File Loading**: `_load_queue_state()` reads the JSON file
2. **Data Parsing**: Extract unfinished, completed, and failed downloads
3. **Queue Restoration**: `_restore_queue_state()` processes unfinished downloads
4. **Task Creation**: Create async download tasks for each unfinished item

### 2. Adding Downloads to Queue

```mermaid
graph TD
    A[User Initiates Download] --> B{Download Type}
    B -->|Single Track| C[download_track()]
    B -->|Album| D[download_album()]
    B -->|Playlist| E[download_playlist()]
    C --> F[Create DownloadWorker]
    D --> G[Fetch Album Tracks]
    E --> H[Fetch Playlist Tracks]
    G --> I[Create Workers for Each Track]
    H --> I
    F --> J[Add to Active Workers]
    I --> J
    J --> K[Save Queue State]
    K --> L[Start Download]
```

#### Queue Addition Logic
```python
def _queue_individual_track_download(self, track_id: int, item_type: str):
    # Create worker instance
    worker = DownloadWorker(self, track_id, item_type, ...)
    
    # Add to active workers dictionary
    self.active_workers[track_id_str] = worker
    
    # Save current state to disk
    self._save_queue_state()
    
    # Start worker in thread pool
    self.thread_pool.start(worker)
```

### 3. Download Execution

```mermaid
graph TD
    A[DownloadWorker.run()] --> B[Fetch Track Details]
    B --> C[Get Download URL]
    C --> D[Download Encrypted File]
    D --> E[Decrypt Audio]
    E --> F[Apply Metadata]
    F --> G[Save Final File]
    G --> H[Emit Success Signal]
    H --> I[Remove from Active Workers]
    I --> J[Update Queue State]
```

#### Worker Lifecycle
1. **Initialization**: Worker created with track/album information
2. **Execution**: `run()` method handles complete download process
3. **Progress Reporting**: Periodic progress signals to UI
4. **Completion**: Success/failure signals emitted
5. **Cleanup**: Worker removed from active workers list

### 4. State Persistence

#### Save Operations
```python
def _save_queue_state(self):
    # Group unfinished downloads by album/artist
    unfinished = {}
    for worker in self.active_workers.values():
        # Extract album/artist information
        album_id = str(track_info.get('album', {}).get('id', 'unknown'))
        # Group tracks by album
        if album_id not in unfinished:
            unfinished[album_id] = {
                'album_id': album_id,
                'album_title': album_title,
                'artist_name': artist_name,
                'type': 'album',
                'queued_tracks': []
            }
        unfinished[album_id]['queued_tracks'].append({
            'track_id': str(track_info.get('id', 'unknown')),
            'title': track_info.get('title', 'Unknown Title')
        })
    
    # Write to JSON file
    with open(queue_state_path, 'w', encoding='utf-8') as f:
        json.dump({
            'unfinished_downloads': list(unfinished.values()),
            'completed_downloads': completed_downloads,
            'failed_downloads': failed_downloads
        }, f, indent=2, ensure_ascii=False)
```

#### Load Operations
```python
def _load_queue_state(self):
    if not queue_state_path.exists():
        return None
    
    with open(queue_state_path, 'r', encoding='utf-8') as f:
        state = json.load(f)
    
    return state
```

## Signal System

### DownloadManager Signals
```python
class DownloadManagerSignals(QObject):
    download_started = pyqtSignal(dict)      # Download initiation
    download_progress = pyqtSignal(str, int) # Progress updates (0-100)
    download_finished = pyqtSignal(str)      # Successful completion
    download_failed = pyqtSignal(str, str)   # Failure with error message
    all_downloads_finished = pyqtSignal()    # Queue empty
    group_download_enqueued = pyqtSignal(dict) # Album/playlist queued
```

### Signal Flow
1. **download_started**: Emitted when worker begins execution
2. **download_progress**: Periodic updates during download/processing
3. **download_finished**: Successful completion with file path
4. **download_failed**: Error occurred with error message
5. **all_downloads_finished**: No active downloads remaining

## Race Condition Prevention System

### Clear Operations Coordination

The queue system implements sophisticated race condition prevention for clear operations:

#### Signal Management
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

The system automatically detects completed albums and removes them from unfinished downloads:

```python
def _are_album_tracks_completed(self, album_entry):
    """Check if all tracks in an album are completed by verifying file existence."""
    # Check each track file existence using pattern matching
    # Remove album from unfinished if all tracks have files
```

### Invalid Entry Filtering

Automatic filtering prevents infinite loops:

```python
def _is_valid_queue_entry(self, entry):
    """Filter out invalid entries that cause infinite loops."""
    # Check for invalid album_id ("unknown", empty, null)
    # Check for invalid track_id ("unknown", empty, non-numeric)
    # Only keep entries with valid, processable data
```

## UI Integration

### Download Queue Widget (`src/ui/download_queue_widget.py`)
- **Purpose**: Visual representation of download queue with race condition prevention
- **Features**:
  - Real-time progress display
  - Album/track grouping
  - Individual track progress
  - Error state visualization
  - Race condition prevention for clear operations
  - Automatic state consistency checking

### Queue Display Modes
1. **Album View**: Groups tracks by album, shows album progress
2. **Track View**: Individual track listing with progress bars
3. **Compact View**: Minimal space usage with essential information

## Error Handling

### Failure Categories
1. **Network Errors**: Connection timeouts, DNS failures
2. **Authentication Errors**: Invalid ARL token, expired session
3. **File System Errors**: Disk space, permissions, path issues
4. **Decryption Errors**: Invalid keys, corrupted data
5. **Metadata Errors**: Missing information, format issues

### Recovery Mechanisms
1. **Automatic Retry**: Failed downloads automatically retry with exponential backoff
2. **Queue Persistence**: Failed items remain in queue for manual retry
3. **Error Logging**: Detailed error information for troubleshooting
4. **Graceful Degradation**: Partial failures don't stop entire queue

## Performance Optimizations

### Concurrent Downloads
```python
# Configurable concurrent download limit
max_threads = self.config.get_setting('downloads.concurrent_downloads', 3)
self.thread_pool.setMaxThreadCount(max_threads)
```

### Memory Management
- **Streaming Processing**: Files processed in chunks, not loaded entirely into memory
- **Worker Cleanup**: Completed workers immediately removed from memory
- **State Compression**: Queue state stored efficiently in JSON format

### Disk I/O Optimization
- **Batch State Saves**: Multiple queue changes batched into single write
- **Atomic Writes**: Queue state written atomically to prevent corruption
- **Temporary Files**: Downloads use temporary files until completion

## Configuration

### Settings Integration
```json
{
  "downloads": {
    "concurrent_downloads": 3,
    "quality": "MP3_320",
    "path": "G:/Music",
    "retry_settings": {
      "max_retries": 3,
      "initial_delay": 1.0,
      "max_delay": 60.0,
      "backoff_factor": 2.0
    }
  }
}
```

### Configurable Parameters
- **Concurrent Downloads**: Maximum simultaneous downloads
- **Download Quality**: Audio quality preference (MP3_320, FLAC, etc.)
- **Download Path**: Target directory for completed files
- **Retry Logic**: Failure retry behavior
- **Timeout Settings**: Network timeout configurations

## Queue Restoration Logic

### Startup Restoration
```python
def _restore_queue_state(self):
    state = self._load_queue_state()
    if not state:
        return
    
    unfinished_downloads = state.get('unfinished_downloads', [])
    for download_group in unfinished_downloads:
        album_id = download_group.get('album_id')
        queued_tracks = download_group.get('queued_tracks', [])
        
        if album_id and album_id != 'unknown':
            # Restore album download
            track_ids = [int(track['track_id']) for track in queued_tracks]
            asyncio.create_task(self.download_album(album_id=int(album_id), track_ids=track_ids))
```

### Restoration Scenarios
1. **Complete Album Restoration**: All tracks from interrupted album download
2. **Partial Album Restoration**: Remaining tracks from partially completed album
3. **Individual Track Restoration**: Standalone track downloads
4. **Mixed Queue Restoration**: Combination of albums and individual tracks

## Debugging and Monitoring

### Logging System
- **Queue Operations**: All queue modifications logged
- **Worker Lifecycle**: Worker creation, execution, completion logged
- **State Changes**: Queue state saves/loads logged
- **Error Details**: Comprehensive error information captured

### Debug Information
```python
logger.info(f"Restoring {len(unfinished_downloads)} unfinished album/playlist downloads")
logger.info(f"Found {len(completed_downloads)} completed downloads in history")
logger.info(f"Active workers after initialization: {len(self.active_workers)}")
```

### Monitoring Capabilities
- **Queue Size Tracking**: Current queue length monitoring
- **Progress Aggregation**: Overall download progress calculation
- **Performance Metrics**: Download speed, success rate tracking
- **Resource Usage**: Memory and disk space monitoring

## Best Practices

### For Developers
1. **Always Save State**: Call `_save_queue_state()` after queue modifications
2. **Handle Async Operations**: Use proper async/await patterns for downloads
3. **Signal Connections**: Ensure UI properly connected to download signals
4. **Error Handling**: Implement comprehensive error handling and recovery
5. **Resource Cleanup**: Properly clean up workers and temporary files

### For Users
1. **Queue Management**: Monitor queue size to avoid overwhelming system
2. **Storage Space**: Ensure adequate disk space for downloads
3. **Network Stability**: Stable internet connection improves success rate
4. **Settings Configuration**: Optimize concurrent downloads for system capabilities

## Troubleshooting

### Common Issues
1. **Queue Not Restoring**: Check file permissions on queue state file
2. **Downloads Stalling**: Verify network connectivity and ARL token validity
3. **High Memory Usage**: Reduce concurrent download count
4. **File Corruption**: Check disk space and file system integrity

### Diagnostic Steps
1. **Check Logs**: Review debug logs for error messages
2. **Verify Configuration**: Ensure download settings are correct
3. **Test Network**: Verify Deezer API accessibility
4. **Clear Queue**: Reset queue state if corruption suspected

## Future Enhancements

### Planned Features
1. **Priority Queue**: User-defined download priorities
2. **Bandwidth Limiting**: Configurable download speed limits
3. **Schedule Downloads**: Time-based download scheduling
4. **Cloud Sync**: Queue synchronization across devices
5. **Advanced Filtering**: Queue filtering and search capabilities

### Performance Improvements
1. **Parallel Processing**: Enhanced concurrent processing
2. **Caching System**: Improved metadata and artwork caching
3. **Compression**: Queue state compression for large queues
4. **Database Backend**: SQLite backend for large queue management

---

## Technical Implementation Details

### File Paths and Structure
```
DeeMusic/
├── src/services/download_manager.py    # Core download management
├── src/ui/download_queue_widget.py     # UI components
└── %APPDATA%/DeeMusic/
    ├── download_queue_state.json       # Persistent queue state
    └── settings.json                    # Application configuration
```

### Key Classes and Methods
- `DownloadManager.__init__()`: Initializes queue and restores state
- `DownloadManager._restore_queue_state()`: Restores unfinished downloads
- `DownloadManager._save_queue_state()`: Persists current queue state
- `DownloadWorker.run()`: Executes individual download tasks
- `DownloadQueueWidget`: Provides visual queue management interface

This comprehensive queue system ensures reliable, persistent, and user-friendly download management for the DeeMusic application.