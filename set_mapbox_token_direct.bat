@echo off
REM Script to directly modify the tour_orchestrator_service.py file to include the Mapbox token

REM Check if token is provided
if "%~1"=="" (
  echo Usage: %0 ^<mapbox_access_token^>
  echo Example: %0 pk.eyJ1IjoieW91cnVzZXJuYW1lIiwiYSI6ImNqeHh4eHh4eHh4eHh4eHh4eHh4eHh4In0.xxxxxxxxxxxxxxxxxxxxxxxx
  exit /b 1
)

set TOKEN=%~1

REM Create a temporary file with the token
echo # This file contains the Mapbox access token > mapbox_token_temp.py
echo MAPBOX_ACCESS_TOKEN = "%TOKEN%" >> mapbox_token_temp.py

REM Copy the file to the Docker container
echo Copying token file to Docker container...
docker cp mapbox_token_temp.py development-tour-orchestrator-1:/app/mapbox_token.py

REM Remove the temporary file
del mapbox_token_temp.py

REM Restart the service
echo Restarting tour-orchestrator service...
docker restart development-tour-orchestrator-1

echo Done! Mapbox token has been set.
echo You can verify it by generating a new tour and checking the logs.