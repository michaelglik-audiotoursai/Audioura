@echo off
echo === Checking synchronization between local files and container files ===

echo.
echo === Creating temporary directory ===
mkdir c:\temp\sync_check 2>nul

echo.
echo === Checking tour_orchestrator_service.py ===
docker cp development-tour-orchestrator-1:/app/tour_orchestrator_service.py c:\temp\sync_check\tour_orchestrator_service.py.container
fc /b C:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py c:\temp\sync_check\tour_orchestrator_service.py.container > nul
if errorlevel 1 (
    echo [OUT OF SYNC] tour_orchestrator_service.py is DIFFERENT in container
) else (
    echo [IN SYNC] tour_orchestrator_service.py is synchronized
)

echo.
echo === Done! ===
echo You can find the container files in c:\temp\sync_check\
pause