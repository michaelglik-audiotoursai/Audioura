@echo off
REM Script to test the coordinates endpoint

REM Check if location is provided
if "%~1"=="" (
  echo.
  echo ===== Test Coordinates Endpoint =====
  echo.
  echo This script tests the coordinates endpoint in the tour-generator service.
  echo.
  echo Usage: %0 ^<location^>
  echo Example: %0 "Keene Public Library, Keene, NH"
  echo.
  exit /b 1
)

set LOCATION=%~1

echo.
echo ===== Testing Coordinates Endpoint =====
echo.

python test_coordinates_endpoint.py "%LOCATION%"

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo The coordinates endpoint is working correctly.
) else (
  echo.
  echo ===== Error =====
  echo.
  echo The coordinates endpoint is not working correctly.
)