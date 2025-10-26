@echo off
echo Setting up database tables...

echo Running SQL script to create audio_tours table...
docker exec -i development-postgres-2-1 psql -U admin -d audiotours < setup_audio_tours_table.sql

echo Done!