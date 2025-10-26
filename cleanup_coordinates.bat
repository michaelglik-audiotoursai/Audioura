@echo off
REM Script to clean up any hardcoded coordinates modules

echo.
echo ===== Cleaning Up Hardcoded Coordinates =====
echo.
echo This script will remove any hardcoded coordinates modules
echo from the tour orchestrator container.
echo.

python cleanup_coordinates.py

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo All hardcoded coordinates modules have been removed.
) else (
  echo.
  echo ===== Error =====
  echo.
  echo Failed to clean up hardcoded coordinates modules.
)