@echo off
echo === Debugging Map Service ===

echo.
echo === Checking service logs ===
docker-compose logs map-delivery --tail=20

echo.
echo === Testing health endpoint ===
curl -s "http://localhost:5005/health"

echo.
echo === Checking if service is running ===
docker-compose ps map-delivery

echo.
echo === Testing with different URL format ===
curl -s "http://localhost:5005/nearby-tours?lat=42.3086718&lng=-71.1942855&radius=50"

pause