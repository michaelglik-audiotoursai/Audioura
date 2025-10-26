@echo off
REM Script to update coordinates for an existing tour

REM Check if all arguments are provided
if "%~3"=="" (
  echo.
  echo ===== Update Tour Coordinates =====
  echo.
  echo This script updates the coordinates for an existing tour in the database.
  echo.
  echo Usage: %0 ^<tour_name^> ^<latitude^> ^<longitude^>
  echo Example: %0 "Keene Public Library, Keene, NH - museum Tour" 42.9336 -72.2781
  echo.
  exit /b 1
)

set TOUR_NAME=%~1
set LATITUDE=%~2
set LONGITUDE=%~3

echo.
echo ===== Updating Tour Coordinates =====
echo.
echo Tour: %TOUR_NAME%
echo Latitude: %LATITUDE%
echo Longitude: %LONGITUDE%
echo.

python update_coordinates.py "%TOUR_NAME%" %LATITUDE% %LONGITUDE%

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo The coordinates were successfully updated in the database.
) else (
  echo.
  echo ===== Error =====
  echo.
  echo Failed to update coordinates in the database.
)