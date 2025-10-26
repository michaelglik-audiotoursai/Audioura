@echo off
echo === Step 2: Deploy debug version to local file and container ===

echo.
echo === Copying local file to container ===
docker cp c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py development-tour-orchestrator-1:/app/

echo.
echo === Restarting tour-orchestrator container ===
docker-compose restart tour-orchestrator
