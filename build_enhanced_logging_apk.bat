@echo off
echo === Building Enhanced Logging APK (Version 1.0.0+98) ===

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
echo APK built successfully with enhanced logging and caching
echo Version: 1.0.0+98
echo Location: build\app\outputs\flutter-apk\app-release.apk
echo.
echo New features:
echo 1. Comprehensive logging in mobile app debug logs
echo 2. Enhanced server-side logging in development-map-delivery-1
echo 3. Tour caching - shows grey markers for cached tours, blue for fresh
echo 4. Detailed request/response logging between mobile and server
echo 5. Timeout handling for network requests
pause