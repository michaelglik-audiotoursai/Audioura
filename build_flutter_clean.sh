#!/bin/bash

# Clean Flutter Build Script for Android Auto Integration
# This script ensures a complete clean build to include all main.dart changes

set -e

echo "=== CLEAN FLUTTER BUILD FOR ANDROID AUTO ==="
echo "Starting clean build process..."

# Create local working directory
WORK_DIR="/tmp/audiotours_clean_build"
SOURCE_DIR="/media/sf_audiotours"

echo "Cleaning up previous build directory..."
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"

echo "Copying source files from Windows directory..."
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

echo "Copying Audioura app icon with proper sizing..."
OWL_IMAGE="$SOURCE_DIR/APK_BUILDS/Audioura_3.png"
ICON_DIR="$WORK_DIR/audio_tour_app/android/app/src/main/res"

# Install ImageMagick if not available
if ! command -v convert >/dev/null 2>&1; then
    echo "Installing ImageMagick for icon processing..."
    sudo apt-get update -qq
    sudo apt-get install -y imagemagick
fi

echo "Looking for Audioura image at: $OWL_IMAGE"
if [ -f "$OWL_IMAGE" ]; then
    echo "Audioura image found, processing..."
    # Resize and copy OwlAudio image to proper Android icon sizes
    # Crop to square first, then resize to fill circular icons properly
    if command -v convert >/dev/null 2>&1; then
        echo "Using ImageMagick to resize icons..."
        # Create optimized, small-sized icons
        convert "$OWL_IMAGE" -resize 48x48! -strip -quality 85 "$ICON_DIR/mipmap-mdpi/ic_launcher.png"
        convert "$OWL_IMAGE" -resize 72x72! -strip -quality 85 "$ICON_DIR/mipmap-hdpi/ic_launcher.png"
        convert "$OWL_IMAGE" -resize 96x96! -strip -quality 85 "$ICON_DIR/mipmap-xhdpi/ic_launcher.png"
        convert "$OWL_IMAGE" -resize 144x144! -strip -quality 85 "$ICON_DIR/mipmap-xxhdpi/ic_launcher.png"
        convert "$OWL_IMAGE" -resize 192x192! -strip -quality 85 "$ICON_DIR/mipmap-xxxhdpi/ic_launcher.png"
        
        # Create optimized foreground versions for adaptive icons
        convert "$OWL_IMAGE" -resize 48x48! -strip -quality 85 "$ICON_DIR/mipmap-mdpi/ic_launcher_foreground.png"
        convert "$OWL_IMAGE" -resize 72x72! -strip -quality 85 "$ICON_DIR/mipmap-hdpi/ic_launcher_foreground.png"
        convert "$OWL_IMAGE" -resize 96x96! -strip -quality 85 "$ICON_DIR/mipmap-xhdpi/ic_launcher_foreground.png"
        convert "$OWL_IMAGE" -resize 144x144! -strip -quality 85 "$ICON_DIR/mipmap-xxhdpi/ic_launcher_foreground.png"
        convert "$OWL_IMAGE" -resize 192x192! -strip -quality 85 "$ICON_DIR/mipmap-xxxhdpi/ic_launcher_foreground.png"
        echo "✅ Audioura app icon optimized and resized to all resolutions (small file sizes)"
    else
        echo "ImageMagick not available, copying directly..."
        # Fallback: direct copy without resizing
        cp "$OWL_IMAGE" "$ICON_DIR/mipmap-hdpi/ic_launcher.png"
        cp "$OWL_IMAGE" "$ICON_DIR/mipmap-mdpi/ic_launcher.png"
        cp "$OWL_IMAGE" "$ICON_DIR/mipmap-xhdpi/ic_launcher.png"
        cp "$OWL_IMAGE" "$ICON_DIR/mipmap-xxhdpi/ic_launcher.png"
        cp "$OWL_IMAGE" "$ICON_DIR/mipmap-xxxhdpi/ic_launcher.png"
        echo "✅ Audioura app icon copied (ImageMagick not available for resizing)"
    fi
else
    echo "⚠️  Audioura image not found at: $OWL_IMAGE"
    echo "Directory contents:"
    ls -la "$SOURCE_DIR/APK_BUILDS/" || echo "APK_BUILDS directory not found"
    echo "Using default icon"
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
    
    # Copy APK back to Windows directory
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
echo "Install the APK and check for startup message in debug logs:"

# Extract version from pubspec.yaml
VERSION=$(grep "^version:" "$WORK_DIR/audio_tour_app/pubspec.yaml" | cut -d' ' -f2)
echo "Built version: AudioTours Dev v$VERSION"