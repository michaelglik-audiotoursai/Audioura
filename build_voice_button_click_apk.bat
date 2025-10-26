@echo off
echo === Building Voice Button Click APK (Version 1.0.0+123) ===

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
echo Version: 1.0.0+123
echo.
echo Button Click Approach:
echo - Finds and clicks actual play buttons near "Stop X" or "Audio X" text
echo - Navigation finds specific stop text and clicks associated play button
echo - Added microphone permission check and request
echo - Clicks buttons with play symbols (▶) or play text
echo.
echo This should actually click the HTML play buttons instead of trying to play audio directly
pause