@echo off
echo === Step 1: Add unbuffered logging to local file ===

echo.
echo === Creating backup of current file ===
copy c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py.unbuf_bak

echo.
echo === Running add_unbuffered_logging.py ===
cd c:\Users\micha\eclipse-workspace\AudioTours\development
python add_unbuffered_logging.py

echo.
echo === Done with Step 1 ===
echo The tour_orchestrator_service.py file has been updated with unbuffered logging.
echo Please review the changes before proceeding to Step 2.
pause