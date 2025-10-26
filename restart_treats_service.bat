@echo off
echo === Restarting Treats Service with Fixed Ports ===

cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development"

echo.
echo === Stopping treats service ===
docker-compose stop treats

echo.
echo === Rebuilding treats service ===
docker-compose build treats

echo.
echo === Starting treats service ===
docker-compose up -d treats

echo.
echo === Testing internal database connection ===
timeout 3
curl -s "http://localhost:5007/health"

echo.
echo === Testing treats endpoint ===
curl -s "http://localhost:5007/treats-near/42.3086805/-71.1942845"

pause