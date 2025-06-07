#!/usr/bin/env python3
"""
DeeMusic Build Script
Compiles the application into a standalone executable using PyInstaller.
"""

import PyInstaller.__main__
import sys
import os
import shutil
from pathlib import Path

def clean_build_dirs():
    """Clean previous build directories."""
    dirs_to_clean = ['build', 'dist', '__pycache__']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"Cleaned {dir_name} directory")

def get_version():
    """Get version from config or default."""
    try:
        # Try to read version from a config file or use default
        return "1.0.0"
    except:
        return "1.0.0"

def build_application():
    """Build the application executable."""
    print("Building DeeMusic executable...")
    
    # Get project root directory (parent of tools directory)
    current_dir = Path(__file__).parent.parent.absolute()
    
    # Define paths
    assets_path = current_dir / "src" / "ui" / "assets"
    styles_path = current_dir / "src" / "ui" / "styles"
    
    # Build arguments
    build_args = [
        str(current_dir / 'run.py'),
        '--onefile',
        '--windowed',
        '--name=DeeMusic',
        f'--distpath={current_dir}/dist',
        f'--workpath={current_dir}/build', 
        f'--specpath={current_dir}/build',
        f'--paths={current_dir}/src',  # Add src directory to Python path
        '--clean',
        
        # Hide imports to ensure they're included
        '--hidden-import=PyQt6',
        '--hidden-import=PyQt6.QtCore',
        '--hidden-import=PyQt6.QtWidgets',
        '--hidden-import=PyQt6.QtGui',
        '--hidden-import=qasync',
        '--hidden-import=mutagen',
        '--hidden-import=mutagen.mp3',
        '--hidden-import=mutagen.flac',
        '--hidden-import=mutagen.id3',
        '--hidden-import=requests',
        '--hidden-import=aiohttp',
        '--hidden-import=cryptography',
        '--hidden-import=Cryptodome',
        '--hidden-import=pycryptodome',
        '--hidden-import=PIL',
        '--hidden-import=pathvalidate',
        '--hidden-import=python-dotenv',
        '--hidden-import=tqdm',
        '--hidden-import=fuzzywuzzy',
        '--hidden-import=yarl',
        '--hidden-import=yt_dlp',
        
        # Application-specific modules
        '--hidden-import=ui.main_window',
        '--hidden-import=ui.settings_dialog',
        '--hidden-import=ui.artist_detail_page',
        '--hidden-import=ui.search_widget',
        '--hidden-import=ui.download_queue_widget',
        '--hidden-import=ui.home_page',
        '--hidden-import=ui.theme_manager',
        '--hidden-import=config_manager',
        '--hidden-import=services.deezer_api',
        '--hidden-import=services.download_manager',
        '--hidden-import=utils.image_cache',
        '--hidden-import=models',
        
        # Collect submodules
        '--collect-submodules=PyQt6',
        '--collect-submodules=qasync',
        '--collect-submodules=mutagen',
        '--collect-submodules=cryptography',
        
        # Exclude unnecessary modules to reduce size
        '--exclude-module=tkinter',
        '--exclude-module=matplotlib',
        '--exclude-module=pandas',
        '--exclude-module=numpy',
        '--exclude-module=scipy',
        '--exclude-module=jupyter',
        '--exclude-module=IPython',
        
        # Add data files
        f'--add-data={current_dir}/src;src',  # Include entire src directory
        f'--add-data={assets_path};src/ui/assets',
        f'--add-data={styles_path};src/ui/styles',
        
        # Add version info
        f'--distpath=dist',
    ]
    
    # Add icon if it exists
    icon_path = assets_path / "logo.ico"
    if icon_path.exists():
        build_args.append(f'--icon={icon_path}')
    else:
        print("Warning: No icon file found at src/ui/assets/logo.ico")
    
    # Run PyInstaller
    try:
        PyInstaller.__main__.run(build_args)
        print("\n✅ Build completed successfully!")
        print(f"📁 Executable location: {current_dir}/dist/DeeMusic.exe")
        print(f"📏 File size: {get_file_size(current_dir / 'dist' / 'DeeMusic.exe')}")
        
    except Exception as e:
        print(f"\n❌ Build failed: {e}")
        return False
    
    return True

def get_file_size(file_path):
    """Get human-readable file size."""
    if not file_path.exists():
        return "File not found"
    
    size = file_path.stat().st_size
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

def create_installer_script():
    """Create a simple installer script."""
    installer_content = '''
@echo off
echo DeeMusic Installer
echo ==================
echo.
echo This will install DeeMusic to C:\\Program Files\\DeeMusic
echo.
pause

if not exist "C:\\Program Files\\DeeMusic" mkdir "C:\\Program Files\\DeeMusic"
copy DeeMusic.exe "C:\\Program Files\\DeeMusic\\DeeMusic.exe"

echo.
echo Installation complete!
echo You can now run DeeMusic from the Start Menu or:
echo C:\\Program Files\\DeeMusic\\DeeMusic.exe
echo.
pause
'''
    
    with open('dist/install.bat', 'w') as f:
        f.write(installer_content)
    print("📦 Created installer script: dist/install.bat")

def main():
    """Main build function."""
    print("DeeMusic Build Tool")
    print("===================")
    
    # Check if PyInstaller is installed
    try:
        import PyInstaller
        print(f"✅ PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("❌ PyInstaller not found. Install it with: pip install pyinstaller")
        return
    
    # Clean previous builds
    clean_build_dirs()
    
    # Build the application
    if build_application():
        create_installer_script()
        print("\n🎉 Build process completed successfully!")
        print("\nNext steps:")
        print("1. Test the executable: dist/DeeMusic.exe")
        print("2. Run the installer: dist/install.bat (optional)")
        print("3. Distribute the executable to users")
    else:
        print("\n💥 Build process failed!")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 