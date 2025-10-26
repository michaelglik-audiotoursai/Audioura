@echo off
REM Script to modify the tour orchestrator service to use the hardcoded coordinates module

echo.
echo ===== Modifying Tour Orchestrator Service =====
echo.
echo This script will modify the tour orchestrator service to use
echo the hardcoded coordinates module.
echo.

python modify_tour_orchestrator.py

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo The tour orchestrator service has been modified to use the hardcoded coordinates module.
  echo.
  echo You can now generate tours for the libraries and they will have coordinates.
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