@echo off
echo === Restarting all services ===

echo.
echo === Stopping all services ===
docker-compose stop

echo.
echo === Starting all services ===
docker-compose up -d

echo.
echo === Done! ===
echo All services have been restarted.
pause