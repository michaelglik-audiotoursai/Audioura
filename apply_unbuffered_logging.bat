@echo off
echo === Applying unbuffered logging ===

echo.
echo === Creating backup of current file ===
copy c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py.unbuf_bak

echo.
echo === Running add_unbuffered_logging.py ===
cd c:\Users\micha\eclipse-workspace\AudioTours\development
python add_unbuffered_logging.py

echo.
echo === Copying updated file to container ===
docker cp c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py development-tour-orchestrator-1:/app/

echo.
echo === Restarting tour-orchestrator container ===
docker-compose restart tour-orchestrator

echo.
echo === Done! ===
echo The tour_orchestrator_service.py file has been updated with unbuffered logging.
echo The container has been restarted.
pause