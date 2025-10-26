@echo off
echo Updating mobile app to version 1.0.0+60...

cd audio_tour_app

echo.
echo Copying pubspec.yaml...
copy ..\pubspec_android_simple.yaml pubspec.yaml

echo.
echo Cleaning project...
flutter clean

echo.
echo Getting dependencies...
flutter pub get

echo.
echo Building APK...
flutter build apk --release

echo.
echo APK built at: build\app\outputs\flutter-apk\app-release.apk