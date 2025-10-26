@echo off
echo Final rebuild with directory fix...
docker-compose -f docker-compose-tour-processor.yml down
docker-compose -f docker-compose-tour-processor.yml build --no-cache
docker-compose -f docker-compose-tour-processor.yml up -d

echo Waiting for service...
timeout /t 8 /nobreak > nul

echo Testing service...
curl http://localhost:5001/health

echo.
echo Service should now work correctly!
pause