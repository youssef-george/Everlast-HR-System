@echo off
chcp 65001 >nul
cd /d "%~dp0"
title EverLast ERP - Flask Server
color 0A

echo.
echo ========================================
echo   EverLast ERP Flask Server
echo ========================================
echo.
echo Starting server on http://127.0.0.1:5000
echo.
echo If you see errors below, check:
echo   1. Database connection in .env file
echo   2. All dependencies installed (pip install -r requirements.txt)
echo   3. Python version compatibility
echo.
echo ========================================
echo.

python app.py

if errorlevel 1 (
    echo.
    echo ========================================
    echo Server failed to start!
    echo ========================================
    echo.
    echo Check the error messages above.
    echo.
) else (
    echo.
    echo Server stopped.
    echo.
)

pause
