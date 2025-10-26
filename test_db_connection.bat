@echo off
echo Testing database connection...

echo Running debug script...
docker exec -i development-postgres-2-1 python debug_db_connection.py

echo Done!