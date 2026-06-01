#!/bin/bash

# iOS Fixes v1.2.9+24 File Copy Script
# Copies updated files with iOS device info, settings persistence, and location permission fixes

echo "🍎 iOS AMAZON-Q - COPYING iOS FIXES v1.2.9+24"
echo "Session Date: $(date '+%Y%m%d_%H%M%S')"
echo ""

# Define source and destination paths
SOURCE_BASE="/Volumes/USB DISK/Audioura/assets"
DEST_BASE="$HOME/Development/AudioTours/development/audio_tour_app"

echo "============================================================"
echo "=== COPYING iOS FIXES v1.2.9+24 FILES ==="
echo "============================================================"
echo "Source: $SOURCE_BASE"
echo "Destination: $DEST_BASE"
echo ""

# Check if source directory exists
if [ ! -d "$SOURCE_BASE" ]; then
    echo "❌ ERROR: Source directory not found: $SOURCE_BASE"
    echo "Please ensure USB drive is mounted and contains updated files"
    exit 1
fi

# Check if destination directory exists
if [ ! -d "$DEST_BASE" ]; then
    echo "❌ ERROR: Destination directory not found: $DEST_BASE"
    echo "Please ensure Flutter project exists at: $DEST_BASE"
    exit 1
fi

echo "✅ Source and destination directories verified"
echo ""

# Files to copy with iOS fixes
FILES_TO_COPY=(
    "lib/screens/about_screen.dart"
    "lib/screens/home_screen.dart"
    "lib/screens/tour_generator_screen.dart"
    "lib/services/device_service.dart"
    "lib/services/subscription_service.dart"
    "lib/services/subscription_encryption_service.dart"
    "lib/services/translation_service.dart"
    "lib/widgets/language_selector.dart"
    "lib/widgets/subscription_credential_dialog.dart"
    "pubspec.yaml"
    "ios/Runner/Info.plist"
)

echo "============================================================"
echo "=== COPYING FILES ==="
echo "============================================================"

COPY_SUCCESS=0
COPY_FAILED=0

for file in "${FILES_TO_COPY[@]}"; do
    SOURCE_FILE="$SOURCE_BASE/$file"
    DEST_FILE="$DEST_BASE/$file"
    
    echo "Copying: $file"
    
    if [ ! -f "$SOURCE_FILE" ]; then
        echo "❌ Source file not found: $SOURCE_FILE"
        ((COPY_FAILED++))
        continue
    fi
    
    # Create destination directory if it doesn't exist
    DEST_DIR=$(dirname "$DEST_FILE")
    if [ ! -d "$DEST_DIR" ]; then
        mkdir -p "$DEST_DIR"
        echo "   Created directory: $DEST_DIR"
    fi
    
    # Copy file
    if cp "$SOURCE_FILE" "$DEST_FILE"; then
        echo "✅ Copied: $file"
        ((COPY_SUCCESS++))
    else
        echo "❌ Failed to copy: $file"
        ((COPY_FAILED++))
    fi
    echo ""
done

echo "============================================================"
echo "=== COPY SUMMARY ==="
echo "============================================================"
echo "✅ Successfully copied: $COPY_SUCCESS files"
echo "❌ Failed to copy: $COPY_FAILED files"
echo ""

if [ $COPY_FAILED -eq 0 ]; then
    echo "🎉 ALL FILES COPIED SUCCESSFULLY"
    echo ""
    echo "iOS Fixes v1.2.9+24 applied:"
    echo "- ✅ iOS device info support (about_screen.dart)"
    echo "- ✅ Settings persistence fix (about_screen.dart)"
    echo "- ✅ Full home_screen.dart with all features restored (home_screen.dart)"
    echo "- ✅ iOS-compatible device_service.dart (Platform.isIOS support)"
    echo "- ✅ Subscription services (subscription_service.dart, subscription_encryption_service.dart)"
    echo "- ✅ Translation service (translation_service.dart)"
    echo "- ✅ Language selector widget (language_selector.dart)"
    echo "- ✅ Subscription credential dialog (subscription_credential_dialog.dart)"
    echo "- ✅ iOS keyboard dismissal fix (tour_generator_screen.dart)"
    echo "- ✅ Version updated to 1.2.9+26 (pubspec.yaml)"
    echo "- ✅ Location permission descriptions (Info.plist)"
    echo ""
    echo "Ready for Assignment 28 Path A execution"
    exit 0
else
    echo "⚠️  SOME FILES FAILED TO COPY"
    echo "Please check the errors above and retry"
    exit 1
fi