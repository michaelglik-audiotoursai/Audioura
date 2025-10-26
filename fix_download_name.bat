@echo off
echo Fixing download filename issue...
docker-compose -f docker-compose-tour-processor.yml down
docker-compose -f docker-compose-tour-processor.yml build
docker-compose -f docker-compose-tour-processor.yml up -d

echo Waiting for service...
timeout /t 5 /nobreak > nul

echo Service ready! Now try downloading again:
echo curl -O http://localhost:5001/download/4e93b901-eb65-4ceb-9ccd-d7a20c75350f

pause