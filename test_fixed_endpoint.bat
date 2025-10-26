@echo off
echo === Testing Fixed Map Endpoint ===

cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development"

echo.
echo === Rebuilding map-delivery service ===
docker-compose build map-delivery
docker-compose up -d map-delivery

echo.
echo === Waiting for service to start ===
timeout 5

echo.
echo === Testing tours-near endpoint ===
curl -s "http://localhost:5005/tours-near/42.3086718/-71.1942855?radius=50"

echo.
echo === Checking service logs ===
docker-compose logs map-delivery --tail=5

pause