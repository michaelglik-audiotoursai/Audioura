@echo off
echo === Building Duplicate Prevention APK (Version 1.0.0+100) ===

cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app"

echo.
echo === Flutter pub get ===
flutter pub get
if errorlevel 1 (
    echo ERROR: Flutter pub get failed
    pause
    exit /b 1
)

echo.
echo === Flutter build APK ===
flutter build apk --release
if errorlevel 1 (
    echo ERROR: Flutter build failed
    pause
    exit /b 1
)

echo.
echo === Build complete ===
echo APK location: build\app\outputs\flutter-apk\app-release.apk
echo Version: 1.0.0+100
echo.
echo Fixed:
echo - Prevents duplicate tours in My Tours
echo - Auto-versioning: Tour Name, Tour Name (v2), Tour Name (v3)
echo - Unique directory names for each version
echo - Tracks tour_id for reference
pause