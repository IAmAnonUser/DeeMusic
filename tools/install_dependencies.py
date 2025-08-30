#!/usr/bin/env python3
"""
DeeMusic Dependency Installer
Ensures all required packages are installed for building.
"""

import sys
import subprocess
from pathlib import Path

def install_requirements():
    """Install all requirements from requirements.txt."""
    print("📦 Installing DeeMusic dependencies...")
    
    # Get path to requirements.txt (one level up from tools/)
    req_file = Path(__file__).parent.parent / 'requirements.txt'
    
    if not req_file.exists():
        print(f"❌ Requirements file not found: {req_file}")
        return False
    
    try:
        subprocess.check_call([
            sys.executable, '-m', 'pip', 'install', '-r', str(req_file)
        ])
        print("✅ Successfully installed all requirements!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install requirements: {e}")
        return False

def verify_critical_packages():
    """Verify critical packages are available."""
    print("\n🔍 Verifying critical packages...")
    
    critical_packages = [
        ('PyQt6', 'PyQt6'),
        ('PyInstaller', 'PyInstaller'),
        ('pycryptodome', 'Cryptodome'),
        ('spotipy', 'spotipy'),
    ]
    
    missing = []
    for package_name, import_name in critical_packages:
        try:
            __import__(import_name)
            print(f"✅ {package_name}")
        except ImportError:
            print(f"❌ {package_name} - MISSING")
            missing.append(package_name)
    
    if missing:
        print(f"\n⚠️  Installing missing critical packages: {', '.join(missing)}")
        try:
            subprocess.check_call([
                sys.executable, '-m', 'pip', 'install'
            ] + missing)
            print("✅ Critical packages installed!")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install critical packages: {e}")
            return False
    
    print("✅ All critical packages verified!")
    return True

def main():
    """Main function."""
    print("DeeMusic Dependency Installer")
    print("=============================")
    
    # Install from requirements.txt
    if not install_requirements():
        return 1
    
    # Verify critical packages
    if not verify_critical_packages():
        return 1
    
    print("\n🎉 All dependencies ready for building!")
    print("You can now run: python build_standalone.py")
    return 0

if __name__ == "__main__":
    sys.exit(main())