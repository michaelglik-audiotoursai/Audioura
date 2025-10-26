@echo off
echo === Applying early logging ===

echo.
echo === Creating backup of current file ===
copy c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py.early_bak

echo.
echo === Running add_early_logging.py ===
cd c:\Users\micha\eclipse-workspace\AudioTours\development
python add_early_logging.py

echo.
echo === Copying updated file to container ===
docker cp c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py development-tour-orchestrator-1:/app/

echo.
echo === Restarting tour-orchestrator container ===
docker-compose restart tour-orchestrator

echo.
echo === Done! ===
echo The tour_orchestrator_service.py file has been updated with early logging.
echo The container has been restarted.
pause