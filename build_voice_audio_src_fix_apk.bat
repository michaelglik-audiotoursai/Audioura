@echo off
echo === Building Voice Audio Src Fix APK (Version 1.0.0+122) ===

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
echo Version: 1.0.0+122
echo.
echo Audio Source Fix Features:
echo - Inspects HTML to show what elements exist (buttons, links, audio)
echo - Dynamically loads audio src as "audioX.mp3" if missing
echo - Clicks any element that might trigger audio (links, buttons with onclick)
echo - Navigation auto-generates audio src for each stop
echo - Headphone volume buttons now working
echo.
echo Test: Logs will show HTML structure and whether audio files are being loaded
pause