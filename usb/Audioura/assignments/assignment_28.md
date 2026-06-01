# Assignment 28 (Path A) — Build with codesign + Install + Launch + Evidence

**Goal:** With Branch B confirmed fixed in A27 (build exit 0, `FLUTTER_BUILD_DIR=build`, Runner.app produced), now produce a properly *signed* Runner.app via Xcode's automatic-signing pipeline, install on iPhone 16, launch, and capture evidence about whether the app stays running or crashes with the historical CwlCatchException dyld error.

**Script to run:** `build_install_launch_a28.sh`

**Scope:** **BUILD-WITH-CODESIGN + INSTALL + LAUNCH + EVIDENCE.** Single composite operation that the iOS toolchain has been doing reliably for years — we delegate signing/profile/entitlements to `flutter build ios --release` (the exact path that worked for A18's drag-and-drop install) instead of trying to imitate it manually.

**Time:** ~7–12 minutes (build with sign + install + 25s monitoring + crash scrape).

**Drafted by:** Claude (session "Audioura Build and Start #4"), 2026-04-29. Drafted directly per Sir Michael's preference — no Amazon-Q intermediary — and self-reviewed before USB transfer (lesson V2).

---

## ⚠️ Supersedes — please use this, not the inline A28

`D:\Audioura\assignments\mac_mini_assignments.md` (lines 701–850) and `D:\Audioura\scripts\sign_install_a28.sh` are an **earlier Amazon-Q draft of A28** that this assignment **REPLACES**. The earlier draft has four critical issues — discussed in the project log under "Why this approach (vs Amazon-Q's A28)" below. **Do not run `sign_install_a28.sh`.** Run `build_install_launch_a28.sh` only.

Sir Michael deletes Mac/USB files himself per Rule 4; both files have been intentionally left in place as history.

---

## Background

A27 hit Case A: build exit 0, `FLUTTER_BUILD_DIR_PRESENT_A27=YES` (value `build`), `RELEASE_SENTINEL_PROPAGATED_A27=YES`. The Branch B fix is fully validated. `Runner.app` was produced at `~/Development/AudioTours/development/audio_tour_app/build/ios/iphoneos/Runner.app` with `Frameworks/CwlCatchException.framework` correctly embedded. RunnerTests `baseConfigurationReference` was correctly untouched.

But A27 used `flutter build ios --release --no-codesign`, which means the resulting `Runner.app`:

- has **no** `embedded.mobileprovision`
- has **no** compiled `Runner.app.xcent` (the runtime entitlements blob with `application-identifier`, `team-identifier`, `get-task-allow=true`, `keychain-access-groups`)
- is **not signed** by any team identity

That's exactly right for verifying the build pipeline is healthy, but wrong for installing on a real device. iOS install requires three things together (the project log captures this as the "iOS Installation 3-step sequence"):

1. **Code signature** — every framework + the main binary signed by an Apple Development identity for team `4HGRU6TKGQ`.
2. **Provisioning profile** embedded as `Runner.app/embedded.mobileprovision`, listing the device UDID.
3. **Entitlements** compiled into a `.xcent` blob with `application-identifier = 4HGRU6TKGQ.com.glikfamily.audioura`.

A28 produces all three by re-running the build *without* `--no-codesign`. Xcode's automatic-signing pipeline handles all three steps in one shot — the exact pipeline that worked for A18's drag-and-drop install — so we don't have to reimplement provisioning-profile lookup and entitlement-blob generation manually in bash.

---

## Why this approach (vs Amazon-Q's A28)

Amazon-Q's `sign_install_a28.sh` tried to take the existing `--no-codesign` Runner.app and *re-sign* it manually. That approach has four bugs that would have blocked install:

1. It never embeds `Runner.app/embedded.mobileprovision`. `xcrun devicectl device install app` fails with `0xe8008015`.
2. `--entitlements $PROJECT_DIR/ios/Runner/Runner.entitlements` points at the human-authored input file, not the compiled `.xcent` blob with `application-identifier`. Install fails with under-specified entitlements.
3. If install fails, the script continues to `process launch` an app that isn't on the device. Same V1 anti-pattern that A26 had ("verification must HALT, not just print").
4. The "launch test" is `xcrun devicectl device process launch` — exit 0 means the launch *command* dispatched, not that the app stayed running. The CwlCatchException crash happens ~0.5s after launch (dyld load time). Amazon-Q's script captures zero evidence of this — it relies entirely on Sir Michael eyeballing the iPhone screen.

A28 (Path A) avoids all four:

1. Build with codesign → Xcode embeds the profile.
2. Build with codesign → Xcode generates the proper `.xcent`.
3. HALTs (exit 1) on every failure: build, codesign verify, install, with no fall-through.
4. Captures process list at +5s and +15s post-launch and scrapes `~/Library/Logs/CrashReporter/MobileDevice/` for any *new* crash report appearing after launch (with a baseline taken pre-launch). The dyld error string `Library not loaded ... CwlCatchException` is grep'd in both the launch log and any new crash file.

---

## Environmental prerequisites (NEW for A28)

These are the only things the script can't fully validate up front. Confirm before running:

- [ ] **Xcode automatic signing is set up** — at some point (likely before A18) Xcode UI was opened with the Audioura project, signed in to the Apple ID for team `4HGRU6TKGQ`, and let auto-resolve a Development profile. A18's successful drag-and-drop install confirms this was true ~3 days ago. If an Apple ID password expiry, certificate expiry, or new device addition has happened since, automatic signing may need a one-time refresh in Xcode UI.
- [ ] **Developer Mode is ON** on iPhone 16. Settings → Privacy & Security → Developer Mode. iOS 16+ requires this for any devicectl-launched app. If off, install may succeed but launch fails.
- [ ] **iPhone 16 is trust-paired with this Mac** — the "Trust This Computer" dialog has been accepted for this Mac at some point, and the iPhone is unlocked when running the script.
- [ ] **An Apple Development codesigning identity for team `4HGRU6TKGQ` is in the Mac's keychain.** The script runs `security find-identity -v -p codesigning` in pre-flight and prints the result; if no `Apple Development` line for the team appears, the build is likely to fail with "No matching profiles".

The script tolerates the device-connectivity probe failing (warns + continues, since `devicectl list devices` can flake without affecting later commands), but a missing signing identity will surface as a build failure with a clear `flutter build` error message — not silent.

---

## Standard prerequisites

- [ ] `D:\Audioura\scripts\build_install_launch_a28.sh` exists (Windows side, copied to USB)
- [ ] USB stick plugged into Mac Mini, mounted as `/Volumes/USB DISK/`
- [ ] iPhone 16 (UDID `00008140-000558A902BA801C`) plugged in and unlocked
- [ ] A27 completed successfully — `project.pbxproj` shows Runner Debug + Release wired to `Flutter/{Debug,Release}.xcconfig`. The script verifies this in Step 0; HALTs if A27 has been reverted.
- [ ] No background `xcodebuild` or Xcode UI build in progress

---

## Step 1 — Switch KVM to Mac Mini

Standard switch.

---

## Step 2 — Navigate and prepare

```
cd "/Volumes/USB DISK/Audioura/scripts"
chmod +x build_install_launch_a28.sh
```

---

## Step 3 — Run the script

```
./build_install_launch_a28.sh
```

**Do NOT wrap with `script ~/Desktop/...`.** The script handles its own output capture via `exec > >(tee ~/Desktop/full_a28_session.txt) 2>&1` (B1).

**What the script does (in order):**

1. **STEP 0 — Pre-flight checks.** Validates project dir + pbxproj exist. Confirms A27's `baseConfigurationReference` fix is still in place for both Debug and Release (HALTs if reverted). Lists codesigning identities (warn-only). Lists devicectl devices (warn-only). Snapshots existing crash report files in `~/Library/Logs/CrashReporter/MobileDevice/` so we can detect any NEW crashes from this run.
2. **STEP 1 — `flutter build ios --release` (WITH codesign).** No `--no-codesign` flag this time. Xcode's automatic-signing pipeline embeds the provisioning profile, generates the `.xcent`, and signs every framework + the main bundle. Build exit captured via `${PIPESTATUS[0]}`. HALTs on non-zero exit and prints common-cause hints (no matching profile, bundle ID mismatch, signing required, etc.).
3. **STEP 2 — Verify the signed Runner.app.** Confirms `embedded.mobileprovision` is present (HALTs if missing — that would mean the build was somehow still `--no-codesign`). Dumps `embedded.mobileprovision` metadata (TeamIdentifier, AppIDName, ExpirationDate, Name), main-bundle codesign info, codesign verify, framework codesign info, compiled entitlements. HALTs if `codesign --verify --verbose=2` fails.
4. **STEP 3 — `xcrun devicectl device install app`.** Streams output to a tee'd log; captures exit via `${PIPESTATUS[0]}`. HALTs on non-zero exit and prints common-cause hints (`0xe8008015`, `0xe800801c`, Developer Mode disabled, device locked, trust not established).
5. **STEP 4 — Launch + monitor.** Captures pre-launch process list (both `process list` and `info processes` devicectl variants for syntax tolerance across Xcode versions). Launches the app via `xcrun devicectl device process launch`. Waits 5 seconds, captures process list, greps for `audioura` / bundle ID — counts as `RUNNING_5S`. Waits 10 more seconds (total 15s), captures again, greps — counts as `RUNNING_15S`. The 15s window is generous: the historical CwlCatchException crash happens within ~0.5s of launch, so absence at +15s strongly indicates the crash recurred.
6. **STEP 5 — Crash report scrape.** Waits 10 more seconds for any device-side crash report to sync to the Mac. Diffs the post-launch `~/Library/Logs/CrashReporter/MobileDevice/` listing against the pre-launch baseline; captures the names of any NEW files; prints the first 80 lines of each. Grep's both the launch log and any new crash file for the literal string `Library not loaded ... CwlCatchException`.
7. **STEP 6 — Final verdict.** Combines the +15s process-presence count with the new-crash-file count into one of four buckets (table below); writes `~/Desktop/a28_final_verdict.txt`.
8. **STEP 7 — Copy results to USB + local backup** (B2 + M5 — real double quotes around USB path, visible per-file errors, parallel local backup).

**Run time:** ~7–12 minutes total (build is the long part; monitoring is exactly 25s post-launch).

---

## Step 4 — Headline result to watch for

The script prints a final on-screen verdict block. The verdict is one of four values, derived from two counts:

| Process at +15s | New crash files | Verdict | Reading |
|---|---|---|---|
| ≥ 1 | 0 | **SUCCESS** | App launched, still running, no new crash. iOS barrier eliminated. |
| 0   | ≥ 1 | **CRASHED** | App not running AND a fresh crash report exists. Look at the printed crash file head — if it says `Library not loaded ... CwlCatchException`, the framework is present in the bundle but rpath-unresolvable for the main binary (would need a separate rpath / Embed-and-Sign-mode investigation). |
| 0   | 0 | **AMBIGUOUS** | Most likely the devicectl process-list output didn't include `audioura` / bundle ID in a form our grep matched (exec name might be `Runner`). Check the iPhone screen — if Audioura is visibly running, the verdict is effectively SUCCESS. |
| ≥ 1 | ≥ 1 | **MIXED** | Process is in list AND a crash file appeared. Most likely an OLD crash file synced just now. Cross-reference the crash file's timestamp + bundle ID with the launch epoch. |

Always glance at the iPhone screen as a sanity backstop, especially for AMBIGUOUS / MIXED.

---

## Step 5 — No cleanup verification this time

Unlike A25/A27, **A28 makes no temporary modifications** that need reverting. There's no cleanup trap, no sentinels, no printenv hook. The build's signed `Runner.app` and the installed app on the iPhone are intentional, durable outputs. If the install succeeds and the app crashes, the failed install is recoverable: hold-press the Audioura icon on the iPhone home screen and tap "Remove App", or run `xcrun devicectl device uninstall app --device 00008140-000558A902BA801C com.glikfamily.audioura`.

---

## Step 6 — Eject USB and return

```
diskutil eject "/Volumes/USB DISK"
```

---

## Step 7 — Report to Claude

Switch back to Windows. Open a new Cowork session with this name:

> "Audioura Build and Start #5"

…and report the verdict + the four counts:

> "Assignment 28 complete. VERDICT: [SUCCESS / CRASHED / AMBIGUOUS / MIXED]. Build exit: [N]. Install exit: [N]. Process matches at +5s/+15s: [N]/[N]. New crash files: [N]. iPhone screen: [Audioura visible and responsive / black / springboard / crashed]."

Plus any notable observations from the terminal output, especially any line of the form `Library not loaded ... CwlCatchException` or any unfamiliar dyld error.

---

## Result files (all timestamped) on USB

```
full_a28_session_<ts>.txt              (full terminal recording -- the master log)
a28_final_verdict_<ts>.txt             (THE HEADLINE: build/install/launch exit + 2 counts + verdict)
a28_signed_app_verification_<ts>.txt   (embedded.mobileprovision metadata + codesign output + entitlements)
flutter_build_a28_<ts>.log             (flutter build with codesign output)
a28_install_<ts>.log                   (devicectl install output)
a28_launch_<ts>.log                    (devicectl process launch output)
a28_proclist_before_<ts>.txt           (pre-launch device process list)
a28_proclist_5s_<ts>.txt               (process list +5s after launch)
a28_proclist_15s_<ts>.txt              (process list +15s after launch)
a28_new_crashes_list_<ts>.txt          (paths of any NEW crash report files since launch baseline)
a28_crash_<ts>_<basename>              (any new crash report file copied verbatim, if present)
```

Local backup copies in `~/Desktop/a28_results/`.

---

## Rollback / cleanup

If the build/install/launch fails, the install state on the iPhone is the only thing that needs cleanup. You can either:

- **Leave it.** A failed install just leaves no Audioura icon on the iPhone — nothing to undo.
- **Remove a partially-installed app.** Hold-press the Audioura icon on the iPhone home screen → "Remove App". Or:
  ```
  xcrun devicectl device uninstall app --device 00008140-000558A902BA801C com.glikfamily.audioura
  ```

`project.pbxproj` is NOT touched by A28 — A27's edit remains in place regardless of A28's outcome. The pre-A27 backup at `project.pbxproj.backup_a27_20260429_160121` on the Mac Mini is also untouched.

If the build fails because Xcode automatic signing has expired/desynced, the recovery is: open the project in Xcode UI (`open ~/Development/AudioTours/development/audio_tour_app/ios/Runner.xcworkspace`), let the Signing & Capabilities tab auto-fix, then re-run this script.

---

## Safety notes

- **No file modifications.** Unlike A25 and A27, A28 modifies no source files, no Flutter SDK files, no xcconfigs. The only things changing are (a) the build artifact (`build/ios/iphoneos/Runner.app` is regenerated with codesign instead of `--no-codesign`), and (b) the iPhone's installed-apps list.
- **HALT-on-failure throughout.** Every step that can fail (build, codesign-verify, install) is followed immediately by an `if [ "$EXIT" -ne 0 ]; then ... exit 1; fi` block that copies results to USB before exiting. (V1 lesson — verification must halt, not just print.)
- **Signing is delegated to Xcode.** A28 makes zero direct `codesign --sign` calls. This is intentional: getting framework-by-framework codesign right (especially for nested signed content, dylib siblings, entitlements blob synthesis) is exactly the failure mode that broke Amazon-Q's draft. Letting `flutter build` invoke `xcodebuild` lets Apple's pipeline do its job.
- **Best-effort process-list parsing.** The script captures both `xcrun devicectl device process list` AND `xcrun devicectl device info processes` outputs; greps both. If the output format changes in a future Xcode update such that our grep misses, the verdict is AMBIGUOUS — recoverable by checking the iPhone screen.

---

## Bash bug-fixes from A24/A25/A26 review baked in upfront

- **B1:** `exec > >(tee ...) 2>&1` for output capture (no `script` from inside script body)
- **B2:** USB `cp` uses real double quotes around the path (it contains a space), visible per-file errors
- **B3:** single-quoted grep patterns for literal text
- **B4:** N/A (no line insertion in this script)
- **B5:** `"$HOME/..."` not `"~/..."` inside double quotes
- **B6:** `${PIPESTATUS[0]}` for flutter build / install / launch exit codes after the `tee` pipe
- **B7:** N/A (no sed-with-shell-variable in this script)
- **V1:** verification HALTS (`exit 1`) on every failure, with USB+local backup copy before exiting
- **V2:** Claude reviewed this script before USB transfer
- **M1:** system-date drift check
- **M3:** `cd` only for the flutter build (the one acceptable absolute-path exception)
- **M5:** local backup directory fallback

---

## Next step (preview, not part of A28)

**If A28 lands SUCCESS:** the iOS development barrier is fully eliminated. The next milestone is feature parity verification — testing core Audioura functionality on iPhone (tour loading, GPS triggering, audio playback, voice activation, network connectivity to the local backend at `192.168.0.136:5002/5004`). That's a manual checklist + maybe an A29 to capture the first sample tour run.

**If A28 lands CRASHED with `Library not loaded ... CwlCatchException`:** this would mean the framework is *embedded* in `Frameworks/` (A27 evidence confirmed it is) but is not *rpath-resolvable* by the main `Runner` binary at load time. That's a different bug from Branch B — likely a `LD_RUNPATH_SEARCH_PATHS` or "Embed & Sign" vs "Embed Without Signing" issue in the Runner target's framework search paths or General > Frameworks list. A29 would diagnose with `otool -L Runner.app/Runner` and the embedded-frameworks build phase inspection.

**If A28 lands CRASHED with a different error:** capture the crash file head and we'll diagnose case-by-case.

**If A28 lands AMBIGUOUS:** if the iPhone screen shows Audioura running, treat as SUCCESS. If it doesn't, A29 would narrow the gap — likely by adding `idevicesyslog` capture (if the Mac has libimobiledevice installed) for richer console capture during launch.

---

**Last Updated:** 2026-04-29 ~16:45 by Claude (session "Audioura Build and Start #4")
**Priority:** CRITICAL — the actual acceptance test for the iOS build pipeline
**Expected Outcome:** SUCCESS verdict — Audioura launches on iPhone 16 and stays running with no CwlCatchException crash
