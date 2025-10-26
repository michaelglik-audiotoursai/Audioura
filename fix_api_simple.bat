@echo off
echo Checking Docker containers...
docker ps

echo.
echo Enter the user-api container name (e.g., development-user-api-2-1):
set /p CONTAINER_NAME=

echo.
echo Enter the postgres container name (e.g., development-postgres-2-1):
set /p PG_CONTAINER_NAME=

echo.
echo Replacing app.py with fixed version...
copy /Y user-tracking\app_fixed.py user-tracking\app.py

echo.
echo Rebuilding user-api-2 Docker container...
docker-compose build user-api-2

echo.
echo Restarting user-api-2 service...
docker-compose restart user-api-2

echo.
echo Waiting for service to start...
timeout /t 10

echo.
echo Checking Docker logs...
docker logs %CONTAINER_NAME% --tail 20

echo.
echo Testing update_tour endpoint...
curl -X POST -H "Content-Type: application/json" -d "{\"tour_id\":\"tour_1981933a718\",\"status\":\"completed\"}" http://localhost:5003/update_tour

echo.
echo.
echo Verifying in database...
docker exec -it %PG_CONTAINER_NAME% psql -U admin -d audiotours -c "SELECT id, tour_id, request_string, status, finished_at FROM tour_requests WHERE tour_id='tour_1981933a718'"