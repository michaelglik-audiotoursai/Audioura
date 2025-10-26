#!/bin/bash

# Flutter APK Build Script for Ubuntu
# This script copies the Flutter project from shared folder and builds APK

set -e  # Exit immediately if any command fails

echo "=== Flutter APK Build Script ==="
echo "Starting build process..."

# Step 1: Navigate to shared folder
echo "Step 1: Accessing shared folder..."
cd /media/sf_audiotours/audio_tour_app || {
    echo "ERROR: Cannot access /media/sf_audiotours/audio_tour_app"
    echo "Make sure VirtualBox shared folder is mounted properly"
    exit 1
}

echo "✓ Successfully accessed shared folder"

# Step 2: Remove old local copy and create fresh one
echo "Step 2: Creating fresh local copy..."
rm -rf /home/Ubuntu/audiotours_local/audio_tour_app
mkdir -p /home/Ubuntu/audiotours_local
cp -r /media/sf_audiotours/audio_tour_app /home/Ubuntu/audiotours_local/ || {
    echo "ERROR: Failed to copy project files"
    exit 1
}

echo "✓ Project files copied successfully"

# Step 3: Navigate to local copy
echo "Step 3: Navigating to local project..."
cd /home/Ubuntu/audiotours_local/audio_tour_app || {
    echo "ERROR: Cannot access local project directory"
    exit 1
}

echo "✓ In local project directory: $(pwd)"

# Step 4: Clean Flutter project
echo "Step 4: Cleaning Flutter project..."
flutter clean || {
    echo "ERROR: Flutter clean failed"
    exit 1
}

echo "✓ Flutter clean completed"

# Step 5: Get dependencies
echo "Step 5: Getting Flutter dependencies..."
flutter pub get || {
    echo "ERROR: Flutter pub get failed"
    exit 1
}

echo "✓ Dependencies downloaded successfully"

# Step 6: Build APK
echo "Step 6: Building APK..."
flutter build apk --debug || {
    echo "ERROR: Flutter build failed"
    exit 1
}

echo "✓ APK build completed successfully!"

# Step 7: Show APK location
APK_PATH="/home/Ubuntu/audiotours_local/audio_tour_app/build/app/outputs/flutter-apk/app-debug.apk"
if [ -f "$APK_PATH" ]; then
    echo "=== BUILD SUCCESSFUL ==="
    echo "APK Location: $APK_PATH"
    echo "APK Size: $(du -h "$APK_PATH" | cut -f1)"
    echo ""
    echo "To copy APK to shared folder:"
    echo "cp \"$APK_PATH\" /media/sf_audiotours/"
else
    echo "ERROR: APK file not found at expected location"
    exit 1
fi

echo "=== Build process completed successfully! ==="