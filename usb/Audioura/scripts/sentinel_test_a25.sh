#!/bin/bash
# ASSIGNMENT 25: SENTINEL TEST FOR XCCONFIG BASE-CONFIGURATION LOADING
# DIAGNOSIS ONLY - NO FIXES
# Determines whether Release.xcconfig and Debug.xcconfig are loaded as the
# active base configuration, by inserting unique sentinel keys and checking
# whether they propagate to the Run Script Phase environment via printenv.
# Bug-fixes from A24 review baked in upfront (B1-B6, M1, M3, M5).

# B1: redirect script output to a tee log; do NOT use `script` from inside script body
exec > >(tee ~/Desktop/full_a25_session.txt) 2>&1

# M1: capture session timestamp + check for system-date drift
SESSION_DATE=$(date +"%Y%m%d_%H%M%S")
CURRENT_YEAR=$(date +"%Y")
if [ "$CURRENT_YEAR" != "2026" ]; then
    echo "WARNING: SYSTEM DATE DRIFT DETECTED: Current year is $CURRENT_YEAR, expected 2026"
    echo "Continuing with timestamp $SESSION_DATE but results may be mislabeled"
fi

echo "iOS AMAZON-Q - SENTINEL TEST FOR XCCONFIG BASE-CONFIG (Assignment 25)"
echo "Session Date: $SESSION_DATE"
echo "Date (shell):  $(date)"
echo "Date (python): $(python3 -c 'import datetime; print(datetime.datetime.now())' 2>/dev/null || echo 'python3 not available')"
echo ""

# B5: $HOME inside quotes (~ does not expand inside double quotes)
RELEASE_XCCONFIG="$HOME/Development/AudioTours/development/audio_tour_app/ios/Flutter/Release.xcconfig"
DEBUG_XCCONFIG="$HOME/Development/AudioTours/development/audio_tour_app/ios/Flutter/Debug.xcconfig"
PROJECT_PBXPROJ="$HOME/Development/AudioTours/development/audio_tour_app/ios/Runner.xcodeproj/project.pbxproj"
PODFILE_LOCK="$HOME/Development/AudioTours/development/audio_tour_app/ios/Podfile.lock"
XCODE_BACKEND_SH="$HOME/flutter/packages/flutter_tools/bin/xcode_backend.sh"
PROJECT_DIR="$HOME/Development/AudioTours/development/audio_tour_app"

USB_RESULTS="/Volumes/USB DISK/Audioura/results"
LOCAL_BACKUP="$HOME/Desktop/a25_results"
mkdir -p "$LOCAL_BACKUP"
echo "Local backup directory: $LOCAL_BACKUP"
echo ""

# Trap-based cleanup -- reverts THREE files even if script aborts.
cleanup() {
    echo ""
    echo "============================================================"
    echo "=== CLEANUP TRAP RUNNING ==="
    echo "============================================================"

    # Revert 1: xcode_backend.sh -- remove printenv line
    if [ -f "$XCODE_BACKEND_SH" ] && grep -q 'flutter_build_phase_env_a25.log' "$XCODE_BACKEND_SH"; then
        sed -i.bak '/flutter_build_phase_env_a25.log/d' "$XCODE_BACKEND_SH"
        rm -f "$XCODE_BACKEND_SH.bak"
    fi

    # Revert 2: Release.xcconfig -- remove sentinel
    if [ -f "$RELEASE_XCCONFIG" ] && grep -q 'XCCONFIG_SENTINEL_RELEASE_A25' "$RELEASE_XCCONFIG"; then
        sed -i.bak '/XCCONFIG_SENTINEL_RELEASE_A25/d' "$RELEASE_XCCONFIG"
        rm -f "$RELEASE_XCCONFIG.bak"
    fi

    # Revert 3: Debug.xcconfig -- remove sentinel
    if [ -f "$DEBUG_XCCONFIG" ] && grep -q 'XCCONFIG_SENTINEL_DEBUG_A25' "$DEBUG_XCCONFIG"; then
        sed -i.bak '/XCCONFIG_SENTINEL_DEBUG_A25/d' "$DEBUG_XCCONFIG"
        rm -f "$DEBUG_XCCONFIG.bak"
    fi

    # Per-file PASS/FAIL verification
    {
        echo "=== A25 CLEANUP VERIFICATION (timestamp: $SESSION_DATE) ==="
        echo ""
        if grep -q 'flutter_build_phase_env_a25.log' "$XCODE_BACKEND_SH" 2>/dev/null; then
            echo "xcode_backend.sh:    FAIL -- printenv line still present"
        else
            echo "xcode_backend.sh:    PASS -- printenv line removed"
        fi
        if grep -q 'XCCONFIG_SENTINEL_RELEASE_A25' "$RELEASE_XCCONFIG" 2>/dev/null; then
            echo "Release.xcconfig:    FAIL -- sentinel still present"
        else
            echo "Release.xcconfig:    PASS -- sentinel removed"
        fi
        if grep -q 'XCCONFIG_SENTINEL_DEBUG_A25' "$DEBUG_XCCONFIG" 2>/dev/null; then
            echo "Debug.xcconfig:      FAIL -- sentinel still present"
        else
            echo "Debug.xcconfig:      PASS -- sentinel removed"
        fi
    } | tee ~/Desktop/a25_cleanup_verification.txt

    # USB-copy the cleanup verification too
    cp ~/Desktop/a25_cleanup_verification.txt "$USB_RESULTS/a25_cleanup_verification_${SESSION_DATE}.txt" 2>/dev/null \
        || echo "(USB copy of cleanup verification failed -- local copy preserved at $LOCAL_BACKUP/)"
    cp ~/Desktop/a25_cleanup_verification.txt "$LOCAL_BACKUP/"

    echo "============================================================"
    echo "=== CLEANUP COMPLETE -- script exiting ==="
    echo "============================================================"
}
trap cleanup EXIT

echo "============================================================"
echo "=== ASSIGNMENT 25: SENTINEL TEST (NO FIXES) ==="
echo "============================================================"
echo "Goal: determine whether Release.xcconfig and Debug.xcconfig are loaded"
echo "      as the active base configuration."
echo "Method: insert unique sentinel keys; check whether they propagate to the"
echo "        Run Script Phase environment via printenv inside xcode_backend.sh."
echo ""
echo "Sentinels to insert:"
echo "  Release.xcconfig: XCCONFIG_SENTINEL_RELEASE_A25 = release_xcconfig_loaded_a25"
echo "  Debug.xcconfig:   XCCONFIG_SENTINEL_DEBUG_A25   = debug_xcconfig_loaded_a25"
echo ""

echo "============================================================"
echo "=== STEP 1: INSERT SENTINELS INTO XCCONFIG FILES ==="
echo "============================================================"

# Release.xcconfig sentinel insert (idempotent)
if [ ! -f "$RELEASE_XCCONFIG" ]; then
    echo "FATAL: $RELEASE_XCCONFIG not found"
    exit 1
fi
if grep -q 'XCCONFIG_SENTINEL_RELEASE_A25' "$RELEASE_XCCONFIG"; then
    echo "OK: Release sentinel already present (idempotent skip)"
else
    echo "" >> "$RELEASE_XCCONFIG"
    echo "XCCONFIG_SENTINEL_RELEASE_A25 = release_xcconfig_loaded_a25" >> "$RELEASE_XCCONFIG"
    if grep -q 'XCCONFIG_SENTINEL_RELEASE_A25' "$RELEASE_XCCONFIG"; then
        echo "OK: Release sentinel inserted at end of Release.xcconfig"
    else
        echo "FAIL: Could not insert Release sentinel"
        exit 1
    fi
fi

# Debug.xcconfig sentinel insert (idempotent)
if [ ! -f "$DEBUG_XCCONFIG" ]; then
    echo "FATAL: $DEBUG_XCCONFIG not found"
    exit 1
fi
if grep -q 'XCCONFIG_SENTINEL_DEBUG_A25' "$DEBUG_XCCONFIG"; then
    echo "OK: Debug sentinel already present (idempotent skip)"
else
    echo "" >> "$DEBUG_XCCONFIG"
    echo "XCCONFIG_SENTINEL_DEBUG_A25 = debug_xcconfig_loaded_a25" >> "$DEBUG_XCCONFIG"
    if grep -q 'XCCONFIG_SENTINEL_DEBUG_A25' "$DEBUG_XCCONFIG"; then
        echo "OK: Debug sentinel inserted at end of Debug.xcconfig"
    else
        echo "FAIL: Could not insert Debug sentinel"
        exit 1
    fi
fi

echo ""
echo "============================================================"
echo "=== STEP 2: ADD PRINTENV TO xcode_backend.sh ==="
echo "============================================================"

if [ ! -f "$XCODE_BACKEND_SH" ]; then
    echo "FATAL: $XCODE_BACKEND_SH not found"
    exit 1
fi
if grep -q 'flutter_build_phase_env_a25.log' "$XCODE_BACKEND_SH"; then
    echo "OK: printenv line already present in xcode_backend.sh (idempotent skip)"
else
    # B4: awk insertion (BSD sed does not support inline 2i\<text> on macOS)
    awk 'NR==1{print; print "printenv | sort > /tmp/flutter_build_phase_env_a25.log"; next} 1' \
        "$XCODE_BACKEND_SH" > "$XCODE_BACKEND_SH.tmp" && mv "$XCODE_BACKEND_SH.tmp" "$XCODE_BACKEND_SH"
    if grep -q 'flutter_build_phase_env_a25.log' "$XCODE_BACKEND_SH"; then
        echo "OK: printenv line inserted into xcode_backend.sh (top of file)"
    else
        echo "FAIL: Could not insert printenv line"
        exit 1
    fi
fi

echo ""
echo "============================================================"
echo "=== STEP 3: DUMP MODIFIED XCCONFIG FILES (post-insertion) ==="
echo "============================================================"

{
    echo "=== Release.xcconfig (post-sentinel-insertion, $SESSION_DATE) ==="
    cat "$RELEASE_XCCONFIG"
    echo ""
    echo "=== Debug.xcconfig (post-sentinel-insertion, $SESSION_DATE) ==="
    cat "$DEBUG_XCCONFIG"
} > ~/Desktop/a25_xcconfig_dumps.txt
echo "OK: Wrote ~/Desktop/a25_xcconfig_dumps.txt"

echo ""
echo "============================================================"
echo "=== STEP 4: CAPTURE baseConfigurationReference + XCBuildConfiguration ==="
echo "============================================================"

{
    echo "=== baseConfigurationReference blocks (project.pbxproj) ==="
    # B3: single-quoted grep pattern
    grep -B2 -A20 'baseConfigurationReference' "$PROJECT_PBXPROJ"
    echo ""
    echo "=== XCBuildConfiguration blocks (project.pbxproj) ==="
    grep -B2 -A15 'isa = XCBuildConfiguration' "$PROJECT_PBXPROJ"
} > ~/Desktop/a25_baseconfig_refs.txt
echo "OK: Wrote ~/Desktop/a25_baseconfig_refs.txt"

echo ""
echo "============================================================"
echo "=== STEP 5: SNAPSHOT Podfile.lock ==="
echo "============================================================"

if [ -f "$PODFILE_LOCK" ]; then
    cp "$PODFILE_LOCK" ~/Desktop/a25_podfile_lock.txt
    echo "OK: Podfile.lock snapshotted to ~/Desktop/a25_podfile_lock.txt"
else
    echo "Podfile.lock not found at $PODFILE_LOCK" > ~/Desktop/a25_podfile_lock.txt
    echo "WARNING: Podfile.lock missing -- placeholder written"
fi

echo ""
echo "============================================================"
echo "=== STEP 6: FLUTTER BUILD (TRIGGERS xcode_backend.sh) ==="
echo "============================================================"

# M3: cd is the one acceptable exception -- flutter requires it for project context
cd "$PROJECT_DIR"
flutter build ios --release --no-codesign 2>&1 | tee /tmp/flutter_build_25.log
# B6: PIPESTATUS for first command's exit code (not tee's exit code)
BUILD_EXIT=${PIPESTATUS[0]}

echo ""
echo "Build exit code: $BUILD_EXIT (non-zero is expected -- we are still pre-fix)"

echo ""
echo "============================================================"
echo "=== STEP 7: SENTINEL DETECTION ==="
echo "============================================================"

RELEASE_HIT="NOT FOUND"
DEBUG_HIT="NOT FOUND"
RELEASE_RESULT="NO"
DEBUG_RESULT="NO"

if [ -f /tmp/flutter_build_phase_env_a25.log ]; then
    echo "OK: printenv capture exists at /tmp/flutter_build_phase_env_a25.log"

    if grep -q 'XCCONFIG_SENTINEL_RELEASE_A25' /tmp/flutter_build_phase_env_a25.log; then
        RELEASE_RESULT="YES"
        RELEASE_HIT=$(grep 'XCCONFIG_SENTINEL_RELEASE_A25' /tmp/flutter_build_phase_env_a25.log)
    fi
    if grep -q 'XCCONFIG_SENTINEL_DEBUG_A25' /tmp/flutter_build_phase_env_a25.log; then
        DEBUG_RESULT="YES"
        DEBUG_HIT=$(grep 'XCCONFIG_SENTINEL_DEBUG_A25' /tmp/flutter_build_phase_env_a25.log)
    fi
else
    echo "FAIL: /tmp/flutter_build_phase_env_a25.log NOT created"
    echo "      This means xcode_backend.sh did not run at all during this build."
fi

{
    echo "=== ASSIGNMENT 25 SENTINEL RESULTS (timestamp: $SESSION_DATE) ==="
    echo ""
    echo "RELEASE_SENTINEL_PROPAGATED=$RELEASE_RESULT"
    echo "DEBUG_SENTINEL_PROPAGATED=$DEBUG_RESULT"
    echo ""
    echo "Release sentinel grep: $RELEASE_HIT"
    echo "Debug sentinel grep:   $DEBUG_HIT"
    echo ""
    echo "Build exit code: $BUILD_EXIT"
    echo ""
    echo "Interpretation guide for Claude:"
    echo "  RELEASE=YES: Release.xcconfig IS the base. Branch A -- inline Generated values into Release.xcconfig."
    echo "  RELEASE=NO:  Release.xcconfig is BYPASSED. Branch B -- fix project.pbxproj baseConfigurationReference."
    echo "  (DEBUG result helps confirm whether the same diagnosis applies symmetrically.)"
} | tee ~/Desktop/a25_sentinel_results.txt

echo ""
echo "============================================================"
echo "=== STEP 8: COPY RESULTS TO USB + LOCAL BACKUP ==="
echo "============================================================"

# B2: real double quotes around USB path (it contains a space), visible errors per line
cp ~/Desktop/full_a25_session.txt          "$USB_RESULTS/full_a25_session_${SESSION_DATE}.txt"          || echo "USB copy failed: full_a25_session.txt"
cp ~/Desktop/a25_sentinel_results.txt      "$USB_RESULTS/a25_sentinel_results_${SESSION_DATE}.txt"      || echo "USB copy failed: a25_sentinel_results.txt"
cp ~/Desktop/a25_xcconfig_dumps.txt        "$USB_RESULTS/a25_xcconfig_dumps_${SESSION_DATE}.txt"        || echo "USB copy failed: a25_xcconfig_dumps.txt"
cp ~/Desktop/a25_baseconfig_refs.txt       "$USB_RESULTS/a25_baseconfig_refs_${SESSION_DATE}.txt"       || echo "USB copy failed: a25_baseconfig_refs.txt"
cp ~/Desktop/a25_podfile_lock.txt          "$USB_RESULTS/a25_podfile_lock_${SESSION_DATE}.txt"          || echo "USB copy failed: a25_podfile_lock.txt"
cp /tmp/flutter_build_25.log               "$USB_RESULTS/flutter_build_25_${SESSION_DATE}.log"          || echo "USB copy failed: flutter_build_25.log"
if [ -f /tmp/flutter_build_phase_env_a25.log ]; then
    cp /tmp/flutter_build_phase_env_a25.log "$USB_RESULTS/flutter_build_phase_env_a25_${SESSION_DATE}.log" || echo "USB copy failed: flutter_build_phase_env_a25.log"
else
    echo "(printenv capture missing -- see a25_sentinel_results for diagnosis)"
fi

# M5: local backup fallback
echo "--- Local backup copies ---"
cp ~/Desktop/full_a25_session.txt          "$LOCAL_BACKUP/"
cp ~/Desktop/a25_sentinel_results.txt      "$LOCAL_BACKUP/"
cp ~/Desktop/a25_xcconfig_dumps.txt        "$LOCAL_BACKUP/"
cp ~/Desktop/a25_baseconfig_refs.txt       "$LOCAL_BACKUP/"
cp ~/Desktop/a25_podfile_lock.txt          "$LOCAL_BACKUP/"
cp /tmp/flutter_build_25.log               "$LOCAL_BACKUP/"
[ -f /tmp/flutter_build_phase_env_a25.log ] && cp /tmp/flutter_build_phase_env_a25.log "$LOCAL_BACKUP/"
echo "OK: Local backup copies in $LOCAL_BACKUP"

echo ""
echo "============================================================"
echo "=== STEP 9: ASSIGNMENT 25 COMPLETE -- TRAP WILL CLEAN UP ==="
echo "============================================================"
echo ""
echo "SENTINEL RESULTS:"
echo "    RELEASE_SENTINEL_PROPAGATED=$RELEASE_RESULT"
echo "    DEBUG_SENTINEL_PROPAGATED=$DEBUG_RESULT"
echo ""
echo "Result files:"
echo "    USB:   $USB_RESULTS/*_${SESSION_DATE}.*"
echo "    Local: $LOCAL_BACKUP/"
echo ""
echo "Next: Claude analyzes a25_sentinel_results to design Assignment 26 (the targeted fix)."
echo ""
echo "(Cleanup trap will now run automatically on EXIT.)"