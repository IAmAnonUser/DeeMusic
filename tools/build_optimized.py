#!/usr/bin/env python3
"""
DeeMusic Optimized Build Script
Creates a high-performance standalone executable with advanced optimizations.
"""

import PyInstaller.__main__
import sys
import os
import shutil
from pathlib import Path

def create_optimized_spec_file():
    """Create a custom .spec file with advanced optimizations."""
    current_dir = Path(__file__).parent.parent.absolute()
    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

# Performance optimizations
block_cipher = None
current_dir = Path(r"{current_dir}")

# Analysis with optimizations
a = Analysis(
    [str(current_dir / 'run.py')],
    pathex=[str(current_dir / 'src')],
    binaries=[],
    datas=[
        (str(current_dir / 'src' / 'ui' / 'assets'), 'src/ui/assets'),
        (str(current_dir / 'src' / 'ui' / 'styles'), 'src/ui/styles'),
    ],
    hiddenimports=[
        # Core PyQt6 modules - ONLY PyQt6
        'PyQt6.QtCore',
        'PyQt6.QtWidgets', 
        'PyQt6.QtGui',
        'PyQt6.QtNetwork',
        
        # Essential standard library modules
        'xml',
        'xml.etree',
        'xml.etree.ElementTree',
        'xml.parsers',
        'xml.parsers.expat',
        'pkg_resources',
        'email',
        'email.mime',
        'email.mime.text',
        'json',
        'pathlib',
        'asyncio',
        'threading',
        'concurrent.futures',
        
        # Essential libraries
        'qasync',
        'requests',
        'aiohttp',
        'aiohttp.client',
        'aiohttp.connector',
        'cryptography',
        'cryptography.hazmat.primitives.ciphers',
        'cryptography.hazmat.backends.openssl',
        'Cryptodome.Cipher.Blowfish',
        'mutagen',
        'mutagen.mp3',
        'mutagen.flac',
        'mutagen.id3',
        'pathvalidate',
        'spotipy',
        'fuzzywuzzy',
        'fuzzywuzzy.fuzz',
        
        # Application modules - Core
        'src.ui.main_window',
        'src.ui.home_page',
        'src.ui.search_widget',
        'src.ui.artist_detail_page',
        'src.ui.album_detail_page',
        'src.ui.playlist_detail_page',
        'src.ui.theme_manager',
        'src.ui.settings_dialog',
        'src.ui.folder_settings_dialog',
        'src.config_manager',
        
        # Services - New System
        'src.services.deezer_api',
        'src.services.download_service',
        'src.services.new_download_engine',
        'src.services.new_download_worker',
        'src.services.new_queue_manager',
        'src.services.event_bus',
        'src.services.spotify_api',
        'src.services.music_player',
        
        # Models and Utils
        'src.models.queue_models',
        'src.utils.image_cache',
        'src.utils.helpers',
        'src.utils.icon_utils',
        
        # UI Components
        'src.ui.components.search_result_card',
        'src.ui.components.toggle_switch',
        'src.ui.components.progress_card',
        'src.ui.components.new_queue_widget',
        'src.ui.components.new_queue_item_widget',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[
        # Exclude conflicting Qt bindings - CRITICAL FIX
        'PyQt5',
        'PyQt5.QtCore',
        'PyQt5.QtWidgets',
        'PyQt5.QtGui',
        'PySide2',
        'PySide6',
        'tkinter',
        # Exclude heavy unused modules
        'matplotlib',
        'pandas',
        'numpy',
        'scipy',
        'jupyter',
        'IPython',
        'pytest',
        'unittest',
        'doctest',
        'pdb',
        'profile',
        'cProfile',
        'pstats',
        'timeit',
        'trace',
        'turtle',
        'curses',
        'readline',
        'rlcompleter',
        'http.server',
        'urllib.robotparser',
        # Exclude problematic modules that cause hook issues
        'rapidfuzz',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
    optimize=2,  # Maximum Python optimization
)

# Remove duplicate entries and optimize
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher, optimize=2)

# Create executable with optimizations
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DeeMusic',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,  # Strip debug symbols
    upx=False,   # Disable UPX for faster startup
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(current_dir / 'src' / 'ui' / 'assets' / 'logo.ico') if (current_dir / 'src' / 'ui' / 'assets' / 'logo.ico').exists() else None,
)
'''
    
    spec_path = Path('DeeMusic_optimized.spec')
    with open(spec_path, 'w') as f:
        f.write(spec_content)
    
    return spec_path

def build_optimized():
    """Build optimized executable using custom spec file."""
    print("🚀 Building optimized DeeMusic executable...")
    
    # Clean previous builds with better error handling (preserve installer files)
    dirs_to_clean = ['build']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            try:
                shutil.rmtree(dir_name)
                print(f"Cleaned {dir_name} directory")
            except PermissionError as e:
                print(f"⚠️  Warning: Could not clean {dir_name} directory - {e}")
                print(f"   Please close DeeMusic.exe if it's running and try again")
                # Try to continue anyway
                pass
            except Exception as e:
                print(f"⚠️  Warning: Error cleaning {dir_name} directory - {e}")
                pass
    
    # Clean only the executable from dist, preserve installer files
    dist_exe = Path('dist/DeeMusic.exe')
    if dist_exe.exists():
        try:
            dist_exe.unlink()
            print("Cleaned previous DeeMusic.exe from dist")
        except PermissionError as e:
            print(f"⚠️  Warning: Could not remove previous DeeMusic.exe - {e}")
            print("   Please close DeeMusic.exe if it's running and try again")
        except Exception as e:
            print(f"⚠️  Warning: Error removing previous DeeMusic.exe - {e}")
    
    # Create optimized spec file
    spec_path = create_optimized_spec_file()
    print(f"📝 Created optimized spec file: {spec_path}")
    
    # Build with spec file
    try:
        PyInstaller.__main__.run([
            str(spec_path),
            '--clean',
            '--noconfirm',
            '--log-level=WARN',  # Reduce build output
        ])
        
        print("\n✅ Optimized build completed successfully!")
        
        # Get file info
        exe_path = Path('dist/DeeMusic.exe')
        if exe_path.exists():
            size = exe_path.stat().st_size
            size_mb = size / (1024 * 1024)
            print(f"📁 Executable location: {exe_path.absolute()}")
            print(f"📏 File size: {size_mb:.1f} MB")
        
        # Clean up spec file
        if spec_path.exists():
            spec_path.unlink()
            print(f"🧹 Cleaned up spec file: {spec_path}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Optimized build failed: {e}")
        return False

def create_performance_tips():
    """Create a performance tips file for users."""
    tips_content = """# DeeMusic Performance Tips

## For Better Executable Performance:

### 1. Antivirus Exclusions
Add DeeMusic.exe to your antivirus exclusions:
- Windows Defender: Settings > Virus & threat protection > Exclusions
- Add the DeeMusic.exe file and installation folder

### 2. Windows Performance Settings
- Disable Windows real-time protection temporarily during first run
- Run as Administrator for better file system access
- Close unnecessary background applications

### 3. Storage Optimization
- Install on SSD if available (faster startup)
- Ensure adequate free disk space (>1GB)
- Defragment HDD if using traditional hard drive

### 4. System Resources
- Close other music/media applications
- Ensure adequate RAM (4GB+ recommended)
- Update graphics drivers for better UI performance

### 5. Network Optimization
- Use wired connection for better download speeds
- Configure firewall to allow DeeMusic
- Consider VPN if experiencing connection issues

## Troubleshooting Slow Startup:

1. **First Run**: Initial startup is slower due to:
   - Windows SmartScreen scanning
   - Antivirus real-time scanning
   - Cache initialization

2. **Subsequent Runs**: Should be faster after first launch

3. **If Still Slow**:
   - Check Task Manager for high CPU/disk usage
   - Temporarily disable antivirus
   - Run from SSD location
   - Ensure Windows is updated
"""
    
    with open('dist/PERFORMANCE_TIPS.txt', 'w') as f:
        f.write(tips_content)
    print("📋 Created performance tips: dist/PERFORMANCE_TIPS.txt")

def main():
    """Main optimized build function."""
    print("DeeMusic Optimized Build Tool")
    print("============================")
    
    # Check PyInstaller
    try:
        import PyInstaller
        print(f"✅ PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("❌ PyInstaller not found. Install it with: pip install pyinstaller")
        return 1
    
    # Build optimized version
    if build_optimized():
        create_performance_tips()
        print("\n🎉 Optimized build process completed!")
        print("\n🚀 Performance Improvements:")
        print("• Python bytecode optimization (--optimize=2)")
        print("• Selective module inclusion")
        print("• Debug symbol stripping")
        print("• UPX compression disabled for faster startup")
        print("• Reduced executable size")
        print("\n📖 See PERFORMANCE_TIPS.txt for user optimization guide")
        return 0
    else:
        print("\n💥 Optimized build failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())