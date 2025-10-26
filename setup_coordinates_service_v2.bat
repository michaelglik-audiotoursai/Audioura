@echo off
REM Master script to set up the coordinates_fromAI service

echo.
echo ===== Setting Up Coordinates from AI Service (lowercase) =====
echo.
echo This script will:
echo 1. Rebuild and restart the coordinates-fromai service
echo 2. Update the tour orchestrator service to use the coordinates-fromai service
echo.
echo Press any key to continue or Ctrl+C to cancel...
pause > nul

echo.
echo Step 1: Rebuilding and restarting the coordinates-fromai service...
echo.
call rebuild_coordinates_service.bat

if %ERRORLEVEL% NEQ 0 (
  echo.
  echo ERROR: Failed to rebuild and restart the coordinates-fromai service.
  exit /b 1
)

echo.
echo Step 2: Updating the tour orchestrator service...
echo.
python update_tour_orchestrator.py

if %ERRORLEVEL% NEQ 0 (
  echo.
  echo ERROR: Failed to update the tour orchestrator service.
  exit /b 1
)

echo.
echo ===== All Done! =====
echo.
echo The coordinates-fromai service is now set up and the tour orchestrator
echo service has been updated to use it.
echo.
echo To verify:
echo 1. Check that the coordinates-fromai service is running:
echo    docker ps | findstr coordinates-fromai
echo 2. Generate a new tour for "Keene Public Library, Keene, NH"
echo 3. Check the logs:
echo    docker-compose logs coordinates-fromai
echo    docker-compose logs tour-orchestrator
echo 4. Check the database:
echo    docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c "SELECT tour_name, lat, lng FROM audio_tours ORDER BY id DESC LIMIT 5;"
echo.
echo If you still have issues, please let me know.