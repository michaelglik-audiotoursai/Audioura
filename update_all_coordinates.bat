@echo off
REM Script to update coordinates for all libraries in the database

echo.
echo ===== Updating All Library Coordinates =====
echo.
echo This script will update coordinates for all libraries in the database.
echo.

python update_all_coordinates.py

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo All library coordinates have been updated in the database.
  echo.
  echo You can verify the updates with:
  echo docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c "SELECT tour_name, lat, lng FROM audio_tours ORDER BY id DESC LIMIT 10;"
) else (
  echo.
  echo ===== Error =====
  echo.
  echo Failed to update coordinates in the database.
)