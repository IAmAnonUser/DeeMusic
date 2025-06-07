# 🛠️ DeeMusic Build Tools

This directory contains all the build scripts and tools needed to create DeeMusic executables and installers.

## 📁 Files Overview

### Core Build Scripts

#### `build.py`
**Purpose:** Main executable builder using PyInstaller  
**Usage:** `python tools/build.py`  
**Output:** `dist/DeeMusic.exe` (standalone Windows executable)  
**Features:**
- Builds 64-bit Windows executable with custom icon
- Includes all dependencies and assets
- Optimized for size and performance
- Creates basic installer script in dist/

#### `create_simple_installer.py`
**Purpose:** Creates Windows installer package without external dependencies  
**Usage:** `python tools/create_simple_installer.py`  
**Output:** 
- `installer_simple/` - Raw installer files
- `DeeMusic_Installer_v1.0.0.zip` - Distribution package
**Features:**
- Multiple installation options (Program Files, portable, current directory)
- Professional batch-based installer with guided setup
- Complete uninstaller with settings cleanup
- Start Menu shortcuts and file associations

### Professional Installer Tools

#### `installer.iss`
**Purpose:** Inno Setup script for professional Windows installer  
**Usage:** Open in Inno Setup and compile, or use `build_installer.py`  
**Output:** Professional `.exe` installer  
**Features:**
- Modern wizard-style interface
- Registry integration and file associations
- Professional uninstaller
- Multilingual support ready

#### `build_installer.py`
**Purpose:** Automated Inno Setup compiler  
**Usage:** `python tools/build_installer.py`  
**Requirements:** Inno Setup must be installed  
**Output:** `installer_output/DeeMusic_Setup_v1.0.0.exe`  
**Features:**
- Automatic Inno Setup detection
- One-command professional installer creation
- Comprehensive error checking

## 🚀 Quick Start

### Build Executable Only
```bash
cd /path/to/deemusic
python tools/build.py
```

### Create Complete Installer Package
```bash
cd /path/to/deemusic
python tools/build.py              # Build executable first
python tools/create_simple_installer.py  # Create installer package
```

### Professional Installer (requires Inno Setup)
```bash
cd /path/to/deemusic
python tools/build.py              # Build executable first  
python tools/build_installer.py    # Create professional installer
```

## 📋 Build Process Flow

1. **Development** → Source code in `src/`
2. **Build** → `tools/build.py` → Creates `dist/DeeMusic.exe`
3. **Package** → `tools/create_simple_installer.py` → Creates installer ZIP
4. **Distribute** → Upload installer package to GitHub releases

## 🔧 Prerequisites

### Required for all builds:
- Python 3.11+ with virtual environment
- All dependencies from `requirements.txt`
- PyQt6 and PyInstaller

### Additional for professional installer:
- [Inno Setup 6](https://jrsoftware.org/isdl.php) (optional)

## 📊 Output Files

| Tool | Output | Size | Purpose |
|------|--------|------|---------|
| `build.py` | `dist/DeeMusic.exe` | ~84MB | Standalone executable |
| `create_simple_installer.py` | `DeeMusic_Installer_v1.0.0.zip` | ~80MB | User-friendly installer |
| `build_installer.py` | `DeeMusic_Setup_v1.0.0.exe` | ~82MB | Professional installer |

## ⚙️ Configuration

### Executable Settings
Edit `build.py` to modify:
- Icon file path
- Excluded modules
- Optimization level
- Hidden imports

### Installer Settings
Edit `create_simple_installer.py` to modify:
- Version number
- Package contents
- Installation options

Edit `installer.iss` to modify:
- Professional installer appearance
- Registry entries
- File associations
- Uninstaller behavior

## 🐛 Troubleshooting

### Common Issues:
- **Permission denied**: Close any running DeeMusic instances
- **Missing icon**: Ensure `src/ui/assets/logo.ico` exists
- **Import errors**: Check all dependencies are installed
- **Inno Setup not found**: Install from official website or use simple installer

### Build Tips:
- Always build from the project root directory
- Use virtual environment for consistent builds
- Test executable on clean system before distribution
- Verify all assets are included in the build

## 📝 Notes

- Scripts are designed to be run from the project root directory
- All paths are relative to the project root
- Generated files are automatically excluded from git via `.gitignore`
- Installer packages include all necessary files for end users 