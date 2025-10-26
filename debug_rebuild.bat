@echo off
echo Rebuilding with debug output...
docker-compose -f docker-compose-tour-processor.yml down
docker-compose -f docker-compose-tour-processor.yml build
docker-compose -f docker-compose-tour-processor.yml up -d

echo Waiting for service...
timeout /t 5 /nobreak > nul

echo Testing with debug output...
curl -X POST http://localhost:5001/process -H "Content-Type: application/json" -d "{\"tour_file\": \"armstrong_kelley_park_from_service_1.txt\"}"

echo.
echo Check the logs to see debug output:
echo docker-compose -f docker-compose-tour-processor.yml logs

pause