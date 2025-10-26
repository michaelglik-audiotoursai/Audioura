@echo off
REM Script to build the mobile app with the updated coordinates system

echo.
echo ===== Building Mobile App with Coordinates System =====
echo.

REM Check if the coordinates-fromai service is running
docker ps | findstr coordinates-fromai > nul
if %ERRORLEVEL% NEQ 0 (
  echo WARNING: The coordinates-fromai service is not running.
  echo You may want to run: fix_coordinates_service.bat
)

REM Update the mobile app version
echo.
echo Updating the mobile app version to 1.0.0+92...
python update_version.py 1.0.0+92

if %ERRORLEVEL% NEQ 0 (
  echo.
  echo ERROR: Failed to update the mobile app version.
  exit /b 1
)

echo.
echo Building the mobile app...
echo.

cd audio_tour_app

echo Running flutter clean...
flutter clean

echo Running flutter pub get...
flutter pub get

echo Building APK...
flutter build apk --release

if %ERRORLEVEL% NEQ 0 (
  echo.
  echo ERROR: Failed to build the mobile app.
  cd ..
  exit /b 1
)

echo.
echo ===== Success! =====
echo.
echo The mobile app has been built successfully with version 1.0.0+92.
echo.
echo The APK file is located at:
echo audio_tour_app\build\app\outputs\flutter-apk\app-release.apk
echo.
echo To test the coordinates system, generate a tour for a location like:
echo "Boston Public Library, Boston, MA"
echo.
echo Then check the database to verify the coordinates were stored:
echo docker exec -it development-postgres-2-1 psql -U admin -d audiotours -c "SELECT tour_name, lat, lng FROM audio_tours ORDER BY id DESC LIMIT 5;"

cd ..