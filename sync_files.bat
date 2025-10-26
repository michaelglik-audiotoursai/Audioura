@echo off
echo === Synchronizing files between local directory and container ===

echo.
echo === Synchronizing tour_orchestrator_service.py ===
echo 1. Local to container
docker cp C:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py development-tour-orchestrator-1:/app/
echo 2. Container to local (backup)
docker cp development-tour-orchestrator-1:/app/tour_orchestrator_service.py C:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py.container

echo.
echo === Done! ===
echo Files have been synchronized between local directory and container.
echo A backup of the container file has been saved as tour_orchestrator_service.py.container
pause