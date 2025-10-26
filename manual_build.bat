@echo off
echo Manual Android Build Process...

echo Step 1: Navigate to Flutter app directory
cd audio_tour_app

echo Step 2: Copy required files
copy ..\pubspec_android_simple.yaml pubspec.yaml
copy ..\main_dart_android_simple.dart lib\main.dart

echo Step 3: Clean previous build
flutter clean

echo Step 4: Get dependencies
flutter pub get

echo Step 5: Build APK
flutter build apk --release

echo.
if exist "build\app\outputs\flutter-apk\app-release.apk" (
    echo ✅ APK built successfully!
    echo 📱 APK Location: %CD%\build\app\outputs\flutter-apk\app-release.apk
) else (
    echo ❌ APK build failed
    echo Check the output above for errors
)

echo.
pause