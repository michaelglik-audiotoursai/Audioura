@echo off
REM Master script to fix the coordinates issue using OpenAI

echo.
echo ===== Fixing Coordinates Issue with OpenAI =====
echo.
echo This script will:
echo 1. Clean up any hardcoded coordinates modules
echo 2. Add a coordinates endpoint to the tour-generator service
echo 3. Modify the tour orchestrator service to use the coordinates endpoint
echo.
echo Press any key to continue or Ctrl+C to cancel...
pause > nul

echo.
echo Step 1: Cleaning up hardcoded coordinates modules...
echo.
call cleanup_coordinates.bat

echo.
echo Step 2: Adding coordinates endpoint to tour-generator service...
echo.
call add_coordinates_endpoint.bat

echo.
echo Step 3: Modifying tour orchestrator service...
echo.
call modify_tour_orchestrator_for_coordinates.bat

echo.
echo ===== All Done! =====
echo.
echo The coordinates issue should now be fixed using OpenAI.
echo.
echo To verify:
echo 1. Generate a new tour for "Keene Public Library, Keene, NH"
echo 2. Check the logs:
echo    docker logs development-tour-generator-1
echo    docker logs development-tour-orchestrator-1
echo 3. Check the database:
echo    docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c "SELECT tour_name, lat, lng FROM audio_tours ORDER BY id DESC LIMIT 5;"
echo.
echo If you still have issues, please let me know.