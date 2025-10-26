@echo off
echo === Deploying Treats Service ===

cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development"

echo.
echo === Building treats service ===
docker-compose build treats

echo.
echo === Starting treats service ===
docker-compose up -d treats

echo.
echo === Checking service status ===
docker-compose ps treats

echo.
echo === Testing service ===
timeout 5
curl -s "http://localhost:5007/health"

echo.
echo === Treats service deployed on port 5007 ===
pause