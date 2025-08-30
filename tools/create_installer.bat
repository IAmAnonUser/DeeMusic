@echo off
setlocal enabledelayedexpansion
echo DeeMusic Installer Creator
echo =========================
echo.
echo This will create a professional Windows installer
echo using Inno Setup.
echo.

REM Check if executable exists
if not exist "dist\DeeMusic.exe" (
    echo ERROR: DeeMusic.exe not found in tools\dist folder!
    echo.
    echo You need to build the executable first:
    echo   1. Run: build_standalone.bat
    echo   2. Then run this installer creator
    echo.
    pause
    exit /b 1
)

echo Step 1: Verifying standalone executable...
for %%I in ("dist\DeeMusic.exe") do (
    echo Found DeeMusic.exe: %%~zI bytes
    set /a size_mb=%%~zI/1048576
    echo Size: !size_mb! MB
    if !size_mb! LSS 50 (
        echo WARNING: Executable may not be standalone ^(too small^)
        echo Please use build_standalone.py for zero-dependency deployment
    ) else (
        echo ✅ Size indicates standalone build with embedded dependencies
    )
)

echo.
echo Step 2: Creating installer with Inno Setup...
python create_inno_installer.py

if errorlevel 1 (
    echo.
    echo ERROR: Installer creation failed!
    echo.
    echo Common issues:
    echo - Inno Setup not installed
    echo - Missing DeeMusic.exe
    echo - Permission issues
    echo.
    echo To install Inno Setup:
    echo Download from: https://jrsoftware.org/isdl.php
    echo.
    pause
    exit /b 1
)

echo.
echo SUCCESS: Installer created successfully!
echo.
echo The installer is located in the installer_output folder.
echo You can now distribute the installer to users.
echo.
pause