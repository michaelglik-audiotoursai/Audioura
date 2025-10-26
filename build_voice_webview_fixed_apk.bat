@echo off
echo === Building Voice WebView Fixed APK (Version 1.0.0+117) ===

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
echo Version: 1.0.0+117
echo.
echo WebView JavaScript Fixes:
echo - Fixed webController initialization timing
echo - Added JavaScript execution error handling
echo - Added detailed logs for JavaScript operations
echo - Should now properly execute audio controls and navigation
echo.
echo Test: Type "play" and check logs for JavaScript execution messages
pause