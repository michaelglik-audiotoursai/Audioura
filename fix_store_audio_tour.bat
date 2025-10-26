@echo off
REM Script to fix the store_audio_tour function and restart the service

echo.
echo ===== Directly Modifying store_audio_tour Function =====
echo.
echo This script will replace the store_audio_tour function with a fixed version
echo that always calls the coordinates-fromai service.
echo.
echo Press any key to continue or Ctrl+C to cancel...
pause > nul

python fix_store_audio_tour.py

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Restarting Tour Orchestrator Service =====
  echo.
  docker-compose restart tour-orchestrator
  
  echo.
  echo ===== Success! =====
  echo.
  echo The store_audio_tour function has been fixed and the service has been restarted.
  echo.
  echo To test it, generate a tour from the mobile app for a location like:
  echo "Boston Public Library, Boston, MA"
  echo.
  echo Then check the logs:
  echo docker-compose logs tour-orchestrator
  echo docker-compose logs coordinates-fromai
  echo.
  echo And check the database:
  echo docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c "SELECT tour_name, lat, lng FROM audio_tours ORDER BY id DESC LIMIT 5;"
) else (
  echo.
  echo ===== Error =====
  echo.
  echo Failed to fix the store_audio_tour function.
)