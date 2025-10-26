@echo off
echo Safe Git Commit Script - Prevents long filename issues
echo.

REM Clean up problematic files first
call cleanup_long_paths.bat

REM Add gitignore if it doesn't exist
if not exist ".gitignore" (
    echo Creating .gitignore...
    copy /y .gitignore.template .gitignore 2>nul
)

REM Add only essential files (avoid tours and container_backup)
echo Adding essential files to Git...
git add audio_tour_app/
git add *.py
git add *.sql
git add *.md
git add *.bat
git add *.sh
git add *.yaml
git add *.yml
git add .gitignore
git add docker-compose.yml
git add Dockerfile*

REM Check if there are changes to commit
git diff --cached --quiet
if %errorlevel% equ 0 (
    echo No changes to commit.
    exit /b 0
)

REM Get commit message from user or use default
set /p commit_msg="Enter commit message (or press Enter for default): "
if "%commit_msg%"=="" set commit_msg="Update: %date% %time%"

REM Commit the changes
echo Committing changes...
git commit -m "%commit_msg%"

if %errorlevel% equ 0 (
    echo ✅ Commit successful!
    echo.
    echo To push to remote: git push origin main
) else (
    echo ❌ Commit failed. Check the error messages above.
)

pause