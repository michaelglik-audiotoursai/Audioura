@echo off
REM Script to directly add the coordinates endpoint to the tour-generator service

echo.
echo ===== Directly Adding Coordinates Endpoint =====
echo.
echo This script will directly add the coordinates endpoint to the tour-generator service.
echo.

python add_coordinates_direct.py

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo The coordinates endpoint has been added to the tour-generator service.
  echo.
  echo You can now test it with:
  echo test_coordinates_endpoint.bat "Keene Public Library, Keene, NH"
) else (
  echo.
  echo ===== Error =====
  echo.
  echo Failed to add coordinates endpoint to tour-generator service.
)