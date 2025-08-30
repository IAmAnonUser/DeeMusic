# Changelog

All notable changes to DeeMusic will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.8] - 2025-01-30

### 🎵 Spotify Playlist Conversion
- **✅ Fixed Conversion Error**: Resolved "item_data is not defined" error that prevented Spotify playlist conversion
  - **Variable Name Fix**: Corrected undefined variable reference in playlist conversion display code
  - **Improved Error Handling**: Better error messages and debugging for playlist conversion issues
  - **Seamless Integration**: Spotify playlists now convert smoothly to Deezer downloads

### 🎨 Enhanced User Interface
- **🎯 Uniform Playlist Display**: Completely redesigned Spotify playlist conversion results to match DeeMusic's interface
  - **Professional Header**: Styled playlist title and conversion statistics with consistent typography
  - **Sortable Track List**: Added clickable column headers (TRACK, ARTIST, ALBUM, DUR.) for sorting
  - **Match Quality Indicators**: Visual tooltips showing match confidence (Excellent/Good/Fair/Weak match)
  - **Failed Match Styling**: Subtle red background and border for tracks not found on Deezer
  - **Download All Button**: Prominent purple button matching DeeMusic's design language
  - **Consistent Spacing**: Proper margins and padding throughout the conversion results

### 🚀 Automated Installer
- **⚡ Zero-Prompt Installation**: Completely automated installer with no user prompts required
  - **Auto System Installation**: Automatically installs to Program Files (requires admin rights)
  - **Auto Desktop Shortcut**: Creates desktop shortcut with proper icon automatically
  - **Auto Launch**: Launches DeeMusic immediately after installation
  - **Fixed Desktop Icons**: Resolved blank desktop shortcut icons by using embedded executable icons
  - **Streamlined Experience**: Installation completes in under 30 seconds with zero user input

### 🔧 Technical Improvements
- **🖼️ Icon System Enhancement**: Improved shortcut icon handling across all installer types
  - **Embedded Icon Usage**: Uses icons embedded in DeeMusic.exe instead of separate .ico files
  - **Cross-Platform Compatibility**: Better icon handling for Windows shortcuts and registry entries
  - **Consistent Display**: All shortcuts (Desktop, Start Menu, Quick Launch) use the same icon source

### 📦 Build System
- **🏗️ Updated Build Tools**: Enhanced installer creation with improved automation
  - **Version Synchronization**: Automatic version detection and updating across all installer components
  - **Professional Packaging**: Consistent branding and styling across all installer elements
  - **Quality Assurance**: Improved error handling and validation in build scripts

## [1.0.6] - 2025-07-26

### 🎯 Major Track Number Fix
- **✅ Correct Track Numbering**: Fixed critical issue where all album tracks showed "01" instead of proper sequential numbers (01, 02, 03, etc.)
  - **API Field Mapping**: Corrected Deezer API field mapping from `TRACK_POSITION` to `SNG_TRACK_NUMBER`
  - **Type Conversion**: Added proper integer conversion for track number fields
  - **Download Logic**: Modified download worker to always fetch detailed track info for album tracks
  - **Consistency**: Ensured `track_position` always matches `track_number` for reliable processing
  - **Fallback Logic**: Improved fallback chain: `SNG_TRACK_NUMBER` → `TRACK_POSITION` → `POSITION` → default to 1

### 🔧 Download Queue Improvements
- **🗑️ Clear Pending Downloads**: Added dedicated "Clear Pending" button to resolve stuck downloads from previous sessions
  - **Targeted Cleanup**: New button specifically clears stuck pending downloads without affecting active downloads
  - **Smart Detection**: Improved album completion detection with enhanced logging for troubleshooting
  - **UI Refresh**: Better queue state management ensures UI properly refreshes after clearing operations
  - **Race Condition Prevention**: Enhanced clear operations to prevent timing issues and phantom downloads

### 🛠️ Technical Enhancements
- **🔄 Queue State Management**: Improved reliability of download queue persistence
  - **Empty State Creation**: Clear operations now create fresh empty queue state files for proper UI refresh
  - **Better Completion Detection**: Enhanced `_are_album_tracks_completed` method with detailed logging
  - **Thread Safety**: Improved thread-safe operations for queue state modifications
  - **Error Handling**: Better exception handling and recovery for queue operations

### 🎨 User Interface
- **📱 Download Queue Widget**: Enhanced download queue interface
  - **Three-Button Layout**: "Clear All", "Clear Pending", and "Clear Completed" buttons for granular control
  - **Tooltips**: Added helpful tooltips explaining each button's function
  - **Better Spacing**: Improved button layout and spacing for better usability

### 📚 Library Scanner Integration (Previous Release)
- **Built-in Access**: "📚 Library Scanner" button added to DeeMusic's top bar for instant access
- **Automatic Results Loading**: Previous scan and comparison results load automatically from AppData
- **Cross-Session Continuity**: Never lose your library analysis work between sessions
- **Professional UI**: Native dark theme integration matching DeeMusic's visual design
- **Easy Navigation**: "← Back to DeeMusic" button for seamless navigation between interfaces
- **Smart Data Persistence**: Loads from `%APPDATA%\DeeMusic\scan_results.json` and `fast_comparison_results.json`
- **Hierarchical View**: Artists panel (left) and albums panel (right) for easy browsing
- **Bulk Selection**: Checkbox system for selecting multiple albums to import
- **Direct Queue Integration**: Import selected albums directly to DeeMusic's download queue
- **Status Display**: Header shows loaded data statistics and scan dates
- **Graceful Fallback**: Works perfectly even if no previous scan results exist

### 🎯 Detailed Progress Tracking (Previous Release)
- **Real-time File Display**: Shows exact file currently being scanned with truncated paths for readability
- **Comprehensive Metrics**: Progress bar, percentage, file counter (1,234 / 5,678 files), and scanning speed
- **Multi-threaded Scanning**: Non-blocking scans using QThread with cancellable operations
- **Performance Indicators**: Real-time "files/sec" or "sec/file" speed calculations
- **Current File Highlighting**: Dedicated display box showing "📁 Scanning: ...Music/Artist/Album/Song.mp3"
- **Thread-safe Updates**: All progress updates use Qt signals for UI responsiveness

### 📁 Complete Library Path Management (Previous Release)
- **Path Input & Browse**: Text field with browse button for selecting library directories
- **Add/Remove Paths**: Dynamic path management with persistent storage in config
- **Paths List Display**: Tree widget showing all configured library paths
- **Validation**: Ensures only valid, existing directories are added
- **Multi-path Support**: Scan multiple library locations simultaneously

### 🔄 Incremental Scanning (Previous Release)
- **Modification Time Tracking**: Uses `%appdata%/DeeMusic/folder_mtimes.json` to track folder changes
- **Smart Change Detection**: Only scans folders that have been modified since last scan
- **Automatic Updates**: Saves new modification times after each scan
- **Performance Optimization**: Dramatically reduces scan time for unchanged libraries

### Fixed
- **🔄 Download Queue Race Conditions**: Comprehensive fixes for queue clear operations
  - **Clear Completed Race Fix**: Prevents last tracks from completing after "Clear Completed" is pressed
  - **Signal Coordination**: Temporary signal disconnection during clear operations prevents phantom downloads
  - **Worker Stopping**: Enhanced worker stop mechanism with proper cleanup and validation
  - **Directory Creation Prevention**: Multiple checkpoints prevent folder creation after clear operations
  - **File Watcher Coordination**: Proper coordination between file watcher and clear operations

- **📁 Completed Album Detection**: Automatic removal of completed albums from unfinished downloads
  - **File Existence Validation**: Smart detection of completed downloads by checking file existence
  - **Pattern Matching**: Flexible file matching handles various naming conventions and folder structures
  - **Queue State Accuracy**: Completed albums are automatically removed from "unfinished_downloads"
  - **Re-download Prevention**: Moving downloaded folders no longer triggers re-downloads of completed content

- **🔄 Infinite Loop Prevention**: Automatic filtering of invalid queue entries
  - **Invalid Entry Detection**: Filters out entries with "unknown" IDs that cause restoration loops
  - **Queue Validation**: Robust validation prevents various types of invalid data from being saved
  - **Startup Cleanup**: Automatic cleanup of invalid entries on application initialization
  - **Logging**: Enhanced logging for debugging queue issues and validation failures

- **🛡️ Queue State Persistence**: Improved reliability of queue state management
  - **Persistent State Cleanup**: Completed downloads no longer persist across app restarts unnecessarily
  - **File Watcher Improvements**: Only reloads queue when appropriate, preventing unnecessary operations
  - **State Consistency**: Automatic detection and fixing of UI/persistent state mismatches
  - **Robust Error Handling**: Better exception handling throughout queue operations

- **🔍 View All Button Navigation**: Fixed "View All" buttons not displaying content
  - **Home Page Fix**: Section frames are now properly added to results layout for home page View All
  - **Search Results Fix**: all_loaded_results is now properly populated for search View All buttons
  - **Content Display**: View All pages now show the expected grid of items
  - **Navigation**: Seamless transition from home page and search results to full category views

### Enhanced
- **🎨 Top Bar Layout**: Optimized search bar width to accommodate Library Scanner button
- **🔄 Navigation System**: Enhanced main window navigation to support Library Scanner integration
- **📁 File Organization**: Moved Library Scanner components to `src/library_scanner/` for better organization
- **📖 Documentation**: Updated README.md and created comprehensive integration documentation

- **📊 Queue Debugging Tools**: Comprehensive testing and debugging utilities
  - **test_queue_fixes.py**: General queue state testing and verification
  - **test_clear_completed_race.py**: Specific testing for clear completed race conditions
  - **test_completed_album_removal.py**: Testing for album completion detection
  - **fix_queue_loop.py**: Manual cleanup tool for invalid queue entries
  - **test_view_all_fix.py**: Testing utility for View All button functionality

- **📝 Documentation**: Comprehensive documentation of queue fixes and implementation details
  - **QUEUE_FIXES_SUMMARY.md**: Complete overview of all queue fixes
  - **CLEAR_COMPLETED_RACE_FIX.md**: Detailed race condition prevention documentation
  - **INFINITE_LOOP_FIX.md**: Invalid entry filtering implementation details
  - **COMPLETED_ALBUM_REMOVAL_FIX.md**: Album completion detection system documentation
  - **docs/DOWNLOAD_QUEUE_RELIABILITY.md**: Comprehensive reliability improvements documentation

- **🎨 Text Visibility & Theme Integration**: Completely resolved text contrast issues
  - **Dual Theme Support**: Automatic light/dark mode detection from DeeMusic's theme manager
  - **Light Mode**: Light backgrounds with dark text for maximum readability
  - **Dark Mode**: Maintains existing dark theme when DeeMusic is in dark mode
  - **High Contrast Styling**: Proper background colors for all text elements
  - **Status Label Enhancement**: Light background with dark text for critical status information

- **🔧 UI State Management**: Intelligent button and control management
  - **Context-aware Buttons**: Scan/Update/Clear buttons enable/disable based on current state
  - **Progress UI Control**: Automatic show/hide of progress elements during operations
  - **Session Restoration**: Proper initialization based on existing scan data
  - **Error Handling**: Graceful error display and recovery

### Fixed
- **🔍 Library Scanner Comparison Engine**: Major fixes to comparison functionality
  - **Data Integrity**: Fixed comparison engine to use clean metadata directly from scan_results.json
  - **Artist Filtering**: Prevented folder names like "Music" or drive letters from appearing as artists
  - **Path Validation**: Added filtering to reject path-like strings as artist names
  - **Smart Processing**: Intelligent detection of data format to avoid unnecessary re-processing
  - **Scan Results Loading**: Fixed scan completion handlers to properly load results into memory
  - **Key Mapping**: Corrected scan worker results key from "files" to "scanned_files"
  - **Clean Conversion**: Added `_convert_tracks_to_albums()` method for clean data processing
  - **Error Prevention**: Comprehensive validation to ensure only valid artist names appear in results

- **🗑️ Code Cleanup**: Removed obsolete and corrupted files
  - Deleted corrupted `library_scanner_widget_clean.py`
  - Removed unused `library_scanner_widget.py` (replaced by minimal version)
  - Cleaned up redundant code and improved maintainability

### Technical Improvements
- **⚡ ScanWorker Thread**: Professional multi-threaded scanning implementation
- **📊 Progress Signals**: Comprehensive signal system for real-time updates
- **🔒 Thread Safety**: Proper Qt signal/slot communication for UI updates
- **💾 Data Persistence**: Enhanced AppData integration for scan results and folder tracking
- **🎛️ Cancellation Support**: Users can stop long-running scans at any time

## [1.0.5] - 2025-01-12

### Fixed
- **🚀 Major UI Responsiveness Improvement**: Fixed blocking downloads that prevented users from searching or browsing while downloads were in progress
- Downloads now run completely in the background without freezing the user interface
- Users can now search, browse, and queue multiple downloads simultaneously
- Eliminated synchronous API calls that were blocking the main UI thread during album/playlist downloads
- **🎯 Search Results Enhancement**: Fixed track list header alignment and padding issues in search results
- Track headers (TRACK, ARTIST, ALBUM, DUR.) now display properly without being cut off
- Improved header padding and spacing for better readability
- **🔧 Critical Crash Fix**: Resolved application crashes when switching between artists in artist detail pages
- Fixed "wrapped C/C++ object has been deleted" RuntimeError that occurred during layout clearing
- Improved widget lifecycle management to prevent accessing deleted Qt objects
- Enhanced layout safety checks with proper SIP object deletion detection

### Added
- **🔄 Sortable Search Results**: Added clickable column headers to search results track lists
- Users can now sort search results by track name, artist, album, or duration
- Sort indicators show current sort direction (ascending/descending)
- Sorting functionality works in both "All" view and dedicated "Tracks" filter view
- Consistent sorting behavior across all track list views (search results, artist pages, etc.)
- **📊 Album Sorting**: Added sorting functionality to Albums, Singles, EPs, and Featured In tabs in artist detail pages
- Sort albums by title, release date, or track count
- Consistent sorting UI across all album grid displays

### Technical Details
- Removed blocking `get_album_details_sync()` calls from search widget
- All album and playlist downloads now use asynchronous `asyncio.create_task()` 
- Download manager handles metadata fetching internally in background threads
- Maintained existing threaded download architecture for optimal performance
- Replaced static search headers with interactive `TrackListHeaderWidget`
- Implemented sorting logic for all track list displays
- Enhanced CSS styling for better header appearance and hover effects
- Added proper track data storage for sorting operations
- Improved widget deletion handling in `_init_tab_content_widgets()` to prevent premature cleanup
- Enhanced `_safe_sip_is_deleted()` method with better Qt object validation
- Added defensive layout clearing with proper object lifecycle checks

## [1.0.4] - 2025-01-XX

### Fixed
- Resolved build issues with PyQt6 and qasync dependencies
- Fixed indentation errors in download manager that caused startup crashes
- Improved error handling in download worker threads
- Updated requirements.txt with compatible package versions

### Changed
- Updated aiohttp dependency to version 3.10.5 for better compatibility
- Enhanced build process to properly include all required modules

## [1.0.3] - 2025-01-XX

### Added
- Initial release with core functionality
- High-quality music downloads (MP3 320kbps, FLAC)
- Modern PyQt6 interface with dark/light themes
- Smart search with instant results
- Spotify playlist conversion support
- Multi-threaded download management
- Automatic metadata and artwork embedding
- Customizable folder organization
- Download queue with progress tracking

### Features
- 🎵 Support for tracks, albums, playlists, and artist discographies
- 🎨 Beautiful, responsive user interface
- 🔍 Advanced search with filtering options
- 📊 Real-time download progress and queue management
- 🖼️ Automatic high-resolution artwork embedding
- 📁 Flexible file organization and naming templates
- ⚡ Concurrent downloads with configurable limits
- 🎧 Spotify playlist import and conversion

---

## Version History Summary

- **v1.0.5**: Non-blocking downloads, sortable search headers, and UI improvements
- **v1.0.4**: Dependency fixes and build improvements  
- **v1.0.3**: Initial stable release with core features 