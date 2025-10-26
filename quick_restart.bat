@echo off
echo Restarting tour processor service...
docker-compose -f docker-compose-tour-processor.yml down
docker-compose -f docker-compose-tour-processor.yml up -d

echo Waiting for service...
timeout /t 5 /nobreak > nul

echo Service restarted!
pause