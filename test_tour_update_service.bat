@echo off
echo Testing tour update service...
curl -X POST -H "Content-Type: application/json" -d "{\"tour_id\":\"tour_1981ae1b1e8\",\"status\":\"completed\"}" http://localhost:5004/update

echo.
echo.
echo Verifying in database...
docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c "SELECT id, tour_id, request_string, status, finished_at FROM tour_requests WHERE tour_id='tour_1981ae1b1e8'"