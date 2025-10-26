@echo off
echo === Step 1: Backup and copy fixed file locally ===

echo.
echo === Creating backup of original file ===
copy c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py.bak

echo.
echo === Creating fixed version of the file ===
copy c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service_fixed.py

echo.
echo === Done with Step 1 ===
echo The original file has been backed up to tour_orchestrator_service.py.bak
echo The fixed file has been created as tour_orchestrator_service_fixed.py
echo Please review the changes before proceeding to Step 2.
pause