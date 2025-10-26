@echo off
REM Script to add coordinates to a tour in the database

REM Check if tour name and location are provided
if "%~2"=="" (
  echo.
  echo ===== Add Coordinates to Tour =====
  echo.
  echo This script adds coordinates to a tour in the database.
  echo.
  echo Usage: %0 ^<tour_name^> ^<location^>
  echo Example: %0 "tolland public library, tolland Connecticut - museum Tour" "tolland public library, tolland Connecticut"
  echo.
  exit /b 1
)

set TOUR_NAME=%~1
set LOCATION=%~2

echo.
echo ===== Adding Coordinates to Tour =====
echo.
echo Tour name: %TOUR_NAME%
echo Location: %LOCATION%
echo.

python add_coordinates_to_tour.py "%TOUR_NAME%" "%LOCATION%"

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo Coordinates have been added to the tour.
  echo.
  echo You can verify the update with:
  echo docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c "SELECT tour_name, lat, lng FROM audio_tours WHERE tour_name = '%TOUR_NAME%';"
) else (
  echo.
  echo ===== Error =====
  echo.
  echo Failed to add coordinates to the tour.
)