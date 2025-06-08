#!/usr/bin/env python3
"""
DeeMusic v1.0.1 Installer Package Creator
Creates a complete installer package with executable, documentation, and uninstaller.
"""

import os
import shutil
import zipfile
from pathlib import Path
import datetime

VERSION = "1.0.1"
BUILD_DATE = datetime.datetime.now().strftime("%Y-%m-%d")

def create_installer_package():
    """Create a comprehensive installer package."""
    print(f"Creating DeeMusic v{VERSION} Installer Package...")
    print("=" * 50)
    
    # Paths
    project_root = Path.cwd()
    dist_dir = project_root / "dist"
    installer_dir = project_root / "installer_simple"
    package_dir = project_root / f"DeeMusic_v{VERSION}_Installer"
    
    # Create package directory
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(exist_ok=True)
    
    print(f"📁 Package directory: {package_dir}")
    
    # Copy main executable
    exe_source = dist_dir / "DeeMusic.exe"
    exe_dest = package_dir / "DeeMusic.exe"
    if exe_source.exists():
        shutil.copy2(exe_source, exe_dest)
        print(f"✅ Copied executable: {exe_dest.name} ({get_file_size(exe_dest)})")
    else:
        print("❌ Executable not found! Run build first.")
        return False
    
    # Copy icon
    icon_source = installer_dir / "logo.ico"
    if icon_source.exists():
        shutil.copy2(icon_source, package_dir / "logo.ico")
        print("✅ Copied icon: logo.ico")
    
    # Create enhanced installer script
    installer_script = f'''@echo off
title DeeMusic v{VERSION} Installer
color 0A
echo.
echo ================================================
echo  DeeMusic v{VERSION} - Music Downloader
echo  Build Date: {BUILD_DATE}
echo ================================================
echo.
echo This installer will:
echo  - Install DeeMusic to Program Files
echo  - Create desktop shortcut
echo  - Add to Start Menu
echo  - Register uninstaller
echo.
echo Press any key to continue or Ctrl+C to cancel...
pause >nul

echo.
echo 📦 Installing DeeMusic v{VERSION}...
echo.

REM Create installation directory
set INSTALL_DIR=C:\\Program Files\\DeeMusic
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

REM Copy files
echo ✅ Copying application files...
copy /Y "DeeMusic.exe" "%INSTALL_DIR%\\DeeMusic.exe" >nul
copy /Y "logo.ico" "%INSTALL_DIR%\\logo.ico" >nul

REM Create desktop shortcut
echo ✅ Creating desktop shortcut...
powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USERPROFILE%\\Desktop\\DeeMusic.lnk'); $Shortcut.TargetPath = '%INSTALL_DIR%\\DeeMusic.exe'; $Shortcut.IconLocation = '%INSTALL_DIR%\\logo.ico'; $Shortcut.Save()"

REM Create Start Menu shortcut
echo ✅ Creating Start Menu shortcut...
if not exist "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\DeeMusic" mkdir "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\DeeMusic"
powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\DeeMusic\\DeeMusic.lnk'); $Shortcut.TargetPath = '%INSTALL_DIR%\\DeeMusic.exe'; $Shortcut.IconLocation = '%INSTALL_DIR%\\logo.ico'; $Shortcut.Save()"

REM Register uninstaller
echo ✅ Registering uninstaller...
reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\DeeMusic" /v "DisplayName" /d "DeeMusic v{VERSION}" /f >nul
reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\DeeMusic" /v "DisplayVersion" /d "{VERSION}" /f >nul
reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\DeeMusic" /v "Publisher" /d "DeeMusic Team" /f >nul
reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\DeeMusic" /v "UninstallString" /d "%INSTALL_DIR%\\uninstall.bat" /f >nul
reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\DeeMusic" /v "InstallLocation" /d "%INSTALL_DIR%" /f >nul

REM Create uninstaller
echo ✅ Creating uninstaller...
(
echo @echo off
echo title DeeMusic v{VERSION} Uninstaller
echo echo.
echo echo Uninstalling DeeMusic v{VERSION}...
echo echo.
echo del /f /q "%%USERPROFILE%%\\Desktop\\DeeMusic.lnk" 2^>nul
echo rmdir /s /q "%%APPDATA%%\\Microsoft\\Windows\\Start Menu\\Programs\\DeeMusic" 2^>nul
echo reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\DeeMusic" /f 2^>nul
echo del /f /q "%%~dp0DeeMusic.exe" 2^>nul
echo del /f /q "%%~dp0logo.ico" 2^>nul
echo del /f /q "%%~dp0uninstall.bat" 2^>nul
echo rmdir "%%~dp0" 2^>nul
echo echo ✅ DeeMusic has been successfully uninstalled.
echo echo.
echo pause
) > "%INSTALL_DIR%\\uninstall.bat"

echo.
echo ================================================
echo  ✅ Installation completed successfully!
echo ================================================
echo.
echo DeeMusic v{VERSION} has been installed to:
echo %INSTALL_DIR%
echo.
echo You can now run DeeMusic from:
echo  - Desktop shortcut
echo  - Start Menu ^> DeeMusic
echo  - %INSTALL_DIR%\\DeeMusic.exe
echo.
echo To uninstall, run: %INSTALL_DIR%\\uninstall.bat
echo or use Windows Programs and Features.
echo.
echo Press any key to exit...
pause >nul
'''
    
    # Write installer script
    with open(package_dir / "install.bat", "w", encoding="utf-8") as f:
        f.write(installer_script)
    print("✅ Created installer: install.bat")
    
    # Copy documentation
    docs_to_copy = [
        ("README.md", "README.txt"),
        ("docs/RELEASE_NOTES_v1.0.1.md", "RELEASE_NOTES.txt"),
        ("docs/CHANGELOG_NEXT_RELEASE.md", "CHANGELOG.txt")
    ]
    
    for src_file, dest_name in docs_to_copy:
        src_path = project_root / src_file
        if src_path.exists():
            shutil.copy2(src_path, package_dir / dest_name)
            print(f"✅ Copied documentation: {dest_name}")
    
    # Create quick start guide
    quick_start = f'''DeeMusic v{VERSION} - Quick Start Guide
=====================================

🎵 Welcome to DeeMusic!

DeeMusic is a powerful music downloader that allows you to search and download
high-quality music from Deezer in various formats including MP3 320kbps and FLAC.

📋 What's New in v{VERSION}:
- ✅ Fixed download quality setting not applying immediately
- ✅ Added playlist download buttons with hover functionality
- 🎨 Enhanced responsive UI layouts
- 🔧 Improved download system reliability

🚀 Getting Started:
1. Run DeeMusic.exe
2. Search for music using the search bar
3. Click download buttons to save tracks
4. Configure quality settings in Settings (File > Settings)
5. Downloads are saved to your configured download folder

🎛️ Key Features:
- Search tracks, albums, artists, and playlists
- Download in MP3 (320kbps, 128kbps) or FLAC quality
- Automatic metadata and artwork embedding
- Lyrics download support
- Concurrent download management
- Dark and light theme support

⚙️ Settings:
Access settings via File > Settings to configure:
- Download quality (MP3 320, FLAC, etc.)
- Download location
- Concurrent downloads
- Lyrics preferences
- UI theme

📂 Default Locations:
- Downloads: Your Downloads folder/DeeMusic/
- Settings: %APPDATA%/DeeMusic/

🔧 Troubleshooting:
- If downloads fail, check your internet connection
- Quality changes now apply immediately (no restart needed)
- Clear cache if experiencing issues: Settings > Clear Cache

💡 Tips:
- Hover over album/playlist covers for quick download buttons
- Use the download queue to monitor progress
- Right-click tracks for additional options

🆘 Support:
For issues or questions, check the documentation files included
with this installation or visit the project repository.

Enjoy your music! 🎶

Build Date: {BUILD_DATE}
'''
    
    with open(package_dir / "QUICK_START.txt", "w", encoding="utf-8") as f:
        f.write(quick_start)
    print("✅ Created quick start guide: QUICK_START.txt")
    
    # Create installer package summary
    print("\n📦 Package Contents:")
    for item in package_dir.iterdir():
        if item.is_file():
            print(f"   📄 {item.name} ({get_file_size(item)})")
    
    # Create ZIP archive
    archive_name = f"DeeMusic_v{VERSION}_Installer_{BUILD_DATE}.zip"
    archive_path = project_root / archive_name
    
    print(f"\n📦 Creating installer archive: {archive_name}")
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
        for file_path in package_dir.rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(package_dir)
                zipf.write(file_path, arcname)
    
    print(f"✅ Created installer archive: {archive_name} ({get_file_size(archive_path)})")
    
    print("\n🎉 Installer package created successfully!")
    print(f"📁 Package directory: {package_dir}")
    print(f"📦 Installer archive: {archive_name}")
    print("\n📋 Distribution files:")
    print(f"   • {archive_name} - Complete installer package")
    print(f"   • {package_dir} - Extracted installer files")
    
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

if __name__ == "__main__":
    create_installer_package() 