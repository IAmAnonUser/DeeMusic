#!/usr/bin/env python3
"""
DeeMusic Release Build Script v1.0.1
Creates a packaged release with all necessary files and documentation.
"""

import os
import shutil
import zipfile
from pathlib import Path
import datetime

# Version information
VERSION = "1.0.1"
BUILD_DATE = datetime.datetime.now().strftime("%Y-%m-%d")

# Directories and files
PROJECT_ROOT = Path(__file__).parent
BUILD_DIR = PROJECT_ROOT / f"build/DeeMusic_v{VERSION}"
DIST_DIR = PROJECT_ROOT / "dist"

# Files to include in release
RELEASE_FILES = {
    # Core application files
    "src/": "src/",
    "run.py": "run.py",
    "requirements.txt": "requirements.txt",
    
    # Documentation
    f"docs/RELEASE_NOTES_v{VERSION}.md": "RELEASE_NOTES.md",
    "README.md": "README.md",
    "docs/DOWNLOAD_SYSTEM_DOCUMENTATION.md": "docs/DOWNLOAD_SYSTEM_DOCUMENTATION.md",
    
    # Configuration
    "installer_simple/": "installer_simple/",
    
    # Tools (if needed)
    "tools/": "tools/",
}

# Exclude patterns
EXCLUDE_PATTERNS = [
    "*.pyc",
    "__pycache__",
    "*.log",
    ".git*",
    "*.tmp",
    "venv*",
    "build/",
    "dist/",
    ".pytest_cache",
    "*.egg-info",
]

def should_exclude(path: Path) -> bool:
    """Check if a path should be excluded from the release."""
    path_str = str(path)
    for pattern in EXCLUDE_PATTERNS:
        if pattern in path_str or path.name.startswith('.'):
            return True
    return False

def copy_files():
    """Copy all necessary files to the build directory."""
    print(f"📂 Creating build directory: {BUILD_DIR}")
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    
    for src_path, dest_path in RELEASE_FILES.items():
        src = PROJECT_ROOT / src_path
        dest = BUILD_DIR / dest_path
        
        if src.is_file():
            print(f"📄 Copying file: {src_path}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        elif src.is_dir():
            print(f"📁 Copying directory: {src_path}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dest, ignore=shutil.ignore_patterns(*EXCLUDE_PATTERNS))

def create_version_info():
    """Create a version info file."""
    version_info = f"""DeeMusic Version Information
==========================

Version: {VERSION}
Build Date: {BUILD_DATE}
Build Type: Release

Release Highlights:
- Fixed critical download quality setting issue
- Added playlist download button functionality
- Improved responsive UI layouts
- Enhanced user experience

For full release notes, see RELEASE_NOTES.md

Installation:
1. Install Python 3.11+ if not already installed
2. Install dependencies: pip install -r requirements.txt
3. Run the application: python run.py

Support:
- Documentation: docs/
- Issues: GitHub repository
"""
    
    version_file = BUILD_DIR / "VERSION.txt"
    with open(version_file, 'w', encoding='utf-8') as f:
        f.write(version_info)
    print(f"📝 Created version info: {version_file}")

def create_quick_start():
    """Create a quick start guide."""
    quick_start = """# 🚀 DeeMusic v1.0.1 - Quick Start Guide

## 📦 Installation

### Prerequisites:
- Python 3.11 or higher
- Windows 7+ (64-bit)

### Steps:
1. **Install Python** (if not installed): Download from https://python.org
2. **Install Dependencies**:
   ```
   pip install -r requirements.txt
   ```
3. **Run DeeMusic**:
   ```
   python run.py
   ```

## ⚙️ Initial Setup

1. **Configure Deezer ARL**:
   - Go to File > Settings
   - Enter your Deezer ARL token
   - Save settings

2. **Set Download Preferences**:
   - Choose audio quality (MP3 320, FLAC)
   - Set download location
   - Configure concurrent downloads

## 🎵 Start Using DeeMusic

1. **Search for Music**: Use the search bar to find artists, albums, playlists
2. **Browse Content**: Explore homepage sections for discovery
3. **Download Music**: 
   - Hover over albums/playlists for download buttons
   - Individual tracks can be downloaded from detail pages
   - Quality settings now apply immediately!

## 🆕 What's New in v1.0.1

- **✅ Fixed**: Download quality changes now work immediately
- **✅ Added**: Playlist download buttons on hover
- **✅ Improved**: Responsive layouts and UI consistency

## 📚 Documentation

- **Full Release Notes**: See RELEASE_NOTES.md
- **Download System**: See docs/DOWNLOAD_SYSTEM_DOCUMENTATION.md

## 🔧 Troubleshooting

- Ensure Python 3.11+ is installed
- Check that all dependencies are installed
- Verify ARL token is valid and current
- Test download quality settings after upgrade

---
**Enjoy your enhanced DeeMusic experience! 🎶**
"""
    
    quick_start_file = BUILD_DIR / "QUICK_START.md"
    with open(quick_start_file, 'w', encoding='utf-8') as f:
        f.write(quick_start)
    print(f"📖 Created quick start guide: {quick_start_file}")

def create_zip_archive():
    """Create a ZIP archive of the release."""
    DIST_DIR.mkdir(exist_ok=True)
    zip_path = DIST_DIR / f"DeeMusic_v{VERSION}_{BUILD_DATE}.zip"
    
    print(f"📦 Creating ZIP archive: {zip_path}")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(BUILD_DIR):
            for file in files:
                file_path = Path(root) / file
                arc_path = file_path.relative_to(BUILD_DIR.parent)
                zipf.write(file_path, arc_path)
    
    print(f"✅ Release archive created: {zip_path}")
    print(f"📊 Archive size: {zip_path.stat().st_size / (1024*1024):.1f} MB")
    return zip_path

def print_release_summary():
    """Print a summary of the release build."""
    print(f"""
🎉 DeeMusic v{VERSION} Release Build Complete!

📋 Release Summary:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Version: {VERSION}
Build Date: {BUILD_DATE}
Build Directory: {BUILD_DIR}
Distribution: {DIST_DIR}

🔧 Key Features in v{VERSION}:
• Fixed critical download quality setting issue
• Added playlist download button functionality  
• Improved responsive UI layouts
• Enhanced user experience and performance

📦 Release Package Includes:
• Complete application source code
• Documentation and release notes
• Quick start guide and setup instructions
• Version information

🚀 Next Steps:
1. Test the release package
2. Distribute to users
3. Update GitHub releases page
4. Announce release to community

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")

def main():
    """Main build process."""
    print(f"🛠️  Building DeeMusic v{VERSION} Release...")
    print(f"📅 Build Date: {BUILD_DATE}")
    print("=" * 50)
    
    try:
        # Clean previous build
        if BUILD_DIR.exists():
            print(f"🧹 Cleaning previous build: {BUILD_DIR}")
            shutil.rmtree(BUILD_DIR)
        
        # Copy files
        copy_files()
        
        # Create additional files
        create_version_info()
        create_quick_start()
        
        # Create distribution archive
        zip_path = create_zip_archive()
        
        # Print summary
        print_release_summary()
        
        print(f"✅ Build completed successfully!")
        print(f"📁 Release files: {BUILD_DIR}")
        print(f"📦 Distribution: {zip_path}")
        
    except Exception as e:
        print(f"❌ Build failed: {e}")
        raise

if __name__ == "__main__":
    main() 