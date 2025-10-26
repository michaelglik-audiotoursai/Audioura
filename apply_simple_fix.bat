@echo off
echo === Applying simple coordinates fix ===

echo.
echo === Creating backup of current file ===
copy c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py.simple_bak

echo.
echo === Running fix_coordinates_service_simple.py ===
cd c:\Users\micha\eclipse-workspace\AudioTours\development
python fix_coordinates_service_simple.py

echo.
echo === Done with Step 1 ===
echo The tour_orchestrator_service.py file has been updated with the simple coordinates fix.
echo Please review the changes before proceeding to Step 2.
pause