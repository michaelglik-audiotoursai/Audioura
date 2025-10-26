@echo off
echo === Cleaning Up Duplicate Sweet Paris Records ===

echo.
echo === Current Sweet Paris records ===
docker exec development-postgres-2-1 psql -U admin -d audiotours -c "SELECT id, ad_name, CASE WHEN ad_image IS NULL THEN 'NO IMAGE' ELSE 'HAS IMAGE (' || LENGTH(ad_image) || ' bytes)' END FROM treats WHERE ad_name LIKE '%Sweet Paris%' ORDER BY id;"

echo.
echo === Keeping only the first record, deleting duplicates ===
docker exec development-postgres-2-1 psql -U admin -d audiotours -c "DELETE FROM treats WHERE ad_name LIKE '%Sweet Paris%' AND id NOT IN (SELECT MIN(id) FROM treats WHERE ad_name LIKE '%Sweet Paris%');"

echo.
echo === Remaining Sweet Paris records ===
docker exec development-postgres-2-1 psql -U admin -d audiotours -c "SELECT id, ad_name, CASE WHEN ad_image IS NULL THEN 'NO IMAGE' ELSE 'HAS IMAGE (' || LENGTH(ad_image) || ' bytes)' END FROM treats WHERE ad_name LIKE '%Sweet Paris%';"

pause