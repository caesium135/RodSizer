@echo off
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ==================================================
echo       Nanorod Detector 2.0 - DEBUG & REPAIR
echo ==================================================
echo.

set "PY_EXE="

REM --- 1. Find Python ---
python --version >nul 2>&1
if %errorlevel% equ 0 set "PY_EXE=python"
if defined PY_EXE goto FOUND_PYTHON

py --version >nul 2>&1
if !errorlevel! equ 0 set "PY_EXE=py"
if defined PY_EXE goto FOUND_PYTHON

REM Auto-Detect
if exist "C:\Python39\python.exe" set "PY_EXE=C:\Python39\python.exe" & goto FOUND_PYTHON
if exist "C:\Python310\python.exe" set "PY_EXE=C:\Python310\python.exe" & goto FOUND_PYTHON
if exist "C:\Python311\python.exe" set "PY_EXE=C:\Python311\python.exe" & goto FOUND_PYTHON
if exist "C:\Program Files\Python39\python.exe" set "PY_EXE=C:\Program Files\Python39\python.exe" & goto FOUND_PYTHON
if exist "C:\Program Files\Python310\python.exe" set "PY_EXE=C:\Program Files\Python310\python.exe" & goto FOUND_PYTHON
if exist "C:\Program Files\Python311\python.exe" set "PY_EXE=C:\Program Files\Python311\python.exe" & goto FOUND_PYTHON

:ASK_USER
echo [ERROR] Could not find Python automatically.
set /p "PY_EXE=Drag and Drop python.exe here: "
set "PY_EXE=!PY_EXE:"=!"

:FOUND_PYTHON
echo [INFO] Using Python: "!PY_EXE!"

REM --- 2. Setup Env ---
if not exist ".venv" (
    echo [INFO] Creating venv...
    "!PY_EXE!" -m venv .venv
)

:CHECK_LIBS
echo.
echo [TEST] Checking libraries...

REM Create a temporary python script to avoid batch syntax errors
echo try: > _check.py
echo     import cv2 >> _check.py
echo     print('  - OpenCV: OK') >> _check.py
echo     import numpy >> _check.py
echo     print('  - NumPy: OK') >> _check.py
echo     import fastapi >> _check.py
echo     print('  - FastAPI: OK') >> _check.py
echo     import uvicorn >> _check.py
echo     print('  - Uvicorn: OK') >> _check.py
echo except Exception as e: >> _check.py
echo     print('\n  [ERROR] ' + str(e)) >> _check.py
echo     exit(1) >> _check.py

REM Run the check
".venv\Scripts\python" _check.py
set BUILD_STATUS=%errorlevel%

REM Clean up
del _check.py

if %BUILD_STATUS% neq 0 (
    echo.
    echo [CRITICAL ERROR] Libraries failed to load.
    echo.
    echo ==================================================
    echo                  ATTEMPTING REPAIR
    echo ==================================================
    echo We will switch to Standard OpenCV to fix DLL errors.
    echo.
    pause
    
    echo [REPAIR] upgrading pip...
    ".venv\Scripts\python" -m pip install --upgrade pip
    
    echo [REPAIR] Swapping OpenCV versions...
    ".venv\Scripts\python" -m pip uninstall -y opencv-python-headless
    ".venv\Scripts\python" -m pip install opencv-python
    
    echo [REPAIR] Installing other dependencies...
    ".venv\Scripts\python" -m pip install -r backend\requirements.txt
    
    echo.
    echo [REPAIR COMPLETE]
    echo Checking again...
    echo.
    goto CHECK_LIBS
) else (
    echo [SUCCESS] Libraries loaded correctly.
)

REM --- 3. Run Server ---
echo.
echo [INFO] Starting Server...
echo [INSTRUCTION] Open browser to: http://127.0.0.1:8501
echo.

cd backend
..\.venv\Scripts\python -m uvicorn main:app --reload --host 127.0.0.1 --port 8501

pause
