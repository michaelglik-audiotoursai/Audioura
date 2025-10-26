@echo off
echo Fixing psycopg2 issue in Docker container...

echo Installing system dependencies in container...
docker exec -i development-tour-orchestrator-1 apt-get update
docker exec -i development-tour-orchestrator-1 apt-get install -y gcc python3-dev libpq-dev

echo Installing psycopg2-binary in Docker container...
docker exec -i development-tour-orchestrator-1 pip install --no-cache-dir psycopg2-binary

echo Restarting tour orchestrator service...
docker restart development-tour-orchestrator-1

echo Done!