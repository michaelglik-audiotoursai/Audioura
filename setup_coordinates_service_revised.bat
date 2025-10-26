@echo off
REM Master script to set up the coordinates_fromAI service (revised)

echo.
echo ===== Setting Up Coordinates from AI Service (Revised) =====
echo.
echo This script will:
echo 1. Build and run the coordinates_fromAI service directly
echo 2. Update the tour orchestrator service to use the coordinates_fromAI service
echo.
echo Press any key to continue or Ctrl+C to cancel...
pause > nul

echo.
echo Step 1: Building and running the coordinates_fromAI service...
echo.
call run_coordinates_service.bat

if %ERRORLEVEL% NEQ 0 (
  echo.
  echo ERROR: Failed to build and run the coordinates_fromAI service.
  exit /b 1
)

echo.
echo Step 2: Updating the tour orchestrator service...
echo.
call update_tour_orchestrator.bat

echo.
echo ===== All Done! =====
echo.
echo The coordinates_fromAI service is now set up and the tour orchestrator
echo service has been updated to use it.
echo.
echo To verify:
echo 1. Check that the coordinates_fromAI service is running:
echo    docker ps | findstr coordinates_fromAI
echo 2. Test the coordinates service:
echo    test_coordinates_service.bat "Keene Public Library, Keene, NH"
echo 3. Generate a new tour for "Keene Public Library, Keene, NH"
echo 4. Check the logs:
echo    docker logs coordinates_fromAI
echo    docker logs development-tour-orchestrator-1
echo 5. Check the database:
echo    docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c "SELECT tour_name, lat, lng FROM audio_tours ORDER BY id DESC LIMIT 5;"
echo.
echo If you still have issues, please let me know.