@echo off
echo === Step 1: Update local file with debug logging ===

echo.
echo === Creating backup of original file ===
copy c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py.bak

echo.
echo === Copying debug version to main file ===
copy c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service_debug.py c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py

echo.
echo === Done with Step 1 ===
echo The original file has been backed up to tour_orchestrator_service.py.bak
echo The main file has been updated with enhanced debug logging.
echo Please review the changes before proceeding to Step 2.
pause