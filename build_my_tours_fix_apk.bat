@echo off
echo === Building My Tours Fix APK (Version 1.0.0+99) ===

echo.
echo === Navigating to Flutter app directory ===
cd /d c:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app
if errorlevel 1 (
    echo ERROR: Failed to navigate to Flutter directory
    pause
    exit /b 1
)

echo.
echo === Cleaning Flutter project ===
flutter clean
if errorlevel 1 (
    echo WARNING: Flutter clean failed, continuing anyway...
)

echo.
echo === Getting Flutter dependencies ===
flutter pub get
if errorlevel 1 (
    echo ERROR: Flutter pub get failed
    pause
    exit /b 1
)

echo.
echo === Building APK for release ===
flutter build apk --release
if errorlevel 1 (
    echo ERROR: Flutter build failed
    pause
    exit /b 1
)

echo.
echo === Done! ===
echo APK built successfully with My Tours integration
echo Version: 1.0.0+99
echo Location: build\app\outputs\flutter-apk\app-release.apk
echo.
echo Fixed:
echo - Downloaded tours now saved to My Tours page
echo - Tours extracted and stored locally
echo - Tour info fetched from server
echo - Proper file management for tour playback
pause