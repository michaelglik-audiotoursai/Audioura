@echo off
REM Script to add a coordinates endpoint to the tour-generator service

echo.
echo ===== Adding Coordinates Endpoint to Tour Generator =====
echo.
echo This script will add a coordinates endpoint to the tour-generator service
echo that can be used to get coordinates for any location using OpenAI.
echo.

python add_coordinates_endpoint.py

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo The coordinates endpoint has been added to the tour-generator service.
  echo.
  echo You can test it with:
  echo curl http://localhost:5000/coordinates/Keene%%20Public%%20Library,%%20Keene,%%20NH
) else (
  echo.
  echo ===== Error =====
  echo.
  echo Failed to add coordinates endpoint to tour-generator service.
)