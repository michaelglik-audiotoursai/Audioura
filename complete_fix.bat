@echo off
echo === Complete fix for tour-orchestrator ===

echo.
echo === Creating a complete new tour_orchestrator_service.py file ===
echo import os > c:\temp\new_orchestrator.py
echo import sys >> c:\temp\new_orchestrator.py
echo import json >> c:\temp\new_orchestrator.py
echo import uuid >> c:\temp\new_orchestrator.py
echo import zipfile >> c:\temp\new_orchestrator.py
echo import shutil >> c:\temp\new_orchestrator.py
echo import time >> c:\temp\new_orchestrator.py
echo import threading >> c:\temp\new_orchestrator.py
echo from datetime import datetime >> c:\temp\new_orchestrator.py
echo from flask import Flask, request, jsonify, send_file >> c:\temp\new_orchestrator.py
echo from flask_cors import CORS >> c:\temp\new_orchestrator.py
echo. >> c:\temp\new_orchestrator.py
echo app = Flask(__name__) >> c:\temp\new_orchestrator.py
echo CORS(app) >> c:\temp\new_orchestrator.py
echo. >> c:\temp\new_orchestrator.py
echo # Global variables >> c:\temp\new_orchestrator.py
echo TOURS_DIR = "/app/tours"  # Docker volume mount point >> c:\temp\new_orchestrator.py
echo ACTIVE_JOBS = {}  # Track running jobs >> c:\temp\new_orchestrator.py
echo. >> c:\temp\new_orchestrator.py
echo def ensure_tours_directory(): >> c:\temp\new_orchestrator.py
echo     """Ensure the tours directory exists.""" >> c:\temp\new_orchestrator.py
echo     if not os.path.exists(TOURS_DIR): >> c:\temp\new_orchestrator.py
echo         os.makedirs(TOURS_DIR) >> c:\temp\new_orchestrator.py
echo. >> c:\temp\new_orchestrator.py
echo def store_audio_tour(tour_name, request_string, zip_path, lat, lng): >> c:\temp\new_orchestrator.py
echo     """Store the audio tour in the database.""" >> c:\temp\new_orchestrator.py
echo     try: >> c:\temp\new_orchestrator.py
echo         import psycopg2 >> c:\temp\new_orchestrator.py
echo         # Connect to the database >> c:\temp\new_orchestrator.py
echo         conn = psycopg2.connect( >> c:\temp\new_orchestrator.py
echo             host="postgres-2", >> c:\temp\new_orchestrator.py
echo             database="audiotours", >> c:\temp\new_orchestrator.py
echo             user="admin", >> c:\temp\new_orchestrator.py
echo             password="password123" >> c:\temp\new_orchestrator.py
echo         ) >> c:\temp\new_orchestrator.py
echo         cur = conn.cursor() >> c:\temp\new_orchestrator.py
echo. >> c:\temp\new_orchestrator.py
echo         # Read the ZIP file as binary data >> c:\temp\new_orchestrator.py
echo         with open(zip_path, "rb") as f: >> c:\temp\new_orchestrator.py
echo             zip_data = f.read() >> c:\temp\new_orchestrator.py
echo. >> c:\temp\new_orchestrator.py
echo         # Insert the tour into the database >> c:\temp\new_orchestrator.py
echo         cur.execute( >> c:\temp\new_orchestrator.py
echo             "INSERT INTO audio_tours (tour_name, request_string, audio_tour, lat, lng) VALUES (%s, %s, %s, %s, %s)", >> c:\temp\new_orchestrator.py
echo             (tour_name, request_string, psycopg2.Binary(zip_data), lat, lng) >> c:\temp\new_orchestrator.py
echo         ) >> c:\temp\new_orchestrator.py
echo         conn.commit() >> c:\temp\new_orchestrator.py
echo. >> c:\temp\new_orchestrator.py
echo         # Close the connection >> c:\temp\new_orchestrator.py
echo         cur.close() >> c:\temp\new_orchestrator.py
echo         conn.close() >> c:\temp\new_orchestrator.py
echo. >> c:\temp\new_orchestrator.py
echo         return True >> c:\temp\new_orchestrator.py
echo     except Exception as e: >> c:\temp\new_orchestrator.py
echo         print(f"ERROR storing tour in database: {e}") >> c:\temp\new_orchestrator.py
echo         return False >> c:\temp\new_orchestrator.py
echo. >> c:\temp\new_orchestrator.py

echo.
echo === Adding the fixed orchestrate_tour_async function ===
type c:\Users\micha\eclipse-workspace\AudioTours\development\direct_fix.py >> c:\temp\new_orchestrator.py

echo.
echo === Adding the rest of the functions ===
type c:\Users\micha\eclipse-workspace\AudioTours\development\tour_orchestrator_service.py >> c:\temp\new_orchestrator.py

echo.
echo === Updating coordinates service URL in the file ===
powershell -Command "(Get-Content c:\temp\new_orchestrator.py) -replace 'http://coordinates-fromai:5004/coordinates/', 'http://coordinates-fromai:5006/coordinates/' | Set-Content c:\temp\new_orchestrator.py"

echo.
echo === Updating timeout in the file ===
powershell -Command "(Get-Content c:\temp\new_orchestrator.py) -replace 'timeout=30', 'timeout=60' | Set-Content c:\temp\new_orchestrator.py"

echo.
echo === Copying the fixed file to the container ===
docker cp c:\temp\new_orchestrator.py development-tour-orchestrator-1:/app/tour_orchestrator_service.py

echo.
echo === Restarting the tour-orchestrator container ===
docker-compose restart tour-orchestrator

echo.
echo === Done! ===
echo The tour_orchestrator_service.py file has been completely replaced and the service has been restarted.
pause