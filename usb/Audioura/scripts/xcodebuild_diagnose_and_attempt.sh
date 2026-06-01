#!/bin/bash
# ASSIGNMENT 22: XCODEBUILD ATTEMPT + XCODE_BACKEND.DART DIAGNOSTIC
# Phase B: Read the failing region of xcode_backend.dart and capture Flutter/Xcode versions.
# Phase A: Try invoking xcodebuild directly to bypass the flutter build wrapper.
# This script touches NO Dart code, NO pubspec.yaml, NO android/.

# Terminal session recorder
exec > >(tee ~/Desktop/xcodebuild_attempt_session.txt) 2>&1

echo "🍎 iOS AMAZON-Q - XCODEBUILD ATTEMPT + DIAGNOSTIC (Assignment 22)"
echo "Date: $(python3 -c "import datetime; print(datetime.datetime.now())")"
echo ""

cd ~/Development/AudioTours/development/audio_tour_app

echo "============================================================"
echo "=== PHASE B: DIAGNOSTICS (these are the most important outputs) ==="
echo "============================================================"

echo ""
echo "--- DIAG B1: Flutter version ---"
flutter --version 2>&1

echo ""
echo "--- DIAG B2: Flutter doctor (Xcode version, iOS SDK, etc.) ---"
flutter doctor -v 2>&1 | head -80

echo ""
echo "--- DIAG B3: Lines 300-370 of xcode_backend.dart (the failing region) ---"
echo "Question: what is the script expecting to be non-null at line 345?"
cat -n ~/flutter/packages/flutter_tools/bin/xcode_backend.dart 2>/dev/null | sed -n '300,370p' || echo "❌ Could not read xcode_backend.dart"

echo ""
echo "--- DIAG B4: Search for the variable being null-checked at line 345 ---"
echo "Pull surrounding context for _embedNativeAssets:"
grep -n -A5 "_embedNativeAssets" ~/flutter/packages/flutter_tools/bin/xcode_backend.dart 2>&1 | head -40

echo ""
echo "--- DIAG B5: Verify Podfile is in reverted state ---"
if grep -q "CwlCatchException" ios/Podfile; then
    echo "❌ CwlCatchException still in ios/Podfile — revert was not preserved"
    echo "Aborting. Re-run podfile_revert_and_diagnose.sh first."
    exit 1
else
    echo "✅ ios/Podfile is in reverted state"
fi

echo ""
echo "--- DIAG B6: Verify Pods/ and Generated.xcconfig exist ---"
if [ ! -d "ios/Pods" ]; then
    echo "⚠️  ios/Pods/ missing — running pod install"
    (cd ios && pod install) || { echo "❌ pod install failed"; exit 1; }
fi
if [ ! -f "ios/Flutter/Generated.xcconfig" ]; then
    echo "⚠️  Generated.xcconfig missing — running flutter pub get"
    flutter pub get || { echo "❌ flutter pub get failed"; exit 1; }
fi
echo "✅ Pods/ and Generated.xcconfig present"

echo ""
echo "============================================================"
echo "=== PHASE A: XCODEBUILD DIRECT ATTEMPT ==="
echo "============================================================"
echo "Calling xcodebuild directly. The Run Script phase will still invoke"
echo "xcode_backend.dart, but environment variables may differ from what"
echo "'flutter build ios' sets. We'll see whether that changes the outcome."
echo ""

cd ios

xcodebuild \
    -workspace Runner.xcworkspace \
    -scheme Runner \
    -configuration Release \
    -sdk iphoneos \
    -destination "generic/platform=iOS" \
    -derivedDataPath ../build/xcodebuild_derived/ \
    build \
    CODE_SIGNING_ALLOWED=NO \
    CODE_SIGNING_REQUIRED=NO \
    2>&1
XCODEBUILD_EXIT=$?

cd ..

echo ""
echo "xcodebuild exit code: $XCODEBUILD_EXIT"

if [ $XCODEBUILD_EXIT -ne 0 ]; then
    echo ""
    echo "❌ xcodebuild failed."
    echo ""
    echo "If the failure was the same xcode_backend.dart:345 null, we have confirmed"
    echo "that bypassing 'flutter build' is not enough. Phase B diagnostics above"
    echo "give Claude what it needs to write the actual fix."
    echo ""
    echo "Copying session log to USB so Claude can read it."
    cp ~/Desktop/xcodebuild_attempt_session.txt "/Volumes/USB DISK/Audioura/results/xcodebuild_attempt_session.txt" 2>/dev/null || echo "⚠️  USB auto-copy failed — copy manually"
    exit 1
fi

echo "✅ xcodebuild build phase succeeded"

# Locate the resulting Runner.app inside derivedData
RUNNER_APP=$(find build/xcodebuild_derived -path "*Release-iphoneos*Runner.app" -type d 2>/dev/null | head -1)

if [ -z "$RUNNER_APP" ] || [ ! -d "$RUNNER_APP" ]; then
    echo "❌ Could not locate Runner.app in build output. Listing what was produced:"
    find build/xcodebuild_derived -name "Runner.app" 2>&1
    exit 1
fi

echo "✅ Runner.app found at: $RUNNER_APP"

echo ""
echo "============================================================"
echo "=== STEP 7: SIX FRAMEWORK DIAGNOSTICS ON THE BUILT APP ==="
echo "============================================================"
echo "(Same six diagnostics from Assignment 21 — never reached then.)"

echo ""
echo "--- DIAGNOSTIC 1: Contents of Runner.app/Frameworks/ ---"
ls -la "$RUNNER_APP/Frameworks/" 2>&1 || echo "(Frameworks/ does not exist)"

echo ""
echo "--- DIAGNOSTIC 2: CwlCatchException.framework specifically ---"
if [ -d "$RUNNER_APP/Frameworks/CwlCatchException.framework" ]; then
    echo "✅ CwlCatchException.framework IS in the app bundle:"
    ls -la "$RUNNER_APP/Frameworks/CwlCatchException.framework/"
    echo ""
    echo "Binary file info:"
    file "$RUNNER_APP/Frameworks/CwlCatchException.framework/CwlCatchException" 2>&1 || echo "(binary missing)"
else
    echo "❌ CwlCatchException.framework NOT in app bundle"
    echo "(This means the build succeeded but framework embedding still failed silently.)"
fi

echo ""
echo "--- DIAGNOSTIC 3: Runner binary linker references to CwlCatchException ---"
otool -L "$RUNNER_APP/Runner" 2>&1 | grep -i cwl || echo "(no cwl reference in Runner)"

echo ""
echo "--- DIAGNOSTIC 4: Runner binary @rpath search paths ---"
otool -l "$RUNNER_APP/Runner" 2>&1 | grep -A2 LC_RPATH

echo ""
echo "--- DIAGNOSTIC 5: All .framework directories produced by the build ---"
find build/xcodebuild_derived -maxdepth 7 -name "*.framework" -type d 2>&1

echo ""
echo "--- DIAGNOSTIC 6: Code signing on CwlCatchException.framework (if present) ---"
if [ -d "$RUNNER_APP/Frameworks/CwlCatchException.framework" ]; then
    codesign -dvvv "$RUNNER_APP/Frameworks/CwlCatchException.framework" 2>&1 || echo "(framework not signed)"
else
    echo "(skipped — framework not in app bundle)"
fi

echo ""
echo "============================================================"
echo "=== STEP 8: SIGN AND INSTALL ON IPHONE ==="
echo "============================================================"

CERT_HASH="594584F3D3BC571D94A822A2158871CA13898701"
if ! security find-identity -v -p codesigning | grep -q "$CERT_HASH"; then
    echo "❌ Certificate $CERT_HASH not found in keychain — aborting"
    exit 1
fi

cat > entitlements.plist << 'EOF2'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>application-identifier</key>
    <string>4HGRU6TKGQ.com.glikfamily.audioura</string>
    <key>com.apple.developer.team-identifier</key>
    <string>4HGRU6TKGQ</string>
</dict>
</plist>
EOF2

codesign --force --sign "$CERT_HASH" --entitlements entitlements.plist --timestamp "$RUNNER_APP" || { echo "❌ codesign failed"; exit 1; }
echo "✅ App signed"

DEVICE_ID="00008140-000558A902BA801C"
xcrun devicectl device install app --device "$DEVICE_ID" "$RUNNER_APP" || { echo "❌ devicectl install failed (may indicate framework embedding bug)"; }

echo ""
echo "============================================================"
echo "=== DONE ==="
echo "============================================================"
echo "1. If install succeeded, try launching Audioura on the iPhone."
echo "2. If app launches: huge win — Assignment 22 succeeded."
echo "3. If app crashes with 'Library not loaded': diagnostic 2 above will"
echo "   tell us whether the framework was missing or signed incorrectly."
echo ""

cp ~/Desktop/xcodebuild_attempt_session.txt "/Volumes/USB DISK/Audioura/results/xcodebuild_attempt_session.txt" 2>/dev/null || echo "⚠️  USB auto-copy failed"
echo "Session log: ~/Desktop/xcodebuild_attempt_session.txt"
echo "Done."