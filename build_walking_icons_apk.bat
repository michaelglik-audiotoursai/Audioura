@echo off
echo === Building Walking Icons APK (Version 1.0.0+102) ===

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
echo Version: 1.0.0+102
echo.
echo Updated:
echo - Tour markers now show walking person icon (Icons.directions_walk)
echo - Both cached (grey) and fresh (blue) tours use walking icon
echo - Better represents walking tours
pause