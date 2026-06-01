# Assignment 24 v3 — Diagnose xcconfig Propagation to Run Script Phase

**Goal:** Capture evidence to determine why `FLUTTER_BUILD_DIR` (present in Generated.xcconfig) isn't reaching the shell environment of `xcode_backend.sh`. **DIAGNOSIS ONLY - NO FIXES YET.**

**Script to run:** `diagnose_xcconfig_propagation_a24_v3.sh`

**Version 3 Changes:** Fixed B5 (tilde-in-quotes for Pods paths) and B6 (PIPESTATUS for flutter build exit code) per Claude review

**Time:** ~5-10 minutes (build + diagnostics)

**Critical:** This assignment temporarily modifies Flutter SDK (`xcode_backend.sh`) to capture environment data, then automatically reverts the change.

## Background

Assignment 23 proved that `FLUTTER_BUILD_DIR=build` and `FLUTTER_ROOT=/Users/micha/flutter` are present in `Generated.xcconfig`. However, `xcode_backend.dart:345` still fails with null-check error, meaning these values aren't reaching the script's shell environment.

**Three hypotheses to test:**
1. **Xcode 26 user script sandboxing** (most likely) - restricts Run Script Phase environment
2. **Broken `#include "Generated.xcconfig"`** - include directive not working
3. **`_embedNativeAssets` called incorrectly** - function shouldn't run at all

## Prerequisites

- [ ] `D:\Audioura\scripts\diagnose_xcconfig_propagation_a24_v3.sh` exists
- [ ] USB stick plugged in, visible at `D:\` in Windows
- [ ] iPhone 16 (UDID `00008140-000558A902BA801C`) plugged into Mac Mini

## Step 1 — Switch KVM to Mac Mini

Standard switch.

## Step 2 — Navigate and prepare

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x diagnose_xcconfig_propagation_a24_v3.sh
```

## Step 3 — Run the diagnostic script

```
./diagnose_xcconfig_propagation_a24_v3.sh
```

**What the script does:**

1. **Full terminal recording** (fixed: no interactive shell freeze)
2. **System date drift check** (new: validates 2026 timestamp)
3. **Temporarily modifies Flutter SDK** - adds `printenv` capture to `xcode_backend.sh` (fixed: BSD-compatible awk)
4. **Captures 6 pieces of evidence:**
   - **A.** Run Script Phase environment (the critical data)
   - **B.** Sandbox settings in Runner project
   - **C.** Full contents of all xcconfig files
   - **D.** Run Script Phase definitions from project.pbxproj (fixed: proper grep quotes)
   - **E.** Native assets evidence (fixed: proper grep quotes)
   - **F.** Flutter build attempt with full output
5. **Automatically reverts Flutter SDK** (cleanup trap ensures this happens)
6. **Copies all results to USB** (fixed: proper quotes, visible errors)
7. **Creates local backup** (new: ~/Desktop/a24_results/ fallback)

**Run time:** ~5-10 minutes

## Step 4 — Key evidence to watch for

**Most important:** After the build completes, the script shows:
- ✅ **"Environment capture successful"** - means `xcode_backend.sh` ran and we captured its environment
- ❌ **"Environment capture failed"** - means the script phase didn't run or failed
- 🚨 **"CRITICAL: FLUTTER_BUILD_DIR missing"** - fail-loud marker for key finding

**Critical question:** Does `FLUTTER_BUILD_DIR` appear in the captured environment?
- If **YES** → Different root cause than expected
- If **NO** → Confirms environment propagation failure

## Step 5 — Copy results and return

The script automatically copies 6 result files to USB with timestamp:
- `full_a24_session_[timestamp].txt` (complete terminal recording)
- `flutter_build_phase_env_a24_[timestamp].log` (THE CRITICAL FILE)
- `flutter_build_24_[timestamp].log` (build output)
- `a24_xcconfig_dumps_[timestamp].txt` (all xcconfig contents)
- `a24_pbxproj_grep_[timestamp].txt` (sandbox + script phase settings)
- `a24_native_assets_evidence_[timestamp].txt` (native assets search)

**Plus local backup in `~/Desktop/a24_results/` if USB fails**

```
diskutil eject "/Volumes/USB DISK"
```

## Step 6 — Report to iOS Amazon-Q

Switch back to Windows and report:

**If environment capture succeeded:**
> "Assignment 24 v2 complete. Environment captured successfully. FLUTTER_BUILD_DIR [was/was not] present in xcode_backend.sh environment."

**If environment capture failed:**
> "Assignment 24 v2 complete. Environment capture failed - xcode_backend.sh may not have run."

**Include any other notable observations from the terminal output.**

## Expected Outcomes

**Outcome 1:** Environment captured, `FLUTTER_BUILD_DIR` missing
- **Meaning:** Confirms xcconfig values not propagating to Run Script Phase
- **Next:** Assignment 25 will add explicit environment variable injection

**Outcome 2:** Environment captured, `FLUTTER_BUILD_DIR` present
- **Meaning:** Different root cause - variable is there but script still fails
- **Next:** Need to investigate `xcode_backend.dart` logic further

**Outcome 3:** Environment capture failed
- **Meaning:** Run Script Phase not executing or diagnostic modification failed
- **Next:** Need to investigate why script phase isn't running

## Safety Notes

- **Flutter SDK modification is temporary** - script automatically reverts changes
- **No project files modified** - only reads xcconfig files, doesn't change them
- **No `flutter clean` or `flutter pub get`** - preserves current state for diagnosis
- **Full terminal recording** - complete session captured for analysis
- **Local backup created** - results preserved even if USB copy fails
- **System date validation** - checks for timestamp drift

**Version 3 Fixes Applied (on top of v2):**
- **B5:** Replaced `"~/...` with `"$HOME/...` for Pods xcconfig paths (tilde inside double quotes is not expanded)
- **B6:** Replaced `BUILD_EXIT=$?` with `BUILD_EXIT=${PIPESTATUS[0]}` (post-pipe exit code now reflects flutter build, not tee)

---

**Next Step:** Claude analyzes the 6 evidence files and writes Assignment 25 (the actual fix, likely one line).

**Last Updated:** 2026-04-28 v3
**Priority:** HIGH - Critical diagnostic for iOS crash fix