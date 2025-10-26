@echo off
echo Building and starting tour update service...
docker-compose build tour-update
docker-compose up -d tour-update

echo.
echo Waiting for service to start...
timeout /t 10

echo.
echo Testing tour update endpoint...
curl -X POST -H "Content-Type: application/json" -d "{\"tour_id\":\"tour_1981933a718\",\"status\":\"completed\"}" http://localhost:5004/update

echo.
echo.
echo Verifying in database...
docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c "SELECT id, tour_id, request_string, status, finished_at FROM tour_requests WHERE tour_id='tour_1981933a718'"