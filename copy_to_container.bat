@echo off
echo === Copying modified files to Docker container ===

echo.
echo === Copying tour_orchestrator_service.py to container ===
docker cp C:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py development-tour-orchestrator-1:/app/

echo.
echo === Restarting the tour-orchestrator container ===
docker-compose restart tour-orchestrator

echo.
echo === Done! ===
echo The files have been copied to the container and the service has been restarted.
pause