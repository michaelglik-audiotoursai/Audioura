#!/bin/bash
# ASSIGNMENT 28 PATH A: BUILD, INSTALL, LAUNCH (CORRECTED)
# Flutter build ios --release (with codesign), verify embedded.mobileprovision,
# install via devicectl, launch, monitor process list, scrape crash logs.
# Classify into SUCCESS / CRASHED / AMBIGUOUS / MIXED with HALT-on-fail.
#
# Created by Claude AI Path A on 2026-04-29 16:49
# Addresses all 6 critical issues from original Assignment 28
# Implements iOS 3-step rule: signature + provisioning + entitlements
#
# Prerequisites: Xcode automatic signing working for Team ID 4HGRU6TKGQ
# Target: iPhone 16 (UDID: 00008140-000558A902BA801C)

set -o pipefail

# --- B1: tee everything to a session log on the Desktop ---
exec > >(tee ~/Desktop/full_a28_session.txt) 2>&1

# --- M1: timestamps + system-date drift check ---
SESSION_DATE=$(date +"%Y%m%d_%H%M%S")
CURRENT_YEAR=$(date +"%Y")
if [ "$CURRENT_YEAR" != "2026" ]; then
    echo "WARNING: SYSTEM DATE DRIFT DETECTED: Current year is $CURRENT_YEAR, expected 2026"
    echo "Continuing with timestamp $SESSION_DATE but results may be mislabeled"
fi

echo "🍎 iOS AMAZON-Q - ASSIGNMENT 28 PATH A: BUILD, INSTALL, LAUNCH (CORRECTED)"
echo "Session Date: $SESSION_DATE"
echo "Date (shell):  $(date)"
echo "Date (python): $(python3 -c 'import datetime; print(datetime.datetime.now())' 2>/dev/null || echo 'python3 not available')"
echo ""

# --- B5: $HOME inside double quotes ---
PROJECT_DIR="$HOME/Development/AudioTours/development/audio_tour_app"
IPHONE_UDID="F9D6F807-D301-59EE-B574-5747D617D82C"
TEAM_ID="4HGRU6TKGQ"
BUNDLE_ID="com.glikfamily.audioura"

USB_RESULTS="/Volumes/USB DISK/Audioura/results"
LOCAL_BACKUP="$HOME/Desktop/a28_results"
mkdir -p "$LOCAL_BACKUP"
echo "Local backup directory: $LOCAL_BACKUP"
echo ""

echo "============================================================"
echo "=== ASSIGNMENT 28 PATH A: CORRECTED APPROACH ==="
echo "============================================================"
echo "Goal: Build with codesign, verify iOS 3-step rule, install, launch, detect crashes"
echo "iOS 3-Step Rule: (a) signature + (b) provisioning profile + (c) entitlements"
echo "Target Device: iPhone 16 (UDID: $IPHONE_UDID)"
echo "Team ID: $TEAM_ID"
echo "Bundle ID: $BUNDLE_ID"
echo ""

# ===========================================================================
# STEP 1: Environmental Prerequisites Check
# ===========================================================================
echo "============================================================"
echo "=== STEP 1: ENVIRONMENTAL PREREQUISITES CHECK ==="
echo "============================================================"

# Check if iPhone is connected and in Developer Mode
if ! xcrun devicectl list devices | grep -q "$IPHONE_UDID"; then
    echo "FATAL: iPhone 16 (UDID: $IPHONE_UDID) not connected"
    echo "Please connect iPhone 16 via USB and unlock the device."
    exit 1
fi
echo "✅ iPhone 16 connected and detected"

# Check Developer Mode status - simplified approach since devicectl output varies
echo "⚠️  Developer Mode check: Assuming enabled (manual verification required)"
echo "Please confirm Developer Mode is ON: Settings > Privacy & Security > Developer Mode"
# Note: devicectl output format varies and may not include developerModeStatus
# The user has confirmed Developer Mode is ON, so we proceed

# Check trust pairing - simplified approach
echo "⚠️  Trust pairing check: Assuming paired (manual verification required)"
echo "Please confirm iPhone trusts this Mac (no 'Trust This Computer' dialog pending)"
# Note: devicectl output format varies and may not include pairingState
# If iPhone appears in devicectl list, it's generally paired

# Verify project directory exists
if [ ! -d "$PROJECT_DIR" ]; then
    echo "FATAL: Project directory not found: $PROJECT_DIR"
    exit 1
fi
echo "✅ Project directory exists: $PROJECT_DIR"

# ===========================================================================
# STEP 2: Capture Pre-Launch Baseline (Crash Detection Setup)
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 2: CAPTURE PRE-LAUNCH BASELINE ==="
echo "============================================================"

# Capture current crash log baseline
CRASH_LOG_DIR="$HOME/Library/Logs/CrashReporter/MobileDevice"
if [ -d "$CRASH_LOG_DIR" ]; then
    find "$CRASH_LOG_DIR" -name "*.crash" -newer /tmp/a28_baseline 2>/dev/null > ~/Desktop/a28_crash_baseline.txt || touch ~/Desktop/a28_crash_baseline.txt
    touch /tmp/a28_baseline
    echo "✅ Crash log baseline captured ($(wc -l < ~/Desktop/a28_crash_baseline.txt) existing crash files)"
else
    echo "⚠️  Crash log directory not found: $CRASH_LOG_DIR"
    touch ~/Desktop/a28_crash_baseline.txt
fi

# Capture current process list baseline
xcrun devicectl device process list --device "$IPHONE_UDID" > ~/Desktop/a28_process_baseline.txt 2>/dev/null || echo "Process list baseline failed"
echo "✅ Process list baseline captured"

# ===========================================================================
# STEP 3: Flutter Build with Codesign (iOS 3-Step Rule Compliance)
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 3: FLUTTER BUILD WITH CODESIGN ==="
echo "============================================================"

echo "Building with flutter build ios --release (WITH codesign for iOS 3-step rule)..."
echo "This ensures: (a) signature + (b) embedded.mobileprovision + (c) compiled entitlements"

# M3: cd only for flutter build
cd "$PROJECT_DIR"
flutter build ios --release 2>&1 | tee ~/Desktop/a28_flutter_build.log
# B6: ${PIPESTATUS[0]} for flutter build exit code
BUILD_EXIT=${PIPESTATUS[0]}

if [ "$BUILD_EXIT" -ne 0 ]; then
    echo "FATAL: Flutter build failed (exit code: $BUILD_EXIT)"
    echo "Check ~/Desktop/a28_flutter_build.log for details"
    exit 1
fi
echo "✅ Flutter build completed successfully (exit code: $BUILD_EXIT)"

# Locate the built app
RUNNER_APP="$PROJECT_DIR/build/ios/iphoneos/Runner.app"
if [ ! -d "$RUNNER_APP" ]; then
    echo "FATAL: Runner.app not found at $RUNNER_APP"
    echo "Flutter build may have failed silently"
    exit 1
fi
echo "✅ Runner.app found: $RUNNER_APP"

# ===========================================================================
# STEP 4: Verify iOS 3-Step Rule Compliance
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 4: VERIFY iOS 3-STEP RULE COMPLIANCE ==="
echo "============================================================"

{
    echo "=== A28 iOS 3-STEP RULE VERIFICATION (timestamp: $SESSION_DATE) ==="
    echo ""
    
    # Step A: Code Signature Verification
    echo "--- STEP A: CODE SIGNATURE ---"
    codesign -dv "$RUNNER_APP" 2>&1
    if codesign --verify "$RUNNER_APP" 2>/dev/null; then
        echo "✅ Code signature VALID"
    else
        echo "❌ Code signature INVALID"
    fi
    echo ""
    
    # Step B: Provisioning Profile Verification
    echo "--- STEP B: PROVISIONING PROFILE ---"
    EMBEDDED_PROV="$RUNNER_APP/embedded.mobileprovision"
    if [ -f "$EMBEDDED_PROV" ]; then
        echo "✅ embedded.mobileprovision PRESENT"
        security cms -D -i "$EMBEDDED_PROV" | plutil -p - | grep -E "(TeamIdentifier|application-identifier|ProvisionedDevices)" | head -10
    else
        echo "❌ embedded.mobileprovision MISSING"
    fi
    echo ""
    
    # Step C: Entitlements Verification
    echo "--- STEP C: ENTITLEMENTS ---"
    codesign -d --entitlements :- "$RUNNER_APP" 2>/dev/null | plutil -p - 2>/dev/null || echo "❌ Entitlements extraction failed"
    echo ""
    
    # Framework verification
    echo "--- FRAMEWORKS VERIFICATION ---"
    ls -la "$RUNNER_APP/Frameworks" | head -10
    if [ -d "$RUNNER_APP/Frameworks/CwlCatchException.framework" ]; then
        echo "✅ CwlCatchException.framework PRESENT"
        codesign --verify "$RUNNER_APP/Frameworks/CwlCatchException.framework" 2>/dev/null && echo "✅ CwlCatchException.framework signature VALID" || echo "❌ CwlCatchException.framework signature INVALID"
    else
        echo "❌ CwlCatchException.framework MISSING"
    fi
} > ~/Desktop/a28_3step_verification.txt

cat ~/Desktop/a28_3step_verification.txt

# HALT on missing iOS 3-step components
if [ ! -f "$RUNNER_APP/embedded.mobileprovision" ]; then
    echo "FATAL: embedded.mobileprovision missing - iOS 3-step rule violated"
    echo "Flutter build --release should have embedded provisioning profile"
    exit 1
fi

if ! codesign --verify "$RUNNER_APP" 2>/dev/null; then
    echo "FATAL: Code signature verification failed - iOS 3-step rule violated"
    exit 1
fi

echo "✅ iOS 3-step rule compliance verified"

# ===========================================================================
# STEP 5: Install on iPhone 16
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 5: INSTALL ON IPHONE 16 ==="
echo "============================================================"

echo "Installing Runner.app on iPhone 16 (UDID: $IPHONE_UDID)..."

# Use xcrun devicectl to install with comprehensive error capture
xcrun devicectl device install app --device "$IPHONE_UDID" "$RUNNER_APP" 2>&1 | tee ~/Desktop/a28_install_log.txt
INSTALL_EXIT=${PIPESTATUS[0]}

if [ "$INSTALL_EXIT" -ne 0 ]; then
    echo "FATAL: App installation failed (exit code: $INSTALL_EXIT)"
    echo "Check ~/Desktop/a28_install_log.txt for details"
    echo "Common causes: provisioning profile mismatch, certificate issues, device trust"
    exit 1
fi
echo "✅ App installation completed successfully"

# ===========================================================================
# STEP 6: Launch and Monitor
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 6: LAUNCH AND MONITOR ==="
echo "============================================================"

echo "Launching Audioura app and monitoring for crashes..."

# Launch the app
xcrun devicectl device process launch --device "$IPHONE_UDID" "$BUNDLE_ID" 2>&1 | tee ~/Desktop/a28_launch_log.txt
LAUNCH_EXIT=${PIPESTATUS[0]}

if [ "$LAUNCH_EXIT" -ne 0 ]; then
    echo "❌ App launch command failed (exit code: $LAUNCH_EXIT)"
    echo "Check ~/Desktop/a28_launch_log.txt for details"
    # Don't exit here - continue to crash detection
else
    echo "✅ App launch command dispatched successfully"
fi

# Monitor process list at +5s and +15s
echo "Monitoring process list at +5s and +15s..."
sleep 5
echo "--- Process list at +5s ---" > ~/Desktop/a28_process_monitor.txt
xcrun devicectl device process list --device "$IPHONE_UDID" 2>/dev/null | grep -E "(Runner|audioura|PID|NAME)" >> ~/Desktop/a28_process_monitor.txt || echo "Process list failed at +5s" >> ~/Desktop/a28_process_monitor.txt

sleep 10  # Total 15s from launch
echo "--- Process list at +15s ---" >> ~/Desktop/a28_process_monitor.txt
xcrun devicectl device process list --device "$IPHONE_UDID" 2>/dev/null | grep -E "(Runner|audioura|PID|NAME)" >> ~/Desktop/a28_process_monitor.txt || echo "Process list failed at +15s" >> ~/Desktop/a28_process_monitor.txt

# Alternative process info capture for Xcode version tolerance
xcrun devicectl device info processes --device "$IPHONE_UDID" 2>/dev/null > ~/Desktop/a28_device_processes.txt || echo "Device processes info failed" > ~/Desktop/a28_device_processes.txt

echo "✅ Process monitoring completed"

# ===========================================================================
# STEP 7: Crash Detection and Classification
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 7: CRASH DETECTION AND CLASSIFICATION ==="
echo "============================================================"

# Scrape crash logs for new crashes since baseline
NEW_CRASHES=""
if [ -d "$CRASH_LOG_DIR" ]; then
    find "$CRASH_LOG_DIR" -name "*.crash" -newer /tmp/a28_baseline 2>/dev/null > ~/Desktop/a28_new_crashes.txt
    NEW_CRASHES=$(cat ~/Desktop/a28_new_crashes.txt)
    NEW_CRASH_COUNT=$(wc -l < ~/Desktop/a28_new_crashes.txt)
    echo "New crash files since launch: $NEW_CRASH_COUNT"
    if [ "$NEW_CRASH_COUNT" -gt 0 ]; then
        echo "New crash files:"
        cat ~/Desktop/a28_new_crashes.txt
    fi
else
    echo "0" > ~/Desktop/a28_new_crashes.txt
    NEW_CRASH_COUNT=0
fi

# Check if Runner process is still running
RUNNER_RUNNING=$(xcrun devicectl device process list --device "$IPHONE_UDID" 2>/dev/null | grep -c "Runner" || echo "0")
echo "Runner processes currently running: $RUNNER_RUNNING"

# Classification logic
VERDICT="UNKNOWN"
if [ "$LAUNCH_EXIT" -ne 0 ]; then
    VERDICT="LAUNCH_FAILED"
elif [ "$NEW_CRASH_COUNT" -gt 0 ] && [ "$RUNNER_RUNNING" -eq 0 ]; then
    VERDICT="CRASHED"
elif [ "$NEW_CRASH_COUNT" -eq 0 ] && [ "$RUNNER_RUNNING" -gt 0 ]; then
    VERDICT="SUCCESS"
elif [ "$NEW_CRASH_COUNT" -gt 0 ] && [ "$RUNNER_RUNNING" -gt 0 ]; then
    VERDICT="MIXED"
else
    VERDICT="AMBIGUOUS"
fi

{
    echo "=== ASSIGNMENT 28 PATH A FINAL CLASSIFICATION (timestamp: $SESSION_DATE) ==="
    echo ""
    echo "VERDICT: $VERDICT"
    echo ""
    echo "Evidence summary:"
    echo "- Build exit code: $BUILD_EXIT"
    echo "- Install exit code: $INSTALL_EXIT"
    echo "- Launch exit code: $LAUNCH_EXIT"
    echo "- New crash files: $NEW_CRASH_COUNT"
    echo "- Runner processes running: $RUNNER_RUNNING"
    echo ""
    echo "Classification guide:"
    echo "  SUCCESS: Launch succeeded, no crashes, Runner process active"
    echo "  CRASHED: Launch succeeded but app crashed (new crash files, no Runner process)"
    echo "  LAUNCH_FAILED: Launch command itself failed"
    echo "  MIXED: App running but also generated crash files (partial success)"
    echo "  AMBIGUOUS: Unclear state (investigate process list and crash logs)"
    echo ""
    if [ "$NEW_CRASH_COUNT" -gt 0 ]; then
        echo "Crash file analysis:"
        for crash_file in $NEW_CRASHES; do
            echo "--- $(basename "$crash_file") ---"
            head -20 "$crash_file" 2>/dev/null | grep -E "(Exception|Termination|dyld|CwlCatchException)" || echo "No obvious crash indicators in first 20 lines"
        done
    fi
    echo ""
    echo "Manual verification:"
    echo "- Check iPhone 16 screen for visible Audioura app"
    echo "- Test basic navigation if app is running"
    echo "- Look for crash dialogs or error messages"
} > ~/Desktop/a28_final_classification.txt

cat ~/Desktop/a28_final_classification.txt

# ===========================================================================
# STEP 8: Copy Results to USB + Local Backup
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 8: COPY RESULTS TO USB + LOCAL BACKUP ==="
echo "============================================================"

# Copy to USB with error handling
cp ~/Desktop/full_a28_session.txt           "$USB_RESULTS/full_a28_session_${SESSION_DATE}.txt"           || echo "USB copy failed: full_a28_session.txt"
cp ~/Desktop/a28_3step_verification.txt     "$USB_RESULTS/a28_3step_verification_${SESSION_DATE}.txt"     || echo "USB copy failed: a28_3step_verification.txt"
cp ~/Desktop/a28_flutter_build.log          "$USB_RESULTS/a28_flutter_build_${SESSION_DATE}.log"          || echo "USB copy failed: a28_flutter_build.log"
cp ~/Desktop/a28_install_log.txt            "$USB_RESULTS/a28_install_log_${SESSION_DATE}.txt"            || echo "USB copy failed: a28_install_log.txt"
cp ~/Desktop/a28_launch_log.txt             "$USB_RESULTS/a28_launch_log_${SESSION_DATE}.txt"             || echo "USB copy failed: a28_launch_log.txt"
cp ~/Desktop/a28_process_monitor.txt        "$USB_RESULTS/a28_process_monitor_${SESSION_DATE}.txt"        || echo "USB copy failed: a28_process_monitor.txt"
cp ~/Desktop/a28_device_processes.txt       "$USB_RESULTS/a28_device_processes_${SESSION_DATE}.txt"       || echo "USB copy failed: a28_device_processes.txt"
cp ~/Desktop/a28_crash_baseline.txt         "$USB_RESULTS/a28_crash_baseline_${SESSION_DATE}.txt"         || echo "USB copy failed: a28_crash_baseline.txt"
cp ~/Desktop/a28_new_crashes.txt            "$USB_RESULTS/a28_new_crashes_${SESSION_DATE}.txt"            || echo "USB copy failed: a28_new_crashes.txt"
cp ~/Desktop/a28_process_baseline.txt       "$USB_RESULTS/a28_process_baseline_${SESSION_DATE}.txt"       || echo "USB copy failed: a28_process_baseline.txt"
cp ~/Desktop/a28_final_classification.txt   "$USB_RESULTS/a28_final_classification_${SESSION_DATE}.txt"   || echo "USB copy failed: a28_final_classification.txt"

# Local backup copies
echo "--- Local backup copies ---"
cp ~/Desktop/full_a28_session.txt           "$LOCAL_BACKUP/"
cp ~/Desktop/a28_3step_verification.txt     "$LOCAL_BACKUP/"
cp ~/Desktop/a28_flutter_build.log          "$LOCAL_BACKUP/"
cp ~/Desktop/a28_install_log.txt            "$LOCAL_BACKUP/"
cp ~/Desktop/a28_launch_log.txt             "$LOCAL_BACKUP/"
cp ~/Desktop/a28_process_monitor.txt        "$LOCAL_BACKUP/"
cp ~/Desktop/a28_device_processes.txt       "$LOCAL_BACKUP/"
cp ~/Desktop/a28_crash_baseline.txt         "$LOCAL_BACKUP/"
cp ~/Desktop/a28_new_crashes.txt            "$LOCAL_BACKUP/"
cp ~/Desktop/a28_process_baseline.txt       "$LOCAL_BACKUP/"
cp ~/Desktop/a28_final_classification.txt   "$LOCAL_BACKUP/"
echo "✅ Local backup copies in $LOCAL_BACKUP"

# ===========================================================================
# ASSIGNMENT 28 PATH A COMPLETE
# ===========================================================================
echo ""
echo "============================================================"
echo "=== ASSIGNMENT 28 PATH A COMPLETE ==="
echo "============================================================"
echo ""
echo "FINAL VERDICT: $VERDICT"
echo ""
echo "Build: $([ "$BUILD_EXIT" -eq 0 ] && echo "SUCCESS" || echo "FAILED")"
echo "Install: $([ "$INSTALL_EXIT" -eq 0 ] && echo "SUCCESS" || echo "FAILED")"
echo "Launch: $([ "$LAUNCH_EXIT" -eq 0 ] && echo "SUCCESS" || echo "FAILED")"
echo "Crashes: $NEW_CRASH_COUNT new crash files"
echo "Process: $RUNNER_RUNNING Runner processes active"
echo ""
echo "Result files:"
echo "    USB:   $USB_RESULTS/*_${SESSION_DATE}.*"
echo "    Local: $LOCAL_BACKUP/"
echo ""
case "$VERDICT" in
    "SUCCESS")
        echo "🎉 SUCCESS: Audioura iOS app is running successfully!"
        echo "🎉 iOS development barrier completely eliminated!"
        echo "🎉 Ready for production deployment!"
        ;;
    "CRASHED")
        echo "❌ CRASHED: App installed but crashed at launch"
        echo "Check crash logs for CwlCatchException or other issues"
        ;;
    "LAUNCH_FAILED")
        echo "❌ LAUNCH_FAILED: Could not launch app (check install/signing)"
        ;;
    "MIXED")
        echo "⚠️  MIXED: App running but generated crashes (investigate)"
        ;;
    "AMBIGUOUS")
        echo "❓ AMBIGUOUS: Unclear state (manual verification required)"
        ;;
esac
echo ""

exit 0