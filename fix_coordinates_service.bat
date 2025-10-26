@echo off
REM Script to fix and restart the coordinates-fromai service

echo.
echo ===== Fixing and Restarting Coordinates from AI Service =====
echo.

REM Check if OPENAI_API_KEY is set
if "%OPENAI_API_KEY%"=="" (
  echo ERROR: OPENAI_API_KEY environment variable is not set.
  echo Please set it first:
  echo set OPENAI_API_KEY=your_openai_api_key
  exit /b 1
)

echo Rebuilding the coordinates-fromai service...
docker-compose build --no-cache coordinates-fromai

if %ERRORLEVEL% NEQ 0 (
  echo.
  echo ERROR: Failed to build the coordinates-fromai service.
  exit /b 1
)

echo.
echo Restarting the coordinates-fromai service...
docker-compose up -d coordinates-fromai

if %ERRORLEVEL% NEQ 0 (
  echo.
  echo ERROR: Failed to restart the coordinates-fromai service.
  exit /b 1
)

echo.
echo ===== Success! =====
echo.
echo The coordinates-fromai service has been fixed and restarted.
echo.
echo You can check the logs with:
echo docker-compose logs coordinates-fromai
echo.
echo You can test the service with:
echo test_coordinates_service_v2.bat "Keene Public Library, Keene, NH"