@echo off
echo === Checking for modified files in Docker containers ===

echo.
echo === Creating temporary directory ===
mkdir c:\temp\docker_files 2>nul

echo.
echo === Checking tour_orchestrator_service.py ===
docker cp development-tour-orchestrator-1:/app/tour_orchestrator_service.py c:\temp\docker_files\
fc /b C:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py c:\temp\docker_files\tour_orchestrator_service.py > nul
if errorlevel 1 (
    echo tour_orchestrator_service.py is DIFFERENT in container
) else (
    echo tour_orchestrator_service.py is in sync
)

echo.
echo === Checking docker-compose.yml ===
docker cp development-tour-orchestrator-1:/app/docker-compose.yml c:\temp\docker_files\
fc /b C:\Users\micha\eclipse-workspace\AudioTours\development\docker-compose.yml c:\temp\docker_files\docker-compose.yml > nul
if errorlevel 1 (
    echo docker-compose.yml is DIFFERENT in container
) else (
    echo docker-compose.yml is in sync
)

echo.
echo === Done! ===
echo You can find the container files in c:\temp\docker_files\
pause