@echo off
REM Script to get coordinates using OpenAI API

REM Check if token is provided
if "%~2"=="" (
  echo.
  echo ===== Get Coordinates from OpenAI =====
  echo.
  echo This script gets coordinates for a location using the OpenAI API.
  echo.
  echo Usage: %0 ^<location^> ^<openai_api_key^>
  echo Example: %0 "Hall Memorial Library, Ellington CT" sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  echo.
  exit /b 1
)

set LOCATION=%~1
set API_KEY=%~2

echo.
echo ===== Getting Coordinates from OpenAI =====
echo.

python get_coordinates_openai.py "%LOCATION%" "%API_KEY%"

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo Coordinates retrieved successfully.
) else (
  echo.
  echo ===== Error =====
  echo.
  echo Failed to get coordinates from OpenAI.
  echo Please check your API key and try again.
)