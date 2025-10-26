@echo off
echo Building Android APK for Audio Tour App...

cd audio_tour_app

echo Step 1: Updating files...
copy ..\pubspec_android_simple.yaml pubspec.yaml
copy ..\main_dart_android_simple.dart lib\main.dart

echo Step 2: Getting dependencies...
flutter pub get

echo Step 3: Building APK...
flutter build apk --release

echo.
echo ✅ APK built successfully!
echo.
echo 📱 APK Location:
echo %CD%\build\app\outputs\flutter-apk\app-release.apk
echo.
echo 📋 Next Steps:
echo 1. Copy APK to your Android phone
echo 2. Enable "Install unknown apps" in phone settings
echo 3. Install the APK
echo 4. Make sure services are running: docker-compose -f docker-compose-complete.yml up -d
echo.
pause