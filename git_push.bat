@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo Git Push Script
echo ========================================
echo.

echo Checking git status...
git status --short
echo.

echo Adding modified files...
git add templates/documentation/edit.html
git add templates/documentation/view.html
git add templates/layout.html
echo Files added.
echo.

echo Committing changes...
git commit -m "Fix CKEditor errors and add image size controls (min 100px, max 1200px) to documentation"
if errorlevel 1 (
    echo Commit failed or nothing to commit.
) else (
    echo Commit successful.
)
echo.

echo Pushing to repository...
git push
if errorlevel 1 (
    echo Push failed. Check your remote configuration.
) else (
    echo Push successful.
)
echo.

echo ========================================
pause
