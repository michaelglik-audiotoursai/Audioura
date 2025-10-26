@echo off
REM Script to rebuild and restart the coordinates_fromAI service

echo.
echo ===== Rebuilding and Restarting Coordinates from AI Service =====
echo.

REM Check if OPENAI_API_KEY is set
if "%OPENAI_API_KEY%"=="" (
  echo ERROR: OPENAI_API_KEY environment variable is not set.
  echo Please set it first:
  echo set OPENAI_API_KEY=your_openai_api_key
  exit /b 1
)

echo Rebuilding the coordinates-fromai service...
docker-compose build coordinates-fromai

if %ERRORLEVEL% NEQ 0 (
  echo.
  echo ERROR: Failed to build the coordinates_fromAI service.
  exit /b 1
)

echo.
echo Restarting the coordinates-fromai service...
docker-compose up -d coordinates-fromai

if %ERRORLEVEL% NEQ 0 (
  echo.
  echo ERROR: Failed to restart the coordinates_fromAI service.
  exit /b 1
)

echo.
echo ===== Success! =====
echo.
echo The coordinates-fromai service has been rebuilt and restarted.
echo.
echo You can check the logs with:
echo docker-compose logs coordinates-fromai
echo.
echo You can test the service with:
echo curl http://localhost:5005/coordinates/Keene%%20Public%%20Library,%%20Keene,%%20NH