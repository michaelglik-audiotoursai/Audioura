#!/bin/bash
# ASSIGNMENT 28: SIGN AND INSTALL RUNNER.APP ON IPHONE 16
# Signs the successfully built Runner.app from Assignment 27 and installs on iPhone 16.
# Tests app launch to confirm CwlCatchException framework loading works correctly.
#
# Created by Strategic Advisor Amazon-Q on 2026-04-29 16:10
# Based on Assignment 27 SUCCESS (Case A: build=0, FLUTTER_BUILD_DIR=YES, sentinels=YES)
#
# Prerequisites: Assignment 27 completed successfully with Runner.app built
# Target: iPhone 16 (UDID: 00008140-000558A902BA801C)
# Signing Identity: 594584F3D3BC571D94A822A2158871CA13898701

set -o pipefail

# --- Output capture to session log ---
exec > >(tee ~/Desktop/full_a28_session.txt) 2>&1

# --- Timestamps + system-date drift check ---
SESSION_DATE=$(date +"%Y%m%d_%H%M%S")
CURRENT_YEAR=$(date +"%Y")
if [ "$CURRENT_YEAR" != "2026" ]; then
    echo "WARNING: SYSTEM DATE DRIFT DETECTED: Current year is $CURRENT_YEAR, expected 2026"
    echo "Continuing with timestamp $SESSION_DATE but results may be mislabeled"
fi

echo "🍎 iOS AMAZON-Q - ASSIGNMENT 28: SIGN AND INSTALL RUNNER.APP"
echo "Session Date: $SESSION_DATE"
echo "Date (shell):  $(date)"
echo "Date (python): $(python3 -c 'import datetime; print(datetime.datetime.now())' 2>/dev/null || echo 'python3 not available')"
echo ""

# --- Paths and configuration ---
PROJECT_DIR="$HOME/Development/AudioTours/development/audio_tour_app"
RUNNER_APP="$PROJECT_DIR/build/ios/iphoneos/Runner.app"
SIGNING_IDENTITY="594584F3D3BC571D94A822A2158871CA13898701"
IPHONE_UDID="00008140-000558A902BA801C"
TEAM_ID="4HGRU6TKGQ"

USB_RESULTS="/Volumes/USB DISK/Audioura/results"
LOCAL_BACKUP="$HOME/Desktop/a28_results"
mkdir -p "$LOCAL_BACKUP"
echo "Local backup directory: $LOCAL_BACKUP"
echo ""

echo "============================================================"
echo "=== ASSIGNMENT 28: SIGN AND INSTALL iOS APP ==="
echo "============================================================"
echo "Goal: Sign Runner.app from Assignment 27 and install on iPhone 16"
echo "Expected: App launches without CwlCatchException crash"
echo "Target Device: iPhone 16 (UDID: $IPHONE_UDID)"
echo "Signing Identity: $SIGNING_IDENTITY"
echo ""

# ===========================================================================
# STEP 1: Verify Prerequisites
# ===========================================================================
echo "============================================================"
echo "=== STEP 1: VERIFY PREREQUISITES ==="
echo "============================================================"

if [ ! -d "$RUNNER_APP" ]; then
    echo "FATAL: Runner.app not found at $RUNNER_APP"
    echo "Assignment 27 must be completed successfully first."
    exit 1
fi
echo "✅ Runner.app exists: $RUNNER_APP"

if [ ! -d "$RUNNER_APP/Frameworks/CwlCatchException.framework" ]; then
    echo "FATAL: CwlCatchException.framework not found in Runner.app"
    echo "This framework is required for app launch."
    exit 1
fi
echo "✅ CwlCatchException.framework present in Runner.app"

# Check if iPhone is connected
if ! xcrun devicectl list devices | grep -q "$IPHONE_UDID"; then
    echo "FATAL: iPhone 16 (UDID: $IPHONE_UDID) not connected"
    echo "Please connect iPhone 16 via USB and unlock the device."
    exit 1
fi
echo "✅ iPhone 16 connected and detected"

# ===========================================================================
# STEP 2: Capture App State Before Signing
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 2: CAPTURE APP STATE BEFORE SIGNING ==="
echo "============================================================"

{
    echo "=== A28 RUNNER.APP STATE (before signing, timestamp: $SESSION_DATE) ==="
    echo ""
    echo "Runner.app size and structure:"
    ls -la "$RUNNER_APP"
    echo ""
    echo "Frameworks directory:"
    ls -la "$RUNNER_APP/Frameworks" | head -20
    echo ""
    echo "CwlCatchException.framework details:"
    ls -la "$RUNNER_APP/Frameworks/CwlCatchException.framework"
    echo ""
    echo "Current code signature status:"
    codesign -dv "$RUNNER_APP" 2>&1 || echo "No existing signature"
    echo ""
    echo "Framework signatures:"
    codesign -dv "$RUNNER_APP/Frameworks/CwlCatchException.framework" 2>&1 || echo "CwlCatchException not signed"
    codesign -dv "$RUNNER_APP/Frameworks/Flutter.framework" 2>&1 || echo "Flutter.framework not signed"
} > ~/Desktop/a28_before_signing.txt
echo "✅ App state captured to ~/Desktop/a28_before_signing.txt"

# ===========================================================================
# STEP 3: Sign the Application
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 3: SIGN THE APPLICATION ==="
echo "============================================================"

echo "Signing Runner.app with identity: $SIGNING_IDENTITY"
echo "Team ID: $TEAM_ID"

# Sign all frameworks first
echo "Signing frameworks..."
for framework in "$RUNNER_APP/Frameworks"/*.framework; do
    if [ -d "$framework" ]; then
        echo "  Signing $(basename "$framework")..."
        codesign --force --sign "$SIGNING_IDENTITY" --timestamp "$framework"
        if [ $? -ne 0 ]; then
            echo "FATAL: Failed to sign $(basename "$framework")"
            exit 1
        fi
    fi
done

# Sign the main app bundle
echo "Signing main app bundle..."
codesign --force --sign "$SIGNING_IDENTITY" --timestamp --entitlements "$PROJECT_DIR/ios/Runner/Runner.entitlements" "$RUNNER_APP"
if [ $? -ne 0 ]; then
    echo "FATAL: Failed to sign Runner.app"
    exit 1
fi

echo "✅ Application signing completed successfully"

# ===========================================================================
# STEP 4: Verify Signatures
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 4: VERIFY SIGNATURES ==="
echo "============================================================"

{
    echo "=== A28 SIGNATURE VERIFICATION (timestamp: $SESSION_DATE) ==="
    echo ""
    echo "Main app signature:"
    codesign -dv "$RUNNER_APP" 2>&1
    echo ""
    echo "Signature verification:"
    codesign --verify --verbose "$RUNNER_APP" 2>&1
    echo ""
    echo "CwlCatchException.framework signature:"
    codesign -dv "$RUNNER_APP/Frameworks/CwlCatchException.framework" 2>&1
    echo ""
    echo "Flutter.framework signature:"
    codesign -dv "$RUNNER_APP/Frameworks/Flutter.framework" 2>&1
} > ~/Desktop/a28_signature_verification.txt

# Verify signatures are valid
if ! codesign --verify "$RUNNER_APP" 2>/dev/null; then
    echo "FATAL: App signature verification failed"
    cat ~/Desktop/a28_signature_verification.txt
    exit 1
fi
echo "✅ All signatures verified successfully"

# ===========================================================================
# STEP 5: Install on iPhone 16
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 5: INSTALL ON IPHONE 16 ==="
echo "============================================================"

echo "Installing Runner.app on iPhone 16 (UDID: $IPHONE_UDID)..."

# Use xcrun devicectl to install
xcrun devicectl device install app --device "$IPHONE_UDID" "$RUNNER_APP" 2>&1 | tee ~/Desktop/a28_install_log.txt
INSTALL_EXIT=${PIPESTATUS[0]}

if [ "$INSTALL_EXIT" -eq 0 ]; then
    echo "✅ App installation completed successfully"
else
    echo "❌ App installation failed (exit code: $INSTALL_EXIT)"
    echo "Check ~/Desktop/a28_install_log.txt for details"
fi

# ===========================================================================
# STEP 6: Test App Launch
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 6: TEST APP LAUNCH ==="
echo "============================================================"

echo "Testing app launch on iPhone 16..."
echo "Bundle identifier: com.glikfamily.audioura"

# Launch the app
xcrun devicectl device process launch --device "$IPHONE_UDID" com.glikfamily.audioura 2>&1 | tee ~/Desktop/a28_launch_log.txt
LAUNCH_EXIT=${PIPESTATUS[0]}

if [ "$LAUNCH_EXIT" -eq 0 ]; then
    echo "✅ App launch command completed successfully"
    echo ""
    echo "🎉 CRITICAL TEST: Check iPhone 16 screen now!"
    echo "Expected: Audioura app should be running without crashes"
    echo "If you see the Audioura interface, Assignment 28 is SUCCESS!"
    echo ""
    echo "Manual verification steps:"
    echo "1. Check iPhone 16 screen - is Audioura app visible and running?"
    echo "2. Try basic navigation - can you access tours, settings, etc?"
    echo "3. Test network connectivity - can app connect to services?"
    echo "4. No crash dialogs or 'Library not loaded' errors?"
else
    echo "❌ App launch failed (exit code: $LAUNCH_EXIT)"
    echo "Check ~/Desktop/a28_launch_log.txt for details"
fi

# ===========================================================================
# STEP 7: Capture Final Results
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 7: CAPTURE FINAL RESULTS ==="
echo "============================================================"

{
    echo "=== ASSIGNMENT 28 FINAL RESULTS (timestamp: $SESSION_DATE) ==="
    echo ""
    echo "Installation exit code: $INSTALL_EXIT"
    echo "Launch exit code: $LAUNCH_EXIT"
    echo ""
    echo "Installation status: $([ "$INSTALL_EXIT" -eq 0 ] && echo "SUCCESS" || echo "FAILED")"
    echo "Launch status: $([ "$LAUNCH_EXIT" -eq 0 ] && echo "SUCCESS" || echo "FAILED")"
    echo ""
    echo "Manual verification required:"
    echo "- Check iPhone 16 screen for running Audioura app"
    echo "- Test basic app functionality"
    echo "- Verify no CwlCatchException crashes"
    echo ""
    echo "If app is running successfully on iPhone 16:"
    echo "🎉 ASSIGNMENT 28 SUCCESS - iOS development barrier completely eliminated!"
    echo "🎉 Audioura iOS app is now fully operational!"
    echo "🎉 Ready for production iOS deployment!"
    echo ""
    echo "Next steps if successful:"
    echo "- Test all Audioura features (tours, maps, voice, audio)"
    echo "- Verify network connectivity to services (192.168.0.136:5002/5004)"
    echo "- Prepare for App Store submission process"
} > ~/Desktop/a28_final_results.txt

cat ~/Desktop/a28_final_results.txt

# ===========================================================================
# STEP 8: Copy Results to USB + Local Backup
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 8: COPY RESULTS TO USB + LOCAL BACKUP ==="
echo "============================================================"

# Copy to USB with error handling
cp ~/Desktop/full_a28_session.txt        "$USB_RESULTS/full_a28_session_${SESSION_DATE}.txt"        || echo "USB copy failed: full_a28_session.txt"
cp ~/Desktop/a28_before_signing.txt      "$USB_RESULTS/a28_before_signing_${SESSION_DATE}.txt"      || echo "USB copy failed: a28_before_signing.txt"
cp ~/Desktop/a28_signature_verification.txt "$USB_RESULTS/a28_signature_verification_${SESSION_DATE}.txt" || echo "USB copy failed: a28_signature_verification.txt"
cp ~/Desktop/a28_install_log.txt         "$USB_RESULTS/a28_install_log_${SESSION_DATE}.txt"         || echo "USB copy failed: a28_install_log.txt"
cp ~/Desktop/a28_launch_log.txt          "$USB_RESULTS/a28_launch_log_${SESSION_DATE}.txt"          || echo "USB copy failed: a28_launch_log.txt"
cp ~/Desktop/a28_final_results.txt       "$USB_RESULTS/a28_final_results_${SESSION_DATE}.txt"       || echo "USB copy failed: a28_final_results.txt"

# Local backup copies
echo "--- Local backup copies ---"
cp ~/Desktop/full_a28_session.txt        "$LOCAL_BACKUP/"
cp ~/Desktop/a28_before_signing.txt      "$LOCAL_BACKUP/"
cp ~/Desktop/a28_signature_verification.txt "$LOCAL_BACKUP/"
cp ~/Desktop/a28_install_log.txt         "$LOCAL_BACKUP/"
cp ~/Desktop/a28_launch_log.txt          "$LOCAL_BACKUP/"
cp ~/Desktop/a28_final_results.txt       "$LOCAL_BACKUP/"
echo "✅ Local backup copies in $LOCAL_BACKUP"

# ===========================================================================
# ASSIGNMENT 28 COMPLETE
# ===========================================================================
echo ""
echo "============================================================"
echo "=== ASSIGNMENT 28 COMPLETE ==="
echo "============================================================"
echo ""
echo "Installation: $([ "$INSTALL_EXIT" -eq 0 ] && echo "SUCCESS" || echo "FAILED")"
echo "Launch: $([ "$LAUNCH_EXIT" -eq 0 ] && echo "SUCCESS" || echo "FAILED")"
echo ""
echo "🎯 CRITICAL: Check iPhone 16 screen for running Audioura app!"
echo ""
echo "Result files:"
echo "    USB:   $USB_RESULTS/*_${SESSION_DATE}.*"
echo "    Local: $LOCAL_BACKUP/"
echo ""
echo "If Audioura is running on iPhone 16 without crashes:"
echo "🎉 iOS DEVELOPMENT BARRIER ELIMINATED!"
echo "🎉 AUDIOURA iOS APP FULLY OPERATIONAL!"
echo "🎉 $260 INVESTMENT FULLY PROTECTED AND PRODUCTIVE!"
echo ""

exit 0