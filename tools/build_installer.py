#!/usr/bin/env python3
"""
Build Windows installer for DeeMusic using Inno Setup
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def find_inno_setup():
    """Find Inno Setup compiler on the system."""
    possible_paths = [
        "C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe",
        "C:\\Program Files\\Inno Setup 6\\ISCC.exe", 
        "C:\\Program Files (x86)\\Inno Setup 5\\ISCC.exe",
        "C:\\Program Files\\Inno Setup 5\\ISCC.exe",
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    # Try to find in PATH
    try:
        result = subprocess.run(['where', 'ISCC.exe'], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip().split('\n')[0]
    except Exception:
        pass
    
    return None

def check_prerequisites():
    """Check if all required files exist."""
    required_files = [
        "dist/DeeMusic.exe",
        "src/ui/assets/logo.ico",
        "README.md",
        "tools/installer.iss"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if missing_files:
        print("❌ Missing required files:")
        for file_path in missing_files:
            print(f"   - {file_path}")
        return False
    
    return True

def create_installer():
    """Create the Windows installer."""
    print("🏗️ DeeMusic Windows Installer Builder")
    print("=" * 50)
    
    # Check prerequisites
    print("📋 Checking prerequisites...")
    if not check_prerequisites():
        print("\n💡 Make sure you have:")
        print("   1. Built the executable: python build.py")
        print("   2. All required files in place")
        return False
    
    print("✅ All required files found")
    
    # Find Inno Setup
    print("\n🔍 Looking for Inno Setup...")
    inno_path = find_inno_setup()
    
    if not inno_path:
        print("❌ Inno Setup not found!")
        print("\n📥 To install Inno Setup:")
        print("1. Download from: https://jrsoftware.org/isdl.php")
        print("2. Install Inno Setup 6 (recommended)")
        print("3. Run this script again")
        print("\n🔧 Manual alternative:")
        print("1. Open installer.iss in Inno Setup")
        print("2. Click Build > Compile")
        return False
    
    print(f"✅ Found Inno Setup: {inno_path}")
    
    # Create output directory
    output_dir = Path("installer_output")
    output_dir.mkdir(exist_ok=True)
    
    # Build installer
    print(f"\n🔨 Building installer...")
    try:
        result = subprocess.run([
            inno_path,
            "tools/installer.iss"
        ], capture_output=True, text=True, cwd=os.getcwd())
        
        if result.returncode == 0:
            print("✅ Installer built successfully!")
            
            # Find the generated installer
            installer_files = list(output_dir.glob("DeeMusic_Setup_*.exe"))
            if installer_files:
                installer_file = installer_files[0]
                file_size = installer_file.stat().st_size / (1024 * 1024)  # MB
                print(f"📦 Installer: {installer_file}")
                print(f"📏 Size: {file_size:.1f} MB")
                
                # Show what the installer includes
                print(f"\n📋 Installer includes:")
                print(f"   ✅ DeeMusic.exe (main application)")
                print(f"   ✅ Application icon")
                print(f"   ✅ README documentation")
                print(f"   ✅ Start Menu shortcuts")
                print(f"   ✅ Uninstaller")
                print(f"   ✅ Optional desktop shortcut")
                print(f"   ✅ Optional file associations")
                
                return True
            else:
                print("❌ Installer file not found in output directory")
                return False
        else:
            print("❌ Error building installer:")
            print(result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Error running Inno Setup: {e}")
        return False

def show_installer_info():
    """Show information about the installer."""
    print("\n🎯 Installer Features:")
    print("=" * 30)
    print("✅ Professional Windows installer (.exe)")
    print("✅ Modern wizard-style interface")
    print("✅ Installs to Program Files")
    print("✅ Creates Start Menu shortcuts")
    print("✅ Optional desktop shortcut")
    print("✅ Optional file associations (.mp3, .flac, .m4a)")
    print("✅ Proper uninstaller")
    print("✅ Settings cleanup on uninstall")
    print("✅ Uses application icon throughout")
    print("✅ Supports Windows 7-11")
    print("✅ x64 architecture")
    
    print("\n📋 Installation Process:")
    print("1. User runs DeeMusic_Setup_v1.0.0.exe")
    print("2. Installer guides through setup")
    print("3. Application installed to C:\\Program Files\\DeeMusic")
    print("4. Shortcuts created as selected")
    print("5. Settings stored in %AppData%\\DeeMusic")

if __name__ == "__main__":
    if create_installer():
        show_installer_info()
        print("\n🎉 Installer creation completed successfully!")
        print("📤 You can now distribute the installer to users.")
    else:
        print("\n❌ Installer creation failed!")
        sys.exit(1) 