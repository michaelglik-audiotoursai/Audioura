@echo off
echo === Adding Sweet Paris Treat to Database ===

cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development"

echo.
echo === Executing SQL insert ===
docker exec development-postgres-2-1 psql -U admin -d audiotours -f /tmp/add_sweet_paris_treat.sql

echo.
echo === Copying SQL file to container ===
docker cp add_sweet_paris_treat.sql development-postgres-2-1:/tmp/

echo.
echo === Executing SQL insert ===
docker exec development-postgres-2-1 psql -U admin -d audiotours -f /tmp/add_sweet_paris_treat.sql

echo.
echo === Verifying insert ===
docker exec development-postgres-2-1 psql -U admin -d audiotours -c "SELECT ad_name, lat, lng FROM treats ORDER BY id DESC LIMIT 5;"

echo.
echo === Sweet Paris treat added successfully ===
pause