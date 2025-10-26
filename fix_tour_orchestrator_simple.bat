@echo off
REM Script to fix the tour orchestrator service (simple approach)

echo.
echo ===== Fixing Tour Orchestrator (Simple Approach) =====
echo.
echo This script will directly modify the tour orchestrator service file
echo to add a new function that calls the coordinates-fromai service directly.
echo.
echo Press any key to continue or Ctrl+C to cancel...
pause > nul

python fix_tour_orchestrator_simple.py

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Restarting Tour Orchestrator Service =====
  echo.
  docker-compose restart tour-orchestrator
  
  echo.
  echo ===== Success! =====
  echo.
  echo The tour orchestrator service has been fixed and restarted.
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
  echo Failed to fix the tour orchestrator service.
)