@echo off
setlocal

title MWO Match Stats

rem ------------------------------------------------------------------
rem Find a working Python command. Some machines only have "py", not
rem "python" on PATH, so try both before giving up.
rem ------------------------------------------------------------------
set "PYCMD="

python --version >nul 2>&1
if not errorlevel 1 set "PYCMD=python"

if "%PYCMD%"=="" (
    py --version >nul 2>&1
    if not errorlevel 1 set "PYCMD=py"
)

if "%PYCMD%"=="" (
    echo.
    echo ============================================================
    echo   Python isn't installed yet - opening the download page...
    echo ============================================================
    echo.
    echo   1. Click the big yellow "Download Python" button.
    echo   2. Run the installer once it downloads.
    echo   3. IMPORTANT: on the installer's first screen, check the box
    echo      that says "Add python.exe to PATH" before clicking Install.
    echo   4. When it finishes, come back and double-click start.bat again.
    echo.
    start "" https://www.python.org/downloads/
    echo Press any key to close this window.
    pause >nul
    exit /b 1
)

echo.
echo Checking everything the app needs is installed - this can take
echo a minute the first time, and is instant after that...
echo.
%PYCMD% -m pip install -q -r requirements.txt
if errorlevel 1 (
    echo.
    echo ============================================================
    echo   Something went wrong installing what the app needs.
    echo   Scroll up to see the error, or check the README's
    echo   Troubleshooting section.
    echo ============================================================
    echo.
    echo Press any key to close this window.
    pause >nul
    exit /b 1
)

echo.
echo Starting the app - your browser will open automatically in a
echo few seconds. Leave THIS window open while you're using it; closing
echo it stops the app.
echo.

start "" /min cmd /c "timeout /t 3 /nobreak >nul & start http://localhost:8000"
%PYCMD% -m uvicorn app.main:app --port 8000

echo.
echo The app has stopped. Press any key to close this window.
pause >nul
