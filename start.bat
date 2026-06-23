@echo off
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
