#!/bin/bash
# ASSIGNMENT 27: BRANCH B FIX (CORRECTED) -- PYTHON-BASED PBXPROJ EDIT
# Re-attempts the A26 fix that failed due to two bash bugs in sed-based editing.
# Uses Python with re.subn(...) and `assert n == 1` per substitution, anchored on
# the specific Runner config UUIDs (not RunnerTests).
#
# Drafted by Claude on 2026-04-29 (session "Audioura Build and Start #4").
# Drafted directly (NOT routed through Amazon-Q) per Sir Michael's instruction,
# given A26 evidence that the prior Amazon-Q draft bypassed Claude's review.
# Self-reviewed before USB transfer.
#
# Lessons baked in (one source -- ../../Audioura_project_log.md):
#   B1  exec > >(tee ...) 2>&1 wrap (no `script` from inside script body)
#   B2  USB cp uses real double quotes, visible per-file errors
#   B3  single-quoted grep patterns
#   B4  awk for line insertion (BSD sed lacks inline 2i\)
#   B5  $HOME inside double quotes (~ does not expand inside "...")
#   B6  ${PIPESTATUS[0]} after pipes
#   B7  no multiline shell variable into sed -- use Python instead
#   V1  verification HALTS (exit 1), not just prints
#   V2  Claude reviewed this script before execution
#   M1  system-date drift check
#   M3  cd only for `flutter build` (the one acceptable exception)
#   M5  local backup directory fallback in case USB copy fails

# Note: do NOT `set -e`. We want explicit control over failure handling so the
# cleanup trap can run AND so verification HALTs are clear.
set -o pipefail

# --- B1: tee everything to a session log on the Desktop ----------------------
exec > >(tee ~/Desktop/full_a27_session.txt) 2>&1

# --- M1: timestamps + system-date drift check --------------------------------
SESSION_DATE=$(date +"%Y%m%d_%H%M%S")
CURRENT_YEAR=$(date +"%Y")
if [ "$CURRENT_YEAR" != "2026" ]; then
    echo "WARNING: SYSTEM DATE DRIFT DETECTED: Current year is $CURRENT_YEAR, expected 2026"
    echo "Continuing with timestamp $SESSION_DATE but results may be mislabeled"
fi

echo "iOS BUILD -- BRANCH B FIX, CORRECTED (Assignment 27)"
echo "Session Date: $SESSION_DATE"
echo "Date (shell):  $(date)"
echo "Date (python): $(python3 -c 'import datetime; print(datetime.datetime.now())' 2>/dev/null || echo 'python3 not available')"
echo ""

# --- B5: $HOME inside double quotes -----------------------------------------
PROJECT_DIR="$HOME/Development/AudioTours/development/audio_tour_app"
IOS_DIR="$PROJECT_DIR/ios"
PROJECT_PBXPROJ="$IOS_DIR/Runner.xcodeproj/project.pbxproj"
RELEASE_XCCONFIG="$IOS_DIR/Flutter/Release.xcconfig"
DEBUG_XCCONFIG="$IOS_DIR/Flutter/Debug.xcconfig"
PODFILE_LOCK="$IOS_DIR/Podfile.lock"
XCODE_BACKEND_SH="$HOME/flutter/packages/flutter_tools/bin/xcode_backend.sh"

USB_RESULTS="/Volumes/USB DISK/Audioura/results"
LOCAL_BACKUP="$HOME/Desktop/a27_results"
mkdir -p "$LOCAL_BACKUP"
echo "Local backup directory: $LOCAL_BACKUP"
echo ""

# --- Runner target config UUIDs (from A25 evidence -- a25_baseconfig_refs)----
RUNNER_DEBUG_UUID="97C147061CF9000F007C117D"
RUNNER_RELEASE_UUID="97C147071CF9000F007C117D"

# --- Idempotency guard for the Python edit ----------------------------------
# Path-side state: backup of pbxproj is created on first run; subsequent runs
# create a NEW timestamped backup (we never overwrite an old one).
PBXPROJ_BACKUP="$PROJECT_PBXPROJ.backup_a27_$SESSION_DATE"

# --- Trap-based cleanup: revert sentinels + printenv hook only ---------------
# IMPORTANT: cleanup does NOT revert project.pbxproj.
# That edit is the actual fix and stays in place. If you want to revert it,
# do so manually:
#     cp "$PBXPROJ_BACKUP" "$PROJECT_PBXPROJ"
cleanup() {
    echo ""
    echo "============================================================"
    echo "=== CLEANUP TRAP RUNNING (sentinels + printenv hook only) ==="
    echo "============================================================"

    # Revert 1: xcode_backend.sh -- remove A27 printenv line
    if [ -f "$XCODE_BACKEND_SH" ] && grep -q 'flutter_build_phase_env_a27.log' "$XCODE_BACKEND_SH"; then
        sed -i.bak '/flutter_build_phase_env_a27.log/d' "$XCODE_BACKEND_SH"
        rm -f "$XCODE_BACKEND_SH.bak"
    fi

    # Revert 2: Release.xcconfig -- remove A27 sentinel
    if [ -f "$RELEASE_XCCONFIG" ] && grep -q 'XCCONFIG_SENTINEL_RELEASE_A27' "$RELEASE_XCCONFIG"; then
        sed -i.bak '/XCCONFIG_SENTINEL_RELEASE_A27/d' "$RELEASE_XCCONFIG"
        rm -f "$RELEASE_XCCONFIG.bak"
    fi

    # Revert 3: Debug.xcconfig -- remove A27 sentinel
    if [ -f "$DEBUG_XCCONFIG" ] && grep -q 'XCCONFIG_SENTINEL_DEBUG_A27' "$DEBUG_XCCONFIG"; then
        sed -i.bak '/XCCONFIG_SENTINEL_DEBUG_A27/d' "$DEBUG_XCCONFIG"
        rm -f "$DEBUG_XCCONFIG.bak"
    fi

    # Per-file PASS/FAIL verification
    {
        echo "=== A27 CLEANUP VERIFICATION (timestamp: $SESSION_DATE) ==="
        echo ""
        if grep -q 'flutter_build_phase_env_a27.log' "$XCODE_BACKEND_SH" 2>/dev/null; then
            echo "xcode_backend.sh:    FAIL -- printenv line still present"
        else
            echo "xcode_backend.sh:    PASS -- printenv line removed"
        fi
        if grep -q 'XCCONFIG_SENTINEL_RELEASE_A27' "$RELEASE_XCCONFIG" 2>/dev/null; then
            echo "Release.xcconfig:    FAIL -- sentinel still present"
        else
            echo "Release.xcconfig:    PASS -- sentinel removed"
        fi
        if grep -q 'XCCONFIG_SENTINEL_DEBUG_A27' "$DEBUG_XCCONFIG" 2>/dev/null; then
            echo "Debug.xcconfig:      FAIL -- sentinel still present"
        else
            echo "Debug.xcconfig:      PASS -- sentinel removed"
        fi
        echo ""
        echo "(NOTE: project.pbxproj is intentionally NOT reverted -- the A27 edit"
        echo " is the actual fix. Backup preserved at: $PBXPROJ_BACKUP)"
    } | tee ~/Desktop/a27_cleanup_verification.txt

    # USB-copy the cleanup verification too (B2)
    cp ~/Desktop/a27_cleanup_verification.txt "$USB_RESULTS/a27_cleanup_verification_${SESSION_DATE}.txt" 2>/dev/null \
        || echo "(USB copy of cleanup verification failed -- local copy preserved at $LOCAL_BACKUP/)"
    cp ~/Desktop/a27_cleanup_verification.txt "$LOCAL_BACKUP/"

    echo "============================================================"
    echo "=== CLEANUP COMPLETE -- script exiting ==="
    echo "============================================================"
}
trap cleanup EXIT

echo "============================================================"
echo "=== ASSIGNMENT 27: BRANCH B FIX (PYTHON-BASED) ==="
echo "============================================================"
echo "Goal: flip the Runner target's Debug + Release baseConfigurationReference"
echo "      from Pods-Runner.{debug,release}.xcconfig to Flutter/{Debug,Release}.xcconfig."
echo "Anchored on Runner config UUIDs:"
echo "  Debug   = $RUNNER_DEBUG_UUID"
echo "  Release = $RUNNER_RELEASE_UUID"
echo "Profile is INTENTIONALLY UNTOUCHED. RunnerTests is INTENTIONALLY UNTOUCHED."
echo ""

# ===========================================================================
# STEP 1: Pre-flight sanity checks
# ===========================================================================
echo "============================================================"
echo "=== STEP 1: PRE-FLIGHT SANITY CHECKS ==="
echo "============================================================"

for path in "$PROJECT_PBXPROJ" "$RELEASE_XCCONFIG" "$DEBUG_XCCONFIG" "$XCODE_BACKEND_SH"; do
    if [ ! -f "$path" ]; then
        echo "FATAL: missing required file: $path"
        exit 1
    fi
done
echo "OK: all four required files present."

# B3: single-quoted grep pattern. Confirm both Runner config UUIDs are present.
if ! grep -q "$RUNNER_DEBUG_UUID" "$PROJECT_PBXPROJ"; then
    echo "FATAL: Runner Debug UUID $RUNNER_DEBUG_UUID not found in project.pbxproj"
    exit 1
fi
if ! grep -q "$RUNNER_RELEASE_UUID" "$PROJECT_PBXPROJ"; then
    echo "FATAL: Runner Release UUID $RUNNER_RELEASE_UUID not found in project.pbxproj"
    exit 1
fi
echo "OK: both Runner config UUIDs present in project.pbxproj."

# ===========================================================================
# STEP 2: Backup project.pbxproj (timestamped)
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 2: BACKUP project.pbxproj ==="
echo "============================================================"

cp "$PROJECT_PBXPROJ" "$PBXPROJ_BACKUP"
if [ ! -f "$PBXPROJ_BACKUP" ]; then
    echo "FATAL: backup creation failed at $PBXPROJ_BACKUP"
    exit 1
fi
echo "OK: backup created at $PBXPROJ_BACKUP"
ls -la "$PBXPROJ_BACKUP"

# Also stash a copy in the local backup dir + USB so it's preserved cross-device.
cp "$PBXPROJ_BACKUP" "$LOCAL_BACKUP/project_pbxproj_backup_a27_${SESSION_DATE}.txt"
cp "$PBXPROJ_BACKUP" "$USB_RESULTS/project_pbxproj_backup_a27_${SESSION_DATE}.txt" 2>/dev/null \
    || echo "(USB copy of pbxproj backup failed -- local copy preserved)"

# ===========================================================================
# STEP 3: Capture BEFORE state of baseConfigurationReference
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 3: CAPTURE BEFORE STATE ==="
echo "============================================================"

{
    echo "=== A27 BEFORE: all baseConfigurationReference lines ==="
    grep -n 'baseConfigurationReference' "$PROJECT_PBXPROJ" || true
    echo ""
    echo "=== A27 BEFORE: Runner Debug + Release config blocks (truncated by first '};') ==="
    echo "--- Runner Debug ($RUNNER_DEBUG_UUID) ---"
    awk "/$RUNNER_DEBUG_UUID \\/\\* Debug \\*\\/ = \\{/,/};/" "$PROJECT_PBXPROJ" | head -30
    echo ""
    echo "--- Runner Release ($RUNNER_RELEASE_UUID) ---"
    awk "/$RUNNER_RELEASE_UUID \\/\\* Release \\*\\/ = \\{/,/};/" "$PROJECT_PBXPROJ" | head -30
} > ~/Desktop/a27_before_fix.txt
echo "OK: BEFORE state captured to ~/Desktop/a27_before_fix.txt"

# ===========================================================================
# STEP 4: Apply the fix via Python (B7)
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 4: APPLY PYTHON-BASED PBXPROJ EDIT ==="
echo "============================================================"

# Use a single-quoted heredoc so the shell does NOT interpolate anything inside.
# The Python script is fully self-contained and uses hardcoded Mac Mini paths.
python3 - <<'PYEOF'
import re
import sys

PBXPROJ = "/Users/micha/Development/AudioTours/development/audio_tour_app/ios/Runner.xcodeproj/project.pbxproj"

# Runner target configuration UUIDs (per A25 evidence).
RUNNER_DEBUG_UUID   = "97C147061CF9000F007C117D"
RUNNER_RELEASE_UUID = "97C147071CF9000F007C117D"

# Expected file-reference IDs (per A25 evidence). Used for sanity warning only;
# we always trust whatever the live file says, looked up via re.search below.
EXPECTED_DEBUG_REF   = "9740EEB21CF90195004384FC"
EXPECTED_RELEASE_REF = "7AFA3C8E1D35360C0083082E"

with open(PBXPROJ, "r", encoding="utf-8") as f:
    content = f.read()

# --- Locate the PBXFileReference IDs for Flutter/Debug.xcconfig and Flutter/Release.xcconfig.
# Canonical line shape in project.pbxproj:
#   <hex24> /* Debug.xcconfig */ = {isa = PBXFileReference; lastKnownFileType = text.xcconfig;
#       name = Debug.xcconfig; path = Flutter/Debug.xcconfig; sourceTree = "<group>"; };
#
# The comment "/* Debug.xcconfig */" is shared between (a) this PBXFileReference, (b) the
# Runner config blocks' baseConfigurationReference uses, and (c) PBXGroup children entries.
# We disambiguate by requiring `= {isa = PBXFileReference` immediately after the comment:
#   - baseConfigurationReference uses are followed by `;`
#   - PBXGroup children are followed by `,`
#   - Only the file ref itself is followed by `= {isa = PBXFileReference`
# (Pods-Runner.debug.xcconfig has a DIFFERENT comment, so the comment match alone disambiguates
# vs Pods xcconfigs.)
debug_match = re.search(
    r'([0-9A-Fa-f]{24})\s+/\*\s*Debug\.xcconfig\s*\*/\s*=\s*\{\s*isa\s*=\s*PBXFileReference\b',
    content)
release_match = re.search(
    r'([0-9A-Fa-f]{24})\s+/\*\s*Release\.xcconfig\s*\*/\s*=\s*\{\s*isa\s*=\s*PBXFileReference\b',
    content)

if not debug_match:
    print("FATAL: could not locate PBXFileReference for Flutter/Debug.xcconfig (path = Debug.xcconfig).")
    sys.exit(1)
if not release_match:
    print("FATAL: could not locate PBXFileReference for Flutter/Release.xcconfig (path = Release.xcconfig).")
    sys.exit(1)

DEBUG_REF_ID   = debug_match.group(1)
RELEASE_REF_ID = release_match.group(1)
print(f"Found Flutter/Debug.xcconfig file ref:   {DEBUG_REF_ID}")
print(f"Found Flutter/Release.xcconfig file ref: {RELEASE_REF_ID}")

if DEBUG_REF_ID != EXPECTED_DEBUG_REF:
    print(f"WARN: Debug.xcconfig file ref ({DEBUG_REF_ID}) differs from A25-recorded "
          f"{EXPECTED_DEBUG_REF}. Proceeding with discovered value.")
if RELEASE_REF_ID != EXPECTED_RELEASE_REF:
    print(f"WARN: Release.xcconfig file ref ({RELEASE_REF_ID}) differs from A25-recorded "
          f"{EXPECTED_RELEASE_REF}. Proceeding with discovered value.")

# --- Substitute baseConfigurationReference inside the specific Runner config blocks.
# Block layout in pbxproj:
#   <UUID> /* Debug */ = {
#       isa = XCBuildConfiguration;
#       baseConfigurationReference = <hex24> /* <name>.xcconfig */;
#       buildSettings = { ... };
#       name = Debug;
#   };
#
# baseConfigurationReference appears BEFORE buildSettings, so we can scan from the
# block opener up to the line we want without crossing any `}` characters
# (the first `}` is the close of buildSettings, well after our target).
def replace_baseconfig(text, runner_uuid, runner_label, new_ref_id, new_ref_name):
    pattern = (
        r'('                                # group 1: prefix to keep
        + re.escape(runner_uuid)
        + r'\s*/\*\s*' + re.escape(runner_label) + r'\s*\*/\s*=\s*\{'
        + r'[^}]*?'                         # everything up to baseConfigurationReference
        + r'baseConfigurationReference\s*=\s*'
        + r')'
        + r'[0-9A-Fa-f]{24}\s*/\*[^*]*\*/'  # the OLD ref + comment to replace
        + r'(\s*;)'                         # group 2: trailing whitespace + ';'
    )
    replacement = r'\g<1>' + new_ref_id + ' /* ' + new_ref_name + ' */' + r'\g<2>'
    new_text, n = re.subn(pattern, replacement, text)
    if n != 1:
        print(f"FATAL: expected exactly 1 substitution for Runner {runner_label}, got n={n}")
        sys.exit(1)
    return new_text

content = replace_baseconfig(content, RUNNER_DEBUG_UUID,   "Debug",   DEBUG_REF_ID,   "Debug.xcconfig")
print("Runner Debug   baseConfigurationReference: substituted (n=1).")

content = replace_baseconfig(content, RUNNER_RELEASE_UUID, "Release", RELEASE_REF_ID, "Release.xcconfig")
print("Runner Release baseConfigurationReference: substituted (n=1).")

with open(PBXPROJ, "w", encoding="utf-8") as f:
    f.write(content)
print("OK: project.pbxproj written.")
PYEOF

PY_EXIT=$?
if [ "$PY_EXIT" -ne 0 ]; then
    echo "FATAL: Python edit failed (exit $PY_EXIT). Restoring backup..."
    cp "$PBXPROJ_BACKUP" "$PROJECT_PBXPROJ"
    echo "OK: project.pbxproj restored from $PBXPROJ_BACKUP."
    echo "    No further steps will run. Bring back the session log via USB."
    exit 1
fi

# ===========================================================================
# STEP 5: Capture AFTER state and HALT-on-failure verification (V1)
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 5: CAPTURE AFTER STATE + VERIFY (HALT ON FAIL) ==="
echo "============================================================"

{
    echo "=== A27 AFTER: all baseConfigurationReference lines ==="
    grep -n 'baseConfigurationReference' "$PROJECT_PBXPROJ" || true
    echo ""
    echo "=== A27 AFTER: Runner Debug + Release config blocks (truncated by first '};') ==="
    echo "--- Runner Debug ($RUNNER_DEBUG_UUID) ---"
    awk "/$RUNNER_DEBUG_UUID \\/\\* Debug \\*\\/ = \\{/,/};/" "$PROJECT_PBXPROJ" | head -30
    echo ""
    echo "--- Runner Release ($RUNNER_RELEASE_UUID) ---"
    awk "/$RUNNER_RELEASE_UUID \\/\\* Release \\*\\/ = \\{/,/};/" "$PROJECT_PBXPROJ" | head -30
    echo ""
    echo "=== A27 AFTER: RunnerTests baseConfigurationReference (must still point at Pods-RunnerTests.*) ==="
    grep -B1 'baseConfigurationReference' "$PROJECT_PBXPROJ" | grep -A1 'RunnerTests' || echo "(no RunnerTests context lines -- inspect full grep above)"
} > ~/Desktop/a27_after_fix.txt
echo "OK: AFTER state captured to ~/Desktop/a27_after_fix.txt"

# Verify Runner Debug now points at Debug.xcconfig (not Pods-Runner.debug.xcconfig).
DEBUG_OK=$(awk "/$RUNNER_DEBUG_UUID \\/\\* Debug \\*\\/ = \\{/,/};/" "$PROJECT_PBXPROJ" \
    | grep -c 'baseConfigurationReference.*\* Debug\.xcconfig \*/' || true)
RELEASE_OK=$(awk "/$RUNNER_RELEASE_UUID \\/\\* Release \\*\\/ = \\{/,/};/" "$PROJECT_PBXPROJ" \
    | grep -c 'baseConfigurationReference.*\* Release\.xcconfig \*/' || true)

echo "Runner Debug   verification grep count: $DEBUG_OK   (expected 1)"
echo "Runner Release verification grep count: $RELEASE_OK (expected 1)"

# Also verify NO Runner block still points at Pods-Runner.{debug,release}.xcconfig.
DEBUG_BAD=$(awk "/$RUNNER_DEBUG_UUID \\/\\* Debug \\*\\/ = \\{/,/};/" "$PROJECT_PBXPROJ" \
    | grep -c 'baseConfigurationReference.*Pods-Runner\.debug\.xcconfig' || true)
RELEASE_BAD=$(awk "/$RUNNER_RELEASE_UUID \\/\\* Release \\*\\/ = \\{/,/};/" "$PROJECT_PBXPROJ" \
    | grep -c 'baseConfigurationReference.*Pods-Runner\.release\.xcconfig' || true)

echo "Runner Debug   stale Pods-Runner.debug.xcconfig refs:   $DEBUG_BAD   (expected 0)"
echo "Runner Release stale Pods-Runner.release.xcconfig refs: $RELEASE_BAD (expected 0)"

if [ "$DEBUG_OK" != "1" ] || [ "$RELEASE_OK" != "1" ] || [ "$DEBUG_BAD" != "0" ] || [ "$RELEASE_BAD" != "0" ]; then
    echo ""
    echo "FATAL: post-edit verification failed. Restoring backup..."
    cp "$PBXPROJ_BACKUP" "$PROJECT_PBXPROJ"
    echo "OK: project.pbxproj restored from $PBXPROJ_BACKUP."
    echo "    Bring back ~/Desktop/a27_before_fix.txt and ~/Desktop/a27_after_fix.txt"
    echo "    via USB so Claude can diagnose."
    exit 1
fi

echo "OK: post-edit verification PASSED (Debug + Release wired to Flutter xcconfigs;"
echo "    Pods-Runner.{debug,release}.xcconfig no longer referenced from Runner blocks)."

# ===========================================================================
# STEP 6: Add A27 sentinel + printenv hook for build-time evidence
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 6: ADD A27 SENTINELS + PRINTENV HOOK ==="
echo "============================================================"

# Sentinels in the Flutter xcconfigs -- if the chain is now correctly wired,
# they should propagate to the Run Script Phase env (mirror of A25's test).
if grep -q 'XCCONFIG_SENTINEL_RELEASE_A27' "$RELEASE_XCCONFIG"; then
    echo "OK: Release A27 sentinel already present (idempotent skip)."
else
    echo "" >> "$RELEASE_XCCONFIG"
    echo "XCCONFIG_SENTINEL_RELEASE_A27 = release_xcconfig_loaded_a27" >> "$RELEASE_XCCONFIG"
    echo "OK: Release A27 sentinel inserted."
fi

if grep -q 'XCCONFIG_SENTINEL_DEBUG_A27' "$DEBUG_XCCONFIG"; then
    echo "OK: Debug A27 sentinel already present (idempotent skip)."
else
    echo "" >> "$DEBUG_XCCONFIG"
    echo "XCCONFIG_SENTINEL_DEBUG_A27 = debug_xcconfig_loaded_a27" >> "$DEBUG_XCCONFIG"
    echo "OK: Debug A27 sentinel inserted."
fi

# B4: awk-based insertion (BSD sed lacks inline 2i\<text>).
if grep -q 'flutter_build_phase_env_a27.log' "$XCODE_BACKEND_SH"; then
    echo "OK: A27 printenv line already present in xcode_backend.sh (idempotent skip)."
else
    awk 'NR==1{print; print "printenv | sort > /tmp/flutter_build_phase_env_a27.log"; next} 1' \
        "$XCODE_BACKEND_SH" > "$XCODE_BACKEND_SH.tmp" && mv "$XCODE_BACKEND_SH.tmp" "$XCODE_BACKEND_SH"
    if grep -q 'flutter_build_phase_env_a27.log' "$XCODE_BACKEND_SH"; then
        echo "OK: A27 printenv line inserted into xcode_backend.sh (top of file)."
    else
        echo "FATAL: could not insert A27 printenv line. Aborting (cleanup trap will run)."
        exit 1
    fi
fi

# Dump the modified files for the record.
{
    echo "=== Release.xcconfig (post-A27-sentinel-insertion, $SESSION_DATE) ==="
    cat "$RELEASE_XCCONFIG"
    echo ""
    echo "=== Debug.xcconfig (post-A27-sentinel-insertion, $SESSION_DATE) ==="
    cat "$DEBUG_XCCONFIG"
} > ~/Desktop/a27_xcconfig_dumps.txt
echo "OK: xcconfig dumps captured to ~/Desktop/a27_xcconfig_dumps.txt"

# ===========================================================================
# STEP 7: Snapshot Podfile.lock (standard since A19 lessons)
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 7: SNAPSHOT Podfile.lock ==="
echo "============================================================"

if [ -f "$PODFILE_LOCK" ]; then
    cp "$PODFILE_LOCK" ~/Desktop/a27_podfile_lock.txt
    echo "OK: Podfile.lock snapshotted to ~/Desktop/a27_podfile_lock.txt"
else
    echo "WARN: Podfile.lock not found at $PODFILE_LOCK"
    echo "Podfile.lock not found at $PODFILE_LOCK" > ~/Desktop/a27_podfile_lock.txt
fi

# ===========================================================================
# STEP 8: flutter build ios --release --no-codesign  (the moment of truth)
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 8: flutter build ios --release --no-codesign ==="
echo "============================================================"

# M3: cd is the one acceptable absolute-path exception -- flutter requires it.
cd "$PROJECT_DIR"
flutter build ios --release --no-codesign 2>&1 | tee /tmp/flutter_build_27.log
# B6: ${PIPESTATUS[0]} reads flutter's exit code, not tee's.
BUILD_EXIT=${PIPESTATUS[0]}

echo ""
echo "Build exit code: $BUILD_EXIT"

# ===========================================================================
# STEP 9: Sentinel detection + post-build env capture
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 9: SENTINEL DETECTION + POST-BUILD ENV CAPTURE ==="
echo "============================================================"

RELEASE_HIT="NOT FOUND"
DEBUG_HIT="NOT FOUND"
FLUTTER_BUILD_DIR_HIT="NOT FOUND"
RELEASE_RESULT="NO"
DEBUG_RESULT="NO"
FLUTTER_BUILD_DIR_RESULT="NO"

if [ -f /tmp/flutter_build_phase_env_a27.log ]; then
    echo "OK: printenv capture exists at /tmp/flutter_build_phase_env_a27.log"

    if grep -q 'XCCONFIG_SENTINEL_RELEASE_A27' /tmp/flutter_build_phase_env_a27.log; then
        RELEASE_RESULT="YES"
        RELEASE_HIT=$(grep 'XCCONFIG_SENTINEL_RELEASE_A27' /tmp/flutter_build_phase_env_a27.log)
    fi
    if grep -q 'XCCONFIG_SENTINEL_DEBUG_A27' /tmp/flutter_build_phase_env_a27.log; then
        DEBUG_RESULT="YES"
        DEBUG_HIT=$(grep 'XCCONFIG_SENTINEL_DEBUG_A27' /tmp/flutter_build_phase_env_a27.log)
    fi
    # The actual goal: FLUTTER_BUILD_DIR should now propagate.
    if grep -q '^FLUTTER_BUILD_DIR=' /tmp/flutter_build_phase_env_a27.log; then
        FLUTTER_BUILD_DIR_RESULT="YES"
        FLUTTER_BUILD_DIR_HIT=$(grep '^FLUTTER_BUILD_DIR=' /tmp/flutter_build_phase_env_a27.log)
    fi
else
    echo "WARN: /tmp/flutter_build_phase_env_a27.log NOT created."
    echo "      This means xcode_backend.sh did not run during this build,"
    echo "      i.e. the build failed BEFORE the Run Script Phase fired."
fi

{
    echo "=== ASSIGNMENT 27 SENTINEL + ENV RESULTS (timestamp: $SESSION_DATE) ==="
    echo ""
    echo "RELEASE_SENTINEL_PROPAGATED_A27=$RELEASE_RESULT"
    echo "DEBUG_SENTINEL_PROPAGATED_A27=$DEBUG_RESULT"
    echo "FLUTTER_BUILD_DIR_PRESENT_A27=$FLUTTER_BUILD_DIR_RESULT"
    echo ""
    echo "Release sentinel grep:    $RELEASE_HIT"
    echo "Debug sentinel grep:      $DEBUG_HIT"
    echo "FLUTTER_BUILD_DIR grep:   $FLUTTER_BUILD_DIR_HIT"
    echo ""
    echo "Build exit code: $BUILD_EXIT"
    echo ""
    echo "Interpretation guide for Claude:"
    echo "  A) BUILD_EXIT=0 + FLUTTER_BUILD_DIR=YES + sentinels=YES"
    echo "     => Branch B fix succeeded. Next step: A28 (sign + install)."
    echo "  B) BUILD_EXIT=0 + FLUTTER_BUILD_DIR=NO"
    echo "     => Build succeeded for an unexpected reason. Inspect the env carefully."
    echo "  C) BUILD_EXIT!=0 + FLUTTER_BUILD_DIR=YES + sentinels=YES"
    echo "     => xcconfig wiring is fixed but a different build error exists. New theory needed."
    echo "  D) BUILD_EXIT!=0 + FLUTTER_BUILD_DIR=NO + sentinels=YES"
    echo "     => Sentinels propagated but Generated.xcconfig still not loading. Inspect the"
    echo "        Flutter/Release.xcconfig #include for Generated.xcconfig."
    echo "  E) BUILD_EXIT!=0 + sentinels=NO"
    echo "     => baseConfigurationReference edit didn't take effect at build time. Inspect"
    echo "        a27_after_fix.txt and the Python output earlier in this session log."
} | tee ~/Desktop/a27_sentinel_results.txt

# ===========================================================================
# STEP 10: Build artifacts info (only present if build succeeded)
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 10: BUILD ARTIFACTS INFO ==="
echo "============================================================"

APP_PATH="$PROJECT_DIR/build/ios/iphoneos/Runner.app"
{
    echo "=== A27 build artifacts (timestamp: $SESSION_DATE) ==="
    echo ""
    echo "Looking for $APP_PATH"
    if [ -d "$APP_PATH" ]; then
        echo "PRESENT: Runner.app"
        ls -la "$APP_PATH"
        echo ""
        echo "--- Frameworks/ in Runner.app ---"
        ls -la "$APP_PATH/Frameworks" 2>/dev/null || echo "(no Frameworks dir)"
        echo ""
        if [ -d "$APP_PATH/Frameworks/CwlCatchException.framework" ]; then
            echo "PRESENT: CwlCatchException.framework is embedded"
            ls -la "$APP_PATH/Frameworks/CwlCatchException.framework"
        else
            echo "ABSENT: CwlCatchException.framework is NOT embedded -- crash will likely recur on launch"
        fi
    else
        echo "ABSENT: Runner.app does not exist (build did not produce it)."
        echo "Searching for any Runner.app in build/..."
        find "$PROJECT_DIR/build" -name 'Runner.app' -maxdepth 6 2>/dev/null | head -5 || true
    fi
} > ~/Desktop/a27_build_artifacts.txt
cat ~/Desktop/a27_build_artifacts.txt

# ===========================================================================
# STEP 11: Copy results to USB + local backup (B2, M5)
# ===========================================================================
echo ""
echo "============================================================"
echo "=== STEP 11: COPY RESULTS TO USB + LOCAL BACKUP ==="
echo "============================================================"

# B2: real double quotes around USB path (it contains a space), visible per-file errors.
cp ~/Desktop/full_a27_session.txt        "$USB_RESULTS/full_a27_session_${SESSION_DATE}.txt"        || echo "USB copy failed: full_a27_session.txt"
cp ~/Desktop/a27_sentinel_results.txt    "$USB_RESULTS/a27_sentinel_results_${SESSION_DATE}.txt"    || echo "USB copy failed: a27_sentinel_results.txt"
cp ~/Desktop/a27_xcconfig_dumps.txt      "$USB_RESULTS/a27_xcconfig_dumps_${SESSION_DATE}.txt"      || echo "USB copy failed: a27_xcconfig_dumps.txt"
cp ~/Desktop/a27_before_fix.txt          "$USB_RESULTS/a27_before_fix_${SESSION_DATE}.txt"          || echo "USB copy failed: a27_before_fix.txt"
cp ~/Desktop/a27_after_fix.txt           "$USB_RESULTS/a27_after_fix_${SESSION_DATE}.txt"           || echo "USB copy failed: a27_after_fix.txt"
cp ~/Desktop/a27_podfile_lock.txt        "$USB_RESULTS/a27_podfile_lock_${SESSION_DATE}.txt"        || echo "USB copy failed: a27_podfile_lock.txt"
cp ~/Desktop/a27_build_artifacts.txt     "$USB_RESULTS/a27_build_artifacts_${SESSION_DATE}.txt"     || echo "USB copy failed: a27_build_artifacts.txt"
cp /tmp/flutter_build_27.log             "$USB_RESULTS/flutter_build_27_${SESSION_DATE}.log"        || echo "USB copy failed: flutter_build_27.log"
if [ -f /tmp/flutter_build_phase_env_a27.log ]; then
    cp /tmp/flutter_build_phase_env_a27.log "$USB_RESULTS/flutter_build_phase_env_a27_${SESSION_DATE}.log" || echo "USB copy failed: flutter_build_phase_env_a27.log"
fi

# M5: local backup fallback
echo "--- Local backup copies ---"
cp ~/Desktop/full_a27_session.txt        "$LOCAL_BACKUP/"
cp ~/Desktop/a27_sentinel_results.txt    "$LOCAL_BACKUP/"
cp ~/Desktop/a27_xcconfig_dumps.txt      "$LOCAL_BACKUP/"
cp ~/Desktop/a27_before_fix.txt          "$LOCAL_BACKUP/"
cp ~/Desktop/a27_after_fix.txt           "$LOCAL_BACKUP/"
cp ~/Desktop/a27_podfile_lock.txt        "$LOCAL_BACKUP/"
cp ~/Desktop/a27_build_artifacts.txt     "$LOCAL_BACKUP/"
cp /tmp/flutter_build_27.log             "$LOCAL_BACKUP/"
[ -f /tmp/flutter_build_phase_env_a27.log ] && cp /tmp/flutter_build_phase_env_a27.log "$LOCAL_BACKUP/"
echo "OK: Local backup copies in $LOCAL_BACKUP"

# ===========================================================================
# STEP 12: Final summary -- the cleanup trap will fire after this
# ===========================================================================
echo ""
echo "============================================================"
echo "=== ASSIGNMENT 27 COMPLETE -- CLEANUP TRAP WILL RUN NEXT ==="
echo "============================================================"
echo ""
echo "Build exit code:                       $BUILD_EXIT"
echo "RELEASE_SENTINEL_PROPAGATED_A27:       $RELEASE_RESULT"
echo "DEBUG_SENTINEL_PROPAGATED_A27:         $DEBUG_RESULT"
echo "FLUTTER_BUILD_DIR_PRESENT_A27:         $FLUTTER_BUILD_DIR_RESULT"
echo ""
echo "project.pbxproj: EDITED (kept). Backup: $PBXPROJ_BACKUP"
echo "Result files:"
echo "    USB:   $USB_RESULTS/*_${SESSION_DATE}.*"
echo "    Local: $LOCAL_BACKUP/"
echo ""
echo "Next step (Claude): analyze a27_sentinel_results to design A28"
echo "(sign + install, OR follow-up diagnostic if build still fails)."
echo ""
echo "(Cleanup trap will now revert sentinels + printenv hook automatically.)"

# Exit 0: the script ran to completion. The build outcome is reported in the
# sentinel results; it is not the script's exit code.
exit 0
