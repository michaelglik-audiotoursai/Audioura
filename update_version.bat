@echo off
REM Script to update the version number in the pubspec files

REM Check if version is provided
if "%~1"=="" (
  echo.
  echo ===== Update Version =====
  echo.
  echo This script updates the version number in the pubspec files.
  echo.
  echo Usage: %0 ^<new_version^>
  echo Example: %0 1.0.0+91
  echo.
  exit /b 1
)

set NEW_VERSION=%~1

echo.
echo ===== Updating Version to %NEW_VERSION% =====
echo.

python update_version.py "%NEW_VERSION%"

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo The version has been updated to %NEW_VERSION%.
) else (
  echo.
  echo ===== Error =====
  echo.
  echo Failed to update version.
)