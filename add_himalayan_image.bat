@echo off
echo === Adding Image to Himalayan Bistro Treat ===

cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development"

echo.
echo === Running Python script to download and add image ===
python add_himalayan_image.py

echo.
echo === Verifying image was added ===
docker exec development-postgres-2-1 psql -U admin -d audiotours -c "SELECT ad_name, CASE WHEN ad_image IS NULL THEN 'NO IMAGE' ELSE 'HAS IMAGE (' || LENGTH(ad_image) || ' bytes)' END as image_status FROM treats WHERE ad_name LIKE '%Himalayan%';"

echo.
echo === Done ===
pause