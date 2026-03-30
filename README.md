# RodSizer

## About This App

RodSizer is a specialized tool for analyzing Transmission Electron Microscopy (TEM) images of gold nanorods.

It automatically:
- Detects and segments nanoparticles from raw images.
- Measures dimensions (Length, Width, Aspect Ratio) using advanced fitting algorithms.
- Filters out non-rod particles (spheres, scale bars, dirt).
- Generates batch statistics, histograms, and professional Excel/PDF reports.

# Instruction for Launching
1. Click "<code>" in Github page.
2. Click "Download ZIP".
3. Open Finder (MacOS) or Files (Windows).
4. Click on the RodSizer.zip to unzip.
5. Double-click on RodSizer_Launcher_MacOS.command or RodSizer_Launcher_Windows.bat.
6. Wait for the environment to be set up (first time only) and the local website to be opened.
### Notes: 
- !DO NOT double-click on RodSizer_CLEANER_MacOS.command unless you are sure that you want to clean ALL local history of data and reports.
- First-time launching may take some time, like 5-10 mins.
- Try ask a coding agent if there's an issue with environment setup.
- MacOS is more recommended.
- (Windows) If Windows Defender asks, click `More Info` -> `Run Anyway`.
- (Windows) Users should ensure `Add Python to PATH` is checked during installation.

## Cleaner Script (Mac)
- `RodSizer_CLEANER_MacOS.command` is a cleanup tool for clearing local history data.
- It permanently removes:
  - uploaded files in `uploads/`
  - generated results in `results/`
  - folder analysis cache in `.analysis_cache`
  - `backend/server.log`
  - Python cache files (`__pycache__` and `*.pyc`)
- It does not remove your Python virtual environment or installed packages in `backend/.venv`.
- Use it only when you want to reset the app's local working history and cached outputs.

## Parameter Guide
- [`PARAMETER_GUIDE.md`](PARAMETER_GUIDE.md) is a reference document for the current detection and measurement parameters used by RodSizer.
- It is mainly intended for developers or advanced users who want to understand or adjust processing behavior.
- The actual implementation is in `backend/processing.py`.

## Requirements
- macOS or Windows
- Python 3 installed (standard on most Macs, or downloadable from `python.org`)

