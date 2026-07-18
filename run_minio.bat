@echo off
netstat -ano | findstr /R /C:":9000 " >nul
if %errorlevel% equ 0 (
    echo MinIO is already running on port 9000, idling...
    pause
) else (
    "C:\tools\minio.exe" server "C:\minio-data" --console-address ":9001"
)
