@echo off
echo === Building Final Treats APK (Version 1.0.0+106) ===

cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app"

echo.
echo === Flutter pub get ===
flutter pub get

echo.
echo === Flutter build APK ===
flutter build apk --release

echo.
echo === Build complete ===
echo APK location: build\app\outputs\flutter-apk\app-release.apk
echo Version: 1.0.0+106
echo.
echo Final features:
echo 1. Clickable treat names open vendor URLs in external browser
echo 2. Right arrow opens full-screen zoomable image with description
echo 3. Real images from database displayed
echo 4. Smart distance calculation
pause