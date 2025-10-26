@echo off
echo Final fix - rebuilding with all fixed components...
docker-compose -f docker-compose-tour-processor.yml down
docker-compose -f docker-compose-tour-processor.yml build --no-cache
docker-compose -f docker-compose-tour-processor.yml up -d

echo Waiting for service...
timeout /t 8 /nobreak > nul

echo Testing the fix...
curl -X POST http://localhost:5001/process -H "Content-Type: application/json" -d "{\"tour_file\": \"armstrong_kelley_park_from_service_1.txt\"}"

echo.
echo Check status in a few seconds with:
echo curl http://localhost:5001/status/JOB_ID

pause