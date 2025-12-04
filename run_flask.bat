@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo Starting EverLast ERP Flask Application
echo ========================================
echo.
python -u app.py
if errorlevel 1 (
    echo.
    echo ========================================
    echo Application failed to start!
    echo ========================================
    pause
)
