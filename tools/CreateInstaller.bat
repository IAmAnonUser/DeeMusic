@echo off
echo DeeMusic Installer Creator
echo =========================
echo.
echo This will create a professional Windows installer (.exe)
echo for DeeMusic with zero dependencies.
echo.

REM Check if executable exists
if not exist "dist\DeeMusic.exe" (
    echo WARNING: DeeMusic.exe not found in dist folder!
    echo.
    echo Building standalone executable first...
    echo.
    call BuildTool.bat
    echo.
)

REM Check again after potential build
if not exist "dist\DeeMusic.exe" (
    echo ERROR: Could not create DeeMusic.exe!
    echo Please check the build process and try again.
    echo.
    pause
    exit /b 1
)

echo Found DeeMusic.exe - proceeding with installer creation...
echo.

call create_installer.bat

echo.
echo Installer creation complete!
echo Check the installer_output folder for the installer.
pause