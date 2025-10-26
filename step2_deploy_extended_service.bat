@echo off
echo === Step 2: Deploy extended map-delivery service ===

echo.
echo === Copying updated service to container ===
docker cp c:\Users\micha\eclipse-workspace\AudioTours\development\map_delivery_service.py development-map-delivery-1:/app/

echo.
echo === Restarting map-delivery container ===
docker-compose restart map-delivery

echo.
echo === Done with Step 2 ===
echo The extended map-delivery service has been deployed and restarted.
echo New endpoints available:
echo   GET /tours-near/^<lat^>/^<lng^>?radius=^<km^> - Get tours near location
echo   GET /download-tour/^<tour_id^> - Download tour zip file
echo   GET /tour-info/^<tour_id^> - Get tour information
pause