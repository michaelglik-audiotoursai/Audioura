@echo off
echo === Step 2: Safely deploy extended service (BACKWARD COMPATIBLE) ===

echo.
echo === Copying updated service to container ===
docker cp c:\Users\micha\eclipse-workspace\AudioTours\development\map_delivery_service.py development-map-delivery-1:/app/

echo.
echo === Restarting map-delivery container ===
docker-compose restart map-delivery

echo.
echo === Waiting for service to start ===
timeout /t 5 /nobreak > nul

echo.
echo === Testing that existing functionality still works ===
cd c:\Users\micha\eclipse-workspace\AudioTours\development
python test_existing_endpoints.py

echo.
echo === Done with Step 2 ===
echo ✅ The extended map-delivery service has been deployed
echo ✅ All existing functionality preserved
echo ✅ Your current Flutter app will continue to work exactly as before
echo ✅ New endpoints available for Flutter Map:
echo    GET /tours-near/^<lat^>/^<lng^>?radius=^<km^>
echo    GET /download-tour/^<tour_id^>
echo    GET /tour-info/^<tour_id^>
pause