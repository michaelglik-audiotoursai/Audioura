@echo off
REM Master script to restore version 91 with hardcoded coordinates

echo.
echo ===== Restoring Version 91 with Hardcoded Coordinates =====
echo.
echo This script will:
echo 1. Restore the hardcoded coordinates lookup table
echo 2. Update the version number to 1.0.0+91
echo.
echo Press any key to continue or Ctrl+C to cancel...
pause > nul

echo.
echo Step 1: Restoring hardcoded coordinates...
echo.
call restore_hardcoded_coordinates.bat

echo.
echo Step 2: Updating version number...
echo.
call update_version.bat 1.0.0+91

echo.
echo ===== All Done! =====
echo.
echo Version 91 with hardcoded coordinates has been restored.
echo.
echo To verify:
echo 1. Generate a new tour for "Keene Public Library, Keene, NH"
echo 2. Check the logs:
echo    docker logs development-tour-orchestrator-1
echo 3. Check the database:
echo    docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c "SELECT tour_name, lat, lng FROM audio_tours ORDER BY id DESC LIMIT 5;"
echo.
echo If you still have issues, please let me know.