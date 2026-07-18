@echo off
echo ==============================================================
echo Cleaning up previous orphaned services and processes...
echo ==============================================================
taskkill /F /IM minio.exe 2>NUL
taskkill /F /IM memurai.exe 2>NUL

:: Target only python processes running this project's workers, backend, or Streamlit app
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name = 'python.exe'\" | Where-Object { ($_.CommandLine -like '*worker_main.py*' -or $_.CommandLine -like '*uvicorn*' -or $_.CommandLine -like '*streamlit*') -and $_.CommandLine -like '*audio-analysis*' } | Stop-Process -Force" 2>NUL

echo.
echo ==============================================================
echo Installing process manager (Honcho) if it is missing...
echo ==============================================================
pip install honcho -q

echo.
echo ==============================================================
echo Starting Audio Analysis Stack (API, 4x Workers, Streamlit)
echo Press Ctrl+C at any time to shut down the ENTIRE system.
echo ==============================================================
echo.

honcho start
