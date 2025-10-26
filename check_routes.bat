@echo off
echo === Checking Flask Routes ===

echo.
echo === Copying route checker to container ===
docker cp check_flask_routes.py development-map-delivery-1:/app/

echo.
echo === Running route checker ===
docker exec development-map-delivery-1 python check_flask_routes.py

pause