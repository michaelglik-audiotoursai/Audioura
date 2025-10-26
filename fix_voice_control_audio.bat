@echo off
echo Fixing voice control audio initialization issue...

echo Step 1: Backing up original file
copy single_file_app_builder.py single_file_app_builder.py.voice_backup

echo Step 2: Replacing with fixed version
copy single_file_app_builder_voice_fixed.py single_file_app_builder.py

echo Step 3: Copying ONLY the HTML builder to tour processor container
docker cp single_file_app_builder.py development-tour-processor-1:/app/single_file_app_builder.py

echo Step 4: Restarting ONLY tour processor service
docker restart development-tour-processor-1

echo Step 5: Checking service health
timeout /t 5
docker exec development-tour-processor-1 curl -s http://localhost:5001/health

echo.
echo Voice control audio fix deployed!
echo.
echo WHAT WAS FIXED:
echo - Added initializeAudioContext() function
echo - Added pauseAllAudio() helper function  
echo - Added setTimeout delays to prevent race conditions
echo - Added proper audio loading and error handling
echo - Added user interaction listeners to initialize audio context
echo.
echo TEST: Generate a new tour to get the fixed HTML with proper voice control