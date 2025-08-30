#!/usr/bin/env python3
"""
DeeMusic Fast Build Script
Creates a fast-loading standalone executable with minimal size and quick startup.
"""

import PyInstaller.__main__
import sys
import os
import shutil
from pathlib import Path

def build_fast():
    """Build fast-loading executable using direct PyInstaller call."""
    print("🚀 Building fast-loading DeeMusic executable...")
    
    # Clean previous builds
    dirs_to_clean = ['build', 'dist']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            try:
                shutil.rmtree(dir_name)
                print(f"Cleaned {dir_name} directory")
            except PermissionError as e:
                print(f"⚠️  Warning: Could not clean {dir_name} directory - {e}")
                pass
    
    # Get current directory
    current_dir = Path(__file__).parent.parent.absolute()
    
    # Build with direct PyInstaller call - optimized for speed
    try:
        PyInstaller.__main__.run([
            str(current_dir / 'run.py'),
            '--onefile',
            '--windowed',
            '--name=DeeMusic',
            '--optimize=2',
            '--strip',
            '--noupx',  # Disable UPX for faster startup
            '--clean',
            '--noconfirm',
            f'--icon={current_dir / "src" / "ui" / "assets" / "logo.ico"}',
            f'--add-data={current_dir / "src" / "ui" / "assets"};src/ui/assets',
            f'--add-data={current_dir / "src" / "ui" / "styles"};src/ui/styles',
            '--hidden-import=PyQt6.QtCore',
            '--hidden-import=PyQt6.QtWidgets',
            '--hidden-import=PyQt6.QtGui',
            '--hidden-import=PyQt6.QtNetwork',
            '--hidden-import=qasync',
            '--hidden-import=requests',
            '--hidden-import=aiohttp',
            '--hidden-import=cryptography',
            '--hidden-import=Cryptodome.Cipher.Blowfish',
            '--hidden-import=mutagen',
            '--hidden-import=pathvalidate',
            '--hidden-import=spotipy',
            '--hidden-import=fuzzywuzzy',
            '--exclude-module=PyQt5',
            '--exclude-module=PySide2',
            '--exclude-module=PySide6',
            '--exclude-module=tkinter',
            '--exclude-module=matplotlib',
            '--exclude-module=pandas',
            '--exclude-module=numpy',
            '--exclude-module=scipy',
            '--exclude-module=jupyter',
            '--exclude-module=pytest',
            '--exclude-module=unittest',
            '--log-level=WARN',
        ])
        
        print("\n✅ Fast build completed successfully!")
        
        # Get file info
        exe_path = Path('dist/DeeMusic.exe')
        if exe_path.exists():
            size = exe_path.stat().st_size
            size_mb = size / (1024 * 1024)
            print(f"📁 Executable location: {exe_path.absolute()}")
            print(f"📏 File size: {size_mb:.1f} MB")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Fast build failed: {e}")
        return False

def main():
    """Main fast build function."""
    print("DeeMusic Fast Build Tool")
    print("========================")
    
    # Check PyInstaller
    try:
        import PyInstaller
        print(f"✅ PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("❌ PyInstaller not found. Install it with: pip install pyinstaller")
        return 1
    
    # Build fast version
    if build_fast():
        print("\n🎉 Fast build process completed!")
        print("\n🚀 Optimizations Applied:")
        print("• Single file executable (--onefile)")
        print("• No console window (--windowed)")
        print("• Python bytecode optimization (--optimize=2)")
        print("• Debug symbol stripping (--strip)")
        print("• UPX disabled for faster startup (--noupx)")
        print("• Minimal dependencies included")
        print("• Excluded heavy unused modules")
        return 0
    else:
        print("\n💥 Fast build failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())