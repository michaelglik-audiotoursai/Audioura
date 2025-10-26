@echo off
echo === Fixing Flutter build issues ===

echo.
echo === Running fix_mapbox_build.py ===
cd c:\Users\micha\eclipse-workspace\AudioTours\development
python fix_mapbox_build.py

echo.
echo === Cleaning Flutter project ===
cd c:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app
flutter clean

echo.
echo === Getting Flutter dependencies ===
flutter pub get

echo.
echo === Attempting to build APK ===
flutter build apk --release

echo.
echo === Done! ===
pause