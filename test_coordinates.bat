@echo off
REM Script to test the OpenAI coordinates functionality

REM Check if location is provided
if "%~1"=="" (
  echo.
  echo ===== Test OpenAI Coordinates =====
  echo.
  echo This script tests getting coordinates from OpenAI and storing them in the database.
  echo.
  echo Usage: %0 ^<location^> [openai_api_key]
  echo Example: %0 "Simsbury Public Library, Simsbury Center, CT"
  echo.
  exit /b 1
)

set LOCATION=%~1
set API_KEY=%~2

echo.
echo ===== Testing OpenAI Coordinates =====
echo.

python test_coordinates.py "%LOCATION%" %API_KEY%

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo The coordinates were successfully retrieved and stored in the database.
) else (
  echo.
  echo ===== Error =====
  echo.
  echo Failed to get coordinates or store them in the database.
)