# Mac Mini Assignment Instructions
## iOS Development Task Execution

# T: 06/2026 - A#82 — Build v2.1.1+8 on iPhone (Major Feature Release — First build since v1.2.9+71)

**Goal:** Build v2.1.1+8 on iPhone. This is a **consolidated parity build** — iPhone has never been built past v1.2.9+71. This single assignment brings the iPhone all the way to v2.1.1+8, which includes all changes from v2.1.1+3 through +8.

**What this build delivers over v1.2.9+71:**

*Dual-Environment Networking (v2.1.1+3):*
- `Endpoints` resolver — all service calls route through a single resolver per active mode
- `Endpoints.apiHeaders()` sends `X-API-Key` in cloud mode
- `TranslationService` cloud migration, dead files removed
- About screen: Local/Cloud toggle + cloud URL field + API Key field

*Poll Hardening (v2.1.1+6/+7):*
- `Timer.periodic` → `Future.delayed` self-scheduling poll loop — no stuck timers
- `_pollTimer` field removed entirely
- `if (_isGenerating) return;` re-entry guard — double-tap Generate starts only one generation
- `unawaited(pollLoop().catchError(...))` — spinner can't stick on crash
- `translation_failed` orange snackbar

*New in v2.1.1+8 — 4 Features:*
- **Account Deletion UI** — Red "Delete My Account" in About → Danger Zone section. Two-step confirmation. Server-first DELETE call. On success: wipes local tours + news + SharedPreferences. iOS behavior: pops to root.
- **Existing-Tour Translation** — Purple translate icon on non-translated tours in Listen page. Language selection dialog (10 languages). Calls `TranslationService.translateTour()`.
- **App Attestation (stubs)** — `AppAttestationService` returns null (Phase 3/4 not yet implemented). `apiHeaders()` extended with optional `requestBody` param → `X-App-Attestation` header stub. iOS native Swift work (Phase 4) is a separate future assignment.
- **News Cloud Paths** — All 5 news/newsletter HTTP calls use `Endpoints.apiHeaders()`. `Endpoints.newsDownloadUrl()` routes `/news-download/<id>` in cloud, `/download/<id>` in local.

**Target commit:** `37dcc49`  **Version:** `2.1.1+8`  **Branch:** `services-migration`
**No pubspec bump needed** — Mobile Kiro already at `2.1.1+8`.
**No iOS-specific changes needed** — `Info.plist` already has `NSLocalNetworkUsageDescription`.

**Roles:**
- **[SIR MICHAEL]** — orchestrator. Switches KVM, runs smoke test, syncs Windows afterward.
- **[MAC MINI Q]** — pulls latest, verifies signing, runs `pod install`, builds, installs. No pubspec bump.

---

## Step 0 — [SIR MICHAEL] Eject USB, carry to Mac Mini, switch KVM

## Step 1 — [SIR MICHAEL on Mac Mini] Launch Q

Paste:
> Read `@/Volumes/USB DISK/Audioura/assignments/mac_mini_assignments.md` and execute the A#82 assignment at the top. Follow STOP conditions; skip steps labelled `[SIR MICHAEL]`.

## Step 2 — [MAC MINI Q] Pull latest

```bash
cd ~/Development/Audioura-build
git pull origin services-migration
```

**Expected:** fast-forward to commit `37dcc49` or later.

If pull fails with "local changes would be overwritten" — STOP and report. Do not `git reset --hard`.

## Step 3 — [MAC MINI Q] Spot-check BEFORE building ⚠️ REQUIRED

```bash
cd ~/Development/Audioura-build/development/audio_tour_app

# 3a — pubspec at 2.1.1+8
grep "^version:" pubspec.yaml
# Expected: version: 2.1.1+8

# 3b — NSLocalNetworkUsageDescription present
grep -n "NSLocalNetworkUsageDescription" ios/Runner/Info.plist
# Expected: 1 match

# 3c — Account deletion button present in about_screen
grep -n "Delete My Account\|delete-account\|deleteAccount\|Danger Zone" lib/screens/about_screen.dart | head -5
# Expected: matches for deletion UI

# 3d — TourTranslationHelper exists (Existing-Tour Translation feature)
ls lib/services/tour_translation_helper.dart 2>/dev/null && echo FOUND || echo MISSING
# Expected: FOUND

# 3e — AppAttestationService exists
ls lib/services/app_attestation_service.dart 2>/dev/null && echo FOUND || echo MISSING
# Expected: FOUND

# 3f — _pollTimer is GONE (removed in v2.1.1+6 — any match = compile error)
grep -n "_pollTimer" lib/screens/tour_generator_screen.dart
# Expected: zero matches

# 3g — newsDownloadUrl present in endpoints.dart
grep -n "newsDownloadUrl\|news-download" lib/config/endpoints.dart
# Expected: at least 1 match

# 3h — signing intact
grep -E 'PRODUCT_BUNDLE_IDENTIFIER|DEVELOPMENT_TEAM' \
  ios/Runner.xcodeproj/project.pbxproj | sort -u
# Expected: com.glikfamily.audioura and 4HGRU6TKGQ
```

If 3a fails — STOP, wrong commit pulled.
If 3f shows any `_pollTimer` match — STOP, will fail to compile.
If 3d or 3e shows MISSING — STOP, new service files not pulled.

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

If build FAILS with compile error mentioning `_pollTimer` — STOP immediately, report to iOS Q.
If `flutter analyze` shows errors in `audio_handler.dart`, `map_page.dart`, `subscription_management_screen.dart`, or `widget_test.dart` — these are known dead files, non-blocking, proceed.

## Step 6 — [SIR MICHAEL] Smoke test on iPhone ⚠️ STOP HERE FOR Q

### Core functionality (5 tests)

**Test 1 — App launches:**
- Launch app. No crash. Home tab loads.

**Test 2 — Local WiFi tour generation:**
1. On WiFi → generate a new English tour.
2. **Expected:** Spinner polls, status updates. Tour opens automatically when ready. No stuck spinner.
3. Tap Generate a second time immediately — **Expected:** only one generation starts (re-entry guard).

**Test 3 — Tour playback:**
1. Open a generated tour → audio plays in WebView.

**Test 4 — POI map button:**
1. In tour player → tap POI map icon.
2. **Expected:** TourMapScreen opens.

**Test 5 — News/Audio mode:**
1. Switch to Audio mode (About tab).
2. Newsletter list loads. Download an article. Playback works.

### New features (4 tests)

**Test 6 — Account Deletion UI:**
1. About tab → scroll down → find **Danger Zone** section → "Delete My Account" red button.
2. Tap it → confirmation dialog appears.
3. Tap **Cancel** — dialog dismisses, nothing deleted.
4. ⚠️ Do NOT confirm deletion unless using a throwaway account.

**Test 7 — Existing-tour Translation:**
1. Listen page → find a non-translated tour.
2. **Expected:** Purple translate icon visible on that tour row.
3. Tap it → language selection dialog appears with 10 language options.
4. Select a language → translated tour starts processing → eventually appears in Listen.
5. Mark NOT_TESTED if no suitable tour available — not a blocker.

**Test 8 — Cloud mode tour generation:**
1. About tab → switch to **Cloud** → enter URL `https://api.audioura.com` + API Key → Save both.
2. Leave gateway path routing checkbox **unchecked**.
3. Generate a tour in Cloud mode.
4. **Expected:** Tour generates via cloud, opens automatically.

**Test 9 — Cloud news download:**
1. In Cloud mode → Audio mode → process newsletter → download an article.
2. **Expected:** Article downloads via cloud path, playback works.
3. Mark NOT_TESTED if cloud news service not deployed — not a blocker.

### Regressions (3 tests)

**Test 10 — Mic regression (A#78):**
1. Audio mode → Listen tab → tap microphone icon.
2. **Expected:** Listening dialog opens. No "Microphone permission required" snackbar.

**Test 11 — Refresh regression (A#77b):**
1. Listen tab → tap Refresh.
2. **Expected:** List reloads in place. No black screen.

**Test 12 — Double-tap generation:**
1. Tap Generate twice rapidly.
2. **Expected:** Only one generation starts.

Tell Q "Smoke test passes, proceed to Step 7" when done. Report each test result including NOT_TESTED where applicable.

## Step 7 — [MAC MINI Q] Verify git state — no commit needed

```bash
cd ~/Development/Audioura-build
git status
# Expected: nothing to commit (or only untracked files)
git log --oneline -3
# Confirm 37dcc49 or later is HEAD
```

If `git status` shows modified tracked files — STOP and report before committing anything.

## Step 8 — [MAC MINI Q] Copy results and eject

```bash
echo "A#82 Results:" > ~/Desktop/a82_results.txt
echo "Date: $(date)" >> ~/Desktop/a82_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a82_results.txt
echo "Test 1  App launches: [YES/NO]" >> ~/Desktop/a82_results.txt
echo "Test 2  Local WiFi generation + re-entry guard: [YES/NO]" >> ~/Desktop/a82_results.txt
echo "Test 3  Tour playback: [YES/NO]" >> ~/Desktop/a82_results.txt
echo "Test 4  POI map button: [YES/NO]" >> ~/Desktop/a82_results.txt
echo "Test 5  News/Audio mode: [YES/NO]" >> ~/Desktop/a82_results.txt
echo "Test 6  Account Deletion UI: [YES/NO]" >> ~/Desktop/a82_results.txt
echo "Test 7  Existing-tour Translation: [YES/NO/NOT_TESTED]" >> ~/Desktop/a82_results.txt
echo "Test 8  Cloud mode generation: [YES/NO/NOT_TESTED]" >> ~/Desktop/a82_results.txt
echo "Test 9  Cloud news download: [YES/NO/NOT_TESTED]" >> ~/Desktop/a82_results.txt
echo "Test 10 Mic regression: [YES/NO]" >> ~/Desktop/a82_results.txt
echo "Test 11 Refresh regression: [YES/NO]" >> ~/Desktop/a82_results.txt
echo "Test 12 Double-tap guard: [YES/NO]" >> ~/Desktop/a82_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a82_results.txt
cp ~/Desktop/a82_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 9 — [MAC MINI Q] Report Results

> "Assignment 82 complete. Build: [SUCCESS/FAILED]. Core (Tests 1-5): [ALL_PASS/ISSUES]. Account Deletion UI (T6): [YES/NO]. Translation icon (T7): [YES/NO/NOT_TESTED]. Cloud generation (T8): [YES/NO/NOT_TESTED]. Cloud news (T9): [YES/NO/NOT_TESTED]. Mic regression (T10): [YES/NO]. Refresh regression (T11): [YES/NO]. Double-tap guard (T12): [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

## Step 10 — [SIR MICHAEL, back on Windows] Sync

```cmd
cd C:\Users\micha\eclipse-workspace\AudioTours\development
git pull origin services-migration
```
Verify `audio_tour_app\pubspec.yaml` shows `version: 2.1.1+8`.

---

# T: 06/2026 - A#81 — Build v2.1.1+7 — SUPERSEDED by A#82
**Status**: ⏭️ SUPERSEDED — never built. A#82 includes all v2.1.1+7 changes.

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
