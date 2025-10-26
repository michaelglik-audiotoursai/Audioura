@echo off
echo === Building Voice HTML Debug APK (Version 1.0.0+124) ===

echo.
echo === Starting voice control service ===
cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development"
docker-compose up -d voice-control

echo.
echo === Building Flutter app ===
cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app"

flutter clean
flutter pub get
flutter build apk --release

echo.
echo === Build complete ===
echo APK location: build\app\outputs\flutter-apk\app-release.apk
echo Version: 1.0.0+124
echo.
echo HTML Debug Features:
echo - Shows actual HTML structure (buttons, onclick events, Stop texts)
echo - Clicks first available button to test functionality
echo - Triggers all onclick events found in HTML
echo - Better error handling for permissions
echo.
echo This will reveal what buttons actually exist in the HTML and whether they work
pause