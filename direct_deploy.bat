@echo off
echo === Direct deployment of fixed function ===

echo.
echo === Stopping the tour-orchestrator container ===
docker-compose stop tour-orchestrator

echo.
echo === Creating a backup of the container file ===
docker cp development-tour-orchestrator-1:/app/tour_orchestrator_service.py c:\temp\tour_orchestrator_service_container_backup.py

echo.
echo === Extracting the beginning of the file ===
docker exec -i development-tour-orchestrator-1 head -n 250 /app/tour_orchestrator_service.py > c:\temp\tour_orchestrator_beginning.py

echo.
echo === Creating a new file with the fixed function ===
type c:\temp\tour_orchestrator_beginning.py > c:\temp\tour_orchestrator_fixed.py
type c:\Users\micha\eclipse-workspace\AudioTours\development\direct_fix.py >> c:\temp\tour_orchestrator_fixed.py
docker exec -i development-tour-orchestrator-1 tail -n +350 /app/tour_orchestrator_service.py >> c:\temp\tour_orchestrator_fixed.py

echo.
echo === Copying the fixed file to the container ===
docker cp c:\temp\tour_orchestrator_fixed.py development-tour-orchestrator-1:/app/tour_orchestrator_service.py

echo.
echo === Updating coordinates service URL ===
docker exec -i development-tour-orchestrator-1 sed -i "s/http:\/\/coordinates-fromai:5004\/coordinates\//http:\/\/coordinates-fromai:5006\/coordinates\//g" /app/tour_orchestrator_service.py

echo.
echo === Updating timeout ===
docker exec -i development-tour-orchestrator-1 sed -i "s/timeout=30/timeout=60/g" /app/tour_orchestrator_service.py

echo.
echo === Starting the tour-orchestrator container ===
docker-compose start tour-orchestrator

echo.
echo === Done! ===
echo The tour_orchestrator_service.py file has been fixed and the service has been restarted.
pause