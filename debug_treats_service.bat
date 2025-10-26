@echo off
echo === Debugging Treats Service ===

echo.
echo === Checking if treats service is running ===
docker-compose ps treats

echo.
echo === Checking treats service logs ===
docker-compose logs treats --tail=20

echo.
echo === Testing health endpoint ===
curl -s "http://localhost:5007/health"

echo.
echo === Testing treats endpoint ===
curl -s "http://localhost:5007/treats-near/42.3086805/-71.1942845"

echo.
echo === Checking port mapping ===
docker port development-treats-1

pause