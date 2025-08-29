# DeeMusic Project Structure & Organization

## Root Directory Layout

```
DeeMusic/
├── src/                           # Source code (main application)
├── tools/                         # Build and distribution scripts
├── docs/                          # Comprehensive documentation
├── .kiro/                         # Kiro AI assistant configuration
├── requirements.txt               # Python dependencies
├── run.py                         # Application entry point
├── BuildTool.bat                  # Quick build script
└── README.md                      # Project overview
```

## Source Code Organization (`src/`)

### Core Architecture Layers

```
src/
├── ui/                            # User Interface Layer
│   ├── components/                # Reusable UI widgets
│   │   ├── search_result_card.py  # Music item display cards
│   │   ├── toggle_switch.py       # Custom theme toggle
│   │   └── progress_card.py       # Download progress display
│   ├── styles/                    # QSS theme stylesheets
│   │   ├── main.qss              # Base styles
│   │   ├── dark.qss              # Dark theme
│   │   └── light.qss             # Light theme
│   ├── assets/                    # Static resources
│   │   ├── logo.ico              # Application icon
│   │   └── icons/                # UI icons
│   ├── main_window.py            # Primary application window
│   ├── home_page.py              # Dashboard/charts page
│   ├── search_widget.py          # Search functionality
│   ├── artist_detail_page.py     # Artist information display
│   ├── album_detail_page.py      # Album track listings
│   ├── playlist_detail_page.py   # Playlist contents
│   ├── download_queue_widget.py  # Download monitoring
│   ├── settings_dialog.py        # Application preferences
│   ├── library_scanner_widget_*.py # Library analysis UI
│   └── theme_manager.py          # Theme switching logic
├── services/                      # Business Logic Layer
│   ├── deezer_api.py             # Deezer API integration
│   ├── spotify_api.py            # Spotify API integration
│   ├── download_manager.py       # Download orchestration
│   ├── playlist_converter.py     # Spotify→Deezer conversion
│   ├── queue_manager.py          # Download queue management
│   ├── library_manager.py        # Local library operations
│   └── music_player.py           # Audio playback (future)
├── library_scanner/               # Library Analysis System
│   ├── core/                     # Core scanning algorithms
│   ├── services/                 # Deezer comparison services
│   ├── ui/                       # Scanner-specific UI components
│   └── utils/                    # Scanner utility functions
├── utils/                         # Utility Functions
│   ├── image_cache.py            # Image caching system
│   ├── helpers.py                # General helper functions
│   ├── icon_utils.py             # Icon loading utilities
│   ├── lyrics_utils.py           # Lyrics processing
│   └── startup_optimizer.py      # Performance optimizations
├── models/                        # Data Models
│   └── database.py               # Database schema
└── config_manager.py             # Configuration management
```

## Build System (`tools/`)

```
tools/
├── build.py                      # Standard PyInstaller build
├── build_optimized.py           # Performance-optimized build
├── create_simple_installer.py   # ZIP package creator
├── build_installer.py           # Professional installer
├── installer.iss                # Inno Setup configuration
└── README.md                    # Build system documentation
```

## Documentation (`docs/`)

```
docs/
├── AI_PROJECT_GUIDE.md          # Comprehensive AI assistant guide
├── TECHNICAL_DOCUMENTATION.md   # Complete technical reference
├── PERFORMANCE_OPTIMIZATION_GUIDE.md # Performance tuning
├── DOWNLOAD_SYSTEM_DOCUMENTATION.md # Encryption & download details
├── LIBRARY_SCANNER_*.md         # Library analysis documentation
├── SPOTIFY_PLAYLIST_CONVERSION.md # Playlist conversion guide
└── CHANGELOG.md                 # Version history
```

## Configuration & Data Storage

### Application Data Locations
```
%AppData%\DeeMusic\              # Windows user data directory
├── settings.json                # Main configuration file
├── download_queue_state.json    # Persistent download queue
├── scan_results.json           # Library scan cache
├── fast_comparison_results.json # Deezer comparison cache
├── folder_mtimes.json          # Folder modification tracking
└── logs\                       # Application log files
    └── deemusic.log            # Main log file
```

### Cache Directories
```
%USERPROFILE%\.cache\deemusic\   # User cache directory
└── image_cache\                 # Album artwork cache
    ├── *.jpg                   # Cached album covers
    └── *.png                   # Cached artist images
```

## Key Architectural Patterns

### Layer Separation
- **UI Layer**: PyQt6 widgets, QSS styling, user interactions
- **Service Layer**: Business logic, API integrations, data processing
- **Data Layer**: Configuration management, caching, persistence

### Communication Patterns
- **Signals/Slots**: Qt-based event system for thread-safe communication
- **Async/Await**: Modern Python concurrency for non-blocking operations
- **Configuration Events**: Centralized settings with change notifications

### File Naming Conventions
- **UI Components**: `*_widget.py`, `*_page.py`, `*_dialog.py`
- **Services**: `*_manager.py`, `*_api.py`, `*_converter.py`
- **Utilities**: `*_utils.py`, `*_helpers.py`, `*_cache.py`

## Module Dependencies

### Core Dependencies Flow
```
run.py → main_window.py → services/ → utils/
   ↓         ↓              ↓         ↓
config_manager.py ← All modules depend on configuration
```

### Import Hierarchy
1. **Standard Library**: Built-in Python modules
2. **Third-Party**: PyQt6, aiohttp, mutagen, etc.
3. **Local Modules**: Relative imports within src/

## Development Workflow

### Adding New Features
1. **UI Components**: Add to `src/ui/` with appropriate naming
2. **Business Logic**: Implement in `src/services/`
3. **Configuration**: Extend `config_manager.py` if needed
4. **Documentation**: Update relevant docs/ files

### File Organization Rules
- **Single Responsibility**: Each file has one primary purpose
- **Logical Grouping**: Related functionality in same directory
- **Clear Naming**: Descriptive filenames indicating purpose
- **Consistent Structure**: Similar files follow same internal organization

## Integration Points

### Library Scanner Integration
- **UI Integration**: Seamless navigation from main window
- **Data Sharing**: Shared configuration and cache systems
- **Theme Consistency**: Uses same styling system as main app

### External Service Integration
- **API Services**: Centralized in `src/services/`
- **Authentication**: Managed through configuration system
- **Error Handling**: Consistent patterns across all integrations

This structure supports maintainable, scalable development while keeping related functionality organized and easily discoverable.