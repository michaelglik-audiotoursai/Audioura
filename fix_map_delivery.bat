@echo off
echo Fixing map delivery service download endpoints...

echo Copying updated map_delivery service to container...
docker cp "C:\Users\micha\eclipse-workspace\AudioTours\development\map_delivery\app.py" development-map-delivery-1:/app/app.py

echo Restarting map-delivery container...
docker restart development-map-delivery-1

echo Waiting for service to start...
timeout /t 5

echo Testing the new endpoints...
curl -f http://192.168.0.217:5005/health

echo.
echo Map delivery service has been updated with download endpoints!
echo The mobile app should now be able to download tours successfully.
pause