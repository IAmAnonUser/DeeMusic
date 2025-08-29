# DeeMusic - Complete AI Project Guide

## 🎯 Project Overview

**DeeMusic** is a comprehensive music management application that combines streaming, downloading, and library analysis capabilities. It's built with Python and PyQt6, featuring a modern dark/light theme interface and sophisticated music processing capabilities.

### Core Functionality
- **Music Streaming & Discovery**: Search and browse Deezer's catalog
- **High-Quality Downloads**: Download music in MP3 320kbps, FLAC, and other formats
- **Library Analysis**: Scan local music libraries and find missing albums
- **Playlist Conversion**: Convert Spotify playlists to Deezer downloads
- **Queue Management**: Robust persistent download queue with progress tracking and race condition prevention

## 🏗️ Architecture Overview

### Directory Structure
```
DeeMusic/
├── src/                           # Source Code
│   ├── ui/                        # User Interface Layer
│   │   ├── components/            # Reusable UI widgets
│   │   ├── styles/                # QSS stylesheets (dark/light themes)
│   │   ├── assets/                # Icons, images, logo
│   │   ├── main_window.py         # Main application window
│   │   ├── search_widget.py       # Search functionality
│   │   ├── download_queue_widget.py # Download queue UI
│   │   └── library_scanner_widget_minimal.py # Library scanner integration
│   ├── services/                  # Business Logic Layer
│   │   ├── deezer_api.py          # Deezer API integration
│   │   ├── spotify_api.py         # Spotify API integration
│   │   ├── download_manager.py    # Download orchestration
│   │   └── queue_manager.py       # Download queue management
│   ├── library_scanner/           # Library Analysis System
│   │   ├── core/                  # Core scanning logic
│   │   ├── services/              # Deezer comparison services
│   │   ├── ui/                    # Library scanner UI components
│   │   └── utils/                 # Utility functions
│   ├── utils/                     # Utility Functions
│   │   ├── image_cache.py         # Image caching system
│   │   ├── helpers.py             # General helpers
│   │   └── icon_utils.py          # Icon loading utilities
│   └── config_manager.py          # Configuration management
├── tools/                         # Build & Distribution
├── docs/                          # Documentation
├── requirements.txt               # Dependencies
└── run.py                         # Application entry point
```

### Key Components

#### Library Scanner Integration (v1.0.6)
The Library Scanner is fully integrated into DeeMusic's main interface:

**Features:**
- **Seamless Access**: "📚 Library Scanner" button in main toolbar
- **Automatic Loading**: Previous scan results load automatically
- **Clean Data Processing**: Uses metadata directly from scan_results.json
- **Smart Filtering**: Prevents folder names from appearing as artists
- **Deezer Comparison**: Find missing albums in your library

**Technical Improvements:**
- Enhanced comparison engine with data integrity validation
- Path filtering to prevent invalid artist names
- Smart detection of data format to avoid re-processing
- Comprehensive error handling and logging

**Data Flow:**
```
Local Library → Scan → Clean Metadata → Deezer Comparison → Missing Albums
     ↓              ↓           ↓              ↓               ↓
  Music Files   scan_results.json  Validated Data  API Calls   Results UI
```

#### 1. **ConfigManager** (`src/config_manager.py`)
- **Purpose**: Centralized configuration management with JSON persistence
- **Features**: 
  - Hierarchical settings (e.g., `downloads.quality`)
  - Thread-safe access
  - Automatic validation and type conversion
  - Hot-reload capabilities
- **Storage**: `%AppData%\DeeMusic\settings.json`

#### 2. **DeezerAPI** (`src/services/deezer_api.py`)
- **Purpose**: Handles all Deezer service interactions
- **Authentication**: ARL token (192-character hex string)
- **Features**:
  - Public API (charts, search) and Private API (downloads)
  - Rate limiting and retry logic
  - Session management and token refresh
  - Response caching

#### 3. **DownloadManager** (`src/services/download_manager.py`)
- **Purpose**: Orchestrates the complete download pipeline
- **Features**:
  - Multi-threaded download execution
  - Persistent queue management
  - Progress tracking and cancellation
  - Blowfish CBC decryption system
  - Metadata application and file organization

#### 4. **Library Scanner** (`src/library_scanner/`)
- **Purpose**: Analyzes local music libraries and finds missing content
- **Features**:
  - Multi-path library scanning
  - Incremental scanning with folder modification tracking
  - Deezer catalog comparison
  - Missing album detection and import to download queue
  - Cross-session result persistence

## 🔐 Encryption & Download System

### Authentication Flow
1. User provides ARL token (from browser cookies)
2. Token stored in config as `deezer.arl`
3. Used as cookie for all private API requests
4. License token retrieved for media URL requests
5. API tokens refreshed automatically

### Download Pipeline
```
User Request → Track Info → Media URL → Download → Decrypt → Metadata → Save
     ↓             ↓          ↓          ↓         ↓         ↓        ↓
  Queue Item   SNG_ID &   Encrypted   Temp File  Blowfish  Audio     Final
               Track      Download      (.part)   Decrypt   Tags      Path
               Token        URL                     ↓         ↓        ↓
                                               (.decrypted) (.tmp)  User Dir
```

### Blowfish CBC Stripe Decryption (CRITICAL)
**This is the most complex part of the system - must be implemented exactly:**

```python
def _generate_decryption_key(self, sng_id_str: str) -> Optional[bytes]:
    bf_secret_str = "g4el58wc0zvf9na1"  # Hardcoded Deezer secret
    
    # Generate MD5 hash of track ID
    hashed_sng_id_hex = MD5.new(sng_id_str.encode('ascii', 'ignore')).hexdigest()
    
    # XOR algorithm: Combine hash parts with secret
    key_char_list = []
    for i in range(16):
        xor_val = (ord(hashed_sng_id_hex[i]) ^ 
                   ord(hashed_sng_id_hex[i + 16]) ^ 
                   ord(bf_secret_str[i]))
        key_char_list.append(chr(xor_val))
    
    key_string = "".join(key_char_list)
    return key_string.encode('utf-8')
```

**Decryption Process:**
- Files processed in 6144-byte segments (3 × 2048 chunks)
- Each segment: [Encrypted 2048 bytes] + [Plain 4096 bytes]
- Only first chunk decrypted using Blowfish CBC
- Fixed IV: `0001020304050607`

## 📊 Data Storage & Persistence

### Configuration Files
```
%AppData%\DeeMusic\
├── settings.json                    # Main application settings
├── download_queue_state.json       # Persistent download queue
├── scan_results.json               # Library scan results
├── fast_comparison_results.json    # Deezer comparison cache
├── folder_mtimes.json              # Folder modification times
└── logs\                           # Application logs
```

### Settings Structure
```json
{
  "deezer": {
    "arl": "192-char-hex-token"
  },
  "downloads": {
    "quality": "MP3_320",
    "path": "C:\\Users\\...\\Music",
    "concurrent_downloads": 3,
    "folder_structure": {
      "create_artist_folders": true,
      "create_album_folders": true
    }
  },
  "appearance": {
    "theme": "dark"
  }
}
```

## 🎨 User Interface Architecture

### PyQt6 Framework
- **QMainWindow**: Primary application container
- **QStackedWidget**: Page navigation system
- **QThreadPool**: Background task execution
- **Signals/Slots**: Inter-component communication

### Theme System
- **Dynamic Switching**: Light/dark theme toggle
- **Consistent Styling**: QSS stylesheets for all components
- **Theme Manager**: Centralized theme state management

### Key UI Components
- **SearchResultCard**: Reusable music item display with artwork caching
- **ToggleSwitch**: Custom theme toggle control
- **ProgressCard**: Download progress visualization
- **LibraryScannerWidget**: Integrated library analysis interface

## 🔄 Library Scanner Integration

### Seamless Integration Features
- **Top Bar Access**: "📚 Library Scanner" button in main interface
- **Automatic Loading**: Previous scan/comparison results load on startup
- **Cross-Session Continuity**: Work persists between application sessions
- **Native Theming**: Matches DeeMusic's dark/light theme system
- **Easy Navigation**: "← Back to DeeMusic" for seamless transitions

### Scanning Process
1. **Library Path Management**: Add/remove multiple library directories
2. **Incremental Scanning**: Only scan changed folders using `folder_mtimes.json`
3. **Album Detection**: Identify album folders and extract metadata
4. **Deezer Comparison**: Compare local albums with Deezer catalog
5. **Missing Album Detection**: Find albums available on Deezer but missing locally
6. **Queue Integration**: Import selected albums directly to download queue

### Data Flow
```
Local Library → Scan → Album Catalog → Deezer API → Missing Albums → Download Queue
     ↓             ↓         ↓            ↓             ↓              ↓
  Folder Scan   Metadata   Album List   Comparison   Selection UI   Queue Import
```

## 🎵 Spotify Integration

### Playlist Conversion System
- **URL Detection**: Automatically detects Spotify playlist URLs in search
- **API Integration**: Uses Spotify Web API with Client Credentials flow
- **Track Matching**: Fuzzy matching algorithm to find Deezer equivalents
- **Quality Scoring**: Match confidence ratings (Excellent/Good/Fair/Poor)

### Matching Algorithm
- **Primary Match**: Artist + Title (weighted 80%)
- **Secondary Match**: Album name (weighted 15%)
- **Duration Tolerance**: ±10 seconds (weighted 5%)
- **Configurable Thresholds**: User-adjustable match quality requirements

## 🚀 Performance Optimizations

### Build Optimizations
- **Python Bytecode**: `--optimize=2` for maximum optimization
- **Selective Modules**: Only essential modules included
- **Debug Symbol Stripping**: Reduced file size and faster loading
- **UPX Disabled**: Faster startup (no decompression needed)

### Runtime Optimizations
- **Startup Optimizer**: Automatic Python interpreter optimization
- **Memory Management**: Optimized garbage collection thresholds
- **UI Performance**: Qt application optimizations for responsiveness
- **Concurrent Processing**: Multi-threaded downloads and UI operations

### User-Side Optimizations
- **Antivirus Exclusions**: Critical for performance improvement
- **SSD Storage**: 3-5x faster startup and operation
- **High Performance Mode**: Prevents CPU throttling
- **Network Optimization**: Wired connections preferred over WiFi

## 🛠️ Development Environment

### Setup Requirements
```bash
# 1. Clone repository
git clone https://github.com/IAmAnonUser/DeeMusic.git
cd DeeMusic

# 2. Create virtual environment
python -m venv venv_py311
.\venv_py311\Scripts\Activate.ps1  # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run application
python run.py
```

### Key Dependencies
```
PyQt6>=6.4.0          # GUI framework
qasync>=0.24.0         # Async Qt integration
aiohttp>=3.8.0         # HTTP client
mutagen>=1.46.0        # Audio metadata
pycryptodome>=3.15.0   # Encryption (Blowfish)
spotipy>=2.22.1        # Spotify API
```

### Code Standards
- **Formatting**: Black code formatter (`black src/ --line-length 100`)
- **Type Hints**: MyPy static type checking
- **Import Organization**: Standard → Third-party → Local
- **Error Handling**: Comprehensive exception handling with logging

## 🔧 Build System

### Distribution Options
1. **Standalone Executable**: Single `.exe` file (~90MB)
2. **Windows Installer**: Professional Inno Setup installer
3. **Simple Package**: ZIP archive with batch launcher

### Build Configuration
```python
# PyInstaller key options
--onefile                    # Single executable
--windowed                   # No console window
--icon=src/ui/assets/icon.ico
--add-data="src/ui/assets;assets"
--hidden-import=mutagen
--optimize=2                 # Maximum optimization
```

## 🐛 Common Issues & Solutions

### Authentication Problems
- **Symptom**: "Invalid CSRF token", "Authentication failed"
- **Solution**: Refresh ARL token from browser cookies

### Audio Quality Issues
- **Symptom**: Garbled, static, or corrupted audio
- **Cause**: Incorrect decryption algorithm implementation
- **Solution**: Verify key generation and stripe decryption logic exactly

### Performance Issues
- **Slow Startup**: Add to antivirus exclusions, use SSD storage
- **UI Freezing**: Ensure downloads run in background threads
- **Memory Usage**: Monitor for memory leaks, restart if usage exceeds 1.5GB

### Library Scanner Issues (Updated v1.0.6)
- **✅ Fixed: Invalid Artists**: No longer shows "Music" or drive letters as artists
- **✅ Fixed: Comparison Not Working**: Resolved scan data loading and key mapping issues
- **✅ Fixed: Data Processing**: Enhanced comparison engine with clean data processing
- **Scan Gets Stuck**: Check folder permissions and disk space
- **Missing Albums**: Verify Deezer availability in your region
- **No Results After Scan**: Ensure scan_results.json exists in %AppData%\DeeMusic\
- **Comparison Button Inactive**: Verify ARL token and library paths are configured

**For detailed troubleshooting, see:** `docs/LIBRARY_SCANNER_TROUBLESHOOTING.md`
- **Import Failures**: Ensure DeeMusic queue is accessible

### Download Queue Issues (Fixed v1.0.6+)
- **✅ Fixed: Race Conditions**: Clear operations no longer allow last tracks to complete after clearing
- **✅ Fixed: Persistent Completed Downloads**: Completed downloads no longer persist across app restarts
- **✅ Fixed: Infinite Loops**: Invalid queue entries are automatically filtered out
- **✅ Fixed: Directory Creation After Clear**: Folders are no longer created after clear operations
- **✅ Fixed: Re-downloading Moved Files**: Completed albums are properly removed from unfinished downloads
- **Clear Completed Items Come Back**: Ensure latest version with race condition fixes
- **Items Stuck in Queue**: Restart application or use "Clear All" to reset queue state
- **Folders Created After Clear**: Check logs for race condition prevention entries

### Navigation Issues (Fixed v1.0.6+)
- **✅ Fixed: View All Button Navigation**: "View All" buttons on home page and search results now properly display content
- **✅ Fixed: Empty Category Pages**: View All pages now show the expected grid of items
- **✅ Fixed: Search View All Buttons**: all_loaded_results is properly populated for search result filtering
- **View All Shows No Content**: Ensure latest version with layout and data population fixes
- **Navigation Not Working**: Check that section frames are properly added to results layout

**For detailed queue troubleshooting, see:** `QUEUE_FIXES_SUMMARY.md`, `CLEAR_COMPLETED_RACE_FIX.md`, `INFINITE_LOOP_FIX.md`

## 📈 Version History & Evolution

### v1.0.6 (Latest) - Library Scanner Integration & Queue Reliability
- **Complete Integration**: Library Scanner built into main application
- **Automatic Loading**: Previous results load seamlessly
- **Professional UI**: Native theming and navigation
- **Cross-Session Continuity**: Never lose analysis work
- **Race Condition Prevention**: Comprehensive fixes for clear operations preventing last tracks from completing after clearing
- **Queue State Accuracy**: Completed albums are properly removed from unfinished downloads, preventing re-downloads of moved files
- **Infinite Loop Prevention**: Invalid queue entries (unknown IDs) are automatically filtered out to prevent restoration loops
- **Signal Management**: Temporary signal disconnection during clear operations prevents race conditions
- **Directory Creation Prevention**: Multiple checkpoints prevent folder creation after clear operations
- **View All Navigation Fix**: "View All" buttons now properly display content instead of empty pages
- **Complete Integration**: Library Scanner built into main application
- **Automatic Loading**: Previous results load seamlessly
- **Professional UI**: Native theming and navigation
- **Cross-Session Continuity**: Never lose analysis work

### v1.0.5 - Performance & UI Improvements
- **Non-blocking Downloads**: Background processing
- **Sortable Results**: Interactive column headers
- **Crash Fixes**: Resolved Qt object lifecycle issues

### v1.0.4 - Stability Improvements
- **Build Fixes**: Resolved PyQt6 and dependency issues
- **Error Handling**: Improved download worker threads

### v1.0.3 - Initial Release
- **Core Features**: Downloads, search, queue management
- **Theme System**: Dark/light mode support
- **Spotify Integration**: Playlist conversion

## 🎯 Key Technical Concepts for AI Understanding

### 1. **Encryption is Critical**
The Blowfish CBC stripe decryption is the most complex and critical part. Any deviation in the key generation or decryption process results in corrupted audio. The hardcoded secret, XOR algorithm, and segment processing must be exact.

### 2. **Thread Safety is Essential**
All UI updates must use Qt signals/slots. Direct UI manipulation from worker threads causes crashes. The download system uses QThread workers with signal-based communication.

### 3. **Configuration Management**
The hierarchical JSON configuration system allows nested access (e.g., `config.get_setting('downloads.quality')`). All settings are validated and type-converted automatically.

### 4. **Library Scanner Integration**
The Library Scanner is fully integrated into the main application, not a separate tool. It loads previous results automatically and provides seamless navigation between library analysis and downloading.

### 5. **Queue Persistence & Race Condition Prevention**
The download queue survives application restarts with robust state management. Unfinished downloads are restored automatically using the `download_queue_state.json` file. Critical race condition fixes ensure:
- Clear operations properly coordinate with worker completion
- Completed albums are automatically removed from unfinished downloads
- Invalid entries are filtered out to prevent infinite loops
- Signal disconnection during clear operations prevents phantom downloads

### 6. **API Rate Limiting**
Both Deezer and Spotify APIs have rate limits. The application implements exponential backoff and request queuing to handle these gracefully.

### 7. **Cross-Platform Considerations**
While primarily Windows-focused, the application uses Path objects and platform-specific AppData locations for cross-platform compatibility.

### 8. **Download Queue Race Condition Management**
The queue system implements sophisticated race condition prevention:
- **Signal Disconnection**: Clear operations temporarily disconnect completion signals
- **Clearing Flags**: `_clearing_queue` flag prevents signal processing during clear operations
- **Worker Coordination**: Workers check if they're still tracked before emitting signals
- **File Existence Validation**: Completed albums are detected by checking file existence
- **Invalid Entry Filtering**: Queue entries are validated to prevent infinite loops

## 🔮 Future Development Areas

### Planned Enhancements
- **Real-time Library Monitoring**: Automatic detection of new files
- **Cloud Sync**: Settings and queue synchronization across devices
- **Advanced Filtering**: More sophisticated library analysis options
- **Batch Operations**: Enhanced bulk download and management features
- **Plugin System**: Extensible architecture for additional services

### Technical Debt
- **Database Backend**: Consider SQLite for large library management
- **Async Refactoring**: More comprehensive async/await usage
- **Test Coverage**: Expand unit and integration test suite
- **Documentation**: API documentation for developers

## 📚 Essential Files for AI Understanding

### Core Application Files
- `src/config_manager.py` - Configuration system
- `src/services/download_manager.py` - Download orchestration with race condition prevention
- `src/services/deezer_api.py` - API integration
- `src/ui/main_window.py` - Main interface
- `src/ui/download_queue_widget.py` - Queue UI with clear operation coordination
- `src/ui/library_scanner_widget_minimal.py` - Library scanner

### Documentation Files
- `docs/TECHNICAL_DOCUMENTATION.md` - Comprehensive technical details
- `docs/DOWNLOAD_SYSTEM_DOCUMENTATION.md` - Encryption and download specifics
- `docs/LIBRARY_SCANNER_COMPLETE_INTEGRATION.md` - Integration details
- `docs/DOWNLOAD_QUEUE_SYSTEM.md` - Queue management system

### Queue Fixes Documentation
- `QUEUE_FIXES_SUMMARY.md` - Complete queue fixes documentation
- `CLEAR_COMPLETED_RACE_FIX.md` - Race condition prevention details
- `INFINITE_LOOP_FIX.md` - Invalid entry filtering implementation
- `COMPLETED_ALBUM_REMOVAL_FIX.md` - Album completion detection system

### Configuration Examples
- `requirements.txt` - Python dependencies
- Example settings.json structure in config_manager.py
- Build scripts in `tools/` directory

This guide provides a complete understanding of DeeMusic's architecture, functionality, and technical implementation for AI assistance and development purposes.