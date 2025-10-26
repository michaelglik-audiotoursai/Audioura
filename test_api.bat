@echo off
echo Testing API health...
curl http://localhost:5003/health

echo.
echo Testing SQL endpoint...
curl -X POST -H "Content-Type: application/json" -d "{\"sql\":\"SELECT COUNT(*) FROM tour_requests\"}" http://localhost:5003/sql

echo.
echo Testing update_tour endpoint...
curl -X POST -H "Content-Type: application/json" -d "{\"tour_id\":\"tour_1981b2356dc\",\"status\":\"completed\"}" http://localhost:5003/update_tour