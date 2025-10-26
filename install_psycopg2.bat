@echo off
echo Installing psycopg2 in Docker container...

echo Installing build dependencies...
docker exec -i development-tour-orchestrator-1 apt-get update
docker exec -i development-tour-orchestrator-1 apt-get install -y gcc python3-dev libpq-dev

echo Installing psycopg2...
docker exec -i development-tour-orchestrator-1 pip install psycopg2-binary

echo Restarting tour orchestrator service...
docker restart development-tour-orchestrator-1

echo Done!