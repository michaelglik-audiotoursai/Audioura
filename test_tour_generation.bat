@echo off
REM Script to test tour generation with coordinates

REM Check if location is provided
if "%~1"=="" (
  echo.
  echo ===== Test Tour Generation with Coordinates =====
  echo.
  echo This script tests generating a tour and verifies that coordinates are added.
  echo.
  echo Usage: %0 ^<location^>
  echo Example: %0 "Boston Public Library, Boston, MA"
  echo.
  exit /b 1
)

set LOCATION=%~1

echo.
echo ===== Testing Tour Generation with Coordinates =====
echo.

python test_tour_generation.py "%LOCATION%"

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo The tour was generated with coordinates.
) else (
  echo.
  echo ===== Error =====
  echo.
  echo The tour was not generated with coordinates.
)