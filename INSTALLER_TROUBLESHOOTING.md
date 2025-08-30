# DeeMusic Installer Troubleshooting Guide

## 🚨 Common Installer Issues & Solutions

### Issue 1: "Windows protected your PC" Message
**Cause:** Windows SmartScreen blocking unsigned executable  
**Solution:**
1. Click "More info" on the warning dialog
2. Click "Run anyway" 
3. Or right-click installer → Properties → Unblock → OK

### Issue 2: Antivirus Software Blocking Installation
**Cause:** Music downloading capabilities trigger false positives  
**Solutions:**
1. **Temporary disable** real-time protection during installation
2. **Add to exclusions:**
   - Add the installer ZIP file
   - Add DeeMusic.exe after installation
   - Add installation folder (e.g., `C:\Program Files\DeeMusic`)
3. **Common antivirus steps:**
   - Windows Defender: Settings → Virus & threat protection → Exclusions
   - Avast: Settings → General → Exceptions
   - Norton: Settings → Antivirus → Scans and Risks → Exclusions

### Issue 3: "Access Denied" or Permission Errors
**Cause:** Insufficient privileges for system installation  
**Solutions:**
1. **Run as Administrator:** Right-click installer → "Run as administrator"
2. **Use User Installation:** Choose option 2 in installer (no admin required)
3. **Use Portable Installation:** Choose option 3 (no installation needed)

### Issue 4: Installer Won't Start or Crashes
**Cause:** Corrupted download or system compatibility  
**Solutions:**
1. **Re-download** installer from GitHub releases
2. **Check file integrity:** File should be ~80MB
3. **Run diagnostic tool:**
   ```bash
   python tools/diagnose_installer_issue.py path/to/installer.zip
   ```
4. **Check system requirements:**
   - Windows 10 or later
   - 100MB free space
   - PowerShell available

### Issue 5: Installation Completes but DeeMusic Won't Start
**Cause:** Missing dependencies or antivirus interference  
**Solutions:**
1. **Check Windows Event Viewer** for error details
2. **Install Visual C++ Redistributables:**
   - Download from Microsoft website
   - Install both x64 and x86 versions
3. **Run from command line** to see error messages:
   ```cmd
   cd "C:\Program Files\DeeMusic"
   DeeMusic.exe
   ```
4. **Try portable version** instead

## 🛠️ Alternative Installation Methods

### Method 1: Emergency Portable Installation
If installers fail, create a portable version:

1. **Build executable:**
   ```bash
   python tools/build_optimized.py
   ```

2. **Create emergency installer:**
   ```bash
   python tools/diagnose_installer_issue.py
   # Choose 'y' when prompted for emergency installer
   ```

3. **Use the portable version:**
   - Extract `dist/DeeMusic_Emergency_Installer/`
   - Run `RUN_DEEMUSIC.bat`

### Method 2: Manual Installation
1. **Extract installer ZIP** to temporary folder
2. **Copy DeeMusic.exe** to desired location:
   - System: `C:\Program Files\DeeMusic\`
   - User: `%LOCALAPPDATA%\DeeMusic\`
   - Portable: Any folder
3. **Create shortcuts manually:**
   - Right-click DeeMusic.exe → Send to → Desktop
   - Copy to Start Menu folder if desired

### Method 3: Build from Source
If pre-built installers don't work:

1. **Clone repository:**
   ```bash
   git clone https://github.com/IAmAnonUser/DeeMusic.git
   cd DeeMusic
   ```

2. **Setup environment:**
   ```bash
   python -m venv venv_py311
   venv_py311\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Build executable:**
   ```bash
   python tools/build_optimized.py
   ```

4. **Create installer:**
   ```bash
   python tools/create_optimized_installer.py
   ```

## 🔍 Diagnostic Commands

### Check System Compatibility
```bash
# Run system requirements checker
python tools/diagnose_installer_issue.py

# Check specific installer
python tools/diagnose_installer_issue.py path/to/installer.zip
```

### Check Available Builds
```bash
# List all available builds and installers
dir dist\DeeMusic*
dir installer_output\DeeMusic*
```

### Verify Installation
```bash
# Check if DeeMusic is properly installed
where DeeMusic.exe
# Or check specific locations:
dir "C:\Program Files\DeeMusic\DeeMusic.exe"
dir "%LOCALAPPDATA%\DeeMusic\DeeMusic.exe"
```

## 📋 Installation Types Explained

### 1. System Installation (Recommended)
- **Location:** `C:\Program Files\DeeMusic`
- **Requirements:** Administrator privileges
- **Features:** 
  - Available for all users
  - Start Menu integration
  - Windows Programs list entry
  - Professional uninstaller

### 2. User Installation
- **Location:** `%LOCALAPPDATA%\DeeMusic`
- **Requirements:** No admin privileges needed
- **Features:**
  - Current user only
  - Start Menu shortcuts
  - Easy uninstallation

### 3. Portable Installation
- **Location:** Any folder (current directory)
- **Requirements:** None
- **Features:**
  - No installation needed
  - Fully portable
  - Settings stored locally
  - Can run from USB drive

## 🚑 Emergency Solutions

### If All Installers Fail:
1. **Download source code** from GitHub
2. **Run directly from Python:**
   ```bash
   python run.py
   ```
3. **Use online alternatives** temporarily
4. **Contact support** with specific error messages

### Quick Portable Setup:
1. Download latest release
2. Extract ZIP file
3. Run `DeeMusic.exe` directly
4. No installation required!

## 📞 Getting Help

### Before Reporting Issues:
1. **Run diagnostic tool:** `python tools/diagnose_installer_issue.py`
2. **Check antivirus logs** for blocked files
3. **Try different installation type** (System/User/Portable)
4. **Test on different user account** if possible

### When Reporting Issues:
Include this information:
- Windows version (run `winver`)
- Antivirus software used
- Exact error messages
- Installation type attempted
- Output from diagnostic tool

### Support Channels:
- **GitHub Issues:** https://github.com/IAmAnonUser/DeeMusic/issues
- **Include logs:** Check `%AppData%\DeeMusic\logs\`
- **System info:** Run `msinfo32` for detailed system information

## ✅ Success Checklist

After successful installation:
- [ ] DeeMusic.exe launches without errors
- [ ] Settings dialog opens (gear icon)
- [ ] Can navigate between pages (Home, Search, etc.)
- [ ] No antivirus warnings during normal operation
- [ ] Shortcuts work properly (if created)

## 🔧 Advanced Troubleshooting

### Registry Issues (System Installation):
```cmd
# Check if DeeMusic is in Programs list
reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\DeeMusic"

# Remove if corrupted
reg delete "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\DeeMusic" /f
```

### PowerShell Issues:
```powershell
# Test PowerShell functionality
Get-ExecutionPolicy
# If restricted, run as admin:
Set-ExecutionPolicy RemoteSigned
```

### File Association Issues:
```cmd
# Check file associations
assoc .deemusic
ftype DeeMusic

# Reset if needed
assoc .deemusic=DeeMusic
ftype DeeMusic="C:\Program Files\DeeMusic\DeeMusic.exe" "%1"
```

Remember: Most installer issues are caused by antivirus software or insufficient permissions. Try the portable installation if other methods fail!