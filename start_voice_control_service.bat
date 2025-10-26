@echo off
echo === Starting Voice Control Service ===

cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development"

echo.
echo === Building and starting voice-control service ===
docker-compose build voice-control
docker-compose up -d voice-control

echo.
echo === Testing voice control service ===
timeout 3
curl -s "http://localhost:5008/health"

echo.
echo === Voice control service started on port 5008 ===
echo Commands supported:
echo - "next stop" - Move to next stop
echo - "previous" - Move to previous stop  
echo - "repeat" - Repeat current stop
echo - "pause" - Pause audio
echo - "play" - Resume audio

pause