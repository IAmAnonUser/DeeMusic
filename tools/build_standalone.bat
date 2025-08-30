@echo off
echo DeeMusic Standalone Builder
echo ==========================
echo.
echo This will create a completely self-contained executable
echo with ZERO dependencies on the target computer.
echo.
pause

echo Step 1: Installing dependencies...
python install_dependencies.py

if errorlevel 1 (
    echo.
    echo ❌ Dependency installation failed!
    pause
    exit /b 1
)

echo.
echo Step 2: Testing build environment...
python test_build_environment.py

if errorlevel 1 (
    echo.
    echo ❌ Build environment test failed!
    echo Please fix the issues above before building.
    pause
    exit /b 1
)

echo.
echo Step 3: Building standalone executable...
python build_standalone.py

if errorlevel 1 (
    echo.
    echo ❌ Build failed!
    pause
    exit /b 1
)

echo.
echo ✅ Build completed successfully!
echo.
echo 📁 Executable location: ..\dist\DeeMusic.exe
echo 📏 This is a completely standalone executable
echo 🚀 No Python or external dependencies required!
echo.
pause