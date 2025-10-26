@echo off
echo Final fix - build_web_page issue resolved...
docker-compose -f docker-compose-tour-processor.yml down
docker-compose -f docker-compose-tour-processor.yml build
docker-compose -f docker-compose-tour-processor.yml up -d

echo Waiting...
timeout /t 5 /nobreak > nul

echo Testing complete pipeline...
curl -X POST http://localhost:5001/process -H "Content-Type: application/json" -d "{\"tour_file\": \"armstrong_kelley_park_from_service_1.txt\"}"

echo.
echo This should work now! Check status in 1-2 minutes.
pause