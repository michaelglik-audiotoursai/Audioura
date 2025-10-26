@echo off
REM Script to directly update the Simsbury Free Library tour with coordinates

echo.
echo ===== Updating Simsbury Free Library Tour =====
echo.
echo This script will directly update the Simsbury Free Library tour with coordinates.
echo.

echo Updating tour for Simsbury Free Library with coordinates...

docker exec -i development-postgres-2-1 psql -U admin -d audiotours -c "UPDATE audio_tours SET lat = 41.8765, lng = -72.8029 WHERE request_string = 'Simsbury Free Library, Simsbury, CT';"

if %ERRORLEVEL% NEQ 0 (
  echo.
  echo ERROR: Failed to update the tour.
  exit /b 1
)

echo.
echo Verifying the update...

docker exec -i development-postgres-2-1 psql -U admin -d audiotours -c "SELECT id, tour_name, request_string, lat, lng FROM audio_tours WHERE request_string = 'Simsbury Free Library, Simsbury, CT';"

echo.
echo ===== Success! =====
echo.
echo The Simsbury Free Library tour has been updated with coordinates.
echo.
echo Now let's restart the services to ensure they're using the latest code:
echo.

echo Restarting tour-orchestrator service...
docker-compose restart tour-orchestrator

echo.
echo Restarting coordinates-fromai service...
docker-compose restart coordinates-fromai

echo.
echo Services restarted. To test the system:
echo 1. Generate a new tour for a location like "Boston Public Library, Boston, MA"
echo 2. Check the logs:
echo    docker-compose logs tour-orchestrator
echo    docker-compose logs coordinates-fromai
echo 3. Check the database:
echo    docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c "SELECT tour_name, lat, lng FROM audio_tours ORDER BY id DESC LIMIT 5;"