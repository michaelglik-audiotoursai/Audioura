@echo off
echo Fixing database storage...

echo Running fix script...
python fix_db_storage.py

echo Copying updated files to Docker container...
docker cp tour_orchestrator_service.py development-tour-orchestrator-1:/app/tour_orchestrator_service.py
docker cp create_audio_tours_table.py development-tour-orchestrator-1:/app/create_audio_tours_table.py

echo Creating audio_tours table...
docker exec -i development-tour-orchestrator-1 python create_audio_tours_table.py

echo Restarting tour orchestrator service...
docker restart development-tour-orchestrator-1

echo Done!