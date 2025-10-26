@echo off
echo Checking Docker container status...
docker ps

echo.
echo Checking user-api-2 logs...
docker logs development_user-api-2_1

echo.
echo Checking if user-api-2 is running...
docker exec -it development_user-api-2_1 ps aux