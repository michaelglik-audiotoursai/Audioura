@echo off
echo ========================================
echo STAGE 2: Deploying Map Delivery Fix
echo ========================================

echo.
echo 1. Backing up current container service...
docker exec development-map-delivery-1 cp /app/app.py /app/app.py.container_backup

echo.
echo 2. Copying updated service to container...
docker cp "C:\Users\micha\eclipse-workspace\AudioTours\development\map_delivery\app.py" development-map-delivery-1:/app/app.py

echo.
echo 3. Restarting map-delivery container...
docker restart development-map-delivery-1

echo.
echo 4. Waiting for service to start...
timeout /t 10

echo.
echo 5. Testing the service endpoints...
echo Testing health endpoint:
curl -f http://192.168.0.217:5005/health

echo.
echo Testing tour info endpoint (if tour ID 6 exists):
curl -f http://192.168.0.217:5005/tour-info/6

echo.
echo ========================================
echo DEPLOYMENT COMPLETE
echo ========================================
echo.
echo The map delivery service now includes:
echo - /download-tour/^<tour_id^> - Downloads tour ZIP files
echo - /tour-info/^<tour_id^> - Gets tour information
echo - /tours-near/^<lat^>/^<lng^> - Gets nearby tours
echo - /health - Health check
echo.
echo The mobile app should now be able to download tours successfully!
echo.
pause