@echo off
echo Quick rebuild with single_file_app_builder fix...
docker-compose -f docker-compose-tour-processor.yml down
docker-compose -f docker-compose-tour-processor.yml build
docker-compose -f docker-compose-tour-processor.yml up -d

echo Waiting...
timeout /t 5 /nobreak > nul

echo Testing...
curl -X POST http://localhost:5001/process -H "Content-Type: application/json" -d "{\"tour_file\": \"armstrong_kelley_park_from_service_1.txt\"}"

pause