@echo off
REM Script to add comprehensive logging to the tour orchestrator service

echo.
echo ===== Adding Comprehensive Logging =====
echo.
echo This script will add comprehensive logging to the tour orchestrator service
echo and the coordinates-fromai service to help diagnose issues with the mobile app.
echo.
echo Press any key to continue or Ctrl+C to cancel...
pause > nul

python add_comprehensive_logging.py

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo Comprehensive logging has been added to both services.
  echo.
  echo To test it, generate a tour from the mobile app for a location like:
  echo "Boston Public Library, Boston, MA"
  echo.
  echo Then check the logs:
  echo docker-compose logs tour-orchestrator
  echo docker-compose logs coordinates-fromai
  echo.
  echo The logs will show:
  echo 1. Complete request details from the mobile app
  echo 2. All function calls with parameters and results
  echo 3. Detailed logging of the coordinates retrieval process
  echo 4. Database storage operations with parameters and results
) else (
  echo.
  echo ===== Error =====
  echo.
  echo Failed to add comprehensive logging.
)