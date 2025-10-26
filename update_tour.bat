@echo off
REM Script to update tour status directly in the database

if "%1"=="" (
    echo Usage: update_tour.bat [tour_id]
    exit /b 1
)

echo Installing required packages...
pip install psycopg2-binary

echo.
echo Updating tour %1 to completed status...
python update_tour_direct.py %1

echo.
echo Verifying in database...
docker exec -it development_postgres-2_1 psql -U admin -d audiotours -c "SELECT id, tour_id, request_string, status, finished_at FROM tour_requests WHERE tour_id='%1'"