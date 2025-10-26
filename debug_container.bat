@echo off
echo Checking container logs...
docker-compose -f docker-compose-tour-processor.yml logs --tail=20

echo.
echo Checking what files are in the container...
docker exec -it development-tour-processor-1 ls -la /app/

echo.
echo Checking if text_to_index_fixed.py exists...
docker exec -it development-tour-processor-1 ls -la /app/text_to_index*

pause