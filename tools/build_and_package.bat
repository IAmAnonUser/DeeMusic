@echo off
echo DeeMusic Complete Build and Package Tool
echo ========================================
echo.
echo This will:
echo 1. Build the standalone executable
echo 2. Create the professional installer
echo 3. Package everything for distribution
echo.
pause

echo ============================================
echo STEP 1: Building Standalone Executable
echo ============================================
echo.

call build_standalone.bat

if errorlevel 1 (
    echo.
    echo ERROR: Executable build failed!
    echo Cannot proceed with installer creation.
    pause
    exit /b 1
)

echo.
echo ============================================
echo STEP 2: Creating Professional Installer
echo ============================================
echo.

call create_installer.bat

if errorlevel 1 (
    echo.
    echo WARNING: Installer creation failed!
    echo The standalone executable is still available in dist\DeeMusic.exe
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================
echo STEP 3: Build Summary
echo ============================================
echo.

REM Show file sizes and locations
if exist "..\dist\DeeMusic.exe" (
    for %%I in ("..\dist\DeeMusic.exe") do echo [OK] Standalone Executable: ..\dist\DeeMusic.exe (%%~zI bytes)
) else (
    echo [ERROR] Standalone executable not found!
)

if exist "installer_output\DeeMusic_Setup_*.exe" (
    for %%I in ("installer_output\DeeMusic_Setup_*.exe") do echo [OK] Professional Installer: %%I (%%~zI bytes)
) else (
    echo [WARNING] Professional installer not found
)

echo.
echo ============================================
echo Distribution Files Ready
echo ============================================
echo.
echo For End Users (Portable):
echo   - Distribute: ..\dist\DeeMusic.exe
echo   - Single file, no installation needed
echo.
echo For End Users (Traditional Install):
echo   - Distribute: installer_output\DeeMusic_Setup_v*.exe  
echo   - Professional Windows installer
echo.
echo Both files are completely standalone and require
echo NO Python or external dependencies!
echo.
pause