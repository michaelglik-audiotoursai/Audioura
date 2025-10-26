@echo off
echo === Deploying debug logging to tour-orchestrator ===

echo.
echo === Creating backup of original file ===
docker exec -it development-tour-orchestrator-1 cp /app/tour_orchestrator_service.py /app/tour_orchestrator_service.py.bak

echo.
echo === Copying add_debug_logging.py to container ===
docker cp c:\Users\micha\eclipse-workspace\AudioTours\development\add_debug_logging.py development-tour-orchestrator-1:/app/

echo.
echo === Running add_debug_logging.py in container ===
docker exec -it development-tour-orchestrator-1 python add_debug_logging.py

echo.
echo === Copying check_tour_generator.py to container ===
docker cp c:\Users\micha\eclipse-workspace\AudioTours\development\check_tour_generator.py development-tour-orchestrator-1:/app/

echo.
echo === Restarting tour-orchestrator container ===
docker-compose restart tour-orchestrator

echo.
echo === Done! ===
echo Debug logging has been added to the tour_orchestrator_service.py file.
echo To check the tour generator service, run:
echo docker exec -it development-tour-orchestrator-1 python check_tour_generator.py
pause