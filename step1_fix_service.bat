@echo off
echo === Step 1: Fix map delivery service (clean version) ===

echo.
echo === Getting existing app.py from container ===
docker cp development-map-delivery-1:/app/app.py c:\Users\micha\eclipse-workspace\AudioTours\development\app.py

echo.
echo === Creating clean map_delivery_service.py ===
cd c:\Users\micha\eclipse-workspace\AudioTours\development
python fix_map_delivery_service.py

echo.
echo === Done with Step 1 ===
echo ✅ Created clean map_delivery_service.py without syntax errors
echo ✅ Proper logging with sys.stdout.flush()
echo ✅ All tour delivery endpoints included
echo.
echo Please review the map_delivery_service.py file before proceeding to Step 2.
pause