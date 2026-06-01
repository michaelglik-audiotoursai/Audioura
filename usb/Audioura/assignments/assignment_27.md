# Assignment 27 — Fix project.pbxproj baseConfigurationReference (Branch B, Python-based)

**Goal:** Re-attempt the Branch B fix that A26 failed to apply, this time using Python (not sed) anchored on the specific Runner config UUIDs. After the edit, run `flutter build ios --release --no-codesign` and capture both build outcome and a fresh printenv from inside the Run Script Phase to prove (or disprove) that `FLUTTER_BUILD_DIR` now reaches the build env.

**Script to run:** `fix_baseconfig_a27.sh`

**Scope:** **TARGETED FIX + EVIDENCE.** Sign + install on the iPhone is **NOT** part of A27 — that will be Assignment 28 if the build succeeds. This honors the "one change per assignment" rule and lets us see clean causality between the pbxproj edit and the build outcome.

**Time:** ~5–10 minutes (edit + build + diagnostics).

**Drafted by:** Claude (session "Audioura Build and Start #4"), 2026-04-29. Drafted directly per Sir Michael's request — no Amazon-Q intermediary — and self-reviewed before USB transfer (lesson V2).

---

## Background

Assignment 25 confirmed Branch B with sentinels: `RELEASE_SENTINEL_PROPAGATED=NO`, `DEBUG_SENTINEL_PROPAGATED=NO`. The Runner target's Debug + Release `baseConfigurationReference` in `project.pbxproj` point at `Pods-Runner.{debug,release}.xcconfig` instead of `Flutter/{Debug,Release}.xcconfig`, so `Flutter/*.xcconfig` is bypassed and `Generated.xcconfig` (which is `#include`d only from `Flutter/*.xcconfig`) never reaches the build env. That's why `FLUTTER_BUILD_DIR` is null at `xcode_backend.dart:345`.

Assignment 26 attempted the fix with sed and **silently failed**. Two bugs:

1. `DEBUG_FLUTTER_REF=$(grep -o '... Debug\.xcconfig \*/' file | cut -d' ' -f1)` returned a multiline shell variable (the same hex24 ID appears in PBXFileReference, PBXBuildFile, AND baseConfigurationReference sections — `grep -o` matched all three lines, `cut` extracted the same ID per line). When that multiline variable was substituted into a sed pattern, sed errored out with `unescaped newline inside substitute pattern`.
2. The sed regex itself was wrong even with a clean variable: it ended in `\*\;` which matches `*;`, but the actual text ends with `*/;` (close-of-comment + semicolon). The missing `\/` would have matched zero occurrences regardless.

Both errors went to stderr but the script kept printing OK markers. `project.pbxproj` was not modified. Backup is intact (`project.pbxproj.backup_a26_20260429_142729`).

A27 fixes both classes of bug at once by switching the edit to Python, which (a) handles regex escaping cleanly, (b) returns a substitution count via `re.subn(...)` so we can `assert n == 1`, and (c) anchors the substitution on the **specific Runner config UUIDs** (`97C147061CF9000F007C117D` Debug, `97C147071CF9000F007C117D` Release), which guarantees RunnerTests is untouched.

---

## What changes on the Mac Mini

**Edited and KEPT:**
- `~/Development/AudioTours/development/audio_tour_app/ios/Runner.xcodeproj/project.pbxproj`
  - Runner Debug `baseConfigurationReference`   → `Flutter/Debug.xcconfig`   (was: `Pods-Runner.debug.xcconfig`)
  - Runner Release `baseConfigurationReference` → `Flutter/Release.xcconfig` (was: `Pods-Runner.release.xcconfig`)
  - Profile is **intentionally left untouched** (off the critical path; we use `--release`)
  - RunnerTests is **intentionally left untouched** (correctly wired to Pods-RunnerTests xcconfigs already)

**Edited and reverted at end via cleanup trap:**
- `Flutter/Release.xcconfig` (sentinel `XCCONFIG_SENTINEL_RELEASE_A27` appended; reverted)
- `Flutter/Debug.xcconfig`   (sentinel `XCCONFIG_SENTINEL_DEBUG_A27` appended; reverted)
- `~/flutter/packages/flutter_tools/bin/xcode_backend.sh` (printenv line inserted at top; reverted)

The trap fires on `EXIT` (normal or aborted) and writes a per-file PASS/FAIL line — three PASS lines confirm cleanup of the temporary modifications. **The pbxproj edit is intentionally NOT reverted by the trap** — that's the actual fix we want to keep (or roll back manually if the build fails).

---

## Prerequisites

- [ ] `D:\Audioura\scripts\fix_baseconfig_a27.sh` exists (Windows side, copied to USB)
- [ ] USB stick plugged into Mac Mini, mounted as `/Volumes/USB DISK/`
- [ ] iPhone 16 (UDID `00008140-000558A902BA801C`) plugged in (not strictly required for A27, but standard)
- [ ] No background `xcodebuild` or Xcode UI build in progress
- [ ] A26's pbxproj backup `project.pbxproj.backup_a26_20260429_142729` still present at `~/Development/AudioTours/development/audio_tour_app/ios/Runner.xcodeproj/` (defense-in-depth — A27 creates its own backup independently)

---

## Step 1 — Switch KVM to Mac Mini

Standard switch.

---

## Step 2 — Navigate and prepare

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x fix_baseconfig_a27.sh
```

---

## Step 3 — Run the fix script

```
./fix_baseconfig_a27.sh
```

**Do NOT wrap with `script ~/Desktop/...`.** The script handles its own output capture via `exec > >(tee ~/Desktop/full_a27_session.txt) 2>&1` (B1 lesson — bare `script` from inside a script body froze the v1→v2 saga).

**What the script does (in order):**

1. **Pre-flight:** validates all four required files exist; confirms both Runner config UUIDs are present in `project.pbxproj`. HALTs if anything is missing.
2. **Backup:** creates `project.pbxproj.backup_a27_<timestamp>` and stashes a copy in the local backup dir + USB.
3. **Capture BEFORE:** dumps every `baseConfigurationReference` line + the Runner Debug/Release config blocks (truncated by first `};`).
4. **Python edit:** locates the live PBXFileReference IDs for `Debug.xcconfig` / `Release.xcconfig` (anchored on `path = Debug.xcconfig;` / `path = Release.xcconfig;` to disambiguate from Pods-Runner.* file refs); rewrites `baseConfigurationReference` inside the two specific Runner config UUID blocks via `re.subn(...)` with `assert n == 1` per substitution. **HALTs and restores from backup** if either substitution misses or matches more than once.
5. **Capture AFTER + verify (HALT-on-fail):** dumps post-edit state; counts (a) `baseConfigurationReference.*\* Debug.xcconfig */` inside the Runner Debug block (must be 1); (b) the same for Release (must be 1); (c) `baseConfigurationReference.*Pods-Runner.debug.xcconfig` in the Runner Debug block (must be 0); (d) the same for Release. Any deviation HALTs and restores from backup. (V1 lesson — verification must `exit 1`, not just print.)
6. **Sentinels + printenv hook:** appends `XCCONFIG_SENTINEL_RELEASE_A27 = release_xcconfig_loaded_a27` to `Release.xcconfig`, the symmetric line to `Debug.xcconfig`, and `printenv | sort > /tmp/flutter_build_phase_env_a27.log` at the top of `xcode_backend.sh` (B4 awk insertion). All idempotent.
7. **Snapshot Podfile.lock** to `~/Desktop/a27_podfile_lock.txt` (standard since A19).
8. **Build:** `flutter build ios --release --no-codesign` with `tee` → `/tmp/flutter_build_27.log`; reads exit code via `${PIPESTATUS[0]}` (B6).
9. **Sentinel detection + env capture:** greps the printenv log for both A27 sentinels AND for `^FLUTTER_BUILD_DIR=`. Writes a headline result file (`a27_sentinel_results`) covering all five interpretation cases (A through E).
10. **Build artifacts info:** captures presence/absence of `Runner.app` and `Frameworks/CwlCatchException.framework`.
11. **Copy to USB + local backup:** all result files timestamped (B2 — real double quotes around USB path with space, visible per-file errors).
12. **Cleanup trap fires on EXIT:** reverts sentinels + printenv hook (NOT pbxproj); writes per-file PASS/FAIL.

**Run time:** ~5–10 minutes.

---

## Step 4 — Headline results to watch for

The script's final on-screen block reports four numbers:

```
Build exit code:                       <0 or non-zero>
RELEASE_SENTINEL_PROPAGATED_A27:       YES | NO
DEBUG_SENTINEL_PROPAGATED_A27:         YES | NO
FLUTTER_BUILD_DIR_PRESENT_A27:         YES | NO
```

The interpretation table is in `~/Desktop/a27_sentinel_results.txt` and on USB at `a27_sentinel_results_<ts>.txt`. Summary:

| Build exit | Sentinels | FLUTTER_BUILD_DIR | Reading |
|---|---|---|---|
| 0 | YES | YES | A — Branch B fix succeeded. Proceed to A28 (sign + install). |
| 0 | NO  | NO  | B — Build succeeded for an unexpected reason. Inspect the env. |
| ≠0 | YES | YES | C — xcconfig wiring fixed; different build error remains. New theory needed. |
| ≠0 | YES | NO  | D — Sentinels propagate but Generated.xcconfig still not loading. Inspect the `#include` chain. |
| ≠0 | NO  | NO  | E — pbxproj edit didn't take effect at build time. Inspect `a27_after_fix.txt`. |

---

## Step 5 — Verify cleanup, then return

The script's final visible output is the cleanup verification (written by the trap). Confirm three PASS lines:

```
xcode_backend.sh:    PASS -- printenv line removed
Release.xcconfig:    PASS -- sentinel removed
Debug.xcconfig:      PASS -- sentinel removed
```

The note below those three lines reminds that `project.pbxproj` is intentionally NOT reverted (it holds the actual fix) and points at the timestamped backup.

If any FAIL appears, do NOT continue any other build work — re-run the script (it is idempotent for sentinels + printenv hook), or contact Claude before any further build attempts. A FAIL means the sentinel/printenv line is still in place and would contaminate any subsequent build.

Then eject the USB:
```
diskutil eject "/Volumes/USB DISK"
```

---

## Step 6 — Report to Claude

Switch back to Windows and report the headline:

> "Assignment 27 complete. Build exit code: [N]. RELEASE/DEBUG sentinel: [YES/NO/YES/NO]. FLUTTER_BUILD_DIR_PRESENT: [YES/NO]. Cleanup [PASS/FAIL per file]."

Plus any notable observations from the terminal output, especially the Python script's printed lines (it reports the file-ref IDs it discovered, the substitution counts, and any WARN if the discovered IDs differ from the A25-recorded values).

---

## Result files (all timestamped) on USB

```
full_a27_session_<ts>.txt              (full terminal recording -- the master log)
a27_sentinel_results_<ts>.txt          (THE HEADLINE: build exit + 3 propagation flags + interpretation)
flutter_build_phase_env_a27_<ts>.log   (printenv from inside xcode_backend.sh)
flutter_build_27_<ts>.log              (flutter build output)
a27_before_fix_<ts>.txt                (baseConfigurationReference + Runner config blocks BEFORE)
a27_after_fix_<ts>.txt                 (same, AFTER the Python edit)
a27_xcconfig_dumps_<ts>.txt            (Release + Debug post-A27-sentinel-insertion)
a27_podfile_lock_<ts>.txt              (Podfile.lock snapshot)
a27_build_artifacts_<ts>.txt           (Runner.app + Frameworks/CwlCatchException presence)
a27_cleanup_verification_<ts>.txt      (per-file PASS/FAIL from the cleanup trap)
project_pbxproj_backup_a27_<ts>.txt    (pre-A27 backup of project.pbxproj)
```

Local backup copies in `~/Desktop/a27_results/`.

Mac Mini also has the live backup at `~/Development/AudioTours/development/audio_tour_app/ios/Runner.xcodeproj/project.pbxproj.backup_a27_<ts>`.

---

## Rollback instructions

If the build fails AND the post-fix verification PASSED (i.e. the edit applied correctly but the build still breaks), the pbxproj edit is in place — do not touch it. Bring back the result files for analysis; A28 will be designed from the evidence.

If you want to manually revert the pbxproj edit:

```
cp ~/Development/AudioTours/development/audio_tour_app/ios/Runner.xcodeproj/project.pbxproj.backup_a27_<timestamp> \
   ~/Development/AudioTours/development/audio_tour_app/ios/Runner.xcodeproj/project.pbxproj
```

Sir Michael deletes the backup himself per the project's Rule 4 (no deletes from `D:\` or the Mac Mini Flutter project by Claude / Amazon-Q).

---

## Safety notes

- **Two-phase modification.** The pbxproj edit is the durable change. Sentinels + printenv hook are temporary and reverted by the cleanup trap.
- **HALT-on-failure throughout.** Both the Python edit and the post-edit shell verification `exit 1` on any anomaly, restoring from backup before returning. (V1 lesson from A26: verification must halt, not just print.)
- **Anchored on specific UUIDs.** The Python regex requires the exact Runner config UUID at the start of the matched block, so RunnerTests blocks (different UUIDs) are mathematically untouched. `re.subn(...)` returns a count we `assert == 1` on, so any drift produces a FATAL — not a silent OK.
- **Idempotent for sentinels + printenv.** Running the script a second time skips lines that are already present rather than duplicating. The pbxproj edit is also effectively idempotent — the regex won't match twice because the second run finds the new (Flutter) ref instead of the old (Pods) ref.
- **No `flutter clean` or `flutter pub get`.** Either would regenerate `Generated.xcconfig` (fine) but also potentially run `pod install` side effects. We avoid them.
- **No Podfile / `pod install` changes.** This assignment is purely a `project.pbxproj` edit + diagnostics.
- **No source code edits.** Only the four files listed above are modified; only `project.pbxproj` is left modified at end.

---

## Bash bug-fixes from A24/A25/A26 review baked in upfront

- **B1:** `exec > >(tee ...) 2>&1` for output capture (no `script` from inside script body)
- **B2:** USB `cp` uses real double quotes around the path (it contains a space), visible per-file errors
- **B3:** single-quoted grep patterns
- **B4:** awk for line insertion (BSD sed lacks inline `2i\<text>` on macOS)
- **B5:** `"$HOME/..."` not `"~/..."` inside double quotes
- **B6:** `${PIPESTATUS[0]}` for flutter build's exit code after the `tee` pipe
- **B7 (NEW from A26):** no multiline shell variable into sed — use Python with `re.search` (first match only) and `re.subn(...)` with `assert n == 1`
- **V1 (NEW from A26):** verification HALTS (`exit 1`) on failure, not just prints — followed by `cp backup pbxproj` to restore
- **V2 (NEW from A26):** Claude reviewed this script before USB transfer — A26 was Amazon-Q-drafted and unreviewed; both bugs would have been caught in a 60-second review. A27 is drafted directly by Claude to keep this discipline.
- **M1:** system-date drift check (Amazon-Q tagged A20 as 01/31/2025 while we were in April 2026)
- **M3:** `cd` only for the flutter build (the one acceptable absolute-path exception)
- **M5:** local backup directory fallback in case USB copy fails

---

## Next step (preview, not part of A27)

**If A27 lands case A (build=0, sentinels=YES, FLUTTER_BUILD_DIR=YES):** Claude drafts Assignment 28 — sign + install on iPhone 16 (UDID `00008140-000558A902BA801C`) using signing identity `594584F3D3BC571D94A822A2158871CA13898701`. The acceptance test is: app launches without `Library not loaded: @rpath/CwlCatchException.framework/CwlCatchException`.

**If A27 lands case C/D/E:** Claude reads the evidence files and designs the next targeted diagnostic. Cases C and D both indicate the pbxproj fix took effect at the file level but something else is still wrong; case E indicates the file-level edit did not propagate to the build env (would require deeper investigation — possibly Xcode caching or a derived-data flush).

---

**Last Updated:** 2026-04-29 ~15:30 by Claude (session "Audioura Build and Start #4")
**Priority:** CRITICAL — re-attempt of the iOS build barrier fix
**Expected Outcome:** Build exit 0 + FLUTTER_BUILD_DIR present in env + both sentinels propagated → green light for A28
