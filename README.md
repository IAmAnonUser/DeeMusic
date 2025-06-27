# �� DeeMusic

A modern desktop application for downloading and managing music with an intuitive interface and high-quality audio support.

![DeeMusic Interface](docs/screenshot.png)

## ✨ Features

- 🎵 **High-Quality Downloads**: Support for MP3 (320kbps) and FLAC formats
- 🎨 **Modern Interface**: Beautiful dark/light theme with responsive design
- 🔍 **Smart Search**: Find tracks, albums, artists, and playlists instantly
- 🎧 **Sp*tify Playlist Conversion**: Convert Spotify playlists to Deezer with automatic track matching
- 📊 **Music Discovery**: Browse charts and recommendations
- 📁 **Smart Organization**: Customizable folder structures and file naming
- 🖼️ **Artwork Management**: High-resolution album covers automatically embedded
- ⚡ **Fast Downloads**: Multi-threaded downloading with progress tracking

## 🚀 Quick Start

### Prerequisites
- **Windows 10/11** (recommended)
- **Python 3.11+** (if running from source)

### Option 1: Download Pre-built Executable
1. Download the latest `DeeMusic.exe` from [Releases](https://github.com/IAmAnonUser/DeeMusic/releases)
2. Run the executable
3. Configure your settings (see Configuration below)

### Option 2: Run from Source
1. **Clone and install:**
```bash
git clone https://github.com/IAmAnonUser/DeeMusic.git
cd DeeMusic
python -m venv venv_py311
.\venv_py311\Scripts\Activate.ps1  # Windows
pip install -r requirements.txt
python run.py
```

## ⚙️ Configuration

### Required Setup
1. **Get your D**zer ARL token:**
   - Log into D**zer in your web browser
   - Press F12 to open Developer Tools
   - Go to Application/Storage → Cookies → `https://www.D**zer.com`
   - Copy the value of the `arl` cookie

2. **Configure DeeMusic:**
   - Open DeeMusic
   - Go to Settings → D**zer Settings
   - Paste your ARL token
   - Choose your download quality and folder preferences

### Optional Settings
- **Download Directory**: Where files are saved
- **Audio Quality**: MP3 320kbps or FLAC
- **File Organization**: Artist/Album folder structure
- **Spotify Integration**: Convert Spotify playlists (requires Spotify API credentials)
- **Theme**: Dark or Light mode

### Spotify Playlist Conversion Setup
1. **Create a Spotify App:**
   - Visit [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
   - Create a new app (name: anything you want)
   - Copy your Client ID and Client Secret

2. **Configure DeeMusic:**
   - Go to Settings → Spotify tab
   - Enter your Client ID and Client Secret
   - Test the connection and save

3. **Convert Playlists:**
   - Paste any Spotify playlist URL into the search bar
   - DeeMusic automatically finds matching tracks on Deezer
   - Click "Download All" to download the entire converted playlist

## 🎯 How to Use

1. **Search**: Use the search bar to find music or paste Spotify playlist URLs
2. **Browse**: Explore charts and recommendations on the home page
3. **Convert**: Paste Spotify playlist URLs to automatically find Deezer matches
4. **Download**: Click the download button on any track, album, or playlist
5. **Monitor**: Watch progress in the Download Queue
6. **Enjoy**: Your music is organized in your chosen download folder

## 🏗️ Building

Want to build your own executable?

```bash
python tools/build.py
```

This creates `dist/DeeMusic.exe` with all dependencies included.

## 📋 System Requirements

- **OS**: Windows 10/11 (primary), Windows 7+ (limited support)
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 100MB for application + space for your music library
- **Network**: Internet connection required

## 🐛 Troubleshooting

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

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/IAmAnonUser/DeeMusic/issues)
- **Feature Requests**: Use GitHub Issues with the "enhancement" label

## ⚠️ Legal Notice

This application is for educational purposes only. Users must comply with:
- D**zer's Terms of Service
- Local copyright laws
- Fair use guidelines

The developers are not responsible for any misuse of this software.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


