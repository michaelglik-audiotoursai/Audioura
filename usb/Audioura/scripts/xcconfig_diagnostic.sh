#!/bin/bash
# ASSIGNMENT 23: READ XCCONFIG FILES TO CONFIRM FIX APPROACH
# Quick diagnostic to see what env vars are currently defined in Flutter xcconfig files
# This takes 30 seconds and tells us exactly what to add in Assignment 24

# Terminal session recorder
exec > >(tee ~/Desktop/xcconfig_diagnostic_session.txt) 2>&1

echo "🍎 iOS AMAZON-Q - XCCONFIG DIAGNOSTIC (Assignment 23)"
echo "Date: $(python3 -c "import datetime; print(datetime.datetime.now())")"
echo ""

cd ~/Development/AudioTours/development/audio_tour_app

echo "============================================================"
echo "=== XCCONFIG FILES DIAGNOSTIC ==="
echo "============================================================"

echo ""
echo "--- FILE 1: Generated.xcconfig (Flutter auto-generated) ---"
echo "Path: ios/Flutter/Generated.xcconfig"
if [ -f "ios/Flutter/Generated.xcconfig" ]; then
    echo "✅ File exists. Contents:"
    cat ios/Flutter/Generated.xcconfig
else
    echo "❌ File missing"
fi

echo ""
echo "--- FILE 2: Release.xcconfig (project-level) ---"
echo "Path: ios/Flutter/Release.xcconfig"
if [ -f "ios/Flutter/Release.xcconfig" ]; then
    echo "✅ File exists. Contents:"
    cat ios/Flutter/Release.xcconfig
else
    echo "❌ File missing"
fi

echo ""
echo "--- FILE 3: Debug.xcconfig (project-level) ---"
echo "Path: ios/Flutter/Debug.xcconfig"
if [ -f "ios/Flutter/Debug.xcconfig" ]; then
    echo "✅ File exists. Contents:"
    cat ios/Flutter/Debug.xcconfig
else
    echo "❌ File missing"
fi

echo ""
echo "--- ANALYSIS: What's missing? ---"
echo "Looking for FLUTTER_BUILD_DIR in any of the above files..."
if grep -q "FLUTTER_BUILD_DIR" ios/Flutter/*.xcconfig 2>/dev/null; then
    echo "✅ FLUTTER_BUILD_DIR found in xcconfig files"
    grep -n "FLUTTER_BUILD_DIR" ios/Flutter/*.xcconfig
else
    echo "❌ FLUTTER_BUILD_DIR NOT found in any xcconfig files"
    echo "This confirms Claude's analysis - we need to add it!"
fi

echo ""
echo "--- FLUTTER_ROOT CHECK ---"
echo "Looking for FLUTTER_ROOT in xcconfig files..."
if grep -q "FLUTTER_ROOT" ios/Flutter/*.xcconfig 2>/dev/null; then
    echo "✅ FLUTTER_ROOT found in xcconfig files"
    grep -n "FLUTTER_ROOT" ios/Flutter/*.xcconfig
else
    echo "❌ FLUTTER_ROOT also missing"
fi

echo ""
echo "============================================================"
echo "=== RECOMMENDATION FOR ASSIGNMENT 24 ==="
echo "============================================================"
echo "Based on the above analysis:"
echo "1. If FLUTTER_BUILD_DIR is missing: Add 'FLUTTER_BUILD_DIR=build' to Release.xcconfig and Debug.xcconfig"
echo "2. If FLUTTER_ROOT is missing: Add 'FLUTTER_ROOT=/Users/micha/flutter' to xcconfig files"
echo "3. Test with direct xcodebuild to confirm fix"
echo ""

cp ~/Desktop/xcconfig_diagnostic_session.txt "/Volumes/USB DISK/Audioura/results/xcconfig_diagnostic_session.txt" 2>/dev/null || echo "⚠️  USB auto-copy failed"
echo "Session log: ~/Desktop/xcconfig_diagnostic_session.txt"
echo "Done - ready for Assignment 24 fix!"