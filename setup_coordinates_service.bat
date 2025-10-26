@echo off
REM Master script to set up the coordinates_fromAI service

echo.
echo ===== Setting Up Coordinates from AI Service =====
echo.
echo This script will:
echo 1. Build and start the coordinates_fromAI service
echo 2. Update the tour orchestrator service to use the coordinates_fromAI service
echo.
echo Press any key to continue or Ctrl+C to cancel...
pause > nul

echo.
echo Step 1: Building and starting the coordinates_fromAI service...
echo.
docker-compose up -d coordinates-fromAI

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
echo    docker ps | findstr coordinates-fromAI
echo 2. Generate a new tour for "Keene Public Library, Keene, NH"
echo 3. Check the logs:
echo    docker logs development-coordinates-fromAI-1
echo    docker logs development-tour-orchestrator-1
echo 4. Check the database:
echo    docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c "SELECT tour_name, lat, lng FROM audio_tours ORDER BY id DESC LIMIT 5;"
echo.
echo If you still have issues, please let me know.