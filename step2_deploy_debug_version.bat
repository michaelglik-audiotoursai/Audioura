@echo off
echo === Step 2: Deploy debug version to local file and container ===

echo.
echo === Copying debug version to main file ===
copy c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service_debug.py c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py

echo.
echo === Copying local file to container ===
docker cp c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py development-tour-orchestrator-1:/app/

echo.
echo === Restarting tour-orchestrator container ===
docker-compose restart tour-orchestrator

echo.
echo === Done with Step 2 ===
echo The debug version has been deployed to the container and the service has been restarted.
pause