@echo off
echo === Step 1: Improve map delivery service with proper naming and logging ===

echo.
echo === Getting existing app.py from container ===
docker cp development-map-delivery-1:/app/app.py c:\Users\micha\eclipse-workspace\AudioTours\development\app.py

echo.
echo === Creating improved map_delivery_service.py ===
cd c:\Users\micha\eclipse-workspace\AudioTours\development
python improve_map_delivery_service.py

echo.
echo === Done with Step 1 ===
echo ✅ Created map_delivery_service.py with:
echo    - Proper naming (consistent with other services)
echo    - Unbuffered logging with sys.stdout.reconfigure(line_buffering=True)
echo    - sys.stdout.flush() after all print statements
echo    - Request logging middleware
echo    - Tour delivery endpoints for Flutter Map
echo    - All existing functionality preserved
echo.
echo Please review the map_delivery_service.py file before proceeding to Step 2.
pause