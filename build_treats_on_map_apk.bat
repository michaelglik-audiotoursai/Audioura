@echo off
echo === Building Treats on Map APK (Version 1.0.0+107) ===

echo.
echo === Rebuilding map-delivery service ===
cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development"
docker-compose build map-delivery
docker-compose up -d map-delivery

echo.
echo === Building Flutter app ===
cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app"

flutter pub get
flutter build apk --release

echo.
echo === Build complete ===
echo APK location: build\app\outputs\flutter-apk\app-release.apk
echo Version: 1.0.0+107
echo.
echo New features:
echo - Treats now appear on Home map with coffee cup icons (orange)
echo - Tours show walking person icons (blue)
echo - Both tours and treats are clickable on the map
echo - Only modified map-delivery service, other services untouched
pause