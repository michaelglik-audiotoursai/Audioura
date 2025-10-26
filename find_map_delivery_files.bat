@echo off
echo === Finding files in map-delivery container ===

echo.
echo === Listing all Python files in the container ===
docker exec development-map-delivery-1 find /app -name "*.py" -type f

echo.
echo === Listing all files in /app directory ===
docker exec development-map-delivery-1 ls -la /app/

echo.
echo === Checking if container is running ===
docker ps | findstr map-delivery

echo.
echo === Done! ===
pause