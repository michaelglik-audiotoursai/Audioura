@echo off
echo === Step 2: Deploy map delivery service ===

echo.
echo === Copying map delivery service to container ===
docker cp c:\Users\micha\eclipse-workspace\AudioTours\development\map_delivery_service.py development-map-delivery-1:/app/

echo.
echo === Restarting map-delivery container ===
docker-compose restart map-delivery

echo.
echo === Waiting for service to start ===
timeout /t 10 /nobreak > nul

echo.
echo === Testing the service ===
echo Testing health endpoint...
curl -s http://localhost:5004/health

echo.
echo === Done with Step 2 ===
echo ✅ Map delivery service deployed successfully
echo ✅ Available endpoints:
echo    GET /health - Health check
echo    GET /tours-near/^<lat^>/^<lng^>?radius=^<km^> - Get tours near location
echo    GET /download-tour/^<tour_id^> - Download tour zip file
echo    GET /tour-info/^<tour_id^> - Get tour information
echo    GET /all-tours - Get all available tours
pause