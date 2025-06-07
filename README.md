# 🎵 DeeMusic

A modern, feature-rich desktop application for streaming, downloading, and managing music from Deezer with an intuitive PyQt6 GUI interface, comprehensive metadata management, and advanced download capabilities.

![DeeMusic Interface](https://via.placeholder.com/800x400/1a1a1a/ffffff?text=DeeMusic+Interface)

## ✨ Features

### 🎯 Core Features
- **🎵 Deezer Integration**: Stream and download music directly from Deezer's extensive catalog
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
- **🌐 Proxy Support**: HTTP/HTTPS proxy configuration for restricted networks
- **💾 Smart Caching**: Image and metadata caching for improved performance

## 🚀 Quick Start

### Prerequisites
- **Python 3.11+** (recommended)
- **Windows 10/11** (primary support)
- **Deezer ARL Token** (see Configuration section)

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

### Deezer ARL Token
To download music, you need a valid Deezer ARL token:

1. Log into your Deezer account in a web browser
2. Open browser Developer Tools (F12)
3. Go to Application/Storage → Cookies → `https://www.deezer.com`
4. Find the `arl` cookie and copy its value
5. In DeeMusic, go to Settings → Deezer Settings and paste the ARL token

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
├── src/
│   ├── ui/                     # User Interface Components
│   │   ├── components/         # Reusable UI widgets
│   │   ├── styles/            # QSS stylesheets
│   │   ├── assets/            # Icons and images
│   │   ├── main_window.py     # Main application window
│   │   ├── home_page.py       # Home page with charts
│   │   ├── search_widget.py   # Search functionality
│   │   ├── artist_detail_page.py # Artist details view
│   │   ├── album_detail_page.py  # Album details view
│   │   └── playlist_detail_page.py # Playlist details view
│   ├── services/              # Backend Services
│   │   ├── deezer_api.py      # Deezer API integration
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
├── tests/                     # Unit and integration tests
├── docs/                      # Documentation
├── requirements.txt           # Python dependencies
├── run.py                     # Application entry point
└── README.md                  # This file
```

## 🔧 Building Executable (EXE)

You can compile DeeMusic into a standalone executable using PyInstaller:

### 1. Install PyInstaller
```bash
pip install pyinstaller
```

### 2. Basic Build
```bash
pyinstaller --onefile --windowed run.py
```

### 3. Advanced Build (Recommended)
Create a `build.py` file for a more sophisticated build:

```python
import PyInstaller.__main__
import sys
import os

# Build configuration
PyInstaller.__main__.run([
    'run.py',
    '--onefile',
    '--windowed',
    '--name=DeeMusic',
    '--icon=src/ui/assets/logo.ico',  # If you have an icon file
    '--add-data=src/ui/assets;src/ui/assets',
    '--add-data=src/ui/styles;src/ui/styles',
    '--hidden-import=PyQt6',
    '--hidden-import=qasync',
    '--hidden-import=mutagen',
    '--hidden-import=requests',
    '--hidden-import=aiohttp',
    '--collect-submodules=PyQt6',
    '--distpath=dist',
    '--workpath=build',
    '--clean',
])
```

Run the build:
```bash
python build.py
```

### 4. Build Options Explained
- `--onefile`: Creates a single executable file
- `--windowed`: Hides the console window (GUI app)
- `--name`: Sets the executable name
- `--icon`: Adds an application icon
- `--add-data`: Includes additional files (assets, styles)
- `--hidden-import`: Ensures specific modules are included
- `--collect-submodules`: Includes all PyQt6 submodules

### 5. After Building
The executable will be in the `dist/` folder. You can distribute this single file, and it will run on Windows systems without requiring Python installation.

### 6. Build Optimization
For smaller executable size:
```bash
# Install UPX for compression
# Download from: https://upx.github.io/

pyinstaller --onefile --windowed --upx-dir=path/to/upx run.py
```

## 🚦 Usage

### Basic Workflow
1. **Setup**: Configure your Deezer ARL token in Settings
2. **Discover**: Browse charts, search for music, or explore recommendations
3. **Preview**: Click any track to preview (30-second samples)
4. **Download**: Click the download button on tracks, albums, or playlists
5. **Monitor**: Track download progress in the Download Queue
6. **Enjoy**: Find your music in the configured download directory

### Keyboard Shortcuts
- `Ctrl+F`: Focus search box
- `Ctrl+D`: Open download queue
- `Ctrl+S`: Open settings
- `Space`: Play/pause current preview
- `Escape`: Stop current preview

## 🔧 Dependencies

### Core Libraries
- **PyQt6**: Modern GUI framework
- **qasync**: Asyncio integration for Qt
- **aiohttp**: Async HTTP client for API calls
- **mutagen**: Audio metadata processing
- **requests**: HTTP library for downloads

### Deezer Integration
- **py-deezer**: Official Deezer API wrapper
- **deezer-py**: Extended Deezer functionality

### Audio & Media
- **yt-dlp**: Media downloading capabilities
- **Pillow**: Image processing
- **cryptography**: Decryption support

### Development
- **pytest**: Testing framework
- **black**: Code formatting
- **mypy**: Type checking

## 🐛 Troubleshooting

### Common Issues

**"Loading timed out" errors:**
- Check your internet connection
- Verify proxy settings if behind corporate firewall
- Ensure Deezer ARL token is valid

**Downloads failing:**
- Verify ARL token is still valid (they expire)
- Check download directory permissions
- Ensure sufficient disk space

**UI not responding:**
- Close and restart the application
- Check logs in `logs/` directory
- Clear image cache in Settings

**Virtual environment issues:**
- Recreate virtual environment: `python -m venv venv_py311`
- Use direct Python path: `C:\Users\[USER]\AppData\Local\Programs\Python\Python311\python.exe run.py`

### Logging
Enable debug logging by setting environment variable:
```bash
set DEEMUSIC_DEBUG=1
python run.py
```

## 🤝 Contributing

We welcome contributions! Here's how you can help:

### Development Setup
1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass: `pytest`
6. Format code: `black src/`
7. Submit a pull request

### Code Style
- Follow PEP 8 guidelines
- Use type hints where possible
- Write docstrings for all public methods
- Add unit tests for new features

### Reporting Issues
- Use the GitHub Issues page
- Include system information (OS, Python version)
- Provide detailed reproduction steps
- Attach relevant log files

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This application is for educational purposes only. Users are responsible for complying with Deezer's Terms of Service and applicable copyright laws. The developers are not responsible for any misuse of this software.

## 🙏 Acknowledgments

- **Deezer** for their comprehensive music API
- **Qt Project** for the excellent GUI framework
- **Python Community** for the amazing ecosystem of libraries
- **Contributors** who help improve this project

## 📞 Support

- **GitHub Issues**: [Report bugs or request features](https://github.com/IAmAnonUser/DeeMusic/issues)
- **Documentation**: Check the `docs/` folder for detailed guides
- **Community**: Join discussions in the Issues section

---

<p align="center">
  <strong>🎵 Made with ❤️ for music lovers everywhere 🎵</strong>
</p>

