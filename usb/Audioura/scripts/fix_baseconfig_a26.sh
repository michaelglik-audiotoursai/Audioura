#!/bin/bash
# ASSIGNMENT 26: FIX PROJECT.PBXPROJ BASECONFIGURATIONREFERENCE (BRANCH B)
# TARGETED FIX BASED ON ASSIGNMENT 25 RESULTS
# Restores Flutter configuration chain: Release.xcconfig → Generated.xcconfig
# Assignment 25 confirmed RELEASE_SENTINEL_PROPAGATED=NO (Branch B)

# Capture session timestamp
SESSION_DATE=$(date +"%Y%m%d_%H%M%S")
CURRENT_YEAR=$(date +"%Y")
if [ "$CURRENT_YEAR" != "2026" ]; then
    echo "WARNING: SYSTEM DATE DRIFT DETECTED: Current year is $CURRENT_YEAR, expected 2026"
    echo "Continuing with timestamp $SESSION_DATE but results may be mislabeled"
fi

echo "🍎 iOS AMAZON-Q - FIX BASECONFIGURATIONREFERENCE (Assignment 26)"
echo "Session Date: $SESSION_DATE"
echo "Date (shell):  $(date)"
echo "Date (python): $(python3 -c 'import datetime; print(datetime.datetime.now())' 2>/dev/null || echo 'python3 not available')"
echo ""

# File paths
PROJECT_PBXPROJ="$HOME/Development/AudioTours/development/audio_tour_app/ios/Runner.xcodeproj/project.pbxproj"
PROJECT_DIR="$HOME/Development/AudioTours/development/audio_tour_app"
USB_RESULTS="/Volumes/USB DISK/Audioura/results"
LOCAL_BACKUP="$HOME/Desktop/a26_results"
mkdir -p "$LOCAL_BACKUP"

echo "============================================================"
echo "=== ASSIGNMENT 26: BRANCH B FIX (TARGETED) ==="
echo "============================================================"
echo "Based on Assignment 25 results: RELEASE_SENTINEL_PROPAGATED=NO"
echo "Fix: Restore Flutter configuration chain by fixing baseConfigurationReference"
echo ""
echo "Current (BROKEN):"
echo "  Debug:   baseConfigurationReference → Pods-Runner.debug.xcconfig"
echo "  Release: baseConfigurationReference → Pods-Runner.release.xcconfig"
echo ""
echo "Target (FIXED):"
echo "  Debug:   baseConfigurationReference → Flutter/Debug.xcconfig"
echo "  Release: baseConfigurationReference → Flutter/Release.xcconfig"
echo ""

# Backup original project.pbxproj
echo "============================================================"
echo "=== STEP 1: BACKUP ORIGINAL PROJECT.PBXPROJ ==="
echo "============================================================"
if [ ! -f "$PROJECT_PBXPROJ" ]; then
    echo "FATAL: $PROJECT_PBXPROJ not found"
    exit 1
fi

cp "$PROJECT_PBXPROJ" "$PROJECT_PBXPROJ.backup_a26_$SESSION_DATE"
echo "✅ Backup created: project.pbxproj.backup_a26_$SESSION_DATE"

# Capture current baseConfigurationReference entries
echo ""
echo "============================================================"
echo "=== STEP 2: CAPTURE CURRENT BASECONFIGURATIONREFERENCE ==="
echo "============================================================"
{
    echo "=== BEFORE FIX (Assignment 26, $SESSION_DATE) ==="
    echo ""
    grep -B2 -A5 "baseConfigurationReference.*Pods-Runner" "$PROJECT_PBXPROJ"
} > ~/Desktop/a26_before_fix.txt
echo "✅ Current state captured to ~/Desktop/a26_before_fix.txt"

# Apply the fix - replace Pods-Runner references with Flutter references
echo ""
echo "============================================================"
echo "=== STEP 3: APPLY BASECONFIGURATIONREFERENCE FIX ==="
echo "============================================================"

# Find the Flutter xcconfig file references in the project
DEBUG_FLUTTER_REF=$(grep -o '[A-F0-9]\{24\} /\* Debug\.xcconfig \*/' "$PROJECT_PBXPROJ" | cut -d' ' -f1)
RELEASE_FLUTTER_REF=$(grep -o '[A-F0-9]\{24\} /\* Release\.xcconfig \*/' "$PROJECT_PBXPROJ" | cut -d' ' -f1)

if [ -z "$DEBUG_FLUTTER_REF" ] || [ -z "$RELEASE_FLUTTER_REF" ]; then
    echo "ERROR: Could not find Flutter xcconfig references in project.pbxproj"
    echo "DEBUG_FLUTTER_REF: $DEBUG_FLUTTER_REF"
    echo "RELEASE_FLUTTER_REF: $RELEASE_FLUTTER_REF"
    exit 1
fi

echo "Found Flutter xcconfig references:"
echo "  Debug.xcconfig:   $DEBUG_FLUTTER_REF"
echo "  Release.xcconfig: $RELEASE_FLUTTER_REF"
echo ""

# Replace Debug baseConfigurationReference
echo "Fixing Debug baseConfigurationReference..."
sed -i.tmp "s/baseConfigurationReference = [A-F0-9]\{24\} \/\* Pods-Runner\.debug\.xcconfig \*\;/baseConfigurationReference = $DEBUG_FLUTTER_REF \/\* Debug.xcconfig \*\;/g" "$PROJECT_PBXPROJ"

# Replace Release baseConfigurationReference  
echo "Fixing Release baseConfigurationReference..."
sed -i.tmp "s/baseConfigurationReference = [A-F0-9]\{24\} \/\* Pods-Runner\.release\.xcconfig \*\;/baseConfigurationReference = $RELEASE_FLUTTER_REF \/\* Release.xcconfig \*\;/g" "$PROJECT_PBXPROJ"

# Clean up temporary files
rm -f "$PROJECT_PBXPROJ.tmp"

echo "✅ baseConfigurationReference entries updated"

# Verify the fix
echo ""
echo "============================================================"
echo "=== STEP 4: VERIFY FIX APPLIED CORRECTLY ==="
echo "============================================================"
{
    echo "=== AFTER FIX (Assignment 26, $SESSION_DATE) ==="
    echo ""
    grep -B2 -A5 "baseConfigurationReference.*Debug\.xcconfig\|baseConfigurationReference.*Release\.xcconfig" "$PROJECT_PBXPROJ"
} > ~/Desktop/a26_after_fix.txt
echo "✅ Fixed state captured to ~/Desktop/a26_after_fix.txt"

# Show the changes
echo ""
echo "Verification - Fixed baseConfigurationReference entries:"
grep "baseConfigurationReference.*Debug\.xcconfig\|baseConfigurationReference.*Release\.xcconfig" "$PROJECT_PBXPROJ" || echo "ERROR: Fix verification failed"

echo ""
echo "============================================================"
echo "=== STEP 5: TEST FLUTTER BUILD (THE MOMENT OF TRUTH) ==="
echo "============================================================"
cd "$PROJECT_DIR"
echo "Running flutter build ios --release --no-codesign..."
echo "Expected: Should complete WITHOUT xcode_backend.dart:345 null-check error"
echo ""

flutter build ios --release --no-codesign 2>&1 | tee /tmp/flutter_build_26.log
BUILD_EXIT=${PIPESTATUS[0]}

echo ""
echo "Build exit code: $BUILD_EXIT"
if [ $BUILD_EXIT -eq 0 ]; then
    echo "🎉 SUCCESS! Flutter build completed without errors!"
    echo "✅ FLUTTER_BUILD_DIR is now available to xcode_backend.sh"
    echo "✅ Configuration chain restored: Release.xcconfig → Generated.xcconfig"
else
    echo "❌ Build still failed. Exit code: $BUILD_EXIT"
    echo "Check /tmp/flutter_build_26.log for details"
fi

echo ""
echo "============================================================"
echo "=== STEP 6: COPY RESULTS TO USB + LOCAL BACKUP ==="
echo "============================================================"

# Copy all result files
cp ~/Desktop/a26_before_fix.txt "$USB_RESULTS/a26_before_fix_${SESSION_DATE}.txt" || echo "USB copy failed: a26_before_fix.txt"
cp ~/Desktop/a26_after_fix.txt "$USB_RESULTS/a26_after_fix_${SESSION_DATE}.txt" || echo "USB copy failed: a26_after_fix.txt"
cp /tmp/flutter_build_26.log "$USB_RESULTS/flutter_build_26_${SESSION_DATE}.log" || echo "USB copy failed: flutter_build_26.log"
cp "$PROJECT_PBXPROJ.backup_a26_$SESSION_DATE" "$USB_RESULTS/project_pbxproj_backup_a26_${SESSION_DATE}.txt" || echo "USB copy failed: project.pbxproj backup"

# Local backup copies
echo "--- Local backup copies ---"
cp ~/Desktop/a26_before_fix.txt "$LOCAL_BACKUP/"
cp ~/Desktop/a26_after_fix.txt "$LOCAL_BACKUP/"
cp /tmp/flutter_build_26.log "$LOCAL_BACKUP/"
cp "$PROJECT_PBXPROJ.backup_a26_$SESSION_DATE" "$LOCAL_BACKUP/"
echo "✅ Local backup copies in $LOCAL_BACKUP"

echo ""
echo "============================================================"
echo "=== ASSIGNMENT 26 COMPLETE ==="
echo "============================================================"
echo ""
echo "RESULTS:"
echo "    Build exit code: $BUILD_EXIT"
if [ $BUILD_EXIT -eq 0 ]; then
    echo "    Status: ✅ SUCCESS - Flutter configuration chain restored!"
    echo "    Next: Sign and install working Audioura app on iPhone 16"
else
    echo "    Status: ❌ FAILED - Additional investigation needed"
    echo "    Check flutter_build_26.log for error details"
fi
echo ""
echo "Result files:"
echo "    USB:   $USB_RESULTS/*_${SESSION_DATE}.*"
echo "    Local: $LOCAL_BACKUP/"
echo ""
echo "Backup: project.pbxproj.backup_a26_$SESSION_DATE (can restore if needed)"
echo ""
if [ $BUILD_EXIT -eq 0 ]; then
    echo "🎯 READY FOR APP INSTALLATION! 🎯"
    echo "The iOS build barrier has been broken!"
else
    echo "Investigation continues..."
fi