@echo off
netstat -ano | findstr /R /C:":6379 " >nul
if %errorlevel% equ 0 (
    echo Redis is already running on port 6379, idling...
    pause
) else (
    "C:\Program Files\Memurai\memurai.exe"
)
