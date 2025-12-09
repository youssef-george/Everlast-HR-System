@echo off
chcp 65001 >nul
cd /d "%~dp0"
title EverLast ERP Flask Server
echo ========================================
echo Starting EverLast ERP Flask Server
echo ========================================
echo.
echo Server will start on http://127.0.0.1:5000
echo Press CTRL+C to stop the server
echo ========================================
echo.

python app.py

pause
