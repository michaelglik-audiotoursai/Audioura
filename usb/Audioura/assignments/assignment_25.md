# Assignment 25 — Sentinel Test for xcconfig Base-Configuration Loading

**Goal:** Determine whether `Flutter/Release.xcconfig` and `Flutter/Debug.xcconfig` are loaded as the active base configuration of their respective build configurations, by inserting unique sentinel keys and checking whether they propagate to the Run Script Phase environment.

**Script to run:** `sentinel_test_a25.sh`

**Scope:** **DIAGNOSIS ONLY — NO FIXES.** Assignment 26 will be the targeted one-change fix designed by Claude after these results land.

**Time:** ~5–10 minutes (build + diagnostics).

**Critical:** This script temporarily modifies THREE files (`Release.xcconfig`, `Debug.xcconfig`, `xcode_backend.sh`) and reverts ALL of them via a `trap` on `EXIT`. The script's last visible output is a per-file PASS/FAIL cleanup verification — confirm three PASS lines before walking away.

---

## Background

Assignment 24 v3 confirmed that `Generated.xcconfig` values (`FLUTTER_BUILD_DIR`, `FLUTTER_APPLICATION_PATH`, `DART_DEFINES`, etc.) do NOT propagate to the Run Script Phase environment, while every key from `Pods-Runner.release.xcconfig` does. This means either:

- **(A)** `Release.xcconfig` IS the active base configuration but its `#include "Generated.xcconfig"` is silently failing, or
- **(B)** `Release.xcconfig` is bypassed entirely — `project.pbxproj`'s `baseConfigurationReference` for the Release configuration points directly at `Pods-Runner.release.xcconfig`, never reaching `Release.xcconfig` (and therefore never reaching `Generated.xcconfig` either).

This sentinel test distinguishes (A) from (B) with a single signal. The fix differs by branch, so we diagnose first, then fix in Assignment 26.

---

## Prerequisites

- [ ] `sentinel_test_a25.sh` exists at `D:\Audioura\scripts\sentinel_test_a25.sh` (Windows side, USB stick)
- [ ] USB stick plugged into Mac Mini, mounted as `/Volumes/USB DISK/`
- [ ] iPhone 16 (UDID `00008140-000558A902BA801C`) plugged into Mac Mini (not strictly required for this build, but standard)
- [ ] No background `xcodebuild` or Xcode UI build in progress

---

## Step 1 — Switch KVM to Mac Mini

Standard switch.

---

## Step 2 — Navigate and prepare

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x sentinel_test_a25.sh
```

---

## Step 3 — Run the sentinel test script

```
./sentinel_test_a25.sh
```

**Do NOT wrap with `script ~/Desktop/...`.** The script handles its own output capture via `exec > >(tee ~/Desktop/full_a25_session.txt) 2>&1`. Wrapping with `script` from inside a script body is what froze the v1→v2 saga (B1 lesson).

**What the script does (in order):**

1. Captures session timestamp and validates system date is in 2026 (M1 — guards against Amazon-Q's prior date-drift bug).
2. Sets up `trap cleanup EXIT` — guarantees three-file revert no matter how the script terminates.
3. **STEP 1:** Inserts `XCCONFIG_SENTINEL_RELEASE_A25 = release_xcconfig_loaded_a25` at the end of `Release.xcconfig` (idempotent — skipped if already present).
4. **STEP 1:** Inserts `XCCONFIG_SENTINEL_DEBUG_A25 = debug_xcconfig_loaded_a25` at the end of `Debug.xcconfig` (idempotent).
5. **STEP 2:** Inserts `printenv | sort > /tmp/flutter_build_phase_env_a25.log` at the top of `~/flutter/packages/flutter_tools/bin/xcode_backend.sh` (idempotent; awk insertion for BSD compatibility — B4 lesson).
6. **STEP 3:** Dumps both modified xcconfig files to `~/Desktop/a25_xcconfig_dumps.txt` (proves sentinels are in place at build time).
7. **STEP 4:** Captures `baseConfigurationReference` and `XCBuildConfiguration` blocks from `project.pbxproj` to `~/Desktop/a25_baseconfig_refs.txt` — needed for Assignment 26 design regardless of which branch the sentinel takes.
8. **STEP 5:** Snapshots `Podfile.lock` (standard since A19 lessons).
9. **STEP 6:** Runs `flutter build ios --release --no-codesign` and captures stdout/stderr; uses `${PIPESTATUS[0]}` to read flutter's true exit code (B6 — `tee` would mask it).
10. **STEP 7:** Greps the printenv capture for both sentinels. Writes the headline result to `~/Desktop/a25_sentinel_results.txt` in the form `RELEASE_SENTINEL_PROPAGATED=YES|NO` and `DEBUG_SENTINEL_PROPAGATED=YES|NO`.
11. **STEP 8:** Copies all result files to `/Volumes/USB DISK/Audioura/results/` (timestamped) and to `~/Desktop/a25_results/` as a local fallback (M5).
12. **CLEANUP TRAP** fires on EXIT — reverts the three modifications and writes a per-file PASS/FAIL line to `~/Desktop/a25_cleanup_verification.txt`. **This file is the last thing the script writes — its on-screen contents are the cleanup confirmation.**

**Run time:** ~5–10 minutes.

---

## Step 4 — Headline result to watch for

The build will likely fail with the same `xcode_backend.dart:345` null-check error — that is **expected**. The sentinel result is what matters.

Look at the final on-screen `SENTINEL RESULTS` block:

```
RELEASE_SENTINEL_PROPAGATED=YES   → Release.xcconfig IS the base. Branch A.
RELEASE_SENTINEL_PROPAGATED=NO    → Release.xcconfig is BYPASSED. Branch B.
```

`DEBUG_SENTINEL_PROPAGATED` is informational — confirms the same diagnosis applies symmetrically.

---

## Step 5 — Verify cleanup, then return

The script's final visible output is the cleanup verification. Confirm three PASS lines:

```
xcode_backend.sh:    PASS -- printenv line removed
Release.xcconfig:    PASS -- sentinel removed
Debug.xcconfig:      PASS -- sentinel removed
```

If any FAIL appears, **do NOT continue any other build work** — re-run the script (it is idempotent), or contact Claude before any further build attempts. A FAIL means the sentinel/printenv line is still in place and would contaminate any subsequent build.

Then eject the USB:
```
diskutil eject "/Volumes/USB DISK"
```

---

## Step 6 — Report to iOS Amazon-Q

Switch back to Windows and report the headline result:

> "Assignment 25 complete. RELEASE_SENTINEL_PROPAGATED=[YES/NO]. DEBUG_SENTINEL_PROPAGATED=[YES/NO]. Cleanup [PASS/FAIL per file]."

Plus any other notable observations from the terminal output.

---

## Result files (all timestamped) on USB

```
full_a25_session_<ts>.txt              (full terminal recording)
a25_sentinel_results_<ts>.txt          (THE HEADLINE)
flutter_build_phase_env_a25_<ts>.log   (printenv capture from inside xcode_backend.sh)
flutter_build_25_<ts>.log              (flutter build output)
a25_xcconfig_dumps_<ts>.txt            (Release + Debug post-sentinel-insertion)
a25_baseconfig_refs_<ts>.txt           (project.pbxproj baseConfigurationReference + XCBuildConfiguration)
a25_podfile_lock_<ts>.txt              (Podfile.lock snapshot)
a25_cleanup_verification_<ts>.txt      (per-file PASS/FAIL revert confirmation)
```

Local backup copies in `~/Desktop/a25_results/`.

---

## Safety notes

- **Three-file modification, all reverted by trap on EXIT.** Even if the script aborts mid-run, all three modifications are undone.
- **Sentinels are unique custom keys** (`XCCONFIG_SENTINEL_RELEASE_A25`, `XCCONFIG_SENTINEL_DEBUG_A25`) — no possible collision with any project setting. Removed by sed pattern matched on the unique key name (no slashes in pattern, so no escape issues).
- **No `flutter clean` or `flutter pub get`** — would regenerate `Generated.xcconfig` and contaminate the experiment.
- **No project source files modified.** Only the two Flutter xcconfigs and the Flutter SDK script — all reverted.
- **No Podfile, no `pod install`** — those are change targets for Assignment 26 if at all.
- **Build will likely fail** with the same `xcode_backend.dart:345` null-check error. That is expected and not an indication of script malfunction.

---

## Bash bug-fixes from A24 review baked in upfront

- **B1:** `exec > >(tee ...) 2>&1` for output capture (no `script` from inside script body — that froze v1)
- **B2:** USB `cp` uses real double quotes, visible per-file errors
- **B3:** single-quoted grep patterns
- **B4:** awk for line insertion (BSD sed does not support inline `2i\<text>` on macOS)
- **B5:** `"$HOME/..."` not `"~/..."` inside double quotes
- **B6:** `${PIPESTATUS[0]}` for flutter build exit code after the `tee` pipe
- **M1:** system-date drift check (Amazon-Q tagged A20 as 01/31/2025 while we were in April 2026)
- **M3:** `cd` only for the flutter build (the one acceptable exception to absolute paths)
- **M5:** local backup directory fallback in case USB copy fails

---

## Next step (preview, not part of A25)

**Branch A (RELEASE_SENTINEL_PROPAGATED=YES):** Claude drafts Assignment 26 to inline `Generated.xcconfig`'s essential values directly into `Release.xcconfig` (and `Debug.xcconfig`) after the existing `#include` lines. Workaround for the silently-failing `#include "Generated.xcconfig"`.

**Branch B (RELEASE_SENTINEL_PROPAGATED=NO):** Claude drafts Assignment 26 to edit `project.pbxproj`'s `baseConfigurationReference` for the Release (and Debug) configurations to point at `Flutter/Release.xcconfig` / `Flutter/Debug.xcconfig` instead of the Pods xcconfigs.

Both branches are followed by `flutter build ios --release --no-codesign`, then sign and install on iPhone (UDID `00008140-000558A902BA801C`).

---

**Last Updated:** 2025-01-29
**Priority:** HIGH — precondition for the iOS crash fix