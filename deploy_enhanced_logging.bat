@echo off
echo === Deploying enhanced logging to tour-orchestrator ===

echo.
echo === Copying enhanced_logging.py to container ===
docker cp enhanced_logging.py development-tour-orchestrator-1:/app/

echo.
echo === Copying update_orchestrator_logging.py to container ===
docker cp update_orchestrator_logging.py development-tour-orchestrator-1:/app/

echo.
echo === Running update script in container ===
docker exec -it development-tour-orchestrator-1 python update_orchestrator_logging.py

echo.
echo === Creating logs directory in container ===
docker exec -it development-tour-orchestrator-1 mkdir -p /app/logs

echo.
echo === Restarting tour-orchestrator service ===
docker-compose restart tour-orchestrator

echo.
echo === Done! ===
echo Enhanced logging has been deployed to the tour-orchestrator service.
echo Logs will be available in the container at /app/logs/
echo You can view them with: docker exec -it development-tour-orchestrator-1 cat /app/logs/tour_orchestrator_YYYYMMDD.log
pause