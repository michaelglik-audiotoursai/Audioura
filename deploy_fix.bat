@echo off
echo === Deploying fix to tour-orchestrator ===

echo.
echo === Copying fix_coordinates_url.py to container ===
docker cp fix_coordinates_url.py development-tour-orchestrator-1:/app/

echo.
echo === Running fix script in container ===
docker exec -it development-tour-orchestrator-1 python fix_coordinates_url.py

echo.
echo === Restarting tour-orchestrator service ===
docker-compose restart tour-orchestrator

echo.
echo === Done! ===
echo The coordinates service URL has been fixed and more logging has been added.
pause