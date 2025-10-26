@echo off
echo === Building Voice Command Dialog APK (Version 1.0.0+115) ===

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
echo Version: 1.0.0+115
echo.
echo Voice Control Features:
echo - Triple-press ANY VOLUME button to open voice command dialog
echo - OR tap MIC button in tour player to open dialog
echo - Type or speak commands: "next stop", "previous", "repeat", "pause", "play"
echo - No speech recognition dependencies - simple text input
echo - Debug logs available in About > View Debug Logs
pause