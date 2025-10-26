@echo off
REM Script to update coordinates for tours in the database

REM Check if API key is provided
if "%~1"=="" (
  echo.
  echo ===== Update Tour Coordinates =====
  echo.
  echo This script updates coordinates for tours in the database using OpenAI API.
  echo.
  echo Usage: %0 ^<openai_api_key^> [tour_id^|tour_name]
  echo Example: %0 sk-abcdef123456 "Keene Public Library, Keene, NH - museum Tour"
  echo.
  echo If no tour_id or tour_name is provided, all tours without coordinates will be updated.
  echo.
  exit /b 1
)

set API_KEY=%~1
set TOUR_IDENTIFIER=%~2

echo.
echo ===== Updating Tour Coordinates =====
echo.

if "%TOUR_IDENTIFIER%"=="" (
  echo Updating all tours without coordinates...
  python update_tour_coordinates.py "%API_KEY%"
) else (
  echo Updating tour: %TOUR_IDENTIFIER%
  python update_tour_coordinates.py "%API_KEY%" "%TOUR_IDENTIFIER%"
)

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo The tour coordinates have been updated in the database.
  echo.
  echo You can verify the updates with:
  echo docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c "SELECT tour_name, lat, lng FROM audio_tours ORDER BY id DESC LIMIT 10;"
) else (
  echo.
  echo ===== Error =====
  echo.
  echo Failed to update tour coordinates.
)