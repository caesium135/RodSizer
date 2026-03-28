@echo off
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ==================================================
echo       Nanorod Detector 2.0 - Launcher
echo ==================================================
echo.

set "PY_EXE="

REM --- 1. Try 'python' command ---
python --version >nul 2>&1
if %errorlevel% equ 0 set "PY_EXE=python"
if defined PY_EXE goto FOUND_PYTHON

REM --- 2. Try 'py' launcher ---
py --version >nul 2>&1
if !errorlevel! equ 0 set "PY_EXE=py"
if defined PY_EXE goto FOUND_PYTHON

REM --- 3. Try Auto-Detect Common Paths ---
if exist "C:\Python39\python.exe" set "PY_EXE=C:\Python39\python.exe" & goto FOUND_PYTHON
if exist "C:\Python310\python.exe" set "PY_EXE=C:\Python310\python.exe" & goto FOUND_PYTHON
if exist "C:\Python311\python.exe" set "PY_EXE=C:\Python311\python.exe" & goto FOUND_PYTHON
if exist "C:\Program Files\Python39\python.exe" set "PY_EXE=C:\Program Files\Python39\python.exe" & goto FOUND_PYTHON
if exist "C:\Program Files\Python310\python.exe" set "PY_EXE=C:\Program Files\Python310\python.exe" & goto FOUND_PYTHON
if exist "C:\Program Files\Python311\python.exe" set "PY_EXE=C:\Program Files\Python311\python.exe" & goto FOUND_PYTHON

REM --- 4. User Input Fallback ---
:ASK_USER
echo.
echo [ERROR] Could not find Python automatically.
echo.
echo Please locate your 'python.exe' file.
echo TIP: Look in "C:\Program Files\Python3x" or "AppData\Local\Programs\Python"
echo.
echo IMPORTANT: Drag the FILE, not a shortcut.
echo.
set /p "PY_EXE=Drag and Drop python.exe here and press Enter: "
set "PY_EXE=!PY_EXE:"=!"

REM Validate Shortcut
echo "!PY_EXE!" | findstr /i ".lnk" >nul
if %errorlevel% equ 0 (
    echo.
    echo [ERROR] You provided a Shortcut (.lnk).
    echo Please use the real python.exe.
    goto ASK_USER
)

:FOUND_PYTHON
echo.
echo [INFO] Using Python: "!PY_EXE!"

REM Verify
"!PY_EXE!" --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [CRITICAL ERROR] Selected python path is invalid.
    pause
    exit /b 1
)

REM --- 5. Setup Virtual Environment ---
if exist ".venv" goto ACTIVATE_VENV
echo.
echo [First Run] Setting up Python environment...
"!PY_EXE!" -m venv .venv

REM Clear screen to focus attention
cls
echo ==================================================================
echo       FIRST RUN SETUP - INSTALLING DEPENDENCIES
echo ==================================================================
echo.
echo    Downloading: OpenCV, NumPy, FastAPI, Uvicorn, and others...
echo.
echo    PLEASE WAIT: This typically takes 1-3 minutes.
echo    You will see download progress below.
echo.
echo    (Do not close this window)
echo.
echo ==================================================================
echo.

REM Give user 2 seconds to read before text flies by
timeout /t 2 >nul

".venv\Scripts\python" -m pip install -r backend\requirements.txt

:ACTIVATE_VENV
echo Activating environment...

REM --- 6. Open Browser ---
echo.
echo Starting Server on PORT 8501...
echo The browser will open in 10 seconds...
echo.
echo IF PAGE FAILS TO LOAD:
echo 1. Keep this window open.
echo 2. Open Chrome/Edge and go to: http://127.0.0.1:8501
echo.

start "" /b cmd /c "timeout /t 10 >nul && start "" "http://127.0.0.1:8501""

REM --- 7. Run Server ---
echo Close this window to stop the app.
cd backend
..\.venv\Scripts\python -m uvicorn main:app --reload --host 127.0.0.1 --port 8501

pause
