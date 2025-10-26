@echo off
echo === Deploying connectivity check script ===

echo.
echo === Copying check_connectivity.py to container ===
docker cp c:\Users\micha\eclipse-workspace\AudioTours\development\check_connectivity.py development-tour-orchestrator-1:/app/

echo.
echo === Running connectivity check ===
docker exec -it development-tour-orchestrator-1 python /app/check_connectivity.py

echo.
echo === Done! ===
pause