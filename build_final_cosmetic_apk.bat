@echo off
echo === Building Final Cosmetic APK (Version 1.0.0+103) ===

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
echo Version: 1.0.0+103
echo.
echo Final cosmetic updates:
echo 1. Added explanatory text: "Most popular tours and treats in your area - Select to download"
echo 2. Fixed refresh button to actually refresh the map and reload tours
echo 3. Hover tooltips would require complex gesture detection - not implemented
pause