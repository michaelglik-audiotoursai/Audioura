# Assignment 26 — Fix project.pbxproj baseConfigurationReference (Branch B)

**Goal:** Restore Flutter configuration chain by fixing `baseConfigurationReference` entries in `project.pbxproj` to point to Flutter xcconfig files instead of Pods xcconfig files.

**Script to run:** `fix_baseconfig_a26.sh`

**Scope:** **TARGETED FIX** based on Assignment 25 Branch B results (`RELEASE_SENTINEL_PROPAGATED=NO`).

**Time:** ~5–10 minutes (fix + build test).

**Critical:** This script modifies `project.pbxproj` and creates a timestamped backup. The fix restores the configuration chain: `Release.xcconfig` → `Generated.xcconfig` → `FLUTTER_BUILD_DIR=build`.

---

## Background

Assignment 25 confirmed **Branch B**: `Release.xcconfig` is bypassed entirely because `project.pbxproj`'s `baseConfigurationReference` entries point directly to Pods xcconfig files instead of Flutter xcconfig files.

**Current (BROKEN) Configuration Chain:**
```
Debug:   baseConfigurationReference → Pods-Runner.debug.xcconfig
Release: baseConfigurationReference → Pods-Runner.release.xcconfig
```

**Target (FIXED) Configuration Chain:**
```
Debug:   baseConfigurationReference → Flutter/Debug.xcconfig → Generated.xcconfig
Release: baseConfigurationReference → Flutter/Release.xcconfig → Generated.xcconfig
```

This will make `FLUTTER_BUILD_DIR=build` (from `Generated.xcconfig`) available to `xcode_backend.sh`, resolving the null-check failure at `xcode_backend.dart:345`.

---

## Prerequisites

- [ ] `D:\Audioura\scripts\fix_baseconfig_a26.sh` exists
- [ ] USB stick plugged into Mac Mini, mounted as `/Volumes/USB DISK/`
- [ ] iPhone 16 (UDID `00008140-000558A902BA801C`) plugged into Mac Mini
- [ ] Assignment 25 completed successfully with `RELEASE_SENTINEL_PROPAGATED=NO`

---

## Step 1 — Switch KVM to Mac Mini

Standard switch.

---

## Step 2 — Navigate and prepare

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x fix_baseconfig_a26.sh
```

---

## Step 3 — Run the fix script

```
./fix_baseconfig_a26.sh
```

**What the script does (in order):**

1. **Backup**: Creates timestamped backup of `project.pbxproj`
2. **Capture Before**: Records current `baseConfigurationReference` entries
3. **Find Flutter References**: Locates Flutter xcconfig file IDs in project
4. **Apply Fix**: Replaces Pods references with Flutter references using `sed`
5. **Verify Fix**: Captures fixed state and shows changes
6. **Test Build**: Runs `flutter build ios --release --no-codesign`
7. **Copy Results**: Saves all evidence files to USB and local backup

**Expected Result**: Flutter build should complete **WITHOUT** the `xcode_backend.dart:345` null-check error.

**Run time:** ~5–10 minutes.

---

## Step 4 — Monitor the critical test

The script will run `flutter build ios --release --no-codesign` after applying the fix.

**Success Indicators:**
```
Build exit code: 0
✅ SUCCESS! Flutter build completed without errors!
✅ FLUTTER_BUILD_DIR is now available to xcode_backend.sh
✅ Configuration chain restored: Release.xcconfig → Generated.xcconfig
```

**If Still Failing:**
```
Build exit code: 1
❌ Build still failed. Exit code: 1
Check flutter_build_26.log for details
```

---

## Step 5 — Next steps based on result

### **If Build Succeeds (Expected)**
1. **Sign and Install**: Use existing signing process to install working app
2. **Test App Launch**: Verify Audioura launches without crashes
3. **Celebrate**: iOS development barrier broken!

### **If Build Still Fails (Unexpected)**
1. **Check Logs**: Review `flutter_build_26.log` for new error details
2. **Verify Fix**: Confirm `baseConfigurationReference` changes applied correctly
3. **Report Results**: Provide build output for further analysis

---

## Step 6 — Copy results and return

```
diskutil eject "/Volumes/USB DISK"
```

---

## Step 7 — Report to iOS Amazon-Q

Switch back to Windows and report the result:

> "Assignment 26 complete. Build exit code: [0/1]. Status: [SUCCESS - ready for app installation / FAILED - additional investigation needed]."

Plus any notable observations from the build output.

---

## Result files (all timestamped) on USB

```
a26_before_fix_<ts>.txt                    (baseConfigurationReference before fix)
a26_after_fix_<ts>.txt                     (baseConfigurationReference after fix)  
flutter_build_26_<ts>.log                  (flutter build test output)
project_pbxproj_backup_a26_<ts>.txt        (original project.pbxproj backup)
```

Local backup copies in `~/Desktop/a26_results/`.

---

## Safety notes

- **Automatic Backup**: `project.pbxproj.backup_a26_<timestamp>` created before any changes
- **Targeted Changes**: Only modifies `baseConfigurationReference` entries (2 lines total)
- **Verification**: Captures before/after state for comparison
- **Reversible**: Can restore from backup if needed
- **No CocoaPods Changes**: Pods xcconfig files remain untouched
- **Build Test**: Immediate verification that fix works

---

## Technical Details

**Fix Mechanism**: Uses `sed` to replace specific `baseConfigurationReference` UUIDs:
- Finds Flutter xcconfig file UUIDs in project
- Replaces Pods-Runner references with Flutter references
- Preserves all other project settings

**Why This Works**:
- `Flutter/Release.xcconfig` contains: `#include "Generated.xcconfig"`
- `Generated.xcconfig` contains: `FLUTTER_BUILD_DIR=build`
- Restored chain makes `FLUTTER_BUILD_DIR` available to `xcode_backend.sh`
- Null-check at `xcode_backend.dart:345` passes

---

**Last Updated:** 2026-04-29 02:15 PM
**Priority:** CRITICAL — Final fix for iOS build barrier
**Expected Outcome:** Working Flutter build + successful Audioura app installation