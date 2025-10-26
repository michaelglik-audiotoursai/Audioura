@echo off
echo === Building Treats with URL Launcher (Version 1.0.0+106) ===

cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app"

echo.
echo === Flutter clean ===
flutter clean

echo.
echo === Flutter pub get ===
flutter pub get

echo.
echo === Flutter build APK ===
flutter build apk --release

echo.
echo === Build complete ===
echo APK location: build\app\outputs\flutter-apk\app-release.apk
echo Version: 1.0.0+106
pause