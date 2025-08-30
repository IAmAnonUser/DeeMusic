# How to Build DeeMusic

All build tools are now in the `tools/` folder. Navigate to the tools folder and use these batch files:

## Quick Start

1. **Open Command Prompt or PowerShell**
2. **Navigate to tools folder**: `cd tools`
3. **Choose your build option below**

## Build Options

### 🔧 Create Standalone Executable Only
```cmd
BuildTool.bat
```
- Creates: `dist/DeeMusic.exe` (standalone executable)
- Time: ~3-5 minutes
- Size: ~60-90 MB

### 📦 Create Installer Only
```cmd
CreateInstaller.bat
```
- Creates: `installer_output/DeeMusic_Setup_v*.exe` (Windows installer)
- Automatically builds executable first if needed
- Time: ~5-7 minutes

### 🚀 Build Everything (Recommended)
```cmd
BuildAndPackage.bat
```
- Creates both executable AND installer
- Complete build pipeline
- Time: ~5-10 minutes
- Best for distribution

### 🧪 Test Environment First
```cmd
TestBuild.bat
```
- Verifies your Python environment is ready
- Checks all dependencies are installed
- Run this first if you have issues

## Output Files

After building, you'll find:
- **`dist/DeeMusic.exe`** - Standalone executable (no dependencies needed)
- **`installer_output/DeeMusic_Setup_v*.exe`** - Professional Windows installer

Both files are completely standalone and work on any Windows 10/11 computer without requiring Python or any additional software.

## Troubleshooting

If builds fail:
1. Run `TestBuild.bat` to check your environment
2. Install missing dependencies: `pip install -r ../requirements.txt`
3. Make sure you're in the `tools/` folder when running batch files

## Distribution

The created files are ready for distribution:
- Share `DeeMusic.exe` for users who want just the app
- Share the installer for users who want a professional installation experience