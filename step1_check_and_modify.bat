@echo off
echo === Step 1: Check usage and modify generate_tour_text function ===

echo.
echo === Checking for usage of generate_tour_text function ===
cd c:\Users\micha\eclipse-workspace\AudioTours\development
python check_function_usage.py

echo.
echo === Modifying generate_tour_text function ===
python modify_generate_tour_text.py

echo.
echo === Done with Step 1 ===
echo Please review the changes to modified_generate_tour_text.py before proceeding to Step 2.
pause