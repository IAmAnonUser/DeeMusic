@echo off
echo DeeMusic Complete Build and Package Tool
echo ========================================
echo.
echo This will:
echo 1. Build a standalone DeeMusic executable
echo 2. Create a professional Windows installer
echo 3. Package everything for distribution
echo.
echo The entire process may take 5-10 minutes.
echo.
pause

echo.
echo ===== STEP 1: Building Standalone Executable =====
echo.
call BuildTool.bat

if not exist "dist\DeeMusic.exe" (
    echo.
    echo ERROR: Build failed! DeeMusic.exe was not created.
    echo Please check the build logs above for errors.
    echo.
    pause
    exit /b 1
)

echo.
echo ===== STEP 2: Creating Windows Installer =====
echo.
call create_installer.bat

echo.
echo ===== STEP 3: Build Summary =====
echo.

if exist "dist\DeeMusic.exe" (
    for %%I in ("dist\DeeMusic.exe") do echo ✅ Standalone executable: dist\DeeMusic.exe (%%~zI bytes)
) else (
    echo ❌ Standalone executable: FAILED
)

if exist "installer_output\DeeMusic_Setup_*.exe" (
    echo ✅ Windows installer: Created in installer_output\
) else (
    echo ❌ Windows installer: FAILED
)

echo.
echo ===== DISTRIBUTION FILES =====
echo.
echo Ready to distribute:
echo - dist\DeeMusic.exe (standalone executable)
echo - installer_output\DeeMusic_Setup_*.exe (installer)
echo.
echo Both files are completely standalone and require
echo no additional dependencies on target computers.
echo.
pause