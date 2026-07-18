@echo off
echo ==============================================================
echo Cleaning up previous orphaned services and processes...
echo ==============================================================
taskkill /F /IM minio.exe 2>NUL
taskkill /F /IM memurai.exe 2>NUL

:: Clean up any leftover processes listening on our ports (8000=FastAPI, 8501=Streamlit, 9000/9001=MinIO)
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000, 8501, 9000, 9001 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }" 2>NUL

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
