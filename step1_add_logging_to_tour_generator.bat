@echo off
echo === Step 1: Add logging to tour-generator service ===

echo.
echo === Creating backup of the file ===
copy c:\Users\micha\eclipse-workspace\AudioTours\development\generate_tour_text_service.py c:\Users\micha\eclipse-workspace\AudioTours\development\generate_tour_text_service.py.bak

echo.
echo === Running add_logging_to_tour_generator.py ===
cd c:\Users\micha\eclipse-workspace\AudioTours\development
python add_logging_to_tour_generator.py

echo.
echo === Done with Step 1 ===
echo The generate_tour_text_service.py file has been updated with enhanced logging.
echo Please review the changes before proceeding to Step 2.
pause