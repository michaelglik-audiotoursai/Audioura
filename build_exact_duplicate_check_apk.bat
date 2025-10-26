@echo off
echo === Building Exact Duplicate Check APK (Version 1.0.0+101) ===

cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app"

echo.
echo === Flutter pub get ===
flutter pub get

echo.
echo === Flutter build APK ===
flutter build apk --release

echo.
echo === Build complete ===
echo APK location: build\app\outputs\flutter-apk\app-release.apk
echo Version: 1.0.0+101
echo.
echo Logic:
echo - Same tour ID = "This tour is already in your My Tours page"
echo - Same name, different tour ID = Downloads with versioning (v2, v3, etc.)
echo - User must delete existing tour to re-download same tour
pause