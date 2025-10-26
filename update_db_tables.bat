@echo off
echo Updating existing database tables...

echo Running SQL script to update audio_tours table...
docker exec -i development-postgres-2-1 psql -U admin -d audiotours < update_audio_tours_table.sql

echo Done!