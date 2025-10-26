@echo off
echo Stopping and removing tour processor service...
docker-compose -f docker-compose-tour-processor.yml down
docker system prune -f

echo Rebuilding with simplified TTS...
docker-compose -f docker-compose-tour-processor.yml build --no-cache

echo Starting tour processor service...
docker-compose -f docker-compose-tour-processor.yml up -d

echo Waiting for service to start...
timeout /t 10 /nobreak > nul

echo Checking service status...
curl http://localhost:5001/health

echo.
echo Tour processor service should now work!
pause