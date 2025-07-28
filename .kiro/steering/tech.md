# DeeMusic Technical Stack & Build System

## Core Technologies

### Framework & UI
- **Python 3.11+**: Primary development language
- **PyQt6**: GUI framework for cross-platform desktop application
- **qasync**: Async/await integration with Qt event loop
- **QSS Stylesheets**: Custom styling for dark/light themes

### Key Libraries
- **aiohttp**: Async HTTP client for API requests
- **mutagen**: Audio metadata manipulation (ID3, FLAC tags)
- **pycryptodome**: Blowfish CBC encryption for audio decryption
- **spotipy**: Spotify Web API integration
- **pathvalidate**: Safe file path handling
- **fuzzywuzzy**: Fuzzy string matching for track comparison

### Architecture Pattern
- **MVC-like separation**: UI layer, Service layer, Data layer
- **Signal/Slot communication**: Qt-based event system for thread-safe UI updates
- **Async/await**: Modern Python concurrency for non-blocking operations
- **Thread pool execution**: Background processing for downloads and API calls

## Project Structure

```
src/
├── ui/                    # User Interface Layer
│   ├── components/        # Reusable widgets
│   ├── styles/           # QSS theme files
│   ├── assets/           # Icons, images
│   └── *.py             # Page components
├── services/             # Business Logic Layer
│   ├── deezer_api.py    # API integration
│   ├── download_manager.py # Download orchestration
│   └── *.py             # Service modules
├── utils/               # Utility functions
├── library_scanner/     # Library analysis system
│   ├── core/           # Scanning algorithms
│   ├── services/       # Deezer comparison services
│   ├── ui/             # Scanner UI components
│   └── utils/          # Scanner utilities
└── config_manager.py    # Configuration management
```

## Build System

### Development Environment
```bash
# Setup
python -m venv venv_py311
.\venv_py311\Scripts\Activate.ps1  # Windows
pip install -r requirements.txt
python run.py
```

### Build Tools
- **PyInstaller**: Creates standalone executables
- **Inno Setup**: Professional Windows installer (optional)
- **Custom build scripts**: Located in `tools/` directory

### Common Build Commands
```bash
# Standard build
python tools/build.py

# Optimized build (recommended)
python tools/build_optimized.py

# Create installer package
python tools/create_simple_installer.py

# Professional installer (requires Inno Setup)
python tools/build_installer.py

# Quick build using batch file
BuildTool.bat
```

### Build Outputs
- `dist/DeeMusic.exe`: Standalone executable (~46-90MB)
- `DeeMusic_Installer_v1.0.0.zip`: Distribution package
- `DeeMusic_Setup_v1.0.0.exe`: Professional installer

## Configuration System

### Settings Storage
- **Location**: `%AppData%\DeeMusic\settings.json` (Windows)
- **Format**: Hierarchical JSON structure
- **Access Pattern**: Dot notation (e.g., `downloads.quality`)

### Key Configuration Areas
```json
{
  "deezer": { "arl": "..." },
  "downloads": {
    "quality": "MP3_320",
    "concurrent_downloads": 3,
    "folder_structure": { ... }
  },
  "appearance": { "theme": "dark" },
  "performance": { "memory_cache_size_mb": 30 },
  "library_scanner": {
    "library_paths": ["C:\\Music\\", "D:\\Audio\\"],
    "comparison_thresholds": { ... }
  }
}
```

### Library Scanner Data Files
- **scan_results.json**: Clean track metadata from library scans
- **fast_comparison_results.json**: Deezer comparison results
- **folder_mtimes.json**: Folder modification time tracking

## Critical Technical Requirements

### Encryption System
- **Blowfish CBC**: Audio decryption using hardcoded Deezer secret
- **Stripe decryption**: 6144-byte segments (encrypted + plain chunks)
- **Key generation**: MD5 hash + XOR algorithm (implementation must be exact)

### Thread Safety
- **UI updates**: Must use Qt signals/slots from worker threads
- **Configuration access**: Thread-safe getter/setter methods
- **Download operations**: Background thread execution with progress signals

### Performance Considerations
- **Startup optimization**: Automatic Python interpreter tuning
- **Memory management**: Garbage collection optimization
- **Image caching**: LRU cache with size limits
- **Async operations**: Non-blocking UI with proper error handling

### Library Scanner Architecture (v1.0.6)
- **Data Integrity**: Uses clean metadata directly from scan_results.json
- **Smart Processing**: Intelligent detection of data format to avoid re-processing
- **Path Filtering**: Automatic rejection of folder names as artist names
- **Comparison Engine**: Enhanced fuzzy matching with Deezer's catalog
- **Thread Safety**: Multi-threaded scanning with Qt signal/slot communication

## Development Standards

### Code Style
- **Formatter**: Black with 100-character line length
- **Type hints**: MyPy static type checking
- **Import order**: Standard → Third-party → Local
- **Error handling**: Comprehensive exception handling with logging

### Testing Approach
- **Unit tests**: Core business logic (pytest)
- **Integration tests**: API interactions
- **UI tests**: QtTest framework for widget testing

### Logging Configuration
- **Levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Location**: `%AppData%\DeeMusic\logs\deemusic.log`
- **Format**: Timestamp, level, module, message