# RodSizer
========

About This App:
---------------
RodSizer is a specialized tool for analyzing Transmission Electron Microscopy (TEM) images of gold nanorods.

It automatically:
- Detects and segments nanoparticles from raw images.
- Measures dimensions (Length, Width, Aspect Ratio) using advanced fitting algorithms.
- Filters out non-rod particles (spheres, scale bars, dirt).
- Generates batch statistics, histograms, and professional Excel/PDF reports.

How to Run (Mac):
-----------------
1. Double-click "RodSizer_Launcher_MacOS.command".
2. The app will open in your browser automatically.
   (If it's your first time, it may take a minute to set up).

How to Run (Windows):
---------------------
1. Double-click "RodSizer_Launcher_Windows.bat".
2. If Windows Defender asks, click "More Info" -> "Run Anyway".
3. The app will open in your browser automatically.

Cleaner Script (Mac):
---------------------
- "RodSizer_CLEANER_MacOS.command" is a cleanup tool for clearing local history data.
- It permanently removes:
  * uploaded files in uploads/
  * generated results in results/
  * folder analysis cache (.analysis_cache)
  * backend/server.log
  * Python cache files (__pycache__ and *.pyc)
- It does NOT remove your Python virtual environment or installed packages in backend/.venv.
- Use it only when you want to reset the app's local working history and cached outputs.

Parameter Guide:
----------------
- "PARAMETER_GUIDE.md" is a reference document for the current detection and measurement parameters used by RodSizer.
- It is mainly intended for developers or advanced users who want to understand or adjust processing behavior.
- The actual implementation is in backend/processing.py.

Requirements:
-------------
- Mac OS or Windows
- Python 3 installed (standard on most Macs, or download from python.org)
  * Windows users: Ensure "Add Python to PATH" is checked during installation.
