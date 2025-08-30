#!/usr/bin/env python3
"""
DeeMusic Installer Diagnostic Tool
Helps diagnose and fix common installer issues.
"""

import os
import sys
import subprocess
import zipfile
from pathlib import Path
import hashlib

def get_version():
    """Get version from centralized version.py file."""
    try:
        sys.path.insert(0, str(Path().absolute().parent))
        from version import __version__
        return __version__
    except ImportError:
        return "1.0.7"

def check_system_requirements():
    """Check if system meets requirements for DeeMusic."""
    print("🔍 Checking System Requirements...")
    print("=" * 40)
    
    issues = []
    
    # Check Windows version
    try:
        import platform
        version = platform.version()
        major_version = int(version.split('.')[0])
        if major_version < 10:
            issues.append("❌ Windows 10 or later required")
        else:
            print("✅ Windows version compatible")
    except:
        issues.append("⚠️  Could not determine Windows version")
    
    # Check disk space
    try:
        import shutil
        free_space = shutil.disk_usage('.').free
        free_space_mb = free_space / (1024 * 1024)
        if free_space_mb < 100:
            issues.append(f"❌ Insufficient disk space ({free_space_mb:.1f} MB available, need 100+ MB)")
        else:
            print(f"✅ Sufficient disk space ({free_space_mb:.1f} MB available)")
    except:
        issues.append("⚠️  Could not check disk space")
    
    # Check PowerShell
    try:
        result = subprocess.run(['powershell', '-Command', 'exit 0'], 
                              capture_output=True, timeout=5)
        if result.returncode == 0:
            print("✅ PowerShell available")
        else:
            issues.append("❌ PowerShell not available")
    except:
        issues.append("❌ PowerShell not available")
    
    return issues

def check_available_builds():
    """Check what builds are available."""
    print("\n🔍 Checking Available Builds...")
    print("=" * 35)
    
    builds = []
    
    # Check for standard build
    exe_path = Path("dist/DeeMusic.exe")
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        builds.append(f"✅ Standard build: {exe_path} ({size_mb:.1f} MB)")
    
    # Check for quick startup build
    quick_path = Path("dist/DeeMusic/DeeMusic.exe")
    if quick_path.exists():
        size_mb = quick_path.stat().st_size / (1024 * 1024)
        builds.append(f"✅ Quick startup build: {quick_path} ({size_mb:.1f} MB)")
    
    # Check for existing installers
    installer_patterns = [
        "dist/DeeMusic_Installer_*.zip",
        "dist/DeeMusic_*_Installer*.zip",
        "installer_output/DeeMusic_Setup_*.exe"
    ]
    
    for pattern in installer_patterns:
        for installer in Path().glob(pattern):
            size_mb = installer.stat().st_size / (1024 * 1024)
            builds.append(f"✅ Installer: {installer} ({size_mb:.1f} MB)")
    
    if not builds:
        print("❌ No builds found. Run a build script first:")
        print("   python tools/build_optimized.py")
        print("   python tools/create_optimized_installer.py")
    else:
        for build in builds:
            print(build)
    
    return len(builds) > 0

def check_installer_integrity(installer_path):
    """Check if installer ZIP is valid."""
    print(f"\n🔍 Checking Installer Integrity: {installer_path}")
    print("=" * 50)
    
    if not Path(installer_path).exists():
        print(f"❌ Installer not found: {installer_path}")
        return False
    
    try:
        with zipfile.ZipFile(installer_path, 'r') as zip_ref:
            # Test ZIP integrity
            bad_files = zip_ref.testzip()
            if bad_files:
                print(f"❌ Corrupted files in ZIP: {bad_files}")
                return False
            
            # List contents
            files = zip_ref.namelist()
            print(f"✅ ZIP file is valid ({len(files)} files)")
            
            # Check for essential files
            essential_files = ['DeeMusic.exe', 'install.bat']
            missing = [f for f in essential_files if not any(f in file for file in files)]
            
            if missing:
                print(f"⚠️  Missing essential files: {missing}")
            else:
                print("✅ All essential files present")
            
            # Show file list
            print("\n📋 Installer Contents:")
            for file in sorted(files):
                print(f"   • {file}")
            
            return True
            
    except zipfile.BadZipFile:
        print("❌ Invalid or corrupted ZIP file")
        return False
    except Exception as e:
        print(f"❌ Error checking installer: {e}")
        return False

def suggest_solutions(issues):
    """Suggest solutions based on detected issues."""
    print("\n💡 Suggested Solutions:")
    print("=" * 25)
    
    if not issues:
        print("✅ No system issues detected!")
        print("\nIf you're still having installer problems:")
        print("1. Check antivirus software (most common cause)")
        print("2. Try running installer as Administrator")
        print("3. Use portable installation instead")
        return
    
    for issue in issues:
        print(issue)
    
    print("\n🔧 Recommended Actions:")
    
    if any("Windows" in issue for issue in issues):
        print("• Upgrade to Windows 10 or later")
    
    if any("disk space" in issue for issue in issues):
        print("• Free up disk space (delete temporary files, empty recycle bin)")
    
    if any("PowerShell" in issue for issue in issues):
        print("• Install PowerShell from Microsoft Store")
        print("• Or use portable installation (no shortcuts needed)")

def create_emergency_installer():
    """Create a simple emergency installer if main ones fail."""
    print("\n🚑 Creating Emergency Installer...")
    print("=" * 35)
    
    exe_path = Path("dist/DeeMusic.exe")
    if not exe_path.exists():
        print("❌ No DeeMusic.exe found to create emergency installer")
        return False
    
    # Create simple emergency installer directory
    emergency_dir = Path("dist/DeeMusic_Emergency_Installer")
    emergency_dir.mkdir(exist_ok=True)
    
    # Copy executable
    import shutil
    shutil.copy2(exe_path, emergency_dir / "DeeMusic.exe")
    
    # Create simple run script
    run_script = emergency_dir / "RUN_DEEMUSIC.bat"
    with open(run_script, 'w') as f:
        f.write('''@echo off
title DeeMusic - Emergency Launcher
echo Starting DeeMusic...
echo.
echo If this is your first time running DeeMusic:
echo 1. Go to Settings (gear icon)
echo 2. Enter your Deezer ARL token
echo 3. Configure download preferences
echo.
start "" "DeeMusic.exe"
''')
    
    # Create simple instructions
    instructions = emergency_dir / "INSTRUCTIONS.txt"
    with open(instructions, 'w') as f:
        f.write('''DeeMusic Emergency Installation
==============================

This is a portable version of DeeMusic that requires no installation.

QUICK START:
1. Double-click "RUN_DEEMUSIC.bat" to start DeeMusic
2. Or double-click "DeeMusic.exe" directly

FIRST-TIME SETUP:
1. Launch DeeMusic
2. Click the Settings icon (gear)
3. Go to Deezer section
4. Enter your Deezer ARL token
5. Configure download preferences

GETTING ARL TOKEN:
1. Go to deezer.com in your browser
2. Log in to your account
3. Press F12 to open Developer Tools
4. Go to Application/Storage → Cookies → deezer.com
5. Find the 'arl' cookie and copy its value
6. Paste it in DeeMusic settings

TROUBLESHOOTING:
- If antivirus blocks DeeMusic, add it to exclusions
- If Windows shows security warning, click "More info" → "Run anyway"
- For support: https://github.com/IAmAnonUser/DeeMusic

This portable version stores all settings in the same folder.
You can move this entire folder anywhere on your system.
''')
    
    print(f"✅ Emergency installer created: {emergency_dir}")
    print("📋 Contents:")
    print("   • DeeMusic.exe - Main application")
    print("   • RUN_DEEMUSIC.bat - Simple launcher")
    print("   • INSTRUCTIONS.txt - Setup guide")
    
    return True

def main():
    """Main diagnostic function."""
    print("🔧 DeeMusic Installer Diagnostic Tool")
    print("=" * 40)
    print(f"Version: {get_version()}")
    print()
    
    # Check system requirements
    issues = check_system_requirements()
    
    # Check available builds
    has_builds = check_available_builds()
    
    # Check specific installer if provided
    if len(sys.argv) > 1:
        installer_path = sys.argv[1]
        check_installer_integrity(installer_path)
    
    # Suggest solutions
    suggest_solutions(issues)
    
    # Offer to create emergency installer
    if has_builds:
        print("\n🚑 Emergency Option:")
        create_emergency = input("Create emergency portable installer? (y/n): ").lower().strip()
        if create_emergency == 'y':
            create_emergency_installer()
    
    print("\n📞 Support Information:")
    print("=" * 22)
    print("• GitHub Issues: https://github.com/IAmAnonUser/DeeMusic/issues")
    print("• Documentation: Check docs/ folder")
    print("• Build Tools: Check tools/README.md")

if __name__ == "__main__":
    main()