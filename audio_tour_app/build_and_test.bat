@echo off
echo Building Audio Tour App with Voice Control Fixes...
echo.

echo Step 1: Getting dependencies...
flutter pub get
if %errorlevel% neq 0 (
    echo Error getting dependencies!
    pause
    exit /b 1
)

echo.
echo Step 2: Cleaning previous build...
flutter clean
flutter pub get

echo.
echo Step 3: Building APK...
flutter build apk --release
if %errorlevel% neq 0 (
    echo Error building APK!
    pause
    exit /b 1
)

echo.
echo Build completed successfully!
echo APK location: build\app\outputs\flutter-apk\app-release.apk
echo.
echo Voice Control Features Added:
echo - Real speech recognition using speech_to_text package
echo - Microphone button in voice dialog for actual voice input
echo - Improved audio playback JavaScript for HTML audio elements
echo - Better error handling and logging
echo.
echo Test Instructions:
echo 1. Install the APK on your phone
echo 2. Grant microphone permissions when prompted
echo 3. Triple-press volume buttons to open voice dialog
echo 4. Tap the microphone icon in the dialog and speak commands
echo 5. Try commands like "play", "pause", "next stop", "previous", "repeat"
echo.
pause