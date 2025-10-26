@echo off
echo === Building Voice Control with Volume Button APK (Version 1.0.0+113) ===

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
echo Version: 1.0.0+113
echo.
echo Voice Control Features:
echo - Triple-press VOLUME UP button to activate voice listening
echo - 10-second listening window after activation
echo - Voice commands: "next stop", "previous", "repeat", "pause", "play"
echo - Debug logs available in About > View Debug Logs
pause