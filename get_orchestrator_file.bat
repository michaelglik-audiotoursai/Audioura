@echo off
echo === Getting tour_orchestrator_service.py from container ===
docker cp development-tour-orchestrator-1:/app/tour_orchestrator_service.py tour_orchestrator_service_container.py
echo === Done! ===
echo The file has been saved as tour_orchestrator_service_container.py
pause