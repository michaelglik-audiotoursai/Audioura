@echo off
echo Rebuilding tour orchestrator container with psycopg2 support...

echo Stopping the current container...
docker stop development-tour-orchestrator-1

echo Removing the current container...
docker rm development-tour-orchestrator-1

echo Building new image with updated requirements...
docker build -t development-tour-orchestrator -f Dockerfile.orchestrator .

echo Starting new container...
docker run -d --name development-tour-orchestrator-1 --network development_default -p 5002:5002 development-tour-orchestrator

echo Done! Container should now have psycopg2 installed.
echo Check logs with: docker logs development-tour-orchestrator-1