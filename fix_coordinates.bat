@echo off
REM Master script to fix the coordinates issue

echo.
echo ===== Fixing Coordinates Issue =====
echo.
echo This script will:
echo 1. Update coordinates for existing tours in the database
echo 2. Create a hardcoded coordinates module in the tour orchestrator container
echo 3. Modify the tour orchestrator service to use the hardcoded coordinates module
echo.
echo Press any key to continue or Ctrl+C to cancel...
pause > nul

echo.
echo Step 1: Updating coordinates for existing tours...
echo.
call update_all_coordinates.bat

echo.
echo Step 2: Creating hardcoded coordinates module...
echo.
call create_coordinates_module.bat

echo.
echo Step 3: Modifying tour orchestrator service...
echo.
call modify_tour_orchestrator.bat

echo.
echo ===== All Done! =====
echo.
echo The coordinates issue should now be fixed.
echo.
echo To verify:
echo 1. Generate a new tour for "Keene Public Library, Keene, NH"
echo 2. Check the database:
echo    docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c "SELECT tour_name, lat, lng FROM audio_tours ORDER BY id DESC LIMIT 5;"
echo.
echo If you still have issues, please let me know.