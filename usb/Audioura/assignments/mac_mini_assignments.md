# Mac Mini Assignment Instructions
## iOS Development Task Execution

# T: 06/2026 - A#81 — Build v2.1.1+7 on iPhone (Consolidated — first build since v1.2.9+71)

**Goal:** Build v2.1.1+7 on iPhone. This is a **consolidated parity build** — iPhone has never been built past v1.2.9+71. This single assignment brings the iPhone all the way to v2.1.1+7, which includes all changes from v2.1.1+3, +6, and +7.

**What this build delivers over v1.2.9+71:**

- Dual-environment networking: Local WiFi (default) and Cloud (HTTPS)
- `Endpoints` resolver — all service calls route through a single resolver per active mode
- `Endpoints.apiHeaders()` sends `X-API-Key` in cloud mode (reads `gateway_api_key` from SharedPreferences)
- `tour_status_service.dart` — REST via `Endpoints(Service.orchestrator)` + `apiHeaders()`, keyed on `tour_xxx` tour_id
- `TranslationService` — migrated to `Endpoints.url(Service.translation)` + `apiHeaders()` — cloud multi-language works
- About screen: Local/Cloud toggle + cloud URL field + API Key field (temporary) + gateway path routing checkbox (leave unchecked)
- Inter-service auth tokens on all service edges, OpenAI + AWS secret key fixes
- Dead files removed: `test_update_api.dart` + raw-SQL files
- `NSLocalNetworkUsageDescription` in `Info.plist` (already in repo at `52d8282`)
- `Timer.periodic` replaced with `Future.delayed` self-scheduling poll loop in `_pollAndAutoDownload` — no stuck timers
- `_pollTimer` State field removed entirely
- `translation_failed` orange snackbar added (reads server response field)
- `if (_isGenerating) return;` re-entry guard at top of `_generateTour` and `_generateTourBackground`
- Removed vestigial `_pollTimer?.cancel()` (compile error guard)
- `pollLoop()` wrapped with `unawaited(...).catchError(...)` — resets `_isGenerating` on crash, spinner can't stick

**Target commit:** `e7c3ade`  **Version:** `2.1.1+7`  **Branch:** `services-migration`

**Roles:**
- **[SIR MICHAEL]** — orchestrator. Switches KVM, runs smoke test, syncs Windows afterward.
- **[MAC MINI Q]** — pulls latest, verifies signing, runs `pod install`, builds, installs. No pubspec bump (already at `2.1.1+7`).

---

## Step 0 — [SIR MICHAEL] Eject USB, carry to Mac Mini, switch KVM

## Step 1 — [SIR MICHAEL on Mac Mini] Launch Q

Paste:
> Read `@/Volumes/USB DISK/Audioura/assignments/mac_mini_assignments.md` and execute the A#81 assignment at the top. Follow STOP conditions; skip steps labelled `[SIR MICHAEL]`.

## Step 2 — [MAC MINI Q] Pull latest

```bash
cd ~/Development/Audioura-build
git pull origin services-migration
```

**Expected:** fast-forward to commit `e7c3ade` or later.

If pull fails with "local changes would be overwritten" — STOP and report. Do not `git reset --hard`.

## Step 3 — [MAC MINI Q] Spot-check BEFORE building ⚠️ REQUIRED

```bash
cd ~/Development/Audioura-build/development/audio_tour_app

# 3a — pubspec at 2.1.1+7
grep "^version:" pubspec.yaml
# Expected: version: 2.1.1+7

# 3b — NSLocalNetworkUsageDescription present in Info.plist
grep -n "NSLocalNetworkUsageDescription" ios/Runner/Info.plist
# Expected: 1 match

# 3c — Endpoints.apiHeaders sends X-API-Key in cloud mode
grep -n "X-API-Key\|apiHeaders\|gateway_api_key" lib/config/endpoints.dart
# Expected: matches for all three

# 3d — TranslationService uses Endpoints (not hardcoded IP)
grep -n "Endpoints\|Service.translation" lib/services/translation_service.dart
# Expected: at least 2 matches

# 3e — _isGenerating re-entry guard present in tour_generator_screen.dart
grep -n "_isGenerating" lib/screens/tour_generator_screen.dart
# Expected: multiple matches including "if (_isGenerating) return;"

# 3f — _pollTimer field is GONE (removed in v2.1.1+6)
grep -n "_pollTimer" lib/screens/tour_generator_screen.dart
# Expected: zero matches

# 3g — signing intact
grep -E 'PRODUCT_BUNDLE_IDENTIFIER|DEVELOPMENT_TEAM' \
  ios/Runner.xcodeproj/project.pbxproj | sort -u
# Expected: com.glikfamily.audioura and 4HGRU6TKGQ
```

If 3a fails (not `2.1.1+7`), STOP and report — wrong commit.
If 3f shows any `_pollTimer` match, STOP — stale code, will fail to compile.
If 3g shows wrong bundle ID or missing team, fix signing before building (see Step 5 signing fix).

## Step 4 — [MAC MINI Q] pod install

```bash
cd ~/Development/Audioura-build/development/audio_tour_app/ios
pod install
```

No new pods expected. Required after any pull.

## Step 5 — [MAC MINI Q] Clean rebuild, install, launch

```bash
cd ~/Development/Audioura-build/development/audio_tour_app
flutter clean && flutter pub get
cd "/Volumes/USB DISK/Audioura/scripts"
./build_install_launch.sh
```

**Expected:** `FINAL VERDICT: SUCCESS`. STOP and tell Sir Michael.

If build FAILS with signing error — open Xcode:
```bash
open ~/Development/Audioura-build/development/audio_tour_app/ios/Runner.xcworkspace
```
Runner → Signing & Capabilities → Automatically manage signing ✅ → Team: Mikhail Glik (4HGRU6TKGQ) → Bundle ID: `com.glikfamily.audioura` → Quit Xcode → re-run Step 5.

If build FAILS with compile error mentioning `_pollTimer` — STOP immediately and report to iOS Q. Do not attempt to fix.

## Step 6 — [SIR MICHAEL] Smoke test on iPhone ⚠️ STOP HERE FOR Q

**Test 1 — Local mode default (on WiFi):**
1. Launch app → Home tab.
2. **Expected:** Tours load from `192.168.0.218`. No errors.
3. About tab → mode shows **Local** by default.

**Test 2 — Local WiFi tour generation (poll loop fix):**
1. On WiFi → generate a new English tour.
2. **Expected:** Spinner runs, status updates polling. Tour opens automatically when ready. No stuck spinner.
3. Leave the screen mid-poll (switch tabs) — return — **Expected:** no crash.
4. Try tapping Generate a second time immediately after first tap — **Expected:** only one generation starts (re-entry guard).

**Test 3 — About screen Cloud setup:**
1. About tab → Local/Cloud toggle visible.
2. Switch to **Cloud** → URL field + API Key field appear.
3. Enter cloud base URL and API Key.
4. Leave gateway path routing checkbox **unchecked**.

**Test 4 — Cloud mode tour generation:**
1. In Cloud mode → generate or download a tour.
2. **Expected:** Tour downloads/generates and plays.

**Test 5 — Cloud multi-language (if available):**
1. In Cloud mode, generate a tour and request a translation.
2. **Expected:** Translation completes. Mark NOT_TESTED if not exercised — not a blocker.

**Test 6 — A#78 regression (mic):**
1. Audio mode → Listen tab → tap microphone icon.
2. **Expected:** Listening dialog opens. No "Microphone permission required" snackbar.

**Test 7 — A#77b regression (Refresh):**
1. Listen tab → tap Refresh.
2. **Expected:** List reloads in place, no black screen.

**Test 8 — General regression:**
1. Open a tour → audio plays.
2. Open a news article → loads.
3. POI map icon → TourMapScreen opens.

Tell Q "Smoke test passes, proceed to Step 7" when done. Report each test result.

## Step 7 — [MAC MINI Q] Verify git state — no pubspec commit needed

```bash
cd ~/Development/Audioura-build
git status
# Expected: nothing to commit (or only untracked files)
git log --oneline -3
# Confirm e7c3ade or later is HEAD
```

If `git status` shows modified tracked files — STOP and report before committing anything.

## Step 8 — [MAC MINI Q] Copy results and eject

```bash
echo "A#81 Results:" > ~/Desktop/a81_results.txt
echo "Date: $(date)" >> ~/Desktop/a81_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a81_results.txt
echo "Local mode tours load (Test 1): [YES/NO]" >> ~/Desktop/a81_results.txt
echo "Local WiFi tour generation + no stuck spinner (Test 2): [YES/NO]" >> ~/Desktop/a81_results.txt
echo "Re-entry guard works — double tap single generation (Test 2): [YES/NO]" >> ~/Desktop/a81_results.txt
echo "About Cloud UI present (Test 3): [YES/NO]" >> ~/Desktop/a81_results.txt
echo "Cloud mode tour download/generate (Test 4): [YES/NO/NOT_TESTED]" >> ~/Desktop/a81_results.txt
echo "Cloud multi-language (Test 5): [YES/NO/NOT_TESTED]" >> ~/Desktop/a81_results.txt
echo "Mic no permission snackbar (Test 6): [YES/NO]" >> ~/Desktop/a81_results.txt
echo "Listen Refresh no black screen (Test 7): [YES/NO]" >> ~/Desktop/a81_results.txt
echo "General regression clean (Test 8): [YES/NO]" >> ~/Desktop/a81_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a81_results.txt
cp ~/Desktop/a81_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 9 — [MAC MINI Q] Report Results

> "Assignment 81 complete. Build: [SUCCESS/FAILED]. Local tours load: [YES/NO]. Local generation no stuck spinner: [YES/NO]. Re-entry guard: [YES/NO]. Cloud UI present: [YES/NO]. Cloud generation: [YES/NO/NOT_TESTED]. Cloud translation: [YES/NO/NOT_TESTED]. Mic regression: [YES/NO]. Refresh regression: [YES/NO]. General regression: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

## Step 10 — [SIR MICHAEL, back on Windows] Sync

```cmd
cd C:\Users\micha\eclipse-workspace\AudioTours\development
git pull origin services-migration
```
Verify `audio_tour_app\pubspec.yaml` shows `version: 2.1.1+7`.

---

# T: 06/2026 - A#78 — Build v1.2.9+71 (Listen Page Microphone Voice Search Fix)
**Status**: ✅ COMPLETE — built, smoke tested. 2026-06-02.

---

# T: 06/2026 - A#77b — Build v1.2.9+70 (Listen Page Refresh Black Screen — Real Fix)
**Status**: ✅ COMPLETE — built, smoke tested. 2026-06-01.

---

# T: 06/2026 - A#76 — Build v1.2.9+68 (POI Map Button Fix — openMap handler + map icon restore)
**Status**: ✅ COMPLETE — built, smoke tested, committed + pushed. 2026-06-01.

---

# T: 05/26/2026 - A#75 — Build v1.2.9+65 (InAppWebView v6 migration in news_player_screen.dart)
**Status**: ✅ COMPLETE — built, smoke tested, committed + pushed. 2026-06-01.

---

# T: 05/26/2026 - A#73 — Build v1.2.9+64 (App Icon Background — #A93105 brick red)
**Status**: ✅ COMPLETE — brick-red icon confirmed on iPhone. 2026-05-26.

---

# T: 05/25/2026 - A#72 — Build v1.2.9+63 (News Article White Screen — Stale Container Paths)
**Status**: ✅ COMPLETE — articles load without white screen. 2026-05-26.
