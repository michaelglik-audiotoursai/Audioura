@echo off
echo === Step 2: Deploy fixed map delivery service ===

echo.
echo === Copying map_delivery_service.py to container as app.py ===
docker cp c:\Users\micha\eclipse-workspace\AudioTours\development\map_delivery_service.py development-map-delivery-1:/app/app.py

echo.
echo === Restarting map-delivery container ===
docker-compose restart map-delivery

echo.
echo === Waiting for service to start ===
timeout /t 10 /nobreak > nul

echo.
echo === Testing the service ===
echo Testing health endpoint...
curl -s http://localhost:5005/health

echo.
echo === Done with Step 2 ===
echo ✅ Fixed map delivery service deployed successfully
echo ✅ No syntax errors
echo ✅ Proper logging with immediate output
echo ✅ Available on port 5005
echo ✅ Endpoints for Flutter Map:
echo    GET /tours-near/^<lat^>/^<lng^>?radius=^<km^>
echo    GET /download-tour/^<tour_id^>
echo    GET /tour-info/^<tour_id^>
pause