@echo off
echo === Testing Treats Endpoint ===

cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development"

echo.
echo === Rebuilding treats service ===
docker-compose build treats
docker-compose up -d treats

echo.
echo === Waiting for service to start ===
timeout 5

echo.
echo === Testing different endpoint formats ===
echo Testing: /health
curl -s "http://localhost:5007/health"

echo.
echo Testing: /treats-near/42.3086805/-71.1942845
curl -s "http://localhost:5007/treats-near/42.3086805/-71.1942845"

echo.
echo === Checking service logs ===
docker-compose logs treats --tail=10

pause