@echo off
echo === Step 1: Backup and add debug logging to local file ===

echo.
echo === Creating backup of original file ===
copy c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py.bak

echo.
echo === Creating enhanced version with debug logging ===
copy c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service_debug.py

echo.
echo === Done with Step 1 ===
echo The original file has been backed up to tour_orchestrator_service.py.bak
echo Please manually add debug logging to tour_orchestrator_service_debug.py
echo Then review the changes before proceeding to Step 2.
pause