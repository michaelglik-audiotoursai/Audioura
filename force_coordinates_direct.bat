@echo off
REM Script to directly patch the tour orchestrator service

echo.
echo ===== Forcing Coordinates Retrieval (Direct Patch) =====
echo.
echo This script will directly patch the tour orchestrator service to FORCE
echo coordinates retrieval for EVERY tour, regardless of any conditions.
echo.
echo Press any key to continue or Ctrl+C to cancel...
pause > nul

python force_coordinates_direct.py

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo The tour orchestrator service has been directly patched to force coordinates retrieval.
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
  echo Failed to apply the direct patch.
)