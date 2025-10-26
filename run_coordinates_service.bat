@echo off
REM Script to build and run the coordinates_fromAI service directly

echo.
echo ===== Building and Running Coordinates from AI Service =====
echo.

REM Check if OPENAI_API_KEY is set
if "%OPENAI_API_KEY%"=="" (
  echo ERROR: OPENAI_API_KEY environment variable is not set.
  echo Please set it first:
  echo set OPENAI_API_KEY=your_openai_api_key
  exit /b 1
)

echo Building the coordinates_fromAI Docker image...
docker build -t coordinates_fromai:latest ./coordinates_fromAI

if %ERRORLEVEL% NEQ 0 (
  echo.
  echo ERROR: Failed to build the Docker image.
  exit /b 1
)

echo.
echo Stopping any existing coordinates_fromAI container...
docker stop coordinates_fromAI 2>nul
docker rm coordinates_fromAI 2>nul

echo.
echo Starting the coordinates_fromAI container...
docker run -d --name coordinates_fromAI --network development_default -p 5005:5004 -e OPENAI_API_KEY=%OPENAI_API_KEY% coordinates_fromai:latest

if %ERRORLEVEL% NEQ 0 (
  echo.
  echo ERROR: Failed to start the Docker container.
  exit /b 1
)

echo.
echo ===== Success! =====
echo.
echo The coordinates_fromAI service is now running.
echo.
echo You can test it with:
echo test_coordinates_service.bat "Keene Public Library, Keene, NH"
echo.
echo You can check the logs with:
echo docker logs coordinates_fromAI