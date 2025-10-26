@echo off
echo === Fixing tour_orchestrator_service.py ===

echo.
echo === Creating backup of original file ===
docker cp development-tour-orchestrator-1:/app/tour_orchestrator_service.py tour_orchestrator_backup.py

echo.
echo === Copying local file to container ===
docker cp c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py development-tour-orchestrator-1:/app/

echo.
echo === Updating coordinates service URL ===
docker exec -it development-tour-orchestrator-1 sed -i "s/http:\/\/coordinates-fromai:5004\/coordinates\//http:\/\/coordinates-fromai:5006\/coordinates\//g" /app/tour_orchestrator_service.py

echo.
echo === Updating timeout ===
docker exec -it development-tour-orchestrator-1 sed -i "s/timeout=30/timeout=60/g" /app/tour_orchestrator_service.py

echo.
echo === Adding more logging ===
docker exec -it development-tour-orchestrator-1 sed -i "s/print(f\"\\\\n==== STEP 1: GENERATING TOUR TEXT ====\\\\n\")/print(f\"\\\\n==== STEP 1: GENERATING TOUR TEXT ====\\\\n\")\n    print(f\"DEBUG: Time: {datetime.now().isoformat()}\")/g" /app/tour_orchestrator_service.py

echo.
echo === Restarting tour-orchestrator service ===
docker-compose restart tour-orchestrator

echo.
echo === Done! ===
echo The tour_orchestrator_service.py file has been fixed and the service has been restarted.
pause