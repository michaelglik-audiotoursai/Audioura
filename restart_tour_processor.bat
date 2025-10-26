@echo off
echo Stopping tour processor service...
docker-compose -f docker-compose-tour-processor.yml down

echo Rebuilding Docker image...
docker-compose -f docker-compose-tour-processor.yml build

echo Starting tour processor service...
docker-compose -f docker-compose-tour-processor.yml up -d

echo Checking service status...
timeout /t 10 /nobreak > nul
curl http://localhost:5001/health

echo.
echo Tour processor service restarted successfully!
pause