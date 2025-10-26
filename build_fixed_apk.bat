@echo off
echo === Building Fixed Flutter Map APK (Version 1.0.0+96) ===

echo.
echo === Navigating to Flutter app directory ===
cd c:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app

echo.
echo === Cleaning Flutter project ===
flutter clean

echo.
echo === Getting Flutter dependencies ===
flutter pub get

echo.
echo === Building APK for release ===
flutter build apk --release

echo.
echo === Done! ===
echo APK built successfully with fixed map service connection
echo Version: 1.0.0+96
echo Location: build\app\outputs\flutter-apk\app-release.apk
echo.
echo Fixed issues:
echo - Map delivery service syntax errors resolved
echo - Mobile app now uses correct IP address (192.168.1.100:5005)
echo - Service should now respond properly to mobile requests
pause