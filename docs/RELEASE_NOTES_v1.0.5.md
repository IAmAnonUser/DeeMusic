# DeeMusic v1.0.5 Release Notes

**Release Date:** January 12, 2025  
**Version:** 1.0.5  
**Build:** Stable Release

## 🎉 What's New in v1.0.5

### 🔧 Critical Bug Fixes
- **Fixed Application Crashes**: Resolved critical crashes when switching between artists in artist detail pages
- **Layout Management**: Fixed "wrapped C/C++ object has been deleted" RuntimeError that occurred during UI navigation
- **Widget Lifecycle**: Improved widget lifecycle management to prevent accessing deleted Qt objects

### 🚀 Performance Improvements
- **Non-blocking Downloads**: Downloads now run completely in the background without freezing the user interface
- **Responsive UI**: Users can now search, browse, and queue multiple downloads simultaneously
- **Optimized API Calls**: Eliminated synchronous API calls that were blocking the main UI thread

### 🔄 New Features
- **Sortable Search Results**: Added clickable column headers to search results track lists
  - Sort by track name, artist, album, or duration
  - Visual sort indicators show current sort direction
  - Works in both "All" view and dedicated "Tracks" filter view
- **Album Sorting**: Added sorting functionality to Albums, Singles, EPs, and Featured In tabs
  - Sort albums by title, release date, or track count
  - Consistent sorting UI across all album grid displays

### 🎯 UI/UX Enhancements
- **Better Track Headers**: Fixed track list header alignment and padding issues
- **Improved Spacing**: Enhanced header padding and spacing for better readability
- **Consistent Design**: Unified sorting behavior across all track list views

## 📦 Distribution Files

### Standalone Executable
- **File:** `DeeMusic.exe` (83.1 MB)
- **Location:** `tools/dist/DeeMusic.exe`
- **Requirements:** Windows 7+ (64-bit), no additional dependencies

### Installer Package
- **File:** `DeeMusic_Installer_v1.0.5.zip` (82.7 MB)
- **Location:** `tools/DeeMusic_Installer_v1.0.5.zip`
- **Features:**
  - Multiple installation options (Program Files, Portable, Current Directory)
  - Automatic Start Menu and Desktop shortcuts
  - Proper uninstaller included
  - User-friendly installation wizard

## 🛠️ Technical Details

### Architecture Improvements
- Enhanced `_safe_sip_is_deleted()` method with better Qt object validation
- Improved widget deletion handling in `_init_tab_content_widgets()` to prevent premature cleanup
- Added defensive layout clearing with proper object lifecycle checks
- Replaced static search headers with interactive `TrackListHeaderWidget`

### Code Quality
- Better error handling for layout operations
- Improved memory management for Qt widgets
- Enhanced debugging and logging for troubleshooting

## 🔄 Upgrade Notes

### From v1.0.4
- **Automatic:** Simply replace the executable or run the new installer
- **Settings:** All existing settings and configurations will be preserved
- **Compatibility:** Fully backward compatible with existing user data

### From Earlier Versions
- **Fresh Install Recommended:** For versions prior to v1.0.4, a fresh installation is recommended
- **Settings Migration:** Manual reconfiguration may be required for optimal performance

## 🎯 Known Issues

### Minor Issues
- Layout cleanup warnings may appear in logs when switching artists (cosmetic only, no functional impact)
- Some Qt dependency warnings during build (does not affect functionality)

### Workarounds
- All known issues have been addressed or have minimal impact on user experience
- Report any new issues on GitHub for community support

## 📋 System Requirements

### Minimum Requirements
- **OS:** Windows 7 SP1 (64-bit) or later
- **RAM:** 2 GB (4 GB recommended)
- **Storage:** 200 MB free space
- **Network:** Internet connection for streaming and downloads

### Recommended Requirements
- **OS:** Windows 10/11 (64-bit)
- **RAM:** 4 GB or more
- **Storage:** 1 GB free space for downloads
- **Network:** Broadband internet connection

## 📖 Installation Instructions

### Option 1: Installer Package (Recommended)
1. Download `DeeMusic_Installer_v1.0.5.zip`
2. Extract the ZIP file
3. Run `install.bat` and follow the wizard
4. Choose installation type (Program Files recommended)
5. Launch DeeMusic from Start Menu or Desktop

### Option 2: Portable Executable
1. Download `DeeMusic.exe` from `tools/dist/`
2. Place in desired folder
3. Run directly (no installation required)
4. Settings stored in `%AppData%\DeeMusic`

## 🔗 Links

- **GitHub Repository:** https://github.com/IAmAnonUser/DeeMusic
- **Issue Tracker:** https://github.com/IAmAnonUser/DeeMusic/issues
- **Documentation:** See `docs/` folder for detailed documentation

## 🙏 Acknowledgments

Thanks to the community for bug reports and feedback that helped improve this release.

---

**Happy Listening with DeeMusic v1.0.5! 🎵** 