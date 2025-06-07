# 🎵 DeeMusic v1.0.0 - Professional Windows Release

A modern, feature-rich desktop application for streaming, downloading, and managing music from Deezer with an intuitive PyQt6 GUI interface.

## ✨ What's New in v1.0.0

### 🚀 Core Features
- **Complete standalone Windows executable** (84.1 MB) 
- **Custom professional icon** throughout Windows integration
- **Fixed artist loading** - No longer requires ARL tokens for basic artist information
- **Modern PyQt6 interface** with comprehensive music management
- **Advanced download capabilities** with metadata management

### 📦 Professional Windows Installer
- **Multiple installation options**: Program Files, portable, current directory
- **Start Menu shortcuts** and optional desktop shortcuts  
- **File associations** for music files (.mp3, .flac, .m4a)
- **Professional uninstaller** with settings cleanup option
- **Guided installation wizard** with user-friendly interface

### 🛠️ Technical Improvements
- Fixed critical Deezer API authentication issues for artist loading
- Optimized executable build process with PyInstaller
- Enhanced error handling and user experience
- Settings stored in `%AppData%\DeeMusic`
- Proper Windows integration with custom branding

## 📥 Download Options

### 🎯 For End Users (Recommended)
**Download:** `DeeMusic_Installer_v1.0.0.zip` - Complete installer package with guided setup

### 🔧 For Advanced Users
**Download:** `DeeMusic.exe` - Standalone executable (requires manual setup)

## 🚀 Installation Instructions

### Using the Installer (Recommended):
1. Download `DeeMusic_Installer_v1.0.0.zip`
2. Extract the ZIP file anywhere on your computer
3. Run `install.bat` to start the installation wizard
4. Choose your preferred installation type:
   - **Program Files** (recommended) - Full Windows integration
   - **Current Directory** - Install where extracted
   - **Portable** - No shortcuts, run from anywhere
5. Follow the prompts for shortcuts and file associations
6. Launch DeeMusic from Start Menu or desktop shortcut

### Manual Installation:
1. Download `DeeMusic.exe`
2. Place it in your desired folder
3. Run `DeeMusic.exe` directly
4. Settings will be stored in `%AppData%\DeeMusic`

## 💡 System Requirements
- **OS:** Windows 7 or later (64-bit)
- **RAM:** 4 GB recommended
- **Storage:** 100 MB free disk space
- **Network:** Internet connection for music streaming and downloads
- **Optional:** Deezer ARL token for downloading (streaming works without)

## 🎯 Key Features

### Music Management
- Browse and search Deezer's music catalog
- Stream tracks directly in the application
- Download high-quality music files (with ARL)
- Comprehensive metadata management
- Artist, album, and playlist browsing

### User Interface
- Modern PyQt6 interface with dark/light themes
- Intuitive navigation and controls
- Real-time download progress tracking
- Queue management system
- Responsive design

### Download System
- Multiple audio formats support (.mp3, .flac, .m4a)
- Batch downloading capabilities
- Automatic metadata embedding
- Custom download locations
- Resume interrupted downloads

## 🔧 First-Time Setup

1. **Launch DeeMusic** after installation
2. **Browse music** - No account required for streaming
3. **For downloads** (optional):
   - Go to Settings → Deezer ARL
   - Add your Deezer ARL token
   - Configure download preferences
4. **Enjoy your music!**

## 🛠️ Development Information

### Built With
- **Python 3.11** - Core application
- **PyQt6** - Modern GUI framework
- **PyInstaller** - Executable packaging
- **Inno Setup** - Professional installer creation

### For Developers
- **Repository:** https://github.com/IAmAnonUser/DeeMusic
- **Build:** `python build.py` 
- **Create Installer:** `python create_simple_installer.py`
- **Requirements:** See `requirements.txt`

## 🐛 Known Issues
- None currently reported
- Report issues on the [GitHub Issues page](https://github.com/IAmAnonUser/DeeMusic/issues)

## 📞 Support
- **Issues:** https://github.com/IAmAnonUser/DeeMusic/issues
- **Documentation:** Check README.md in repository
- **Community:** GitHub Discussions

## 📄 License
This project is licensed under the MIT License - see the LICENSE file for details.

---

**Full Changelog**: Initial release v1.0.0

### File Checksums (for verification)
- `DeeMusic_Installer_v1.0.0.zip`: 79.7 MB
- `DeeMusic.exe`: 84.1 MB

**Release Date:** June 7, 2025  
**Built with:** PyInstaller 6.14.0, Python 3.11.0 