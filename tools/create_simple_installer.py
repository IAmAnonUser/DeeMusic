#!/usr/bin/env python3
"""
Create a simple Windows installer for DeeMusic without requiring Inno Setup
"""

import os
import sys
import shutil
import zipfile
from pathlib import Path

def create_simple_installer():
    """Create a simple installer package."""
    print("📦 DeeMusic Simple Installer Creator")
    print("=" * 45)
    
    # Check if executable exists
    exe_path = Path("dist/DeeMusic.exe")
    if not exe_path.exists():
        print("❌ DeeMusic.exe not found! Run 'python build.py' first.")
        return False
    
    print("✅ DeeMusic.exe found")
    
    # Create installer directory
    installer_dir = Path("installer_simple")
    if installer_dir.exists():
        shutil.rmtree(installer_dir)
    installer_dir.mkdir()
    
    print(f"📁 Creating installer in {installer_dir}")
    
    # Copy files
    print("📋 Copying files...")
    
    # Copy executable
    shutil.copy2(exe_path, installer_dir / "DeeMusic.exe")
    print("   ✅ DeeMusic.exe")
    
    # Copy icon
    icon_path = Path("src/ui/assets/logo.ico")
    if icon_path.exists():
        shutil.copy2(icon_path, installer_dir / "logo.ico")
        print("   ✅ logo.ico")
    
    # Copy README
    readme_path = Path("README.md")
    if readme_path.exists():
        shutil.copy2(readme_path, installer_dir / "README.txt")
        print("   ✅ README.txt")
    
    # Create advanced installer script
    installer_script = installer_dir / "install.bat"
    with open(installer_script, 'w', encoding='utf-8') as f:
        f.write(f'''@echo off
title DeeMusic Installer v1.0.4
color 0A
echo.
echo     ╔══════════════════════════════════════════╗
echo     ║              DeeMusic Installer          ║
echo     ║         Version 1.0.4                    ║
echo     ╚══════════════════════════════════════════╝
echo.
echo Welcome to DeeMusic - Modern Music Streaming and Downloading
echo.

:menu
echo Please choose an installation option:
echo.
echo [1] Install to Program Files (Recommended)
echo [2] Install to current directory
echo [3] Portable installation (no shortcuts)
echo [4] Cancel installation
echo.
set /p choice="Enter your choice (1-4): "

if "%choice%"=="1" goto install_program_files
if "%choice%"=="2" goto install_current
if "%choice%"=="3" goto install_portable
if "%choice%"=="4" goto cancel
echo Invalid choice. Please try again.
goto menu

:install_program_files
echo.
echo Installing DeeMusic to Program Files...
set "install_path=C:\\Program Files\\DeeMusic"

echo Creating directory: %install_path%
if not exist "%install_path%" mkdir "%install_path%"

echo Copying files...
copy /Y "DeeMusic.exe" "%install_path%\\DeeMusic.exe" >nul
if exist "logo.ico" copy /Y "logo.ico" "%install_path%\\logo.ico" >nul
if exist "README.txt" copy /Y "README.txt" "%install_path%\\README.txt" >nul

echo Creating Start Menu shortcuts...
powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%ProgramData%\\Microsoft\\Windows\\Start Menu\\Programs\\DeeMusic.lnk'); $Shortcut.TargetPath = '%install_path%\\DeeMusic.exe'; $Shortcut.IconLocation = '%install_path%\\logo.ico'; $Shortcut.Description = 'DeeMusic - Music Streaming and Downloading'; $Shortcut.Save()"

echo.
set /p desktop="Create desktop shortcut? (y/n): "
if /i "%desktop%"=="y" (
    powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USERPROFILE%\\Desktop\\DeeMusic.lnk'); $Shortcut.TargetPath = '%install_path%\\DeeMusic.exe'; $Shortcut.IconLocation = '%install_path%\\logo.ico'; $Shortcut.Description = 'DeeMusic - Music Streaming and Downloading'; $Shortcut.Save()"
    echo Desktop shortcut created.
)

echo.
echo ✅ Installation completed successfully!
echo.
echo DeeMusic has been installed to: %install_path%
echo You can now run DeeMusic from:
echo   • Start Menu
echo   • Desktop shortcut (if created)
echo   • Direct path: %install_path%\\DeeMusic.exe
echo.
echo Settings will be stored in: %%AppData%%\\DeeMusic
goto end

:install_current
echo.
echo Installing DeeMusic to current directory...
echo Files are already in the current directory.
echo.
set /p desktop="Create desktop shortcut? (y/n): "
if /i "%desktop%"=="y" (
    powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USERPROFILE%\\Desktop\\DeeMusic.lnk'); $Shortcut.TargetPath = '%CD%\\DeeMusic.exe'; $Shortcut.IconLocation = '%CD%\\logo.ico'; $Shortcut.Description = 'DeeMusic - Music Streaming and Downloading'; $Shortcut.Save()"
    echo Desktop shortcut created.
)
echo ✅ Installation completed!
goto end

:install_portable
echo.
echo Portable installation selected.
echo Files are ready to use from current directory.
echo No shortcuts will be created.
echo You can run DeeMusic.exe directly.
echo ✅ Portable installation ready!
goto end

:cancel
echo.
echo Installation cancelled.
goto end

:end
echo.
echo Thank you for using DeeMusic!
echo Visit: https://github.com/IAmAnonUser/DeeMusic
echo.
pause
''')
    
    print("   ✅ install.bat")
    
    # Create uninstaller script
    uninstaller_script = installer_dir / "uninstall.bat"
    with open(uninstaller_script, 'w', encoding='utf-8') as f:
        f.write(f'''@echo off
title DeeMusic Uninstaller
color 0C
echo.
echo     ╔══════════════════════════════════════════╗
echo     ║            DeeMusic Uninstaller          ║
echo     ╚══════════════════════════════════════════╝
echo.

set "install_path=C:\\Program Files\\DeeMusic"

echo Removing DeeMusic installation...
echo.

if exist "%install_path%" (
    echo Removing program files...
    rmdir /s /q "%install_path%"
    echo Program files removed.
) else (
    echo Program files not found in default location.
)

echo Removing shortcuts...
if exist "%ProgramData%\\Microsoft\\Windows\\Start Menu\\Programs\\DeeMusic.lnk" (
    del "%ProgramData%\\Microsoft\\Windows\\Start Menu\\Programs\\DeeMusic.lnk"
    echo Start Menu shortcut removed.
)

if exist "%USERPROFILE%\\Desktop\\DeeMusic.lnk" (
    del "%USERPROFILE%\\Desktop\\DeeMusic.lnk"
    echo Desktop shortcut removed.
)

echo.
set /p settings="Remove settings and data from %%AppData%%\\DeeMusic? (y/n): "
if /i "%settings%"=="y" (
    if exist "%APPDATA%\\DeeMusic" (
        rmdir /s /q "%APPDATA%\\DeeMusic"
        echo Settings and data removed.
    )
)

echo.
echo ✅ DeeMusic has been uninstalled.
echo.
pause
''')
    
    print("   ✅ uninstall.bat")
    
    # Create README for installer
    installer_readme = installer_dir / "INSTALL_README.txt"
    with open(installer_readme, 'w', encoding='utf-8') as f:
        f.write(f'''DeeMusic Windows Installer Package
===================================

This package contains everything needed to install DeeMusic on Windows.

INSTALLATION OPTIONS:
===================

OPTION 1: Automatic Installation (Recommended)
----------------------------------------------
1. Double-click "install.bat"
2. Follow the installation wizard
3. Choose your preferred installation type
4. Enjoy DeeMusic!

OPTION 2: Manual Installation
-----------------------------
1. Copy "DeeMusic.exe" to your desired location
2. Optionally copy "logo.ico" and "README.txt"
3. Run DeeMusic.exe

INCLUDED FILES:
==============
• DeeMusic.exe - Main application (80+ MB)
• logo.ico - Application icon
• README.txt - Documentation
• install.bat - Automatic installer
• uninstall.bat - Uninstaller
• INSTALL_README.txt - This file

UNINSTALLING:
============
• If installed via install.bat: Run "uninstall.bat"
• If manually installed: Delete the files manually

SYSTEM REQUIREMENTS:
==================
• Windows 7 or later (64-bit)
• 100 MB free disk space
• Internet connection for music streaming

SETTINGS LOCATION:
================
DeeMusic stores settings in: %AppData%\\DeeMusic
This includes your Deezer ARL token and preferences.

SUPPORT:
=======
Visit: https://github.com/IAmAnonUser/DeeMusic
Report issues on GitHub for community support.

VERSION: 1.0.4
BUILD DATE: {Path(exe_path).stat().st_mtime}
''')
    
    print("   ✅ INSTALL_README.txt")
    
    # Create zip package
    zip_path = Path("DeeMusic_Installer_v1.0.4.zip")
    print(f"\n📦 Creating installer package: {zip_path}")
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in installer_dir.rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(installer_dir)
                zipf.write(file_path, arcname)
                print(f"   📁 {arcname}")
    
    # Get sizes
    installer_size = sum(f.stat().st_size for f in installer_dir.rglob('*') if f.is_file())
    zip_size = zip_path.stat().st_size
    
    print(f"\n✅ Simple installer created successfully!")
    print(f"📁 Installer directory: {installer_dir} ({installer_size / 1024 / 1024:.1f} MB)")
    print(f"📦 Installer package: {zip_path} ({zip_size / 1024 / 1024:.1f} MB)")
    
    return True

def show_usage_instructions():
    """Show instructions for using the installer."""
    print(f"\n🎯 Distribution Instructions:")
    print("=" * 35)
    print("📤 To distribute DeeMusic:")
    print("1. Send users the 'DeeMusic_Installer_v1.0.4.zip' file")
    print("2. Users extract the ZIP file")
    print("3. Users run 'install.bat' for guided installation")
    print("4. Alternative: Users can run DeeMusic.exe directly (portable)")
    
    print(f"\n📋 Installation Features:")
    print("✅ Multiple installation options")
    print("✅ Program Files installation with Start Menu shortcuts")
    print("✅ Portable installation option")
    print("✅ Desktop shortcut creation")
    print("✅ Proper uninstaller included")
    print("✅ Settings cleanup option")
    print("✅ User-friendly colored interface")
    
    print(f"\n⚙️ Advanced Options:")
    print("• installer_simple/ - Raw installer files")
    print("• DeeMusic_Installer_v1.0.4.zip - Distribution package")
    print("• Users can run install.bat for guided setup")
    print("• Users can run DeeMusic.exe directly for portable use")

if __name__ == "__main__":
    if create_simple_installer():
        show_usage_instructions()
        print("\n🎉 Simple installer creation completed!")
        print("📤 Ready for distribution to users.")
    else:
        print("\n❌ Simple installer creation failed!")
        sys.exit(1) 