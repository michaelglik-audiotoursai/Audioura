@echo off
echo === Synchronizing files from Docker containers to local directory ===

echo.
echo === Copying tour_orchestrator_service.py from container ===
docker cp development-tour-orchestrator-1:/app/tour_orchestrator_service.py C:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py

echo.
echo === Checking if docker-compose.yml was modified ===
docker cp development-tour-orchestrator-1:/app/docker-compose.yml C:\Users\micha\eclipse-workspace\AudioTours\development\docker-compose.yml.container
fc /b C:\Users\micha\eclipse-workspace\AudioTours\development\docker-compose.yml C:\Users\micha\eclipse-workspace\AudioTours\development\docker-compose.yml.container > nul
if errorlevel 1 (
    echo Docker-compose.yml was modified in the container. Copying...
    move C:\Users\micha\eclipse-workspace\AudioTours\development\docker-compose.yml.container C:\Users\micha\eclipse-workspace\AudioTours\development\docker-compose.yml
) else (
    echo Docker-compose.yml is in sync.
    del C:\Users\micha\eclipse-workspace\AudioTours\development\docker-compose.yml.container
)

echo.
echo === Done! ===
echo Files have been synchronized from the containers to your local directory.
pause