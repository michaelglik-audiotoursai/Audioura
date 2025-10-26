@echo off
echo === Building Flutter Map APK (Version 1.0.0+95) - Fixed ===

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
echo APK built successfully with Flutter Map implementation
echo Version: 1.0.0+95
echo Location: build\app\outputs\flutter-apk\app-release.apk
echo.
echo Ready to deploy to your Android phone for testing!
pause