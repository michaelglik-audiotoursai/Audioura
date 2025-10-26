@echo off
echo === Copying fixed tour_orchestrator_service.py file ===

echo.
echo === Creating backup of original file ===
copy c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py.bak

echo.
echo === Copying fixed file to development directory ===
copy c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service_fixed.py c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py

echo.
echo === Copying fixed file to container ===
docker cp c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py development-tour-orchestrator-1:/app/

echo.
echo === Restarting tour-orchestrator container ===
docker-compose restart tour-orchestrator

echo.
echo === Done! ===
echo The tour_orchestrator_service.py file has been fixed and the service has been restarted.
pause