@echo off
echo Rebuilding tour processor service with fixes...
docker-compose -f docker-compose-tour-processor.yml down
docker-compose -f docker-compose-tour-processor.yml build
docker-compose -f docker-compose-tour-processor.yml up -d

echo Waiting for service...
timeout /t 5 /nobreak > nul

echo Testing service...
curl http://localhost:5001/health

echo.
echo Service rebuilt and ready!
pause