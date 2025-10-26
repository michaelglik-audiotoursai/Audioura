@echo off
echo === Restarting Docker services ===

echo.
echo === Stopping services ===
docker-compose stop

echo.
echo === Starting services ===
docker-compose up -d

echo.
echo === Checking service status ===
docker-compose ps

echo.
echo === Done! ===
echo All services have been restarted.
pause