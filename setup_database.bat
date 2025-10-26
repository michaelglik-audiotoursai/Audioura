@echo off
echo Setting up database...

echo Copying script to Docker container...
docker cp create_audio_tours_table.py development-tour-orchestrator-1:/app/create_audio_tours_table.py

echo Creating audio_tours table...
docker exec -i development-tour-orchestrator-1 python create_audio_tours_table.py

echo Done!