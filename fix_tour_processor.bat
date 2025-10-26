@echo off
echo Stopping tour processor service...
docker-compose -f docker-compose-tour-processor.yml down

echo Removing old images...
docker image prune -f

echo Rebuilding Docker image with Python 3.10...
docker-compose -f docker-compose-tour-processor.yml build --no-cache

echo Starting tour processor service...
docker-compose -f docker-compose-tour-processor.yml up -d

echo Waiting for service to start...
timeout /t 15 /nobreak > nul

echo Checking service status...
curl http://localhost:5001/health

echo.
echo Tour processor service fixed and restarted!
pause