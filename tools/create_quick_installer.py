#!/usr/bin/env python3
"""
DeeMusic Quick Startup Installer Creator
Creates an installer package for the quick-startup version.
"""

import os
import shutil
import zipfile
from pathlib import Path

def get_version():
    """Get version from centralized version.py file."""
    try:
        # Import version from the root directory
        import sys
        sys.path.insert(0, str(Path().absolute().parent))
        from version import __version__
        return __version__
    except ImportError:
        # Fallback if version.py doesn't exist
        return "1.0.7"

def create_installer():
    """Create installer package for quick startup version."""
    version = get_version()
    
    print("📦 DeeMusic Quick Startup Installer Creator")
    print("===========================================")
    print(f"🏷️  Version: {version}")
    
    # Check if build exists
    dist_dir = Path('dist/DeeMusic')
    exe_path = dist_dir / 'DeeMusic.exe'
    
    if not exe_path.exists():
        print("❌ DeeMusic.exe not found. Run 'python tools/build_quick_startup.py' first.")
        return False
    
    # Get file size
    total_size = sum(f.stat().st_size for f in dist_dir.rglob('*') if f.is_file())
    total_size_mb = total_size / (1024 * 1024)
    print(f"✅ DeeMusic distribution found ({total_size_mb:.1f} MB)")
    
    # Create installer directory
    installer_dir = Path('dist/DeeMusic_QuickStart_Installer')
    if installer_dir.exists():
        shutil.rmtree(installer_dir)
        print("🧹 Cleaned existing installer directory")
    
    installer_dir.mkdir(parents=True)
    print(f"📁 Creating installer in {installer_dir}")
    
    # Copy the entire DeeMusic distribution
    app_dir = installer_dir / 'DeeMusic'
    shutil.copytree(dist_dir, app_dir)
    print("   ✅ DeeMusic application")
    
    # Copy assets
    assets_to_copy = {
        'src/ui/assets/logo.ico': 'logo.ico',
        'dist/DeeMusic_Launcher.bat': 'DeeMusic_Launcher.bat'
    }
    
    for src, dst in assets_to_copy.items():
        src_path = Path(src)
        if src_path.exists():
            shutil.copy2(src_path, installer_dir / dst)
            print(f"   ✅ {dst}")
    
    # Create ZIP package
    zip_name = f'DeeMusic_QuickStart_v{version}.zip'
    zip_path = Path('dist') / zip_name
    
    print(f"\\n📦 Creating installer package: {zip_path}")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipf:
        for file_path in installer_dir.rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(installer_dir)
                zipf.write(file_path, arcname)
    
    # Get final sizes
    installer_size = sum(f.stat().st_size for f in installer_dir.rglob('*') if f.is_file())
    installer_size_mb = installer_size / (1024 * 1024)
    
    zip_size = zip_path.stat().st_size
    zip_size_mb = zip_size / (1024 * 1024)
    
    print(f"\\n✅ Quick startup installer created successfully!")
    print(f"📁 Installer directory: {installer_dir} ({installer_size_mb:.1f} MB)")
    print(f"📦 Installer package: {zip_path} ({zip_size_mb:.1f} MB)")
    
    return True

def main():
    """Main installer creation function."""
    if create_installer():
        print("\\n🎉 Quick startup installer creation completed!")
        print("📤 Ready for professional distribution to users.")
        return 0
    else:
        print("\\n💥 Installer creation failed!")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())