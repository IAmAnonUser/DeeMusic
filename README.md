# 🎵 DeeMusic

A modern, feature-rich desktop application for streaming, downloading, and managing music from D**zer with an intuitive PyQt6 GUI interface, comprehensive metadata management, and advanced download capabilities.

## ✨ Features

### 🎯 Core Features
- **🎵 D**zer Integration**: Stream and download music directly from D**zer's extensive catalog
- **🎨 Modern GUI**: Beautiful, responsive PyQt6 interface with dark/light theme support
- **⬇️ Advanced Downloads**: Multi-threaded downloading with queue management
- **🔍 Smart Search**: Search tracks, albums, artists, and playlists with real-time results
- **📊 Music Discovery**: Browse charts, featured playlists, and personalized recommendations

### 🎛️ Audio & Quality
- **🎧 High-Quality Audio**: Support for MP3 (320kbps) and FLAC formats
- **🎼 Rich Metadata**: Automatic tagging with artist, album, genre, release date, and more
- **🖼️ Artwork Management**: High-resolution album covers and artist images
- **📝 Lyrics Support**: Synchronized and static lyrics display

### 🗂️ Organization & Management
- **📁 Smart Organization**: Customizable folder structures and file naming
- **📚 Library Management**: Local music library with sync capabilities
- **🎵 Playlist Management**: Create, edit, and download complete playlists
- **🏷️ Tag Editor**: Advanced metadata editing and batch operations

### 🌐 Network & Performance
- **🚀 Concurrent Downloads**: Multiple simultaneous downloads with progress tracking
- **🔄 Resume Support**: Pause and resume downloads seamlessly
- **💾 Smart Caching**: Image and metadata caching for improved performance

## 🚀 Quick Start

### Prerequisites
- **Python 3.11+** (recommended)
- **Windows 10/11** (primary support)
- **D**zer ARL Token** (see Configuration section)

### Installation

1. **Clone the repository:**
```bash
git clone https://github.com/IAmAnonUser/DeeMusic.git
cd DeeMusic
```

2. **Create and activate a virtual environment:**
```bash
# Create virtual environment
python -m venv venv_py311

# Activate virtual environment
# Windows:
.\venv_py311\Scripts\Activate.ps1
# Or for Command Prompt:
.\venv_py311\Scripts\activate.bat

# Linux/macOS:
source venv_py311/bin/activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

4. **Run the application:**
```bash
python run.py
```

## ⚙️ Configuration

### D**zer ARL Token
To download music, you need a valid D**zer ARL token:

1. Log into your D**zer account in a web browser
2. Open browser Developer Tools (F12)
3. Go to Application/Storage → Cookies → `https://www.D**zer.com`
4. Find the `arl` cookie and copy its value
5. In DeeMusic, go to Settings → D**zer Settings and paste the ARL token

### Settings Overview
- **Download Quality**: Choose between MP3 320kbps and FLAC
- **Download Directory**: Set custom download location
- **File Organization**: Configure folder structure and naming patterns
- **Network Settings**: Proxy configuration and connection timeouts
- **UI Theme**: Dark/Light theme selection

<<<<<<< HEAD
## 🏗️ Project Structure

```
DeeMusic/
├── src/                       # Source Code
│   ├── ui/                     # User Interface Components
│   │   ├── components/         # Reusable UI widgets
│   │   ├── styles/            # QSS stylesheets
│   │   ├── assets/            # Icons, images, and logo
│   │   ├── main_window.py     # Main application window
│   │   ├── home_page.py       # Home page with charts
│   │   ├── search_widget.py   # Search functionality
│   │   ├── artist_detail_page.py # Artist details view
│   │   ├── album_detail_page.py  # Album details view
│   │   └── playlist_detail_page.py # Playlist details view
│   ├── services/              # Backend Services
│   │   ├── D**zer_api.py      # D**zer API integration
│   │   ├── download_manager.py # Download orchestration
│   │   ├── music_player.py    # Audio playback
│   │   ├── library_manager.py # Local library management
│   │   └── queue_manager.py   # Download queue management
│   ├── utils/                 # Utility Functions
│   │   ├── image_cache.py     # Image caching system
│   │   ├── helpers.py         # General helpers
│   │   └── lyrics_utils.py    # Lyrics processing
│   ├── models/                # Data Models
│   │   └── database.py        # Database schema
│   └── config_manager.py      # Configuration management
├── tools/                     # Build Scripts & Tools
│   ├── build.py               # Main executable builder (PyInstaller)
│   ├── create_simple_installer.py # Windows installer creator
│   ├── build_installer.py     # Professional Inno Setup builder
│   ├── installer.iss          # Inno Setup script
│   └── README.md              # Build tools documentation
├── docs/                      # Documentation & Release Notes
├── dist/                      # Built executables (generated)
├── build/                     # Build artifacts (generated)
├── venv_py311/               # Python virtual environment
├── requirements.txt           # Python dependencies
├── run.py                     # Application entry point
└── README.md                  # This file
```

## 🔧 Building & Distribution

### 📦 Quick Build
Build a standalone Windows executable with custom icon:

```bash
# Build executable only
python tools/build.py

# Build + create installer package  
python tools/build.py
python tools/create_simple_installer.py
```

**Output:**
- `dist/DeeMusic.exe` - Standalone executable with custom icon
- `DeeMusic_Installer_v1.0.0.zip` - Installer package for distribution

### 🛠️ Build Tools Overview

| Tool | Purpose | Output | Requirements |
|------|---------|--------|-------------|
| `tools/build.py` | Main executable builder | `dist/DeeMusic.exe` | PyInstaller |
| `tools/create_simple_installer.py` | Windows installer package | `.zip` installer | None |
| `tools/build_installer.py` | Professional installer | `.exe` installer (~82MB) | Inno Setup |

### 🚀 Professional Installer (Optional)
For enterprise distribution with registry integration:

1. **Install Inno Setup:** Download from [jrsoftware.org](https://jrsoftware.org/isdl.php)
2. **Build:** `python tools/build_installer.py`
3. **Output:** Professional `.exe` installer with wizard interface

### 📋 Build Features
- **Custom Icon**: Professional DeeMusic branding throughout Windows
- **Optimized Size**: Standalone executable (includes all dependencies)
- **Multiple Install Options**: Program Files, portable, current directory
- **Start Menu Integration**: Shortcuts and file associations
- **Professional Uninstaller**: Clean removal with settings cleanup option
- **Settings Preservation**: Configurations stored in `%AppData%\DeeMusic`

### 🔧 Build Configuration
Customize builds by editing `tools/build.py`:
- Icon file path and build optimizations
- Excluded modules and hidden imports  
- Output directory and file naming

For detailed build instructions, see `tools/README.md`.

## 🚦 Usage

### Basic Workflow
1. **Setup**: Configure your D**zer ARL token in Settings
2. **Discover**: Browse charts, search for music, or explore recommendations
3. **Download**: Click the download button on tracks, albums, or playlists
4. **Monitor**: Track download progress in the Download Queue
5. **Enjoy**: Find your music in the configured download directory

### Development Setup
1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass: `pytest`
6. Format code: `black src/`
7. Submit a pull request

### Reporting Issues
- Use the GitHub Issues page
- Include system information (OS, Python version)
- Provide detailed reproduction steps
- Attach relevant log files

## ⚠️ Disclaimer

This application is for educational purposes only. Users are responsible for complying with D**zer's Terms of Service and applicable copyright laws. The developers are not responsible for any misuse of this software.


