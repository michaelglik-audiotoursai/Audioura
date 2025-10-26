@echo off
echo === Building Voice Debug Fixed APK (Version 1.0.0+116) ===

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
echo Version: 1.0.0+116
echo.
echo Debug Improvements:
echo - Added volume change detection logs
echo - Added voice command execution logs
echo - Added typed command processing logs
echo - Better debugging for volume button and command execution issues
echo.
echo Test: Try volume buttons and check logs for "Volume changed" messages
echo Test: Type "next stop" in dialog and check logs for execution steps
pause