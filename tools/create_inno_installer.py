#!/usr/bin/env python3
"""
DeeMusic Inno Setup Installer Creator
Creates a Windows installer using Inno Setup with dynamic version.
"""

import os
import sys
import subprocess
from pathlib import Path

def get_version():
    """Get version from centralized version.py file."""
    try:
        # Import version from the root directory
        sys.path.insert(0, str(Path().absolute().parent))
        from version import __version__
        return __version__
    except ImportError:
        # Fallback if version.py doesn't exist
        return "1.0.7"

def create_dynamic_installer_script():
    """Create an installer script with dynamic version."""
    version = get_version()
    
    # Read the template installer script
    template_path = Path("installer.iss")
    if not template_path.exists():
        print("❌ installer.iss template not found!")
        return False
    
    # Read and update the template
    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace the version
    content = content.replace('#define MyAppVersion "1.0.7"', f'#define MyAppVersion "{version}"')
    
    # Create the dynamic installer script
    dynamic_script = Path("installer_dynamic.iss")
    with open(dynamic_script, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Created dynamic installer script with version {version}")
    return True

def create_installer():
    """Create Windows installer using Inno Setup."""
    print("📦 DeeMusic Inno Setup Installer Creator")
    print("========================================")
    
    version = get_version()
    print(f"🏷️  Version: {version}")
    
    # Check if DeeMusic.exe exists and verify it's standalone
    exe_path = Path("dist/DeeMusic.exe")
    if not exe_path.exists():
        print("❌ DeeMusic.exe not found in tools/dist folder!")
        print("   Run 'python tools/build_standalone.py' first for zero-dependency deployment.")
        return False
    
    # Verify executable is standalone (should be 80-120MB with embedded Python)
    size_mb = exe_path.stat().st_size / (1024*1024)
    print(f"✅ DeeMusic.exe found ({size_mb:.1f} MB)")
    
    if size_mb < 50:
        print("⚠️  WARNING: Executable is too small to be standalone!")
        print("   Standalone builds should be 80-120MB with embedded Python runtime.")
        print("   Please use 'python tools/build_standalone.py' for zero-dependency deployment.")
        print("   Current build may require Python installation on target computers.")
    elif size_mb > 200:
        print("⚠️  WARNING: Executable is unusually large!")
        print("   This may indicate build issues or unnecessary dependencies.")
    else:
        print("✅ Executable size indicates standalone build with embedded dependencies")
    
    # Create dynamic installer script
    if not create_dynamic_installer_script():
        return False
    
    # Try to compile with Inno Setup
    inno_paths = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        "ISCC.exe"  # If in PATH
    ]
    
    inno_compiler = None
    for path in inno_paths:
        if Path(path).exists() or path == "ISCC.exe":
            inno_compiler = path
            break
    
    if not inno_compiler:
        print("⚠️  Inno Setup compiler not found!")
        print("   Please install Inno Setup 6 or add ISCC.exe to PATH")
        print("   Download from: https://jrsoftware.org/isdl.php")
        print(f"✅ Dynamic installer script created: installer_dynamic.iss")
        return True
    
    # Compile the installer
    try:
        print(f"🔨 Compiling installer with {inno_compiler}...")
        result = subprocess.run([
            inno_compiler,
            "installer_dynamic.iss"
        ], capture_output=True, text=True, cwd=Path().absolute())
        
        if result.returncode == 0:
            output_file = Path(f"installer_output/DeeMusic_Setup_v{version}.exe")
            if output_file.exists():
                size_mb = output_file.stat().st_size / (1024 * 1024)
                print(f"✅ Installer created successfully!")
                print(f"📦 Output: {output_file} ({size_mb:.1f} MB)")
            else:
                print("✅ Compilation completed, check installer_output folder")
        else:
            print("❌ Compilation failed!")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return False
            
    except Exception as e:
        print(f"❌ Error running Inno Setup: {e}")
        return False
    
    return True

def main():
    """Main installer creation function."""
    if create_installer():
        print("\n🎉 Inno Setup installer creation completed!")
        return 0
    else:
        print("\n💥 Installer creation failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())