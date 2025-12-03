#!/bin/bash

# Clean Flutter Build Script for Local Ubuntu Directory
# Modified for /home/Ubuntu/audiotours_local/audio_tour_app/

set -e

echo "=== CLEAN FLUTTER BUILD FOR LOCAL UBUNTU ===" 
echo "Starting clean build process..."

# Use local directory instead of shared folder
WORK_DIR="/tmp/audiotours_clean_build"
SOURCE_DIR="/home/Ubuntu/audiotours_local"

echo "Cleaning up previous build directory..."
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"

echo "Copying source files from local directory..."
cp -r "$SOURCE_DIR/audio_tour_app" "$WORK_DIR/"

echo "Copying original debug keystore for signature compatibility..."
ORIGINAL_KEYSTORE="$SOURCE_DIR/audio_tour_app/android/app/debug.keystore"
BUILD_KEYSTORE="$WORK_DIR/audio_tour_app/android/app/debug.keystore"

if [ -f "$ORIGINAL_KEYSTORE" ]; then
    cp "$ORIGINAL_KEYSTORE" "$BUILD_KEYSTORE"
    echo "✅ Original debug keystore copied for signature compatibility"
else
    echo "⚠️  Original keystore not found, using default (may cause signature mismatch)"
fi

cd "$WORK_DIR/audio_tour_app"

echo "Current directory: $(pwd)"
echo "Flutter version:"
flutter --version

echo "=== PERFORMING CLEAN BUILD ==="
echo "Step 1: Flutter clean (removing all build artifacts)..."
flutter clean

echo "Step 2: Getting dependencies..."
flutter pub get

echo "Step 3: Building APK with clean cache..."
flutter build apk --release

echo "=== BUILD COMPLETED ==="
APK_PATH="$WORK_DIR/audio_tour_app/build/app/outputs/flutter-apk/app-release.apk"

if [ -f "$APK_PATH" ]; then
    echo "✅ APK built successfully!"
    echo "APK location: $APK_PATH"
    
    # Copy APK back to local directory
    cp "$APK_PATH" "$SOURCE_DIR/audioura-dev.apk"
    echo "✅ APK copied to: $SOURCE_DIR/audioura-dev.apk"
    
    # Show APK info
    echo "APK size: $(du -h "$APK_PATH" | cut -f1)"
    echo "Build timestamp: $(date)"
else
    echo "❌ APK build failed!"
    exit 1
fi

echo "=== CLEAN BUILD PROCESS COMPLETED ==="

# Extract version from pubspec.yaml
VERSION=$(grep "^version:" "$WORK_DIR/audio_tour_app/pubspec.yaml" | cut -d' ' -f2)
echo "Built version: AudioTours Dev v$VERSION"