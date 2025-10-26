@echo off
echo === Restarting Map Delivery Service ===

cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development"

echo.
echo === Stopping map-delivery service ===
docker-compose stop map-delivery

echo.
echo === Rebuilding map-delivery service ===
docker-compose build map-delivery

echo.
echo === Starting map-delivery service ===
docker-compose up -d map-delivery

echo.
echo === Testing endpoint ===
timeout 3
curl -s "http://localhost:5005/tours-near/42.3086718/-71.1942855?radius=50"

pause