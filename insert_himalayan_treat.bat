@echo off
echo === Adding Himalayan Bistro Treat to Database ===

cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development"

echo.
echo === Copying SQL file to container ===
docker cp add_himalayan_bistro_treat.sql development-postgres-2-1:/tmp/

echo.
echo === Executing SQL insert ===
docker exec development-postgres-2-1 psql -U admin -d audiotours -f /tmp/add_himalayan_bistro_treat.sql

echo.
echo === Verifying insert ===
docker exec development-postgres-2-1 psql -U admin -d audiotours -c "SELECT ad_name, lat, lng FROM treats ORDER BY id DESC LIMIT 3;"

echo.
echo === Himalayan Bistro treat added successfully ===
pause