@echo off
title AtmosDB - Meteorological and Aviation Telemetry
echo ===================================================
echo   Starting AtmosDB Telemetry DBMS Server...
echo ===================================================
echo.
cd /d "%~dp0"
echo Checking Python installation...
python --version
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH. Please install Python 3.9+.
    pause
    exit /b 1
)

echo Installing / verifying dependencies...
pip install -r backend/requirements.txt

echo.
echo Launching server at http://127.0.0.1:5000 ...
echo Opening your default browser...
start http://127.0.0.1:5000
python backend/app.py
pause
