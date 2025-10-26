@echo off
echo === Testing Fixed Route ===

echo.
echo === Rebuilding map-delivery service ===
docker-compose build map-delivery
docker-compose up -d map-delivery

echo.
echo === Waiting for service to start ===
timeout 5

echo.
echo === Testing with Python ===
python test_exact_endpoint.py

pause