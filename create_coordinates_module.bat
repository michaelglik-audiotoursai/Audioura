@echo off
REM Script to create a hardcoded coordinates module in the tour orchestrator container

echo.
echo ===== Creating Hardcoded Coordinates Module =====
echo.
echo This script will create a Python module with hardcoded coordinates
echo and install it in the tour orchestrator container.
echo.

python create_coordinates_module.py

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo The hardcoded coordinates module has been installed in the tour orchestrator container.
  echo.
  echo You can now generate tours for the following libraries and they will have coordinates:
  echo - Keene Public Library, Keene, NH
  echo - Simsbury Public Library, Simsbury Center, CT
  echo - Clapp Memorial Library, Belchertown, MA
  echo - Belmont Public Library, Belmont, MA
  echo - Hall Memorial Library, Ellington, CT
  echo - Enfield Public Library, Enfield, CT
  echo - South Windsor Public Library, Windsor, CT
  echo - Westfield Athenaeum, Westfield, MA
  echo - Norfolk Library, Norfolk, CT
) else (
  echo.
  echo ===== Error =====
  echo.
  echo Failed to create hardcoded coordinates module.
)