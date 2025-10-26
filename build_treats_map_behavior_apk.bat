@echo off
echo === Building Treats Map Behavior APK (Version 1.0.0+108) ===

echo.
echo === Testing map service first ===
call test_map_service_simple.bat

echo.
echo === Building Flutter app ===
cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app"

flutter pub get
flutter build apk --release

echo.
echo === Build complete ===
echo APK location: build\app\outputs\flutter-apk\app-release.apk
echo Version: 1.0.0+108
echo.
echo New behavior:
echo - Click tour on map: Shows download dialog
echo - Click treat on map: Opens Treats tab
echo - Tours: Blue walking icons
echo - Treats: Orange coffee cup icons
pause