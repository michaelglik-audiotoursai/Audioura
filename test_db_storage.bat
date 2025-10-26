@echo off
echo Testing database storage...

echo Running debug script...
docker exec -i development-tour-orchestrator-1 python debug_store_audio_tour.py

echo Done!