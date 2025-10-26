@echo off
echo === Step 1: Create map delivery service ===

echo.
echo === Finding existing files in map-delivery container ===
cd c:\Users\micha\eclipse-workspace\AudioTours\development
call find_map_delivery_files.bat

echo.
echo === Creating new map delivery service ===
python create_map_delivery_service.py

echo.
echo === Done with Step 1 ===
echo ✅ Created map_delivery_service.py with tour delivery endpoints
echo ✅ Ready to deploy to container
echo.
echo Please review the created file before proceeding to Step 2.
pause