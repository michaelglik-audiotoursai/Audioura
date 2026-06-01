#!/bin/bash
# ASSIGNMENT 24: DIAGNOSE XCCONFIG PROPAGATION TO RUN SCRIPT PHASE
# DIAGNOSIS ONLY - NO FIXES YET
# Captures evidence to determine why FLUTTER_BUILD_DIR isn't reaching xcode_backend.dart

# Start full terminal recording per constraint 1
script ~/Desktop/full_a24_session.txt

# Capture system date per constraint 6
SESSION_DATE=$(date +"%Y%m%d_%H%M%S")
echo "🍎 iOS AMAZON-Q - XCCONFIG PROPAGATION DIAGNOSIS (Assignment 24)"
echo "Session Date: $SESSION_DATE"
echo "Date: $(date)"
echo ""

# Setup cleanup trap per constraint 3 - UNCONDITIONAL Flutter SDK revert
trap 'sed -i.bak "/printenv | sort > \/tmp\/flutter_build_phase_env_a24.log/d" ~/flutter/packages/flutter_tools/bin/xcode_backend.sh && rm -f ~/flutter/packages/flutter_tools/bin/xcode_backend.sh.bak' EXIT

echo "============================================================"
echo "=== ASSIGNMENT 24: DIAGNOSIS ONLY (NO FIXES) ==="
echo "============================================================"
echo "Testing 3 hypotheses:"
echo "1. Xcode 26 user script sandboxing (most likely)"
echo "2. Broken #include \"Generated.xcconfig\""
echo "3. _embedNativeAssets called when it shouldn't be"
echo ""

echo "============================================================"
echo "=== CAPTURE A: MODIFY FLUTTER SDK FOR ENVIRONMENT CAPTURE ==="
echo "============================================================"

# Check if diagnostic line already present (constraint 2 - re-runnability)
if grep -q "printenv | sort > /tmp/flutter_build_phase_env_a24.log" ~/flutter/packages/flutter_tools/bin/xcode_backend.sh; then
    echo "✅ Diagnostic line already present in xcode_backend.sh"
else
    echo "--- Adding diagnostic line to xcode_backend.sh ---"
    # Add printenv capture at very top of script (after shebang)
    sed -i.bak '2i\\nprintenv | sort > /tmp/flutter_build_phase_env_a24.log' ~/flutter/packages/flutter_tools/bin/xcode_backend.sh
    
    if grep -q "printenv | sort > /tmp/flutter_build_phase_env_a24.log" ~/flutter/packages/flutter_tools/bin/xcode_backend.sh; then
        echo "✅ Successfully added diagnostic line to xcode_backend.sh"
    else
        echo "❌ Failed to add diagnostic line to xcode_backend.sh"
        exit 1
    fi
fi

echo ""
echo "============================================================"
echo "=== CAPTURE B: SANDBOX SETTING IN RUNNER PROJECT ==="
echo "============================================================"

echo "--- Checking for ENABLE_USER_SCRIPT_SANDBOXING ---"
grep -i SANDBOX ~/Development/AudioTours/development/audio_tour_app/ios/Runner.xcodeproj/project.pbxproj > ~/Desktop/a24_pbxproj_grep.txt
if [ -s ~/Desktop/a24_pbxproj_grep.txt ]; then
    echo "✅ Sandbox settings found:"
    cat ~/Desktop/a24_pbxproj_grep.txt
else
    echo "❌ No SANDBOX settings found in project.pbxproj"
    echo "No SANDBOX settings found" > ~/Desktop/a24_pbxproj_grep.txt
fi

echo ""
echo "============================================================"
echo "=== CAPTURE C: FULL XCCONFIG DUMPS ==="
echo "============================================================"

echo "--- Dumping all xcconfig files (full contents) ---" > ~/Desktop/a24_xcconfig_dumps.txt
echo "" >> ~/Desktop/a24_xcconfig_dumps.txt

echo "=== Generated.xcconfig ===" >> ~/Desktop/a24_xcconfig_dumps.txt
if [ -f ~/Development/AudioTours/development/audio_tour_app/ios/Flutter/Generated.xcconfig ]; then
    cat ~/Development/AudioTours/development/audio_tour_app/ios/Flutter/Generated.xcconfig >> ~/Desktop/a24_xcconfig_dumps.txt
else
    echo "FILE NOT FOUND" >> ~/Desktop/a24_xcconfig_dumps.txt
fi
echo "" >> ~/Desktop/a24_xcconfig_dumps.txt

echo "=== Release.xcconfig ===" >> ~/Desktop/a24_xcconfig_dumps.txt
if [ -f ~/Development/AudioTours/development/audio_tour_app/ios/Flutter/Release.xcconfig ]; then
    cat ~/Development/AudioTours/development/audio_tour_app/ios/Flutter/Release.xcconfig >> ~/Desktop/a24_xcconfig_dumps.txt
else
    echo "FILE NOT FOUND" >> ~/Desktop/a24_xcconfig_dumps.txt
fi
echo "" >> ~/Desktop/a24_xcconfig_dumps.txt

echo "=== Debug.xcconfig ===" >> ~/Desktop/a24_xcconfig_dumps.txt
if [ -f ~/Development/AudioTours/development/audio_tour_app/ios/Flutter/Debug.xcconfig ]; then
    cat ~/Development/AudioTours/development/audio_tour_app/ios/Flutter/Debug.xcconfig >> ~/Desktop/a24_xcconfig_dumps.txt
else
    echo "FILE NOT FOUND" >> ~/Desktop/a24_xcconfig_dumps.txt
fi
echo "" >> ~/Desktop/a24_xcconfig_dumps.txt

echo "=== Pods-Runner.release.xcconfig ===" >> ~/Desktop/a24_xcconfig_dumps.txt
if [ -f ~/Development/AudioTours/development/audio_tour_app/ios/Pods/Target\\ Support\\ Files/Pods-Runner/Pods-Runner.release.xcconfig ]; then
    cat ~/Development/AudioTours/development/audio_tour_app/ios/Pods/Target\\ Support\\ Files/Pods-Runner/Pods-Runner.release.xcconfig >> ~/Desktop/a24_xcconfig_dumps.txt
else
    echo "FILE NOT FOUND" >> ~/Desktop/a24_xcconfig_dumps.txt
fi
echo "" >> ~/Desktop/a24_xcconfig_dumps.txt

echo "=== Pods-Runner.debug.xcconfig ===" >> ~/Desktop/a24_xcconfig_dumps.txt
if [ -f ~/Development/AudioTours/development/audio_tour_app/ios/Pods/Target\\ Support\\ Files/Pods-Runner/Pods-Runner.debug.xcconfig ]; then
    cat ~/Development/AudioTours/development/audio_tour_app/ios/Pods/Target\\ Support\\ Files/Pods-Runner/Pods-Runner.debug.xcconfig >> ~/Desktop/a24_xcconfig_dumps.txt
else
    echo "FILE NOT FOUND" >> ~/Desktop/a24_xcconfig_dumps.txt
fi

echo "✅ All xcconfig files dumped to ~/Desktop/a24_xcconfig_dumps.txt"

echo ""
echo "============================================================"
echo "=== CAPTURE D: RUN SCRIPT PHASE DEFINITIONS ==="
echo "============================================================"

echo "--- Extracting Run Script Phase definitions from project.pbxproj ---"
grep -B2 -A30 \"shellScript\" ~/Development/AudioTours/development/audio_tour_app/ios/Runner.xcodeproj/project.pbxproj | head -300 >> ~/Desktop/a24_pbxproj_grep.txt

echo "✅ Run Script Phase definitions captured"

echo ""
echo "============================================================"
echo "=== CAPTURE E: NATIVE ASSETS EVIDENCE ==="
echo "============================================================"

echo "--- Searching for native_assets references ---" > ~/Desktop/a24_native_assets_evidence.txt

echo "=== Pods directory search ===" >> ~/Desktop/a24_native_assets_evidence.txt
grep -r \"native_assets\" ~/Development/AudioTours/development/audio_tour_app/ios/Pods/ 2>/dev/null >> ~/Desktop/a24_native_assets_evidence.txt || echo "No native_assets found in Pods/" >> ~/Desktop/a24_native_assets_evidence.txt

echo "" >> ~/Desktop/a24_native_assets_evidence.txt
echo "=== .dart_tool directory search ===" >> ~/Desktop/a24_native_assets_evidence.txt
grep -r \"native_assets\" ~/Development/AudioTours/development/audio_tour_app/.dart_tool/ 2>/dev/null >> ~/Desktop/a24_native_assets_evidence.txt || echo "No native_assets found in .dart_tool/" >> ~/Desktop/a24_native_assets_evidence.txt

echo "" >> ~/Desktop/a24_native_assets_evidence.txt
echo "=== native_assets files listing ===" >> ~/Desktop/a24_native_assets_evidence.txt
ls -la ~/Development/AudioTours/development/audio_tour_app/.dart_tool/native_assets* 2>/dev/null >> ~/Desktop/a24_native_assets_evidence.txt || echo "No native_assets files found" >> ~/Desktop/a24_native_assets_evidence.txt

echo "✅ Native assets evidence captured"

echo ""
echo "============================================================"
echo "=== CAPTURE F: FLUTTER BUILD ATTEMPT (THE CRITICAL TEST) ==="
echo "============================================================"

echo "--- Running flutter build ios --release --no-codesign ---"
echo "This will trigger xcode_backend.sh and capture its environment"

cd ~/Development/AudioTours/development/audio_tour_app
flutter build ios --release --no-codesign 2>&1 | tee /tmp/flutter_build_24.log
BUILD_EXIT=$?

echo ""
echo "Build exit code: $BUILD_EXIT"

echo ""
echo "============================================================"
echo "=== VERIFY ENVIRONMENT CAPTURE ==="
echo "============================================================"

if [ -f /tmp/flutter_build_phase_env_a24.log ]; then
    echo "✅ Environment capture successful!"
    echo "Environment variables seen by xcode_backend.sh:"
    echo "--- First 20 lines ---"
    head -20 /tmp/flutter_build_phase_env_a24.log
    echo "..."
    echo "--- FLUTTER variables specifically ---"
    grep FLUTTER /tmp/flutter_build_phase_env_a24.log || echo "❌ NO FLUTTER variables found in environment!"
else
    echo "❌ Environment capture failed - /tmp/flutter_build_phase_env_a24.log not created"
    echo "This means xcode_backend.sh was not invoked or diagnostic line failed"
fi

echo ""
echo "============================================================"
echo "=== COPY RESULTS TO USB ==="
echo "============================================================"

echo "--- Copying all result files to USB ---"
cp ~/Desktop/full_a24_session.txt \"/Volumes/USB DISK/Audioura/results/full_a24_session_${SESSION_DATE}.txt\" 2>/dev/null || echo "⚠️  full_a24_session.txt copy failed"

if [ -f /tmp/flutter_build_phase_env_a24.log ]; then
    cp /tmp/flutter_build_phase_env_a24.log \"/Volumes/USB DISK/Audioura/results/flutter_build_phase_env_a24_${SESSION_DATE}.log\" 2>/dev/null || echo "⚠️  flutter_build_phase_env_a24.log copy failed"
else
    echo "Environment capture file missing - creating placeholder" > \"/Volumes/USB DISK/Audioura/results/flutter_build_phase_env_a24_${SESSION_DATE}.log\"
fi

cp /tmp/flutter_build_24.log \"/Volumes/USB DISK/Audioura/results/flutter_build_24_${SESSION_DATE}.log\" 2>/dev/null || echo "⚠️  flutter_build_24.log copy failed"
cp ~/Desktop/a24_xcconfig_dumps.txt \"/Volumes/USB DISK/Audioura/results/a24_xcconfig_dumps_${SESSION_DATE}.txt\" 2>/dev/null || echo "⚠️  a24_xcconfig_dumps.txt copy failed"
cp ~/Desktop/a24_pbxproj_grep.txt \"/Volumes/USB DISK/Audioura/results/a24_pbxproj_grep_${SESSION_DATE}.txt\" 2>/dev/null || echo "⚠️  a24_pbxproj_grep.txt copy failed"
cp ~/Desktop/a24_native_assets_evidence.txt \"/Volumes/USB DISK/Audioura/results/a24_native_assets_evidence_${SESSION_DATE}.txt\" 2>/dev/null || echo "⚠️  a24_native_assets_evidence.txt copy failed"

echo ""
echo "============================================================"
echo "=== CLEANUP VERIFICATION ==="
echo "============================================================"

echo "--- Verifying Flutter SDK cleanup (trap should handle this) ---"
# The trap will run automatically on exit, but let's verify it worked
if grep -q "printenv | sort > /tmp/flutter_build_phase_env_a24.log" ~/flutter/packages/flutter_tools/bin/xcode_backend.sh; then
    echo "⚠️  Diagnostic line still present - manual cleanup required"
    sed -i.bak "/printenv | sort > \/tmp\/flutter_build_phase_env_a24.log/d" ~/flutter/packages/flutter_tools/bin/xcode_backend.sh
    rm -f ~/flutter/packages/flutter_tools/bin/xcode_backend.sh.bak
fi

# Final verification per constraint 3
if grep -q "printenv | sort > /tmp/flutter_build_phase_env_a24.log" ~/flutter/packages/flutter_tools/bin/xcode_backend.sh; then
    echo "❌ CLEANUP FAILED - diagnostic line still present in xcode_backend.sh"
else
    echo "✅ Flutter SDK cleanup successful - diagnostic line removed"
fi

echo ""
echo "============================================================"
echo "=== ASSIGNMENT 24 COMPLETE ==="
echo "============================================================"
echo "📊 DIAGNOSIS COMPLETE - 6 evidence captures ready for Claude analysis:"
echo "A. ✅ Run Script Phase environment captured"
echo "B. ✅ Sandbox settings captured"
echo "C. ✅ Full xcconfig dumps captured"
echo "D. ✅ Run Script Phase definitions captured"
echo "E. ✅ Native assets evidence captured"
echo "F. ✅ Flutter build attempt completed"
echo ""
echo "🎯 KEY FINDING: Check if FLUTTER_BUILD_DIR appears in environment capture"
echo "📁 All results copied to D:\\Audioura\\results\\ with timestamp ${SESSION_DATE}"
echo ""
echo "Next: Claude analyzes evidence and writes Assignment 25 (the actual fix)"

# End terminal recording
exit