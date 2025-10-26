@echo off
echo === Building Voice Fixed Functionality APK (Version 1.0.0+120) ===

echo.
echo === Starting voice control service ===
cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development"
docker-compose up -d voice-control

echo.
echo === Building Flutter app ===
cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app"

flutter clean
flutter pub get
flutter build apk --release

echo.
echo === Build complete ===
echo APK location: build\app\outputs\flutter-apk\app-release.apk
echo Version: 1.0.0+120
echo.
echo Fixed Issues:
echo - Audio play now clicks buttons instead of empty audio elements
echo - Navigation tries multiple approaches (data-stop, nth-child, scroll position)
echo - Volume button detection window reduced to 500ms for faster triple-press
echo - Should now actually play audio and navigate between stops
echo.
echo Test: Triple-press volume buttons quickly (within 500ms)
echo Test: "play" should click play buttons, "next stop" should scroll/navigate
pause