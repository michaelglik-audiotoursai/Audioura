#!/bin/bash

# Clean Flutter Build Script for Android Auto Integration
# This script ensures a complete clean build to include all main.dart changes

set -e

echo "=== CLEAN FLUTTER BUILD FOR ANDROID AUTO ==="
echo "Starting clean build process..."

# Create local working directory
WORK_DIR="/tmp/audiotours_clean_build"
SOURCE_DIR="/media/sf_audiotours"

# Source secrets file for build-time keys (gitignored — never committed)
if [ -f "$SOURCE_DIR/build_secrets.env" ]; then
    source "$SOURCE_DIR/build_secrets.env"
    echo "✅ Loaded build secrets from build_secrets.env"
else
    echo "⚠️  No build_secrets.env found at $SOURCE_DIR/build_secrets.env"
fi

# Fail-fast if GATEWAY_API_KEY is not set — prevents building an APK that 401s on cloud
if [ -z "$GATEWAY_API_KEY" ]; then
    echo "ERROR: GATEWAY_API_KEY not set."
    echo "Create $SOURCE_DIR/build_secrets.env with: GATEWAY_API_KEY=your-key-here"
    exit 1
fi

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
# Use the iOS app icon as the source — it already has the #A93105 brick-orange background baked in.
# (APK_BUILDS/Audioura_3.png has an OPAQUE WHITE background, so -flatten could not recolor it.)
OWL_IMAGE="$SOURCE_DIR/audio_tour_app/ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-1024x1024@1x.png"
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
    # First composite onto solid #A93105 background to ensure no transparency
    if command -v convert >/dev/null 2>&1; then
        echo "Using ImageMagick to resize icons..."
        # Create a temp icon with solid #A93105 background (matches iOS icon)
        TEMP_ICON="/tmp/audioura_icon_solid.png"
        convert "$OWL_IMAGE" -background '#A93105' -flatten "$TEMP_ICON"
        # Create optimized, small-sized icons from the solid-background version
        convert "$TEMP_ICON" -resize 48x48! -strip -quality 85 "$ICON_DIR/mipmap-mdpi/ic_launcher.png"
        convert "$TEMP_ICON" -resize 72x72! -strip -quality 85 "$ICON_DIR/mipmap-hdpi/ic_launcher.png"
        convert "$TEMP_ICON" -resize 96x96! -strip -quality 85 "$ICON_DIR/mipmap-xhdpi/ic_launcher.png"
        convert "$TEMP_ICON" -resize 144x144! -strip -quality 85 "$ICON_DIR/mipmap-xxhdpi/ic_launcher.png"
        convert "$TEMP_ICON" -resize 192x192! -strip -quality 85 "$ICON_DIR/mipmap-xxxhdpi/ic_launcher.png"
        
        # Create optimized foreground versions for adaptive icons (same solid background)
        convert "$TEMP_ICON" -resize 48x48! -strip -quality 85 "$ICON_DIR/mipmap-mdpi/ic_launcher_foreground.png"
        convert "$TEMP_ICON" -resize 72x72! -strip -quality 85 "$ICON_DIR/mipmap-hdpi/ic_launcher_foreground.png"
        convert "$TEMP_ICON" -resize 96x96! -strip -quality 85 "$ICON_DIR/mipmap-xhdpi/ic_launcher_foreground.png"
        convert "$TEMP_ICON" -resize 144x144! -strip -quality 85 "$ICON_DIR/mipmap-xxhdpi/ic_launcher_foreground.png"
        convert "$TEMP_ICON" -resize 192x192! -strip -quality 85 "$ICON_DIR/mipmap-xxxhdpi/ic_launcher_foreground.png"
        rm -f "$TEMP_ICON"
        echo "✅ Audioura app icon optimized with solid #A93105 background (matches iOS)"
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

echo "Step 3: Building APK and AAB with clean cache..."
flutter build apk --release --dart-define=GATEWAY_API_KEY="$GATEWAY_API_KEY"
echo "✅ APK built successfully"

echo "Step 4: Building App Bundle (.aab) for Play Store..."
flutter build appbundle --release --dart-define=GATEWAY_API_KEY="$GATEWAY_API_KEY"
echo "✅ AAB built successfully"

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