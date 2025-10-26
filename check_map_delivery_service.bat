@echo off
echo === Checking existing map-delivery service ===

echo.
echo === Copying map delivery service file from container ===
docker cp development-map-delivery-1:/app/map_delivery_service.py c:\Users\micha\eclipse-workspace\AudioTours\development\map_delivery_service.py

echo.
echo === Checking current endpoints ===
findstr /C:"@app.route" c:\Users\micha\eclipse-workspace\AudioTours\development\map_delivery_service.py

echo.
echo === Done! ===
echo The map_delivery_service.py file has been copied to your development directory.
echo You can examine it to see what endpoints already exist.
pause