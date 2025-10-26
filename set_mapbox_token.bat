@echo off
REM Script to set Mapbox access token in Docker environment

REM Check if token is provided
if "%~1"=="" (
  echo.
  echo ===== Set Mapbox Access Token =====
  echo.
  echo This script sets the Mapbox access token in the Docker environment.
  echo.
  echo Usage: %0 ^<mapbox_access_token^>
  echo Example: %0 pk.eyJ1IjoieW91cnVzZXJuYW1lIiwiYSI6ImNqeHh4eHh4eHh4eHh4eHh4eHh4eHh4In0.xxxxxxxxxxxxxxxxxxxxxxxx
  echo.
  echo To get a Mapbox access token:
  echo 1. Go to https://www.mapbox.com/ and create an account
  echo 2. Navigate to your account dashboard
  echo 3. Create a new access token with Geocoding API permissions
  echo.
  exit /b 1
)

set TOKEN=%~1

echo.
echo ===== Setting Mapbox Access Token =====
echo.

REM Update the Docker environment
echo [1/3] Setting token in Docker environment...
docker exec -it development-tour-orchestrator-1 /bin/bash -c "echo 'export MAPBOX_ACCESS_TOKEN=%TOKEN%' >> /etc/environment"
docker exec -it development-tour-orchestrator-1 /bin/bash -c "echo 'export MAPBOX_ACCESS_TOKEN=%TOKEN%' >> /root/.bashrc"

REM Set the token directly in the running container
echo [2/3] Setting token in running container...
docker exec -it development-tour-orchestrator-1 /bin/bash -c "export MAPBOX_ACCESS_TOKEN=%TOKEN%"

REM Restart the service to apply changes
echo [3/3] Restarting tour-orchestrator service...
docker restart development-tour-orchestrator-1

echo.
echo ===== Success! =====
echo.
echo Mapbox access token has been set successfully.
echo.
echo You can verify it by running:
echo docker exec -it development-tour-orchestrator-1 /bin/bash -c "echo $MAPBOX_ACCESS_TOKEN"
echo.
echo Now you can generate tours with proper geo coordinates.