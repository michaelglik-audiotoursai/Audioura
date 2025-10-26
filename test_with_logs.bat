@echo off
echo === Testing with Live Logs ===

echo.
echo === Starting log monitoring in background ===
start /B docker-compose logs -f map-delivery

echo.
echo === Waiting 2 seconds ===
timeout 2

echo.
echo === Testing tours-near endpoint ===
curl -s "http://localhost:5005/tours-near/42.3086718/-71.1942855?radius=50"

echo.
echo === Stopping log monitoring ===
taskkill /F /IM docker-compose.exe 2>nul

pause