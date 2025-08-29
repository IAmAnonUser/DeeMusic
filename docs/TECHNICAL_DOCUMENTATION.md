# DeeMusic - Comprehensive Technical Documentation

## Table of Contents
1. [Project Architecture](#1-project-architecture)
2. [Download System](#2-download-system)  
3. [User Interface Architecture](#3-user-interface-architecture)
4. [Database & Configuration](#4-database--configuration)
5. [API Integration](#5-api-integration)
6. [Build System](#6-build-system)
7. [Development Guide](#7-development-guide)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Project Architecture

### 1.1 High-Level Overview
DeeMusic follows a modular MVC-like architecture with clear separation between UI, business logic, and data layers.

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   UI Layer      │◄──►│  Service Layer  │◄──►│   Data Layer    │
│                 │    │                 │    │                 │
│ • PyQt6 Widgets │    │ • API Services  │    │ • Config Mgr    │
│ • Themes/Styles │    │ • Download Mgr  │    │ • Image Cache   │
│ • Components    │    │ • Queue Mgr     │    │ • Database      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### 1.2 Directory Structure
```
DeeMusic/
├── src/                       # Source Code
│   ├── ui/                    # User Interface Layer
│   │   ├── components/        # Reusable UI widgets
│   │   │   ├── search_result_card.py
│   │   │   ├── toggle_switch.py
│   │   │   └── progress_card.py
│   │   ├── styles/            # QSS stylesheets  
│   │   │   ├── main.qss
│   │   │   ├── dark.qss
│   │   │   └── light.qss
│   │   ├── assets/            # Icons, images, logo
│   │   ├── main_window.py     # Main application window
│   │   ├── home_page.py       # Home/dashboard
│   │   ├── search_widget.py   # Search functionality
│   │   ├── artist_detail_page.py
│   │   ├── album_detail_page.py
│   │   ├── playlist_detail_page.py
│   │   ├── settings_dialog.py
│   │   └── library_scanner_widget_minimal.py  # Library Scanner integration
│   ├── library_scanner/       # Library Scanner Module
│   │   ├── core/              # Core scanning algorithms
│   │   ├── services/          # Deezer comparison services
│   │   ├── ui/                # Scanner-specific UI components
│   │   └── utils/             # Scanner utility functions
│   │   └── download_queue_widget.py
│   ├── services/              # Business Logic Layer
│   │   ├── deezer_api.py      # Deezer API integration
│   │   ├── spotify_api.py     # Spotify API integration
│   │   ├── playlist_converter.py # Spotify→Deezer conversion
│   │   ├── download_manager.py # Download orchestration
│   │   ├── music_player.py    # Audio playback (future)
│   │   ├── library_manager.py # Local library management
│   │   └── queue_manager.py   # Download queue management
│   ├── utils/                 # Utility Functions
│   │   ├── image_cache.py     # Image caching system
│   │   ├── helpers.py         # General helpers
│   │   ├── lyrics_utils.py    # Lyrics processing
│   │   └── icon_utils.py      # Icon loading utilities
│   ├── models/                # Data Models
│   │   └── database.py        # Database schema & models
│   └── config_manager.py      # Configuration management
├── tools/                     # Build & Distribution
├── docs/                      # Documentation
├── requirements.txt           # Dependencies
└── run.py                     # Application entry point
```

### 1.3 Core Components

**ConfigManager**: Centralized configuration management with JSON persistence
- Settings validation and type conversion
- Nested configuration access (e.g., `downloads.quality`)
- Automatic file watching and hot-reload
- Thread-safe access patterns

**DeezerAPI**: Encapsulates all Deezer service interactions
- Authentication management (ARL tokens)
- Rate limiting and retry logic
- Public and private API endpoint abstraction
- Response caching and validation

**DownloadManager**: Orchestrates the download pipeline
- Multi-threaded download execution
- Queue management with priority support
- Progress tracking and cancellation
- Error handling and retry mechanisms

---

## 2. Download System

### 2.1 Overview
The download system handles encrypted audio files from Deezer's CDN and decrypts them locally using Blowfish CBC encryption. The system includes sophisticated queue management with race condition prevention and automatic completion detection.

### 2.1.1 Recent Queue System Enhancements (v1.0.7+)
- **Race Condition Prevention**: Comprehensive fixes for clear operations preventing phantom downloads
- **Completed Album Detection**: Automatic removal of completed albums from unfinished downloads
- **Invalid Entry Filtering**: Prevention of infinite loops from malformed queue entries
- **Signal Coordination**: Temporary signal disconnection during clear operations
- **Directory Creation Prevention**: Multiple checkpoints prevent folder creation after clear operations

### 2.2 Authentication Flow
```
1. User provides ARL token (192-char hex string)
2. Token stored in config as 'deezer.arl' 
3. Set as cookie for all private API requests
4. License token retrieved for media URL requests
5. API tokens refreshed automatically via getUserData
```

### 2.3 Download Pipeline
```
User Request → Track Info → Media URL → Download → Decrypt → Metadata → Save
     ↓             ↓          ↓          ↓         ↓         ↓        ↓
  Queue Item   SNG_ID &   Encrypted   Temp File  Blowfish  Audio     Final
               Track      Download      (.part)   Decrypt   Tags      Path
               Token        URL                     ↓         ↓        ↓
                                               (.decrypted) (.tmp)  User Dir
```

### 2.4 Encryption System: Blowfish CBC Stripe

**Key Generation Algorithm** (CRITICAL - must be exact):
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

**Decryption Process: CBC Stripe Method**
- Files processed in 6144-byte segments (3 × 2048 chunks)
- Each segment: [Encrypted 2048 bytes] + [Plain 4096 bytes]
- Only first chunk decrypted using Blowfish CBC
- Fixed IV: `0001020304050607`

### 2.5 Quality & Format Support
- **MP3_320**: 320 kbps MP3 (most common)
- **FLAC**: Lossless format
- **MP3_128**: 128 kbps fallback
- **AAC_64**: 64 kbps (rare)

### 2.6 Metadata Processing
Applied post-decryption using Mutagen:
```python
# Standard ID3v2 tags
TIT2: Title
TPE1: Artist
TALB: Album
TRCK: Track number
TPOS: Disc number
TCON: Genre
TDRC: Release date
APIC: Embedded artwork (Cover front)
```

### 2.7 File Organization
Customizable folder structures:
```
{Download Dir}/
├── {Artist}/
│   ├── {Album}/
│   │   ├── CD1/ (if multi-disc)
│   │   │   ├── 01 - Artist - Title.mp3
│   │   │   └── 02 - Artist - Title.mp3
│   │   └── cover.jpg
│   └── artist.jpg
```

Template variables:
- `{artist}`, `{album}`, `{title}`
- `{track_number:02d}`, `{disc_number}`
- `{year}`, `{genre}`, `{album_artist}`

---

## 3. User Interface Architecture

### 3.1 PyQt6 Framework
- **QMainWindow**: Primary application container
- **QStackedWidget**: Page navigation system
- **QThreadPool**: Background task execution
- **Signals/Slots**: Inter-component communication

### 3.2 Theme System
Dynamic theme switching with separate stylesheets:
- `styles/light.qss`: Light theme colors and styling
- `styles/dark.qss`: Dark theme implementation
- `theme_manager.py`: Theme state management

### 3.3 Component Architecture
**SearchResultCard**: Reusable music item display
- Artwork loading with caching
- Hover effects and download buttons
- Type-specific rendering (track/album/artist/playlist)

**ToggleSwitch**: Custom theme toggle control  
- Native QCheckBox with custom styling
- Animated state transitions
- Accessibility support

**ProgressCard**: Download progress visualization
- Real-time progress updates via signals
- Cancellation and retry controls
- Status indicators (downloading/completed/failed)

### 3.4 Navigation Flow
```
MainWindow (QStackedWidget)
├── HomePage (charts, recommendations)
├── SearchWidget (search results)
├── ArtistDetailPage (artist info + discography)
├── AlbumDetailPage (track listing)
├── PlaylistDetailPage (playlist contents)
└── DownloadQueueWidget (download monitoring)
```

---

## 4. Library Scanner Integration

### 4.1 Architecture Overview
The Library Scanner is fully integrated into DeeMusic's main interface, providing seamless library analysis and missing album detection.

```
┌─────────────────────────────────────────────────────────────┐
│                    Main DeeMusic Window                     │
├─────────────────────────────────────────────────────────────┤
│ Top Bar: [Search] [📚 Library Scanner] [Settings] [Theme]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Library Scanner Widget                 │    │
│  │  ┌─ Library Scan ─┬─ Comparison ─┐                 │    │
│  │  │ Artists Panel  │ Albums Panel │                 │    │
│  │  │ (Left Side)    │ (Right Side) │                 │    │
│  │  └────────────────┴──────────────┘                 │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Data Processing Pipeline
```
scan_results.json → Load Clean Data → Smart Processing → Comparison Engine
       ↓                   ↓               ↓                    ↓
   File Metadata    Track-Level Data   Album Grouping    Deezer Comparison
   (Artist, Album)  (Clean & Validated) (Filtered)      (Missing Albums)
```

### 4.3 Comparison Engine (v1.0.6)
Enhanced comparison system with intelligent data processing:

```python
def _convert_tracks_to_albums(self, tracks):
    """Convert clean track data from scan_results.json to album format."""
    # Key improvements:
    # 1. Uses clean metadata directly from JSON
    # 2. Filters out path-like artists (containing \, /, :)
    # 3. Validates artist names to prevent folder names appearing
    # 4. Preserves data integrity without re-processing
```

### 4.4 Data Integrity Features
- **Clean Data Processing**: Uses metadata directly from scan_results.json
- **Path Filtering**: Automatically rejects folder names as artists
- **Smart Detection**: Intelligently detects data format and processes accordingly
- **Error Prevention**: Comprehensive validation to ensure clean results

### 4.5 File Structure
```
%APPDATA%\DeeMusic\
├── scan_results.json              # Clean track metadata
├── fast_comparison_results.json   # Deezer comparison results
├── folder_mtimes.json             # Folder modification tracking
└── settings.json                  # Configuration
```

---

## 5. Database & Configuration

### 4.1 Configuration System
JSON-based configuration with hierarchical structure:
```json
{
  "deezer": {
    "arl": "19...", 
    "api_token": "...",
    "csrf_token": "..."
  },
  "downloads": {
    "quality": "MP3_320",
    "directory": "C:\\Users\\...\\Music",
    "concurrent_downloads": 3,
    "folder_structure": {
      "create_artist_folders": true,
      "create_album_folders": true,
      "create_cd_folders": true
    }
  },
  "appearance": {
    "theme": "dark"
  }
}
```

### 4.2 Settings Management
**Thread-Safe Access**: All config operations are thread-safe
**Validation**: Type checking and value validation on set
**Persistence**: Automatic saving to `%AppData%\DeeMusic\settings.json`
**Hot Reload**: UI updates automatically when settings change

### 4.3 Cache Management
**Image Cache**: `%USERPROFILE%\.cache\deemusic\image_cache\`
- MD5-hashed filenames
- Automatic size limits
- LRU eviction policy

**Metadata Cache**: In-memory caching of API responses
- Track info cache (30 minutes)
- Artist/album details (60 minutes)
- Search results (15 minutes)

---

## 5. API Integration

### 5.1 Deezer API Endpoints

**Public API** (no authentication):
```
GET /chart/0/tracks?limit=25    # Chart tracks
GET /chart/0/albums?limit=25    # Chart albums
GET /search/track?q=query       # Search tracks
GET /artist/{id}                # Artist details
GET /album/{id}                 # Album details
```

**Private API** (requires ARL):
```
POST /ajax/gw-light.php?method=deezer.pageTrack
POST /ajax/gw-light.php?method=deezer.getUserData
POST https://media.deezer.com/v1/get_url
```

### 5.2 Spotify API Integration

**Spotify Web API** (requires Client Credentials):
```
GET /playlists/{playlist_id}           # Playlist metadata
GET /playlists/{playlist_id}/tracks    # Playlist tracks
GET /tracks/{track_id}                 # Track details
```

**Authentication Flow**:
1. User creates Spotify app at developer.spotify.com
2. Client ID and Client Secret obtained
3. Client Credentials flow used (no user login required)
4. Access token retrieved for API requests
5. Token automatically refreshed when expired

**Playlist Conversion Pipeline**:
```
Spotify URL → Playlist ID → Track List → Deezer Search → Match Scoring → Results
     ↓             ↓           ↓            ↓              ↓            ↓
  URL Parse    API Request   Track Info   Search Each   Fuzzy Match   UI Display
                   ↓           ↓            ↓              ↓            ↓
                Metadata   Track Details  Candidates    Confidence   Download Queue
```

**Track Matching Algorithm**:
- Primary match: Artist + Title (weighted 80%)
- Secondary match: Album name (weighted 15%) 
- Duration tolerance: ±10 seconds (weighted 5%)
- Fuzzy string matching with configurable thresholds
- Quality scoring: 90%+ Excellent, 70%+ Good, 50%+ Fair

### 5.3 Authentication Management
**ARL Token**: 192-character hexadecimal authentication token
- Retrieved from browser cookies
- Stored securely in application config
- Required for downloads and private data

**Session Management**:
- API tokens refreshed automatically
- CSRF protection handling
- Session timeout detection and recovery

### 5.4 Track Number Processing (v1.0.6 Fix)

**Critical Fix**: Resolved track numbering issue where all album tracks showed "01"

**Root Cause**: 
- Album listing API (`get_album_details`) uses different field names than individual track API
- Download worker was using initial track info from album listing instead of detailed track info
- Field mapping was incorrect: `TRACK_POSITION` vs `SNG_TRACK_NUMBER`

**Solution Implementation**:
```python
# Fixed API field mapping in deezer_api.py
key_mappings_to_ensure = {
    'track_number': 'SNG_TRACK_NUMBER',  # Changed from 'TRACK_POSITION'
    'disk_number': 'DISK_NUMBER',
    'duration': 'DURATION',
    # ... other mappings
}

# Enhanced download worker logic
if self.item_type == 'album_track':
    # Always fetch detailed track info for correct track numbers
    authoritative_track_info = self.download_manager.deezer_api.get_track_details_sync_private(self.item_id)
```

**Field Priority Chain**:
1. `SNG_TRACK_NUMBER` (primary - correct field)
2. `TRACK_POSITION` (fallback)
3. `POSITION` (secondary fallback)
4. Default to `1` (last resort)

**Type Conversion**: Added proper integer conversion for numeric fields
**Consistency**: Ensured `track_position` always matches `track_number`

### 5.5 Rate Limiting
**Implementation**:
- Per-endpoint rate limits
- Exponential backoff on 429 responses  
- Request queuing and throttling
- User-configurable delay settings

---

## 6. Build System

### 6.1 PyInstaller Configuration
**Main Build Script**: `tools/build.py`
```python
# Key configuration options
--onefile                    # Single executable
--windowed                   # No console window
--icon=src/ui/assets/icon.ico
--add-data="src/ui/assets;assets"
--hidden-import=mutagen
--exclude-module=tkinter
```

### 6.2 Distribution Options

**Standalone Executable** (`build.py`):
- Single `.exe` file (~90MB)
- All dependencies included
- Portable - no installation required

**Windows Installer** (`build_installer.py`):
- Professional Inno Setup installer
- Registry integration
- Start menu shortcuts
- Uninstaller with settings cleanup

**Simple Package** (`create_simple_installer.py`):
- ZIP archive with executable
- Batch file launcher
- Basic documentation

### 6.3 Build Features
- **Custom Icon**: Professional branding throughout Windows
- **Optimized Size**: Excluded unnecessary modules
- **Dependency Management**: Automatic library detection
- **Settings Preservation**: User config survives updates

---

## 7. Development Guide

### 7.1 Development Environment Setup
```bash
# 1. Clone repository
git clone https://github.com/IAmAnonUser/DeeMusic.git
cd DeeMusic

# 2. Create virtual environment  
python -m venv venv_py311
.\venv_py311\Scripts\Activate.ps1  # Windows
source venv_py311/bin/activate     # Linux/macOS

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install development tools
pip install black pytest mypy

# 5. Run application
python run.py
```

### 7.2 Code Style & Standards
**Formatting**: Black code formatter
```bash
black src/ --line-length 100
```

**Type Hints**: MyPy static type checking
```bash
mypy src/ --ignore-missing-imports
```

**Imports**: Organized and explicit
- Standard library imports first
- Third-party imports second  
- Local imports last
- Absolute imports preferred over relative

### 7.3 Testing Strategy
**Unit Tests**: Core business logic
```python
# Example test structure
def test_key_generation():
    sng_id = "123456789"
    key = generate_decryption_key(sng_id)
    assert len(key) == 16
    assert isinstance(key, bytes)
```

**Integration Tests**: API interactions
**UI Tests**: QtTest framework for widget testing

### 7.4 Logging Configuration
**Log Levels**:
- DEBUG: Detailed diagnostic information
- INFO: General application flow
- WARNING: Potential issues
- ERROR: Error conditions
- CRITICAL: Serious errors requiring attention

**Log Files**: `%AppData%\DeeMusic\logs\deemusic.log`

### 7.5 Error Handling Patterns
**Network Errors**: Retry with exponential backoff
**Authentication Errors**: Token refresh and re-attempt
**File System Errors**: Graceful degradation and user notification
**API Errors**: Error categorization and appropriate user messages

---

## 8. Troubleshooting

### 8.1 Common Issues

**Authentication Failures**:
- Symptom: "Invalid CSRF token", "Authentication failed"
- Cause: Expired or invalid ARL token
- Solution: Refresh ARL token from browser cookies

**Audio Quality Issues**:
- Symptom: Garbled, static, or corrupted audio
- Cause: Incorrect decryption algorithm
- Solution: Verify key generation and stripe decryption logic

**Download Failures**:
- Symptom: Empty files, network timeouts
- Cause: Network issues, expired URLs, rate limiting
- Solution: Check connectivity, retry with fresh tokens

### 8.2 Diagnostic Tools
**Debug Mode**: Enable via command line `--debug`
**Log Analysis**: Detailed logging in `%AppData%\DeeMusic\logs\`
**Network Inspection**: Built-in request/response logging
**Cache Inspection**: View cached images and metadata

### 8.3 Performance Optimization
**Memory Usage**:
- Streaming decryption (avoid loading entire files)
- Image cache size limits
- Periodic garbage collection

**Network Performance**:
- Connection pooling and reuse
- Concurrent download limits
- Request batching where possible

**UI Responsiveness**:
- Background thread execution
- Progressive loading of large lists
- Efficient widget updates

---

## 9. Security Considerations

### 9.1 Key Management
- **Never log complete decryption keys**
- **Hardcoded secret** (reverse-engineered constant)
- **Unique keys per track** - no reuse
- **Memory cleanup** of sensitive data

### 9.2 Network Security
- **HTTPS only** for all requests
- **ARL token protection** - treat as password
- **Session validation** and automatic refresh
- **Input sanitization** for all user data

### 9.3 File System Security
- **Temporary file cleanup** after processing
- **Safe path construction** to prevent directory traversal
- **Permissions validation** before file operations

---

## 10. Legal & Compliance

### 10.1 Copyright Considerations
- Educational use only
- User responsibility for compliance
- Respect for content creators' rights
- No circumvention of DRM systems

### 10.2 Terms of Service
Users must comply with:
- Deezer's Terms of Service
- Local copyright laws
- Fair use guidelines
- Regional restrictions

---

**Note**: This documentation is based on reverse-engineering for educational purposes. Implementation details may change as services evolve. Always ensure compliance with applicable laws and service terms. 