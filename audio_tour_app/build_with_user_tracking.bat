@echo off
echo 🔧 Building Flutter APK with User Tracking Fix
echo =============================================

echo 📱 Current Flutter app already has user tracking implemented!
echo 🔧 Fixed IP address configuration to match your network
echo.

echo 🧹 Cleaning previous build...
call flutter clean

echo 📦 Getting dependencies...
call flutter pub get

echo 🏗️ Building release APK...
call flutter build apk --release

echo.
if exist "build\app\outputs\flutter-apk\app-release.apk" (
    echo ✅ SUCCESS! APK built successfully
    echo 📱 APK Location: build\app\outputs\flutter-apk\app-release.apk
    echo.
    echo 🎯 User Tracking Features:
    echo   - Generates unique user IDs automatically
    echo   - Sends user_id with every tour request
    echo   - Registers users with tracking service
    echo   - Includes location data if permission granted
    echo.
    echo 📋 Next Steps:
    echo 1. Install APK on your device
    echo 2. Generate a tour from the app
    echo 3. Check user tracking with: python test_user_tracking_simple.py
) else (
    echo ❌ Build failed! Check the output above for errors.
)

echo.
pause