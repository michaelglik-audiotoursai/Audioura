@echo off
echo === Building URL Launcher Fix APK (Version 1.0.0+109) ===

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
echo Version: 1.0.0+109
echo.
echo URL Launcher fixes:
echo - Added HTTP/HTTPS intent queries to AndroidManifest.xml
echo - Removed canLaunchUrl check that can cause failures
echo - Added WebView configuration for better compatibility
echo - Links should now open in external browser properly
pause