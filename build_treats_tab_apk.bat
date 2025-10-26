@echo off
echo === Building Treats Tab APK (Version 1.0.0+104) ===

echo.
echo === Starting treats service ===
cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development"
docker-compose up -d treats

echo.
echo === Building Flutter app ===
cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app"

flutter pub get
flutter build apk --release

echo.
echo === Build complete ===
echo APK location: build\app\outputs\flutter-apk\app-release.apk
echo Version: 1.0.0+104
echo.
echo New features:
echo - Added Treats tab with coffee cup icon
echo - Shows 5 nearest treats from database
echo - Treats with coordinates shown first (sorted by distance)
echo - Treats without coordinates shown after (latest first)
echo - New treats service running on port 5007
pause