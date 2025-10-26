@echo off
echo === Simple Flutter Build (Version 1.0.0+99) ===

cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app"

echo.
echo === Current directory ===
echo %CD%

echo.
echo === Flutter doctor check ===
flutter doctor --version

echo.
echo === Flutter pub get ===
flutter pub get

echo.
echo === Flutter build APK ===
flutter build apk --release

echo.
echo === Build complete ===
echo APK location: build\app\outputs\flutter-apk\app-release.apk
pause