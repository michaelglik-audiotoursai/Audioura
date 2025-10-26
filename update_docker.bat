@echo off
echo Rebuilding user-api-2 Docker container...
docker-compose build user-api-2

echo.
echo Restarting user-api-2 service...
docker-compose restart user-api-2

echo.
echo Waiting for service to start...
timeout /t 5

echo.
echo Testing SQL endpoint...
curl -X POST -H "Content-Type: application/json" -d "{\"sql\":\"SELECT COUNT(*) FROM tour_requests\"}" http://localhost:5003/sql

echo.
echo.
echo Testing update_tour endpoint...
curl -X POST -H "Content-Type: application/json" -d "{\"tour_id\":\"tour_1981b2356dc\",\"status\":\"completed\"}" http://localhost:5003/update_tour