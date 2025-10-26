@echo off
echo Quick fix for file parsing issue...
docker-compose -f docker-compose-tour-processor.yml down
docker-compose -f docker-compose-tour-processor.yml build
docker-compose -f docker-compose-tour-processor.yml up -d

echo Waiting...
timeout /t 5 /nobreak > nul

echo Testing parsing fix...
curl -X POST http://localhost:5001/process -H "Content-Type: application/json" -d "{\"tour_file\": \"armstrong_kelley_park_from_service_1.txt\"}"

echo.
echo Check status in 1-2 minutes - this should work now!
pause