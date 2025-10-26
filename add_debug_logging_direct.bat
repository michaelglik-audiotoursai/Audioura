@echo off
echo === Adding debug logging directly to tour_orchestrator_service.py ===

echo.
echo === Creating backup of original file ===
copy c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py.bak

echo.
echo === Copying debug version to main file ===
copy c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service_debug.py c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py

echo.
echo === Copying updated file to container ===
docker cp c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py development-tour-orchestrator-1:/app/

echo.
echo === Restarting tour-orchestrator container ===
docker-compose restart tour-orchestrator

echo.
echo === Done! ===
echo Debug logging has been added to tour_orchestrator_service.py and deployed to the container.
pause