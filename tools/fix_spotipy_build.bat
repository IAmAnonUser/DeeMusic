@echo off
echo DeeMusic Spotipy Fix Builder
echo ===========================
echo.
echo This will rebuild DeeMusic with proper Spotipy support
echo to fix the "Missing Library" error.
echo.
pause

echo Installing/updating Spotipy...
pip install spotipy>=2.22.1

echo.
echo Building DeeMusic with Spotipy fix...
python build_standalone.py

echo.
echo Build complete! Check dist/DeeMusic.exe
pause