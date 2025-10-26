@echo off
echo === Updating Himalayan Bistro Coordinates ===

echo.
echo === Updating coordinates ===
docker exec development-postgres-2-1 psql -U admin -d audiotours -c "UPDATE treats SET lat = 42.28753041197673, lng = -71.14977005766976 WHERE id = 6;"

echo.
echo === Verifying update ===
docker exec development-postgres-2-1 psql -U admin -d audiotours -c "SELECT ad_name, lat, lng FROM treats WHERE ad_name LIKE '%Himalayan%';"

echo.
echo === Coordinates updated successfully ===
pause