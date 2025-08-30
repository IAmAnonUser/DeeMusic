@echo off
echo DeeMusic Build Environment Test
echo ===============================
echo.
echo This will test if your environment is ready for building.
echo.

echo Testing Python environment...
python test_build_environment.py

if errorlevel 1 (
    echo.
    echo ERROR: Build environment test failed!
    echo.
    echo Common fixes:
    echo 1. Install missing dependencies: pip install -r ../requirements.txt
    echo 2. Run dependency installer: python install_dependencies.py
    echo 3. Make sure Python 3.11+ is installed
    echo.
    pause
    exit /b 1
)

echo.
echo ===== Environment Check Results =====
echo.
echo ✅ Python environment is ready
echo ✅ All required packages are installed
echo ✅ PyInstaller is working
echo ✅ Critical imports are available
echo.
echo You can now run:
echo - BuildTool.bat (create executable)
echo - CreateInstaller.bat (create installer)
echo - BuildAndPackage.bat (create both)
echo.
pause