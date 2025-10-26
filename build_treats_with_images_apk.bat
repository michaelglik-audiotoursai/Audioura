@echo off
echo === Building Treats with Images APK (Version 1.0.0+105) ===

echo.
echo === Synchronizing all services ===
cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development"
call sync_all_services.bat

echo.
echo === Rebuilding treats service ===
docker-compose build treats
docker-compose up -d treats

echo.
echo === Building Flutter app ===
cd /d "c:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app"

flutter pub get
flutter build apk --release

echo.
echo === Build complete ===
echo APK location: build\app\outputs\flutter-apk\app-release.apk
echo Version: 1.0.0+105
echo.
echo New features:
echo - Treats show actual images from database
echo - Treat names are clickable links to vendor URLs
echo - Distance calculated from user location if database value is 0
echo - Base64 image encoding for mobile display
pause