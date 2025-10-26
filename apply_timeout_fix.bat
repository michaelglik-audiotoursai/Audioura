@echo off
echo === Applying timeout fix ===

echo.
echo === Creating backup of current file ===
copy c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py.timeout_bak

echo.
echo === Running fix_timeout_issue.py ===
cd c:\Users\micha\eclipse-workspace\AudioTours\development
python fix_timeout_issue.py

echo.
echo === Copying updated file to container ===
docker cp c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py development-tour-orchestrator-1:/app/

echo.
echo === Restarting tour-orchestrator container ===
docker-compose restart tour-orchestrator

echo.
echo === Done! ===
echo Timeouts have been increased and retry logic has been added.
pause