@echo off
REM Script to verify the coordinates endpoint

echo.
echo ===== Verifying Coordinates Endpoint =====
echo.
echo This script will verify that the coordinates endpoint exists
echo in the tour-generator service and add it if it doesn't.
echo.

python verify_coordinates_endpoint.py

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo The coordinates endpoint is properly set up in the tour-generator service.
  echo.
  echo You can now test it with:
  echo test_coordinates_endpoint.bat "Keene Public Library, Keene, NH"
) else (
  echo.
  echo ===== Error =====
  echo.
  echo Failed to verify or add the coordinates endpoint.
)