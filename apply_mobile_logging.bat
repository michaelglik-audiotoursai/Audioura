@echo off
echo === Applying enhanced mobile app logging ===

echo.
echo === Creating backup of current file ===
copy c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py.mobile_bak

echo.
echo === Running enhance_mobile_logging.py ===
cd c:\Users\micha\eclipse-workspace\AudioTours\development
python enhance_mobile_logging.py

echo.
echo === Done with Step 1 ===
echo The tour_orchestrator_service.py file has been updated with enhanced mobile app logging.
echo Please review the changes before proceeding to Step 2.
pause