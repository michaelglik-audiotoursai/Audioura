#!/bin/bash

# iOS File Copy Script (version-neutral)
# Copies all current iOS-compatible app files from USB to Mac Mini Flutter project.
# Update FILES_TO_COPY and the summary block below when files change.
# Run this, then run build_install_launch_a28.sh. Never mix build/install logic into this script.

echo "🍎 iOS AMAZON-Q - COPYING iOS FILES"
echo "Session Date: $(date '+%Y%m%d_%H%M%S')"
echo ""

SOURCE_BASE="/Volumes/USB DISK/Audioura/assets"
DEST_BASE="$HOME/Development/Audioura-build/audio_tour_app"

echo "Source: $SOURCE_BASE"
echo "Destination: $DEST_BASE"
echo ""

if [ ! -d "$SOURCE_BASE" ]; then
    echo "❌ ERROR: Source directory not found: $SOURCE_BASE"
    echo "Please ensure USB drive is mounted and contains updated files"
    exit 1
fi

if [ ! -d "$DEST_BASE" ]; then
    echo "❌ ERROR: Destination directory not found: $DEST_BASE"
    exit 1
fi

echo "✅ Source and destination directories verified"
echo ""

# ── PRE-FLIGHT: copy USB source files to DEST, then flutter analyze ──────────
# Strategy: copy first, then analyze. If analyze fails, the copy already happened
# but we abort before the user runs build. This is correct because flutter analyze
# needs a full project tree (pubspec.yaml, all lib files) to resolve imports.
# The post-flight analyze is the real gate — pre-flight is now removed.
# ──────────────────────────────────────────────────────────────────────────────

# Delete stale part files from Mac Mini that no longer exist in the project
for stale in \
    "$DEST_BASE/lib/screens/edit_tour_screen_part2.dart" \
    "$DEST_BASE/lib/screens/edit_tour_screen_part3.dart" \
    "$DEST_BASE/lib/screens/edit_tour_screen_part4.dart"; do
    if [ -f "$stale" ]; then
        rm "$stale"
        echo "🗑️  Removed stale: $(basename $stale)"
    fi
done
echo ""

FILES_TO_COPY=(
    "lib/screens/about_screen.dart"
    "lib/screens/home_screen.dart"
    "lib/screens/main_screen.dart"
    "lib/screens/my_tours_screen.dart"
    "lib/screens/tour_generator_screen.dart"
    "lib/screens/voice_methods.dart"
    "lib/screens/edit_tour_screen.dart"
    "lib/screens/edit_stop_screen.dart"
    "lib/screens/tour_player_screen.dart"
    "lib/screens/tour_map_screen.dart"
    "lib/screens/news_player_screen.dart"
    "lib/services/device_service.dart"
    "lib/services/subscription_service.dart"
    "lib/services/subscription_encryption_service.dart"
    "lib/services/translation_service.dart"
    "lib/services/voice_control_service.dart"
    "lib/services/html_audio_recorder_service.dart"
    "lib/widgets/language_selector.dart"
    "lib/widgets/subscription_credential_dialog.dart"
    "lib/config.dart"
    "pubspec.yaml"
    "ios/Runner/Info.plist"
    "ios/Podfile"
)

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

    DEST_DIR=$(dirname "$DEST_FILE")
    if [ ! -d "$DEST_DIR" ]; then
        mkdir -p "$DEST_DIR"
    fi

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
echo "✅ Successfully copied: $COPY_SUCCESS files"
echo "❌ Failed to copy: $COPY_FAILED files"
echo ""

if [ $COPY_FAILED -eq 0 ]; then
    echo "🎉 ALL FILES COPIED SUCCESSFULLY"
    echo ""
    echo "🔍 Running flutter analyze on Mac Mini after copy (post-flight)..."
    cd "$DEST_BASE" || exit 1
    flutter analyze --no-pub 2>&1 | tee /tmp/flutter_analyze_output.txt || true
    # Count errors only in files we own (exclude known pre-existing broken files)
    ANALYZE_ERRORS=$(grep " error " /tmp/flutter_analyze_output.txt \
        | grep -v "audio_handler.dart" \
        | grep -v "map_page.dart" \
        | wc -l | tr -d ' ')
    if [ "$ANALYZE_ERRORS" -gt 0 ]; then
        echo ""
        echo "❌ POST-FLIGHT FAILED: flutter analyze found $ANALYZE_ERRORS error(s) — do NOT build."
        grep " error " /tmp/flutter_analyze_output.txt | grep -v "audio_handler.dart" | grep -v "map_page.dart"
        exit 1
    fi
    echo "✅ Post-flight analyze passed (0 errors in project files)"
    echo ""
    echo "Next: run build_install_launch.sh"
    exit 0
else
    echo "⚠️  SOME FILES FAILED TO COPY - check errors above and retry"
    exit 1
fi
