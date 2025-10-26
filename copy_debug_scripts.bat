@echo off
echo Copying debug scripts to Docker container...

echo Copying debug_store_audio_tour.py...
docker cp debug_store_audio_tour.py development-tour-orchestrator-1:/app/debug_store_audio_tour.py

echo Done!