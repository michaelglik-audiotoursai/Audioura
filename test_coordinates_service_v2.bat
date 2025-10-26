@echo off
REM Script to test the coordinates_fromAI service

REM Check if location is provided
if "%~1"=="" (
  echo.
  echo ===== Test Coordinates from AI Service =====
  echo.
  echo This script tests the coordinates_fromAI service.
  echo.
  echo Usage: %0 ^<location^>
  echo Example: %0 "Keene Public Library, Keene, NH"
  echo.
  exit /b 1
)

set LOCATION=%~1

echo.
echo ===== Testing Coordinates from AI Service =====
echo.

python test_coordinates_service_v2.py "%LOCATION%"

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo The coordinates_fromAI service is working correctly.
) else (
  echo.
  echo ===== Error =====
  echo.
  echo The coordinates_fromAI service is not working correctly.
)