@echo off
REM Script to modify the tour orchestrator to call the coordinates-fromai service

echo.
echo ===== Modifying Tour Orchestrator to Call Coordinates Service =====
echo.
echo This script will modify the tour orchestrator to call the coordinates-fromai service
echo before storing tours in the database.
echo.
echo Press any key to continue or Ctrl+C to cancel...
pause > nul

python modify_orchestrator_minimal.py

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo The tour orchestrator has been modified to call the coordinates-fromai service.
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
  echo Failed to modify the tour orchestrator.
)