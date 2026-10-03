@echo off
rem Benoit Saint-Moulin
rem Traktor Bridge : portable build in a clean venv
setlocal
cd /d "%~dp0"

where python >nul 2>nul || (echo Python 3.11+ not found on PATH & pause & exit /b 1)

if not exist ".venv\Scripts\python.exe" (
    echo Creating the build environment in .venv ...
    python -m venv .venv || (pause & exit /b 1)
)
set PY=.venv\Scripts\python.exe

"%PY%" -m pip install --upgrade pip >nul
"%PY%" -m pip install PySide6 numpy scipy soundfile Pillow pyinstaller nuitka || (pause & exit /b 1)

"%PY%" build.py %* || (echo Build failed, see above. & pause & exit /b 1)

echo.
echo Done: dist\TraktorBridge\ and the zip next to it.
pause
