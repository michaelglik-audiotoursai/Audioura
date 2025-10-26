@echo off
echo === Step 1: Check existing map-delivery service ===

echo.
echo === Copying map delivery service file from container ===
docker cp development-map-delivery-1:/app/map_delivery_service.py c:\Users\micha\eclipse-workspace\AudioTours\development\map_delivery_service.py

echo.
echo === Extending the service with tour delivery endpoints ===
cd c:\Users\micha\eclipse-workspace\AudioTours\development
python extend_map_delivery_service.py

echo.
echo === Done with Step 1 ===
echo The map_delivery_service.py file has been extended with tour delivery endpoints.
echo Please review the changes before proceeding to Step 2.
pause