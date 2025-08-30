#!/usr/bin/env python3
"""
DeeMusic Optimized Installer Creator
Creates a professional Windows installer package with advanced features.
"""

import os
import sys
import shutil
import zipfile
from pathlib import Path
import datetime

def get_version():
    """Get version from centralized version.py file."""
    try:
        # Import version from the root directory
        import sys
        sys.path.insert(0, str(Path().absolute()))
        from version import __version__
        return __version__
    except ImportError:
        # Fallback if version.py doesn't exist
        return "1.0.7"

def create_optimized_installer():
    """Create an optimized installer package."""
    print("📦 DeeMusic Optimized Installer Creator")
    print("=" * 45)
    
    version = get_version()
    
    # Check if executable exists
    exe_path = Path("dist/DeeMusic.exe")
    if not exe_path.exists():
        print("❌ DeeMusic.exe not found in dist folder!")
        print("   Run 'python tools/build_optimized.py' first.")
        return False
    
    print(f"✅ DeeMusic.exe found ({exe_path.stat().st_size / (1024*1024):.1f} MB)")
    
    # Create installer directory in dist folder
    installer_dir = Path("dist/DeeMusic_Installer_Optimized")
    if installer_dir.exists():
        try:
            shutil.rmtree(installer_dir)
            print(f"🧹 Cleaned existing installer directory")
        except PermissionError as e:
            print(f"⚠️  Warning: Could not clean installer directory - {e}")
            print("   Please close any files in the installer directory and try again")
            return False
    
    installer_dir.mkdir(exist_ok=True)
    print(f"📁 Creating optimized installer in {installer_dir}")
    
    # Copy files
    print("📋 Copying files...")
    
    # Copy executable (don't remove the original)
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
    
    # Copy performance tips if it exists
    perf_tips_path = Path("dist/PERFORMANCE_TIPS.txt")
    if perf_tips_path.exists():
        shutil.copy2(perf_tips_path, installer_dir / "PERFORMANCE_TIPS.txt")
        print("   ✅ PERFORMANCE_TIPS.txt")
    
    # Create advanced installer script
    create_advanced_installer_script(installer_dir, version)
    
    # Create uninstaller script
    create_advanced_uninstaller_script(installer_dir, version)
    
    # Create installation guide
    create_installation_guide(installer_dir, version)
    
    # Create system requirements checker
    create_system_checker(installer_dir)
    
    # Create zip package in dist folder
    zip_path = Path(f"dist/DeeMusic_Installer_Optimized_v{version}.zip")
    print(f"\n📦 Creating optimized installer package: {zip_path}")
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
        for file_path in installer_dir.rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(installer_dir)
                zipf.write(file_path, arcname)
                print(f"   📁 {arcname}")
    
    # Get sizes
    installer_size = sum(f.stat().st_size for f in installer_dir.rglob('*') if f.is_file())
    zip_size = zip_path.stat().st_size
    
    print(f"\n✅ Optimized installer created successfully!")
    print(f"📁 Installer directory: {installer_dir} ({installer_size / 1024 / 1024:.1f} MB)")
    print(f"📦 Installer package: {zip_path} ({zip_size / 1024 / 1024:.1f} MB)")
    
    return True

def create_advanced_installer_script(installer_dir: Path, version: str):
    """Create an advanced installer script with modern features."""
    installer_script = installer_dir / "install.bat"
    with open(installer_script, 'w', encoding='utf-8') as f:
        f.write(f'''@echo off
setlocal enabledelayedexpansion
title DeeMusic Installer v{version} - Optimized Edition
color 0B
cls

:: Check for administrator privileges
net session >nul 2>&1
if %errorLevel% == 0 (
    set "isAdmin=true"
) else (
    set "isAdmin=false"
)

echo.
echo     ╔══════════════════════════════════════════════════════════╗
echo     ║                DeeMusic Installer v{version}                ║
echo     ║                   Optimized Edition                      ║
echo     ║          Modern Music Streaming and Downloading         ║
echo     ╚══════════════════════════════════════════════════════════╝
echo.
echo Welcome to DeeMusic - Your Ultimate Music Experience
echo.

:: System requirements check
echo [1/6] Checking system requirements...
call :check_system_requirements
if !errorlevel! neq 0 (
    echo ❌ System requirements not met. Installation cannot continue.
    pause
    exit /b 1
)
echo ✅ System requirements check passed
echo.

:: Antivirus warning
echo [2/6] Important Security Notice:
echo ⚠️  Some antivirus software may flag DeeMusic as suspicious due to:
echo    • Music downloading capabilities
echo    • Network access requirements
echo    • Executable compression
echo.
echo 💡 This is a FALSE POSITIVE. DeeMusic is safe and open-source.
echo    You may need to add DeeMusic to your antivirus exclusions.
echo.
echo Proceeding with automatic installation...
echo.

echo [3/6] Automatic installation type selection:
echo.
echo Selecting System Installation (Recommended)
echo     • Install to Program Files
echo     • Available for all users
echo     • Start Menu shortcuts
echo     • Desktop shortcut created automatically
echo.
goto install_system

:install_system
echo.
echo [4/6] Installing DeeMusic to System (Program Files)...
if "!isAdmin!"=="false" (
    echo ❌ Administrator privileges required for system installation.
    echo    Please run this installer as Administrator or choose User Installation.
    echo.
    goto menu
)

set "install_path=C:\\Program Files\\DeeMusic"
set "install_type=System"
goto perform_installation

:install_user
echo.
echo [4/6] Installing DeeMusic to User Directory...
set "install_path=%LOCALAPPDATA%\\DeeMusic"
set "install_type=User"
goto perform_installation

:install_portable
echo.
echo [4/6] Setting up Portable Installation...
set "install_path=%CD%"
set "install_type=Portable"
echo ✅ DeeMusic is ready to run from current directory.
echo.
echo 📋 Portable Installation Complete!
echo    • Run DeeMusic.exe to start the application
echo    • All settings will be stored in the current directory
echo    • You can move this folder anywhere on your system
echo.
goto create_shortcuts_prompt

:perform_installation
echo Creating directory: !install_path!
if not exist "!install_path!" mkdir "!install_path!"

echo [5/6] Copying files...
copy /Y "DeeMusic.exe" "!install_path!\\DeeMusic.exe" >nul
if exist "logo.ico" copy /Y "logo.ico" "!install_path!\\logo.ico" >nul
if exist "README.txt" copy /Y "README.txt" "!install_path!\\README.txt" >nul
if exist "PERFORMANCE_TIPS.txt" copy /Y "PERFORMANCE_TIPS.txt" "!install_path!\\PERFORMANCE_TIPS.txt" >nul

echo ✅ Files copied successfully

:create_shortcuts_prompt
if "!install_type!"=="Portable" goto installation_complete

echo.
echo [6/6] Creating shortcuts...

:: Create Start Menu shortcut
if "!install_type!"=="System" (
    set "start_menu_path=%ProgramData%\\Microsoft\\Windows\\Start Menu\\Programs"
) else (
    set "start_menu_path=%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs"
)

powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('!start_menu_path!\\DeeMusic.lnk'); $Shortcut.TargetPath = '!install_path!\\DeeMusic.exe'; $Shortcut.IconLocation = '!install_path!\\DeeMusic.exe,0'; $Shortcut.Description = 'DeeMusic - Modern Music Streaming and Downloading'; $Shortcut.Save()" >nul 2>&1
echo ✅ Start Menu shortcut created

:: Desktop shortcut (automatically created)
echo Creating desktop shortcut...
powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%USERPROFILE%\\Desktop\\DeeMusic.lnk'); $Shortcut.TargetPath = '!install_path!\\DeeMusic.exe'; $Shortcut.IconLocation = '!install_path!\\DeeMusic.exe,0'; $Shortcut.Description = 'DeeMusic - Modern Music Streaming and Downloading'; $Shortcut.Save()" >nul 2>&1
echo ✅ Desktop shortcut created

:: Add to Windows Programs list (for system installation)
if "!install_type!"=="System" (
    reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\DeeMusic" /v "DisplayName" /t REG_SZ /d "DeeMusic v{version}" /f >nul 2>&1
    reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\DeeMusic" /v "UninstallString" /t REG_SZ /d "!install_path!\\uninstall.bat" /f >nul 2>&1
    reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\DeeMusic" /v "DisplayVersion" /t REG_SZ /d "{version}" /f >nul 2>&1
    reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\DeeMusic" /v "Publisher" /t REG_SZ /d "DeeMusic Team" /f >nul 2>&1
    reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\DeeMusic" /v "DisplayIcon" /t REG_SZ /d "!install_path!\\logo.ico" /f >nul 2>&1
    echo ✅ Added to Windows Programs list
)

:installation_complete
cls
echo.
echo     ╔══════════════════════════════════════════════════════════╗
echo     ║                 🎉 Installation Complete! 🎉             ║
echo     ╚══════════════════════════════════════════════════════════╝
echo.
echo ✅ DeeMusic v{version} has been successfully installed!
echo.
echo 📍 Installation Details:
echo    • Type: !install_type! Installation
if not "!install_type!"=="Portable" (
    echo    • Location: !install_path!
    echo    • Start Menu: Available
    if "!desktop!"=="y" echo    • Desktop: Shortcut created
)
echo    • Settings: %%AppData%%\\DeeMusic
echo.
echo 🚀 Getting Started:
if "!install_type!"=="Portable" (
    echo    • Run DeeMusic.exe to start the application
) else (
    echo    • Launch from Start Menu or Desktop shortcut
    echo    • Or run: !install_path!\\DeeMusic.exe
)
echo    • Configure your Deezer ARL token in Settings
echo    • Start downloading your favorite music!
echo.
echo 📖 Documentation:
echo    • README.txt - Basic usage guide
echo    • PERFORMANCE_TIPS.txt - Optimization guide
echo.
echo 🔧 Troubleshooting:
echo    • If antivirus blocks DeeMusic, add it to exclusions
echo    • For support, visit: https://github.com/IAmAnonUser/DeeMusic
echo.
echo Launching DeeMusic automatically...
timeout /t 2 /nobreak >nul
if "!install_type!"=="Portable" (
    start "" "DeeMusic.exe"
) else (
    start "" "!install_path!\\DeeMusic.exe"
)
echo.
echo Thank you for choosing DeeMusic! 🎵
echo Installation completed successfully. DeeMusic is now starting...
timeout /t 3 /nobreak >nul
goto :eof

:cancel
echo.
echo Installation cancelled by user.
pause
exit /b 0

:check_system_requirements
:: Check Windows version
for /f "tokens=4-5 delims=. " %%i in ('ver') do set VERSION=%%i.%%j
if "%VERSION%" lss "10.0" (
    echo ❌ Windows 10 or later required (detected: Windows %VERSION%^)
    exit /b 1
)

:: Check available disk space (approximate)
for /f "tokens=3" %%a in ('dir /-c "%SystemDrive%\\" ^| find "bytes free"') do set FREE_SPACE=%%a
if %FREE_SPACE% lss 104857600 (
    echo ❌ Insufficient disk space (need at least 100 MB^)
    exit /b 1
)

:: Check if .NET Framework is available (for PowerShell shortcuts)
powershell -Command "exit 0" >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ PowerShell not available (required for shortcut creation^)
    exit /b 1
)

exit /b 0
''')
    
    print("   ✅ install.bat (Advanced)")

def create_advanced_uninstaller_script(installer_dir: Path, version: str):
    """Create an advanced uninstaller script."""
    uninstaller_script = installer_dir / "uninstall.bat"
    with open(uninstaller_script, 'w', encoding='utf-8') as f:
        f.write(f'''@echo off
setlocal enabledelayedexpansion
title DeeMusic Uninstaller v{version}
color 0C
cls

echo.
echo     ╔══════════════════════════════════════════════════════════╗
echo     ║                DeeMusic Uninstaller v{version}              ║
echo     ╚══════════════════════════════════════════════════════════╝
echo.

:: Detect installation type
set "system_path=C:\\Program Files\\DeeMusic"
set "user_path=%LOCALAPPDATA%\\DeeMusic"
set "install_path="
set "install_type="

if exist "!system_path!\\DeeMusic.exe" (
    set "install_path=!system_path!"
    set "install_type=System"
) else if exist "!user_path!\\DeeMusic.exe" (
    set "install_path=!user_path!"
    set "install_type=User"
) else (
    echo ❌ DeeMusic installation not found in standard locations.
    echo    This uninstaller works for installations created by the DeeMusic installer.
    echo.
    echo 💡 For portable installations, simply delete the DeeMusic folder.
    echo.
    pause
    exit /b 1
)

echo 📍 Found DeeMusic installation:
echo    • Type: !install_type! Installation
echo    • Location: !install_path!
echo.

:: Automatic uninstallation
echo Proceeding with automatic uninstallation...

echo.
echo [1/4] Stopping DeeMusic processes...
taskkill /f /im "DeeMusic.exe" >nul 2>&1
echo ✅ Processes stopped

echo.
echo [2/4] Removing program files...
if exist "!install_path!" (
    rmdir /s /q "!install_path!" >nul 2>&1
    if exist "!install_path!" (
        echo ⚠️  Some files could not be removed (may be in use)
        echo    Location: !install_path!
    ) else (
        echo ✅ Program files removed
    )
) else (
    echo ✅ Program files already removed
)

echo.
echo [3/4] Removing shortcuts and registry entries...

:: Remove Start Menu shortcuts
if "!install_type!"=="System" (
    set "start_menu_path=%ProgramData%\\Microsoft\\Windows\\Start Menu\\Programs"
) else (
    set "start_menu_path=%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs"
)

if exist "!start_menu_path!\\DeeMusic.lnk" (
    del "!start_menu_path!\\DeeMusic.lnk" >nul 2>&1
    echo ✅ Start Menu shortcut removed
)

:: Remove Desktop shortcut
if exist "%USERPROFILE%\\Desktop\\DeeMusic.lnk" (
    del "%USERPROFILE%\\Desktop\\DeeMusic.lnk" >nul 2>&1
    echo ✅ Desktop shortcut removed
)

:: Remove from Windows Programs list (system installation)
if "!install_type!"=="System" (
    reg delete "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\DeeMusic" /f >nul 2>&1
    echo ✅ Removed from Windows Programs list
)

echo.
echo [4/4] User data and settings...
echo Preserving user settings and downloaded music...
echo ✅ User settings preserved

cls
echo.
echo     ╔══════════════════════════════════════════════════════════╗
echo     ║              🗑️  Uninstallation Complete! 🗑️             ║
echo     ╚══════════════════════════════════════════════════════════╝
echo.
echo ✅ DeeMusic has been successfully uninstalled.
echo.
echo 📋 Summary:
echo    • Program files: Removed
echo    • Shortcuts: Removed
echo    • Registry entries: Cleaned
if /i "!remove_data!"=="y" (
    echo    • User settings: Removed
) else (
    echo    • User settings: Preserved
)
echo.
echo 💭 We're sorry to see you go!
echo    If you encountered any issues, please let us know:
echo    https://github.com/IAmAnonUser/DeeMusic/issues
echo.
echo Thank you for using DeeMusic! 🎵
pause
''')
    
    print("   ✅ uninstall.bat (Advanced)")

def create_installation_guide(installer_dir: Path, version: str):
    """Create a comprehensive installation guide."""
    guide_path = installer_dir / "INSTALLATION_GUIDE.txt"
    with open(guide_path, 'w', encoding='utf-8') as f:
        f.write(f'''DeeMusic v{version} - Installation Guide
{'=' * 50}

QUICK START:
===========
1. Run install.bat as Administrator (recommended)
2. Choose your installation type
3. Follow the on-screen instructions
4. Launch DeeMusic and configure your Deezer ARL token

INSTALLATION TYPES:
==================

1. SYSTEM INSTALLATION (Recommended)
   • Location: C:\\Program Files\\DeeMusic
   • Available for all users
   • Requires Administrator privileges
   • Integrated with Windows (Start Menu, Programs list)
   • Professional installation

2. USER INSTALLATION
   • Location: %LOCALAPPDATA%\\DeeMusic
   • Available for current user only
   • No Administrator privileges required
   • Start Menu integration
   • Good for restricted environments

3. PORTABLE INSTALLATION
   • Location: Current directory
   • No system integration
   • No installation required
   • Fully portable - can be moved anywhere
   • Perfect for USB drives or temporary use

SYSTEM REQUIREMENTS:
===================
• Windows 10 or later (64-bit)
• 100 MB free disk space (minimum)
• Internet connection for music streaming
• PowerShell (for shortcut creation)

ANTIVIRUS CONSIDERATIONS:
========================
Some antivirus software may flag DeeMusic due to:
• Music downloading capabilities
• Network access requirements
• Executable compression techniques

This is a FALSE POSITIVE. DeeMusic is safe and open-source.

RECOMMENDED ACTIONS:
• Add DeeMusic.exe to antivirus exclusions
• Add installation folder to exclusions
• Temporarily disable real-time protection during installation

FIRST-TIME SETUP:
================
1. Launch DeeMusic
2. Go to Settings (gear icon)
3. Navigate to Deezer section
4. Enter your Deezer ARL token
5. Configure download preferences
6. Start enjoying music!

GETTING YOUR DEEZER ARL TOKEN:
=============================
1. Open your web browser
2. Go to deezer.com and log in
3. Open Developer Tools (F12)
4. Go to Application/Storage tab
5. Find Cookies for deezer.com
6. Copy the 'arl' cookie value
7. Paste it in DeeMusic settings

TROUBLESHOOTING:
===============

Problem: "Windows protected your PC" message
Solution: Click "More info" then "Run anyway"

Problem: Antivirus blocks DeeMusic
Solution: Add to exclusions or temporarily disable

Problem: DeeMusic won't start
Solution: 
• Check Windows Event Viewer for errors
• Try running as Administrator
• Reinstall Microsoft Visual C++ Redistributables

Problem: Downloads fail
Solution:
• Verify ARL token is correct and not expired
• Check internet connection
• Try different download quality settings

Problem: Slow performance
Solution:
• Read PERFORMANCE_TIPS.txt
• Close other applications
• Check available disk space

UNINSTALLATION:
==============
• System/User Installation: Run uninstall.bat
• Portable Installation: Delete the folder
• Manual: Remove shortcuts and registry entries

SUPPORT:
=======
• GitHub: https://github.com/IAmAnonUser/DeeMusic
• Issues: Report bugs and request features
• Documentation: Check the docs folder

LEGAL NOTICE:
============
DeeMusic is for personal use only. Users must comply with:
• Deezer's Terms of Service
• Local copyright laws
• Fair use guidelines

The software is provided "as-is" without warranty.

VERSION INFORMATION:
===================
Version: {version}
Build Date: {datetime.datetime.now().strftime('%Y-%m-%d')}
Type: Optimized Build
Size: ~46 MB

Thank you for choosing DeeMusic! 🎵
''')
    
    print("   ✅ INSTALLATION_GUIDE.txt")

def create_system_checker(installer_dir: Path):
    """Create a system requirements checker."""
    checker_script = installer_dir / "check_system.bat"
    with open(checker_script, 'w', encoding='utf-8') as f:
        f.write('''@echo off
title DeeMusic System Requirements Checker
color 0A
cls

echo.
echo     ╔══════════════════════════════════════════════════════════╗
echo     ║           DeeMusic System Requirements Checker          ║
echo     ╚══════════════════════════════════════════════════════════╝
echo.

echo Checking system compatibility...
echo.

:: Check Windows version
echo [1/6] Checking Windows version...
for /f "tokens=4-5 delims=. " %%i in ('ver') do set VERSION=%%i.%%j
echo Current Windows version: %VERSION%
if "%VERSION%" geq "10.0" (
    echo ✅ Windows version compatible
) else (
    echo ❌ Windows 10 or later required
    set "compatible=false"
)
echo.

:: Check architecture
echo [2/6] Checking system architecture...
if "%PROCESSOR_ARCHITECTURE%"=="AMD64" (
    echo ✅ 64-bit system detected
) else (
    echo ⚠️  32-bit system detected (64-bit recommended)
)
echo.

:: Check available disk space
echo [3/6] Checking available disk space...
for /f "tokens=3" %%a in ('dir /-c "%SystemDrive%\\" ^| find "bytes free"') do set FREE_SPACE=%%a
set /a FREE_SPACE_MB=%FREE_SPACE%/1048576 2>nul
if not defined FREE_SPACE_MB set FREE_SPACE_MB=0
if %FREE_SPACE_MB% geq 100 (
    echo ✅ Sufficient disk space available (%FREE_SPACE_MB% MB)
) else (
    echo ❌ Insufficient disk space (need at least 100 MB)
    set "compatible=false"
)
echo.

:: Check PowerShell
echo [4/6] Checking PowerShell availability...
powershell -Command "exit 0" >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ PowerShell available
) else (
    echo ❌ PowerShell not available (required for shortcuts)
    set "compatible=false"
)
echo.

:: Check .NET Framework
echo [5/6] Checking .NET Framework...
reg query "HKLM\\SOFTWARE\\Microsoft\\NET Framework Setup\\NDP\\v4\\Full" /v Release >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ .NET Framework 4.0+ detected
) else (
    echo ⚠️  .NET Framework status unclear (may affect some features)
)
echo.

:: Check internet connectivity
echo [6/6] Checking internet connectivity...
ping -n 1 google.com >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ Internet connection available
) else (
    echo ⚠️  Internet connection not detected (required for music streaming)
)
echo.

:: Summary
echo ╔══════════════════════════════════════════════════════════╗
echo ║                    COMPATIBILITY SUMMARY                 ║
echo ╚══════════════════════════════════════════════════════════╝
echo.
if not defined compatible (
    echo ✅ Your system meets all requirements for DeeMusic!
    echo    You can proceed with the installation.
) else (
    echo ❌ Your system does not meet some requirements.
    echo    DeeMusic may not work properly on this system.
)
echo.

echo 📋 System Information:
echo    • OS: Windows %VERSION%
echo    • Architecture: %PROCESSOR_ARCHITECTURE%
echo    • Free Space: %FREE_SPACE_MB% MB
echo    • PowerShell: Available
echo.

echo Press any key to close this window...
pause >nul
''')
    
    print("   ✅ check_system.bat")

def show_usage_instructions(version: str):
    """Show instructions for using the installer."""
    print(f"\n🎯 Distribution Instructions:")
    print("=" * 35)
    print("📤 To distribute DeeMusic:")
    print(f"1. Send users the 'DeeMusic_Installer_Optimized_v{version}.zip' file")
    print("2. Users extract the ZIP file")
    print("3. Users run 'install.bat' for guided installation")
    print("4. Alternative: Users can run 'check_system.bat' first to verify compatibility")
    
    print(f"\n📋 Installer Features:")
    print("✅ Three installation types (System/User/Portable)")
    print("✅ System requirements checking")
    print("✅ Antivirus compatibility warnings")
    print("✅ Professional Windows integration")
    print("✅ Advanced uninstaller included")
    print("✅ Comprehensive documentation")
    print("✅ User-friendly colored interface")
    print("✅ Registry integration for system installs")
    
    print(f"\n⚙️ Package Contents:")
    print("• DeeMusic.exe - Main application")
    print("• install.bat - Advanced installer")
    print("• uninstall.bat - Complete uninstaller")
    print("• check_system.bat - System compatibility checker")
    print("• INSTALLATION_GUIDE.txt - Comprehensive guide")
    print("• PERFORMANCE_TIPS.txt - Optimization guide")
    print("• README.txt - Basic documentation")
    print("• logo.ico - Application icon")

def main():
    """Main installer creation function."""
    print("DeeMusic Optimized Installer Creator")
    print("===================================")
    
    if create_optimized_installer():
        version = get_version()
        show_usage_instructions(version)
        print("\n🎉 Optimized installer creation completed!")
        print("📤 Ready for professional distribution to users.")
        print("\n💡 The installer package includes:")
        print("   • Advanced installation options")
        print("   • System requirements checking")
        print("   • Professional Windows integration")
        print("   • Complete uninstallation support")
        return 0
    else:
        print("\n❌ Optimized installer creation failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())