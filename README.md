# DeeMusic

A modern desktop application for downloading and managing music with an intuitive interface and high-quality audio support.

## Features

- **High-Quality Downloads**: Support for MP3 (320kbps) and FLAC formats
- **Modern Interface**: Beautiful dark/light theme with responsive design
- **Smart Search**: Find tracks, albums, artists, and playlists instantly
- **Spotify Playlist Conversion**: Convert Spotify playlists to Deezer with automatic track matching
- **Library Scanner**: Analyze your music library and find missing albums from Deezer
- **Music Discovery**: Browse charts and recommendations
- **Smart Organization**: Customizable folder structures and file naming
- **Artwork Management**: High-resolution album covers automatically embedded
- **Fast Downloads**: Multi-threaded downloading with progress tracking
- **Cross-Session Continuity**: Previous scans and comparisons load automatically

## What's New in v1.0.6

### Major Track Number Fix
- **Fixed Critical Issue**: All album tracks now show correct sequential numbers (01, 02, 03, etc.) instead of all showing "01"
- **Complete Solution**: Resolved API field mapping and download logic issues
- **Better Organization**: Albums now have properly numbered tracks for clean library organization

### Enhanced Queue Management
- **New "Clear Pending" Button**: Dedicated button to clear stuck downloads from previous sessions
- **Smart Detection**: Improved album completion detection prevents phantom downloads
- **Better UI Sync**: Queue state properly synchronized between UI and storage

### Technical Improvements
- **API Processing**: Enhanced Deezer API integration with correct field mappings
- **Type Safety**: Added proper integer conversion for numeric fields
- **Error Handling**: Better exception handling and recovery for queue operations
- **Debug Logging**: Enhanced logging for troubleshooting download issues

See [CHANGELOG.md](docs/CHANGELOG.md) for complete release notes and [RELEASE_NOTES_v1.0.6.md](docs/RELEASE_NOTES_v1.0.6.md) for detailed information.

## Quick Start

### Prerequisites
- Windows 10/11 (recommended)
- Python 3.11+ (if running from source)

### Option 1: Download Pre-built Executable
1. Download the latest `DeeMusic.exe` from releases
2. Run the executable
3. Configure your settings (see Configuration below)

### Option 2: Run from Source
1. Clone and install:
```bash
git clone https://github.com/IAmAnonUser/DeeMusic.git
cd DeeMusic
python -m venv venv_py311
.\venv_py311\Scripts\Activate.ps1  # Windows
pip install -r requirements.txt
python run.py
```

## Configuration

### Required Setup
1. Get your Deezer ARL token:
   - Log into Deezer in your web browser
   - Press F12 to open Developer Tools
   - Go to Application/Storage → Cookies → `https://www.deezer.com`
   - Copy the value of the `arl` cookie

2. Configure DeeMusic:
   - Open DeeMusic
   - Go to Settings → Deezer Settings
   - Paste your ARL token
   - Choose your download quality and folder preferences

### Optional Settings
- **Download Directory**: Where files are saved
- **Audio Quality**: MP3 320kbps or FLAC
- **File Organization**: Artist/Album folder structure
- **Spotify Integration**: Convert Spotify playlists (requires Spotify API credentials)
- **Theme**: Dark or Light mode

### Spotify Playlist Conversion Setup
1. Create a Spotify App:
   - Visit Spotify Developer Dashboard
   - Create a new app (name: anything you want)
   - Copy your Client ID and Client Secret

2. Configure DeeMusic:
   - Go to Settings → Spotify tab
   - Enter your Client ID and Client Secret
   - Test the connection and save

3. Convert Playlists:
   - Paste any Spotify playlist URL into the search bar
   - DeeMusic automatically finds matching tracks on Deezer
   - Click "Download All" to download the entire converted playlist

## How to Use

### Basic Usage
1. **Search**: Use the search bar to find music or paste Spotify playlist URLs
2. **Browse**: Explore charts and recommendations on the home page
3. **Convert**: Paste Spotify playlist URLs to automatically find Deezer matches
4. **Download**: Click the download button on any track, album, or playlist
5. **Monitor**: Watch progress in the Download Queue
6. **Enjoy**: Your music is organized in your chosen download folder

### Library Scanner
Analyze your existing music library and find missing albums:

1. **Access**: Click the "Library Scanner" button in the top bar
2. **Automatic Loading**: Previous scan and comparison results load automatically
3. **Browse Results**: 
   - Left panel: Artists with missing albums
   - Right panel: Missing albums for selected artist
4. **Select Albums**: Use checkboxes to choose albums to download
5. **Import**: Click "Import Selected to DeeMusic" to add to download queue
6. **Navigate Back**: Use "Back to DeeMusic" to return to main interface

Key Features:
- **Cross-Session Continuity**: Your scan and comparison results are saved and loaded automatically
- **Smart Analysis**: Compares your local library with Deezer's catalog
- **Easy Selection**: Hierarchical view with checkboxes for easy album selection
- **Seamless Integration**: Import missing albums directly to DeeMusic's download queue

## Building

Want to build your own executable?

```bash
python tools/build.py
```

This creates `dist/DeeMusic.exe` with all dependencies included.

## System Requirements

- **OS**: Windows 10/11 (primary), Windows 7+ (limited support)
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 100MB for application + space for your music library
- **Network**: Internet connection required

## Troubleshooting

**Can't download music?**
- Check your ARL token is valid and not expired
- Verify your internet connection
- Make sure the track is available in your region

**Application won't start?**
- Run as administrator if needed
- Check Windows Defender hasn't blocked the file
- Ensure .NET Framework is installed

**Downloads are slow?**
- Check your internet speed
- Try reducing concurrent downloads in settings
- Consider using a VPN if regional restrictions apply

## Support

- **Issues**: GitHub Issues
- **Feature Requests**: Use GitHub Issues with the "enhancement" label

## Legal Notice

This application is for educational purposes only. Users must comply with:
- Deezer's Terms of Service
- Local copyright laws
- Fair use guidelines

The developers are not responsible for any misuse of this software.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


