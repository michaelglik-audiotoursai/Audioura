@echo off
echo === Building Flutter Map APK with Server IP Support (Version 1.0.0+97) ===

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
echo APK built successfully with server IP support
echo Version: 1.0.0+97
echo Location: build\app\outputs\flutter-apk\app-release.apk
echo.
echo Features:
echo - Map service now uses server IP from About page
echo - Same IP setting for both tour generation and map services
echo - Default IP: 192.168.0.217 (matches your existing setup)
pause