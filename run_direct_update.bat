@echo off
echo Running direct update script inside Docker container...
docker cp user-tracking\direct_update.py development-user-api-2-1:/app/direct_update.py
docker exec -it development-user-api-2-1 python direct_update.py tour_1981933a718 completed

echo.
echo Verifying in database...
docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c "SELECT id, tour_id, request_string, status, finished_at FROM tour_requests WHERE tour_id='tour_1981933a718'"