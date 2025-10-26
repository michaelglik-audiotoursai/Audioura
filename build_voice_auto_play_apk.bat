@echo off
echo === Building Voice Auto-Play APK (Version 1.0.0+121) ===

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
echo Version: 1.0.0+121
echo.
echo Auto-Play Features:
echo - "play" tries multiple button selectors and forces audio play after delay
echo - "next stop" navigates AND auto-plays audio after 500ms
echo - "pause" clicks pause buttons in addition to pausing audio elements
echo - Phone volume buttons work (headphone buttons may not work on all devices)
echo.
echo Test: "play next" should now navigate AND start playing audio automatically
pause