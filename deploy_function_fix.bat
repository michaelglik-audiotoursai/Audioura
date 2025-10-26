@echo off
echo === Deploying function fix to tour-orchestrator ===

echo.
echo === Copying fix_orchestrate_function.py to container ===
docker cp fix_orchestrate_function.py development-tour-orchestrator-1:/app/

echo.
echo === Copying replace_function.py to container ===
docker cp replace_function.py development-tour-orchestrator-1:/app/

echo.
echo === Running replace function script in container ===
docker exec -it development-tour-orchestrator-1 python replace_function.py

echo.
echo === Restarting tour-orchestrator service ===
docker-compose restart tour-orchestrator

echo.
echo === Done! ===
echo The orchestrate_tour_async function has been replaced and the service has been restarted.
pause