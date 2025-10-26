@echo off
REM Script to directly fix the tour orchestrator service

echo.
echo ===== Fixing Tour Orchestrator Service (Direct) =====
echo.
echo This script will:
echo 1. Directly modify the tour orchestrator to call the coordinates-fromai service
echo 2. Add detailed logging to both services
echo 3. Update the existing tour for Gale Free Library with coordinates
echo.
echo Press any key to continue or Ctrl+C to cancel...
pause > nul

python fix_tour_orchestrator_direct.py

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo The tour orchestrator service has been fixed.
  echo.
  echo To test it, generate a tour for a location like:
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