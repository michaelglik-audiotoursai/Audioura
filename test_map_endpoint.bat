@echo off
echo === Testing Map Delivery Endpoint ===

cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development"

echo.
echo === Rebuilding map-delivery service ===
docker-compose build map-delivery
docker-compose up -d map-delivery

echo.
echo === Waiting for service to start ===
timeout 5

echo.
echo === Testing health endpoint ===
curl -s "http://localhost:5005/health"

echo.
echo === Testing tours-near endpoint ===
curl -s "http://localhost:5005/tours-near/42.3086718/-71.1942855?radius=50"

pause