@echo off
REM Script to test tour orchestrator logging

echo.
echo ===== Testing Tour Orchestrator Logging =====
echo.

python test_logging.py

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Next Steps =====
  echo.
  echo 1. Check if you see the test message in the logs
  echo 2. If not, restart the tour orchestrator service:
  echo    docker restart development-tour-orchestrator-1
  echo 3. Try generating a new tour and check the logs again
) else (
  echo.
  echo ===== Error =====
  echo.
  echo Failed to test logging.
)