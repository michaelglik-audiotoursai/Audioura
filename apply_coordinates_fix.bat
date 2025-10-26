@echo off
echo === Applying coordinates service fix ===

echo.
echo === Creating backup of current file ===
copy c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py.coords_bak

echo.
echo === Running fix_coordinates_service.py ===
cd c:\Users\micha\eclipse-workspace\AudioTours\development
python fix_coordinates_service.py

echo.
echo === Copying updated file to container ===
docker cp c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py development-tour-orchestrator-1:/app/

echo.
echo === Restarting tour-orchestrator container ===
docker-compose restart tour-orchestrator

echo.
echo === Done! ===
echo The tour_orchestrator_service.py file has been made more resilient to coordinates service failures.
pause