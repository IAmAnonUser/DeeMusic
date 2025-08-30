@echo off
echo DeeMusic Build Tool
echo ==================
echo.
echo This will build a standalone DeeMusic executable
echo with zero dependencies.
echo.
pause

call build_standalone.bat

echo.
echo Build complete! Executable is in dist/DeeMusic.exe
pause