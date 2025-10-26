@echo off
echo === Building Direct Treat View APK (Version 1.0.0+110) ===

echo.
echo === Rebuilding map-delivery service with image support ===
cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development"
docker-compose build map-delivery
docker-compose up -d map-delivery

echo.
echo === Building Flutter app ===
cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app"

flutter clean
flutter pub get
flutter build apk --release

echo.
echo === Build complete ===
echo APK location: build\app\outputs\flutter-apk\app-release.apk
echo Version: 1.0.0+110
echo.
echo New feature:
echo - Click treat on Home map: Opens full-screen treat detail view
echo - Shows treat image with zoom capability
echo - Shows treat description
echo - Browser icon in app bar to open vendor link
echo - Same experience as clicking right arrow in Treats tab
pause