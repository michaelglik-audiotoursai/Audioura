@echo off
REM Script to modify the tour orchestrator service to use the coordinates endpoint

echo.
echo ===== Modifying Tour Orchestrator Service =====
echo.
echo This script will modify the tour orchestrator service to use
echo the coordinates endpoint from the tour-generator service.
echo.

python modify_tour_orchestrator_for_coordinates.py

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo The tour orchestrator service has been modified to use the coordinates endpoint.
  echo.
  echo You can now generate tours and they will have coordinates from OpenAI.
  echo.
  echo To test it, try generating a tour for "Keene Public Library, Keene, NH"
  echo and then check the database:
  echo docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c "SELECT tour_name, lat, lng FROM audio_tours ORDER BY id DESC LIMIT 5;"
) else (
  echo.
  echo ===== Error =====
  echo.
  echo Failed to modify tour orchestrator service.
)