@echo off
echo === Getting existing app.py from map-delivery container ===

echo.
echo === Copying app.py from container ===
docker cp development-map-delivery-1:/app/app.py c:\Users\micha\eclipse-workspace\AudioTours\development\app.py

echo.
echo === Showing current endpoints ===
findstr /C:"@app.route" c:\Users\micha\eclipse-workspace\AudioTours\development\app.py

echo.
echo === Done! ===
echo The app.py file has been copied to your development directory.
echo You can now examine what endpoints already exist.
pause