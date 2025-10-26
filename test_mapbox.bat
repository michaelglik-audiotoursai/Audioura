@echo off
REM Script to test the Mapbox Geocoding API

REM Check if token is provided
if "%~2"=="" (
  echo.
  echo ===== Test Mapbox Geocoding API =====
  echo.
  echo This script tests the Mapbox Geocoding API with your token.
  echo.
  echo Usage: %0 ^<location^> ^<mapbox_access_token^>
  echo Example: %0 "Hall Memorial Library, Ellington CT" pk.eyJ1IjoieW91cnVzZXJuYW1lIiwiYSI6ImNqeHh4eHh4eHh4eHh4eHh4eHh4eHh4In0.xxxxxxxxxxxxxxxxxxxxxxxx
  echo.
  exit /b 1
)

set LOCATION=%~1
set TOKEN=%~2

echo.
echo ===== Testing Mapbox Geocoding API =====
echo.

python test_mapbox.py "%LOCATION%" "%TOKEN%"

if %ERRORLEVEL% EQU 0 (
  echo.
  echo ===== Success! =====
  echo.
  echo The Mapbox token is working correctly.
  echo You can now use it in the AudioTours application.
  echo.
  echo To set this token in the application:
  echo set_mapbox_token_direct.bat %TOKEN%
) else (
  echo.
  echo ===== Error =====
  echo.
  echo The Mapbox token test failed.
  echo Please check your token and try again.
)