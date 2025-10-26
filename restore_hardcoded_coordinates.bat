@echo off
REM Script to restore the hardcoded coordinates lookup table

echo.
echo ===== Restoring Hardcoded Coordinates =====
echo.
echo This script will restore the hardcoded coordinates lookup table
echo in the tour orchestrator service.
echo.

python restore_hardcoded_coordinates.py

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo The hardcoded coordinates lookup table has been restored.
  echo.
  echo You can now generate tours for the following locations and they will have coordinates:
  echo - Clapp Memorial Library, Belchertown, MA
  echo - Belmont Public Library, Belmont, MA
  echo - Hall Memorial Library, Ellington, CT
  echo - Enfield Public Library, Enfield, CT
  echo - South Windsor Public Library, Windsor, CT
  echo - Keene Public Library, Keene, NH
  echo - Simsbury Public Library, Simsbury Center, CT
  echo - Newton Waban, Newton, MA
  echo.
  echo To test it, try generating a tour for "Keene Public Library, Keene, NH"
  echo and then check the database:
  echo docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c "SELECT tour_name, lat, lng FROM audio_tours ORDER BY id DESC LIMIT 5;"
) else (
  echo.
  echo ===== Error =====
  echo.
  echo Failed to restore hardcoded coordinates.
)