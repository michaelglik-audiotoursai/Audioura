@echo off
set /p JOB_ID=Enter Job ID: 
echo Downloading with proper filename...
curl -o armstrong_kelley_park_netlify_deploy_%JOB_ID:~0,8%.zip http://localhost:5001/download/%JOB_ID%

echo.
echo Download complete!
dir armstrong_kelley_park_netlify_deploy_%JOB_ID:~0,8%.zip
pause