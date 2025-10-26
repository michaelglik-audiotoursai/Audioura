@echo off
echo === Building Voice Control with Debug Logs APK (Version 1.0.0+113) ===

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
echo Debug Features Added:
echo - Voice control events logged to About > View Debug Logs
echo - Logs: button presses, voice listening start/stop, commands received
echo - Logs: command processing results and errors
echo - Use debug logs to troubleshoot voice control issues
pause