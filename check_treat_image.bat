@echo off
echo === Checking Sweet Paris Treat Image ===

echo.
echo === Checking image data ===
docker exec development-postgres-2-1 psql -U admin -d audiotours -c "SELECT ad_name, CASE WHEN ad_image IS NULL THEN 'NO IMAGE' ELSE 'HAS IMAGE (' || LENGTH(ad_image) || ' bytes)' END as image_status FROM treats WHERE ad_name LIKE '%Sweet Paris%';"

echo.
echo === All treats with image status ===
docker exec development-postgres-2-1 psql -U admin -d audiotours -c "SELECT id, ad_name, CASE WHEN ad_image IS NULL THEN 'NO IMAGE' ELSE 'HAS IMAGE (' || LENGTH(ad_image) || ' bytes)' END as image_status FROM treats ORDER BY id DESC LIMIT 5;"

pause