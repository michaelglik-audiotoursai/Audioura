@echo off
echo === Building Voice Enhanced Debug APK (Version 1.0.0+118) ===

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
echo Version: 1.0.0+118
echo.
echo Enhanced Debug Features:
echo - Detailed audio element detection (shows count of audio elements found)
echo - Alternative play button detection if no audio elements
echo - Improved volume button detection with timestamps
echo - Volume button triple-press opens dialog
echo - Better error handling for volume listener
echo.
echo Test Steps:
echo 1. Press volume up 3 times quickly - should open dialog
echo 2. Type "play" - logs will show audio element count and execution details
pause