@echo off
echo Stopping Docker service...
docker-compose down

echo Rebuilding Docker image...
docker-compose build

echo Starting Docker service...
docker-compose up -d

echo Checking service status...
timeout /t 5 /nobreak > nul
curl http://localhost:5000/health

echo.
echo Service restarted successfully!
pause