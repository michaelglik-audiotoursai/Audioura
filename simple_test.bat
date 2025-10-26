@echo off
echo Testing if the service can find files...

echo Checking container logs:
docker-compose -f docker-compose-tour-processor.yml logs --tail=10

echo.
echo Checking what's in the tours directory:
docker exec development-tour-processor-1 ls -la /app/tours/

echo.
echo Checking working directory in container:
docker exec development-tour-processor-1 pwd

pause