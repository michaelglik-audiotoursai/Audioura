# Mac Mini Assignment Instructions
## iOS Development Task Execution

# T: 06/2026 - A#77 — Build v1.2.9+69 (Newsletter Refresh Black Screen Fix)

**Goal:** Build v1.2.9+69 on iPhone. The fix is already committed to `services-migration` at `4dba042`. This is a one-line removal — Mac Mini only needs to pull, bump pubspec, build, and smoke test.

**What changed:**

| Version | File | Change |
|---------|------|--------|
| +69 | `home_screen.dart` | Removed `setState(() { _isLoading = true; })` from newsletter Refresh button handler in `_buildNewsletterView` |
| +69 | `pubspec.yaml` | `1.2.9+68` → `1.2.9+69` |

**Root cause of black screen:** Setting `_isLoading = true` triggered the Tours-mode spinner scaffold to render while the app was in Audio/Newsletter mode. No recovery path — only kill + restart. Fix: remove that setState call entirely; the `_newsController.refresh()` call below it handles the reload.

**Roles:**
- **[SIR MICHAEL]** — orchestrator. Switches KVM, runs smoke test, syncs Windows afterward.
- **[MAC MINI Q]** — pulls latest, bumps pubspec, builds, commits.

**Version target:** v1.2.9+69  **Branch:** `services-migration`  **Time:** ~20 minutes

---

## Step 0 — [SIR MICHAEL] Eject USB, carry to Mac Mini, switch KVM

Standard switch.

## Step 1 — [SIR MICHAEL on Mac Mini] Launch Q

```bash
kiro-cli chat --trust-all-tools
```

Paste:

> Read `@/Volumes/USB DISK/Audioura/assignments/mac_mini_assignments.md` and execute the A#77 assignment at the top. Follow STOP conditions; skip steps labelled `[SIR MICHAEL]`.

## Step 2 — [MAC MINI Q] Pull latest

```bash
cd ~/Development/Audioura-build
git pull origin services-migration
```

**Expected:** fast-forward that includes commit `4dba042` (A#77 fix in home_screen.dart).

If pull fails with "local changes would be overwritten," STOP and report. Do not `git reset --hard`.

## Step 3 — [MAC MINI Q] Spot-check BEFORE building ⚠️ REQUIRED

```bash
cd ~/Development/Audioura-build/development/audio_tour_app

# 3a — pubspec still at +68 (not yet bumped)
grep "^version:" pubspec.yaml
# Expected: version: 1.2.9+68

# 3b — confirm the offending setState is GONE from home_screen.dart
grep -n "_isLoading = true" lib/screens/home_screen.dart
# Expected: zero or only lines NOT in _buildNewsletterView refresh handler
# (There should be no line that sets _isLoading=true inside the newsletter Refresh onPressed)

# 3c — confirm _newsController.refresh() is still present
grep -n "_newsController.refresh" lib/screens/home_screen.dart
# Expected: at least 1 match
```

If check 3b shows `_isLoading = true` inside the newsletter refresh handler, STOP and report.

## Step 4 — [MAC MINI Q] Bump pubspec to +69

```bash
cd ~/Development/Audioura-build/development/audio_tour_app
sed -i '' 's/^version: 1.2.9+68/version: 1.2.9+69/' pubspec.yaml
grep "^version:" pubspec.yaml
# Must print: version: 1.2.9+69
```

If grep does not show `+69`, STOP and report.

## Step 5 — [MAC MINI Q] Verify Xcode signing ⚠️ REQUIRED BEFORE BUILD

```bash
grep -E 'PRODUCT_BUNDLE_IDENTIFIER|DEVELOPMENT_TEAM' \
  ios/Runner.xcodeproj/project.pbxproj | sort -u
```

**Expected:** `PRODUCT_BUNDLE_IDENTIFIER = com.glikfamily.audioura;` AND `DEVELOPMENT_TEAM = 4HGRU6TKGQ;`

If either is missing — open Xcode:
```bash
open ios/Runner.xcworkspace
```
Runner target → Signing & Capabilities → "Automatically manage signing" ✅ → Team: **Mikhail Glik (4HGRU6TKGQ)** → Bundle ID: `com.glikfamily.audioura` → Quit Xcode → re-run grep to confirm.

## Step 6 — [MAC MINI Q] Clean rebuild, install, launch

```bash
cd ~/Development/Audioura-build/development/audio_tour_app
flutter clean
flutter pub get
cd "/Volumes/USB DISK/Audioura/scripts"
./build_install_launch.sh
```

**Expected:** `FINAL VERDICT: SUCCESS`, app running on iPhone. Then STOP and tell Sir Michael.

If build FAILS: copy `~/Desktop/full_a28_session.txt` and `~/Desktop/a28_flutter_build.log` to `/Volumes/USB DISK/Audioura/results/`, then STOP and report.

## Step 7 — [SIR MICHAEL] Smoke test on iPhone (STOP HERE FOR Q)

**Test 1 — Newsletter Refresh (primary fix):**
1. Tap the **Audio/Newsletter tab** (not Tours mode).
2. Tap **Refresh** in the newsletter view.
3. **Expected:** Newsletter list reloads cleanly. No black screen. No spinner takeover.
4. Tap Refresh a second time to confirm it's repeatable.
5. Black screen or no response = fix did not land. STOP.

**Test 2 — Tours mode not broken:**
1. Switch to **Tours mode** (Listen tab).
2. Navigate normally — tour list loads.
3. No regression in spinner or loading behavior.

**Test 3 — Regression:**
1. Open a tour → confirm it still plays audio normally.
2. News tab → tap an article → confirm it loads (no white screen).
3. POI map icon → confirm TourMapScreen still opens.

Tell Q "Smoke test passes, proceed to Step 8" if all three pass.

## Step 8 — [MAC MINI Q] Commit and push (only after Sir Michael confirms Step 7 passed)

```bash
cd ~/Development/Audioura-build
git add development/audio_tour_app/pubspec.yaml
git commit -m "v1.2.9+69 — A#77 bump pubspec (fix already in 4dba042)"
git push origin services-migration
```

**Expected:** Push succeeds. If blocked by GitHub secret scanning — STOP and report. Never click "Allow secret".

## Step 9 — [MAC MINI Q] Copy results and eject

```bash
echo "A#77 Results:" > ~/Desktop/a77_results.txt
echo "Date: $(date)" >> ~/Desktop/a77_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a77_results.txt
echo "Newsletter Refresh no black screen: [YES/NO]" >> ~/Desktop/a77_results.txt
echo "Tours mode loads (no regression): [YES/NO]" >> ~/Desktop/a77_results.txt
echo "Tour audio plays (no regression): [YES/NO]" >> ~/Desktop/a77_results.txt
echo "News article loads (no regression): [YES/NO]" >> ~/Desktop/a77_results.txt
echo "POI map opens (no regression): [YES/NO]" >> ~/Desktop/a77_results.txt
echo "git push: [SUCCESS/FAILED]" >> ~/Desktop/a77_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a77_results.txt
cp ~/Desktop/a77_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 10 — [MAC MINI Q] Report Results

> "Assignment 77 complete. Build: [SUCCESS/FAILED]. Newsletter Refresh no black screen: [YES/NO]. Tours regression: [YES/NO]. git push: [SUCCESS/FAILED]. Overall: [SUCCESS/PARTIAL/FAILED]."

## Step 11 — [SIR MICHAEL, back on Windows] Sync

```cmd
cd C:\Users\micha\eclipse-workspace\AudioTours\development
git pull origin services-migration
```

Verify `audio_tour_app\pubspec.yaml` shows `version: 1.2.9+69`.

---

# T: 06/2026 - A#76 — Build v1.2.9+68 (POI Map Button Fix — openMap handler + map icon restore)

**Goal:** Build v1.2.9+68 on iPhone. Three versions of work are bundled here — +66, +67, +68 — none have been built for iPhone yet. The critical fix is in +68: tapping POI map icons during tour playback did nothing because `TourPlayerScreen` never registered the `'openMap'` JavaScript handler. The bridge call from the server HTML was silently dropped every time.

**What changed across +66 → +67 → +68:**

| Version | File | Change |
|---------|------|--------|
| +66 | `my_tours_screen.dart` | Map icon (`Icons.map`) restored on Listen page per-tour |
| +66 | `pubspec.yaml` | `1.2.9+65` → `1.2.9+66` |
| +67 | `tour_map_screen.dart` | `HitTestBehavior.opaque` on marker `GestureDetector` (wrong diagnosis — kept as hardening) |
| +67 | `pubspec.yaml` | `1.2.9+66` → `1.2.9+67` |
| +68 | `tour_player_screen.dart` | Added `import 'tour_map_screen.dart'` + `addJavaScriptHandler('openMap')` in `onWebViewCreated` |
| +68 | `pubspec.yaml` | `1.2.9+67` → `1.2.9+68` |

**Root cause of the silent tap bug:** `flutter_inappwebview` silently drops `callHandler('openMap', ...)` calls if no handler named `'openMap'` is registered on the Dart side. `TourPlayerScreen.onWebViewCreated` never registered it. The server HTML was always correct.

**Roles:**
- **[SIR MICHAEL]** — orchestrator. Switches KVM, runs smoke test, syncs Windows afterward.
- **[MAC MINI Q]** — pulls latest, builds, commits.

**Version target:** v1.2.9+68  **Branch:** `services-migration`  **Time:** ~20 minutes

---

## Step 0 — [SIR MICHAEL] Eject USB, carry to Mac Mini, switch KVM

Standard switch.

## Step 1 — [SIR MICHAEL on Mac Mini] Launch Q

```bash
kiro-cli chat --trust-all-tools
```

Paste:

> Read `@/Volumes/USB DISK/Audioura/assignments/mac_mini_assignments.md` and execute the A#76 assignment at the top. Follow STOP conditions; skip steps labelled `[SIR MICHAEL]`.

## Step 2 — [MAC MINI Q] Pull latest

```bash
cd ~/Development/Audioura-build
git pull origin services-migration
```

**Expected:** fast-forward that brings in commits `0d4d46a` (v1.2.9+67) and `7d012d5` (v1.2.9+68) plus the code review doc `development/code_review_v1.2.9.68.md`.

If pull fails with "local changes would be overwritten," STOP and report. Do not `git reset --hard`.

## Step 3 — [MAC MINI Q] Spot-check BEFORE building ⚠️ REQUIRED

```bash
cd ~/Development/Audioura-build/development/audio_tour_app

# 3a — pubspec at +68
grep "^version:" pubspec.yaml
# Expected: version: 1.2.9+68

# 3b — openMap handler registered in tour_player_screen.dart
grep -n "openMap" lib/screens/tour_player_screen.dart
# Expected: at least 2 matches (addJavaScriptHandler + callback log line)

# 3c — tour_map_screen import present in tour_player_screen.dart
grep -n "tour_map_screen" lib/screens/tour_player_screen.dart
# Expected: 1 match (the import)

# 3d — map icon present in my_tours_screen.dart
grep -n "Icons.map" lib/screens/my_tours_screen.dart
# Expected: at least 1 match
```

If any check fails, STOP and report which one.

## Step 4 — [MAC MINI Q] Verify Xcode signing ⚠️ REQUIRED BEFORE BUILD

```bash
grep -E 'PRODUCT_BUNDLE_IDENTIFIER|DEVELOPMENT_TEAM' \
  ios/Runner.xcodeproj/project.pbxproj | sort -u
```

**Expected:** `PRODUCT_BUNDLE_IDENTIFIER = com.glikfamily.audioura;` AND `DEVELOPMENT_TEAM = 4HGRU6TKGQ;`

If either is missing — open Xcode:
```bash
open ios/Runner.xcworkspace
```
Runner target → Signing & Capabilities → "Automatically manage signing" ✅ → Team: **Mikhail Glik (4HGRU6TKGQ)** → Bundle ID: `com.glikfamily.audioura` → Quit Xcode → re-run grep to confirm.

## Step 5 — [MAC MINI Q] Clean rebuild, install, launch

```bash
cd ~/Development/Audioura-build/development/audio_tour_app
flutter clean
flutter pub get
cd "/Volumes/USB DISK/Audioura/scripts"
./build_install_launch.sh
```

**Expected:** `FINAL VERDICT: SUCCESS`, app running on iPhone. Then STOP and tell Sir Michael.

If build FAILS: copy `~/Desktop/full_a28_session.txt` and `~/Desktop/a28_flutter_build.log` to `/Volumes/USB DISK/Audioura/results/`, then STOP and report.

## Step 6 — [SIR MICHAEL] Smoke test on iPhone (STOP HERE FOR Q)

**Test 1 — POI map button (primary fix):**
1. Listen tab → tap a walking tour that has coordinate data → tour player opens.
2. Tap a POI map icon (🗺️) in the tour HTML.
3. **Expected:** `TourMapScreen` opens, centred on that stop.
4. Open debug log (About tab → Debug Log).
5. **Expected log line:** `MAP: openMap handler fired for stop 1` (or whichever stop was tapped).
6. The absence of this log line = handler still not registered. STOP if missing.

**Test 2 — Map icon on Listen page (+66):**
1. Listen tab → Tours mode.
2. **Expected:** Green map icon (`Icons.map`) visible in trailing row for tours with coordinate data.
3. Tours without coordinates should NOT show the icon.

**Test 3 — Regression:**
1. Open a tour → confirm it still plays audio normally.
2. News tab → tap an article → confirm it loads (no white screen).

Tell Q "Smoke test passes, proceed to Step 7" if all three pass.

## Step 7 — [MAC MINI Q] Commit and push (only after Sir Michael confirms Step 6 passed)

All three versions (+66, +67, +68) are already committed in git. No new commit needed — just verify and push if not already pushed:

```bash
cd ~/Development/Audioura-build
git log --oneline -5
# Confirm 7d012d5 (v1.2.9+68) and 0d4d46a (v1.2.9+67) are present
git push origin services-migration
```

If already pushed (remote is up to date), that's fine — report it.

## Step 8 — [MAC MINI Q] Copy results and eject

```bash
echo "A#76 Results:" > ~/Desktop/a76_results.txt
echo "Date: $(date)" >> ~/Desktop/a76_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a76_results.txt
echo "MAP: openMap handler fired log present: [YES/NO]" >> ~/Desktop/a76_results.txt
echo "TourMapScreen opened on tap: [YES/NO]" >> ~/Desktop/a76_results.txt
echo "Map icon visible on Listen page: [YES/NO]" >> ~/Desktop/a76_results.txt
echo "Tour audio plays (no regression): [YES/NO]" >> ~/Desktop/a76_results.txt
echo "News article loads (no regression): [YES/NO]" >> ~/Desktop/a76_results.txt
echo "git push: [SUCCESS/ALREADY_PUSHED/FAILED]" >> ~/Desktop/a76_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a76_results.txt
cp ~/Desktop/a76_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 9 — [MAC MINI Q] Report Results

> "Assignment 76 complete. Build: [SUCCESS/FAILED]. openMap log present: [YES/NO]. Map opened on tap: [YES/NO]. Map icon on Listen page: [YES/NO]. Tour plays: [YES/NO]. News loads: [YES/NO]. git push: [SUCCESS/ALREADY_PUSHED/FAILED]. Overall: [SUCCESS/PARTIAL/FAILED]."

## Step 10 — [SIR MICHAEL, back on Windows] Sync

```cmd
cd C:\Users\micha\eclipse-workspace\AudioTours\development
git pull origin services-migration
```

Verify `audio_tour_app\pubspec.yaml` shows `version: 1.2.9+68`.

---

# T: 05/26/2026 - A#75 — Build v1.2.9+65 (InAppWebView v6 migration in news_player_screen.dart)
**Status**: ✅ COMPLETE — built, smoke tested, committed + pushed. 2026-06-01.

---

# T: 05/26/2026 - A#73 — Build v1.2.9+64 (App Icon Background — #A93105 brick red)
**Status**: ✅ COMPLETE — brick-red icon confirmed on iPhone. 2026-05-26.

---

# T: 05/25/2026 - A#72 — Build v1.2.9+63 (News Article White Screen — Stale Container Paths)
**Status**: ✅ COMPLETE — articles load without white screen. 2026-05-26.
