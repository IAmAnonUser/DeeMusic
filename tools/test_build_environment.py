#!/usr/bin/env python3
"""
Test Build Environment
Quick test to verify all dependencies are available for building.
"""

import sys

def test_imports():
    """Test all critical imports."""
    print("Testing critical imports...")
    
    tests = [
        ('PyQt6', lambda: __import__('PyQt6')),
        ('PyQt6.QtCore', lambda: __import__('PyQt6.QtCore')),
        ('PyQt6.QtWidgets', lambda: __import__('PyQt6.QtWidgets')),
        ('PyInstaller', lambda: __import__('PyInstaller')),
        ('Cryptodome.Cipher.Blowfish', lambda: __import__('Cryptodome.Cipher.Blowfish')),
        ('spotipy', lambda: __import__('spotipy')),
        ('requests', lambda: __import__('requests')),
        ('mutagen', lambda: __import__('mutagen')),
        ('aiohttp', lambda: __import__('aiohttp')),
        ('qasync', lambda: __import__('qasync')),
    ]
    
    failed = []
    for name, test_func in tests:
        try:
            test_func()
            print(f"✅ {name}")
        except ImportError as e:
            print(f"❌ {name} - {e}")
            failed.append(name)
    
    return len(failed) == 0, failed

def main():
    """Main test function."""
    print("DeeMusic Build Environment Test")
    print("===============================")
    print(f"Python version: {sys.version}")
    print()
    
    success, failed = test_imports()
    
    print()
    if success:
        print("🎉 Build environment is ready!")
        print("You can proceed with building the standalone executable.")
        return 0
    else:
        print(f"❌ Build environment has issues!")
        print(f"Failed imports: {', '.join(failed)}")
        print()
        print("To fix:")
        print("1. Run: python install_dependencies.py")
        print("2. Or manually install: pip install " + " ".join(failed))
        return 1

if __name__ == "__main__":
    sys.exit(main())