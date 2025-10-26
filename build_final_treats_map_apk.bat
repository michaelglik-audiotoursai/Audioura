@echo off
echo === Building Final Treats Map APK (Version 1.0.0+108) ===

cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app"

echo.
echo === Flutter clean and pub get ===
flutter clean
flutter pub get

echo.
echo === Building APK ===
flutter build apk --release

echo.
echo === Build complete ===
echo APK location: build\app\outputs\flutter-apk\app-release.apk
echo Version: 1.0.0+108
echo.
echo Final features:
echo - Tours and treats appear on Home map
echo - Click tour: Download dialog (adds to My Tours)
echo - Click treat: Opens Treats tab
echo - Tours: Blue walking icons
echo - Treats: Orange coffee cup icons
echo - Treats tab shows real images and clickable vendor links
echo - Full-screen image viewer with zoom
pause