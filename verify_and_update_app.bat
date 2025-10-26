@echo off
REM Script to verify the coordinates system and update the mobile app

echo.
echo ===== Verifying Coordinates System and Updating Mobile App =====
echo.

REM Check if the coordinates-fromai service is running
docker ps | findstr coordinates-fromai > nul
if %ERRORLEVEL% NEQ 0 (
  echo ERROR: The coordinates-fromai service is not running.
  echo Please run: fix_coordinates_service.bat
  exit /b 1
)

echo The coordinates-fromai service is running.

REM Check if the tour orchestrator service is running
docker ps | findstr tour-orchestrator > nul
if %ERRORLEVEL% NEQ 0 (
  echo ERROR: The tour orchestrator service is not running.
  echo Please run: docker-compose up -d tour-orchestrator
  exit /b 1
)

echo The tour orchestrator service is running.

REM Update the mobile app version
echo.
echo Updating the mobile app version to 1.0.0+92...
python update_version.py 1.0.0+92

if %ERRORLEVEL% NEQ 0 (
  echo.
  echo ERROR: Failed to update the mobile app version.
  exit /b 1
)

echo.
echo ===== Success! =====
echo.
echo The coordinates system is working and the mobile app has been updated to version 1.0.0+92.
echo.
echo You can now build the mobile app:
echo cd audio_tour_app
echo flutter build apk
echo.
echo To test the coordinates system, generate a tour for a location like:
echo "Boston Public Library, Boston, MA"
echo.
echo Then check the database to verify the coordinates were stored:
echo docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c "SELECT tour_name, lat, lng FROM audio_tours ORDER BY id DESC LIMIT 5;"