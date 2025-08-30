# DeeMusic Build Tools

This directory contains the essential build scripts for creating DeeMusic executables and installers.

## Build Scripts

### Standalone Executable
- **`build_standalone.py`** - Creates a completely self-contained executable with ZERO dependencies
- **`build_standalone.bat`** - Easy Windows batch file to build standalone executable

### Installer Creation
- **`create_inno_installer.py`** - Creates a professional Windows installer using Inno Setup
- **`installer.iss`** - Inno Setup configuration file

### Utilities
- **`fix_spotipy_build.bat`** - Quick fix for spotipy dependency issues (uses standalone build)
- **`STANDALONE_FIX_GUIDE.md`** - Comprehensive guide for standalone builds and troubleshooting

## Quick Start

### Build Standalone Executable
```bash
# From project root
python tools/build_standalone.py

# Or from tools directory
cd tools
python build_standalone.py

# Or use batch file (Windows)
cd tools
build_standalone.bat
```

### Create Professional Installer
```bash
# From project root (after building executable)
python tools/create_inno_installer.py
```

## What You Get

### Standalone Executable (`build_standalone.py`)
- **Single file**: DeeMusic.exe (~80-120MB)
- **Zero dependencies**: No Python, pip packages, or external libraries needed
- **Universal compatibility**: Runs on any Windows 10/11 system
- **Complete functionality**: All features including Spotify integration
- **Portable**: Can run from USB drive or any location

### Professional Installer (`create_inno_installer.py`)
- **Windows installer**: DeeMusic_Setup_v1.0.0.exe
- **Start menu shortcuts**: Automatically created
- **Uninstaller**: Proper Windows uninstall support
- **Registry integration**: File associations and program registration

## Requirements

- Python 3.11+
- PyInstaller (`pip install pyinstaller`)
- All project dependencies (`pip install -r requirements.txt`)
- Inno Setup (for installer) - Download from https://jrsoftware.org/isinfo.php

## Output Locations

- **Standalone executable**: `dist/DeeMusic.exe`
- **Installer**: `DeeMusic_Setup_v1.0.0.exe` (project root)
- **Build logs**: Displayed in console

## Deployment

### For End Users (Standalone)
1. Build: `python tools/build_standalone.py`
2. Distribute: Single `DeeMusic.exe` file
3. Usage: Double-click to run - no installation needed

### For Distribution (Installer)
1. Build executable: `python tools/build_standalone.py`
2. Create installer: `python tools/create_inno_installer.py`
3. Distribute: `DeeMusic_Setup_v1.0.0.exe`
4. Users run installer for traditional Windows installation

## Key Features

✅ **Zero Dependencies**: No Python installation required on target computers  
✅ **Single File Distribution**: Just DeeMusic.exe for portable use  
✅ **Professional Installer**: Traditional Windows installation experience  
✅ **Complete Functionality**: All features work without external libraries  
✅ **Universal Compatibility**: Works on clean Windows systems  

## Troubleshooting

### Build Issues
1. Ensure all dependencies installed: `pip install -r requirements.txt`
2. Update PyInstaller: `pip install --upgrade pyinstaller`
3. Check Python version: Requires Python 3.11+

### Runtime Issues
- **Antivirus warnings**: Add DeeMusic.exe to exclusions
- **Slow startup**: Normal for first run (Windows scanning)
- **Missing features**: Rebuild with `build_standalone.py`

The standalone build ensures your application works on any Windows computer without requiring users to install Python or any additional packages. 