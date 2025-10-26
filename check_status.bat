@echo off
echo Checking the status of the last job...
curl http://localhost:5001/status/c956b1cf-0cc4-4e72-930d-536672e90ca1

echo.
echo Checking more recent logs...
docker-compose -f docker-compose-tour-processor.yml logs --tail=30

pause