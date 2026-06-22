# Mac Mini Assignment Instructions
## iOS Development Task Execution

# T: 06/2026 - A#83 — Build v2.1.1+9 on iPhone (Final — Cloud E2E + Hardcoded URL Audit)

**Goal:** Build v2.1.1+9 on iPhone. This is the **final v2.1.1+9 build** — supersedes the earlier A#83 draft (which targeted `f72ee23`). iPhone has never been built past v1.2.9+71. This single assignment brings the iPhone all the way to v2.1.1+9.

**What this build delivers over v1.2.9+71:**

*Dual-Environment Networking (v2.1.1+3):*
- `Endpoints` resolver — all service calls route through a single resolver per active mode
- `Endpoints.apiHeaders()` sends `X-API-Key` in cloud mode
- `TranslationService` cloud migration, dead files removed
- About screen: Local/Cloud toggle + cloud URL field + API Key field (temporary)

*Poll Hardening (v2.1.1+6/+7):*
- `Future.delayed` self-scheduling poll loop — `_pollTimer` field completely gone
- `if (_isGenerating) return;` re-entry guard, `unawaited(pollLoop().catchError(...))` crash recovery
- `translation_failed` orange snackbar

*New Features (v2.1.1+8):*
- **Account Deletion UI** — Danger Zone in About, two-step confirm, server-first DELETE, local wipe on success
- **Existing-Tour Translation** — purple translate icon on Listen page, 10-language dialog
- **App Attestation stubs** — `AppAttestationService` returns null (Phase 4 native Swift is future work)
- **News Cloud Paths** — all news/newsletter calls use `apiHeaders()`, `newsDownloadUrl()` routes correctly

*Cloud Fixes + Audit (v2.1.1+9):*
- **Cloud auth fix** — `user_id` included in tour generation body (fixes 401 `auth_required`)
- **Hardcoded URL audit** — all 4 `5012`/`5017` hardcoded URLs in `tour_generator_screen.dart` replaced with `Endpoints.url()`
- **3 new Service enum entries** — `treats` (:5007), `voice` (:5008), `tourEditing` (:5022)
- **Cloud gate** — treats/voice/tourEditing show clean "only available on WiFi" message in cloud mode
- **Subscription service** — `/submit_credentials` and `/key_exchange` migrated to `Endpoints`
- **`newsStatusUrl()`** — `/news-status/<id>` cloud, `/status/<id>` local
- **402 handling** — newsletter 402 → orange snackbar; article download 402 → skips cleanly; tour generator newsletter tab 402 → 🔒 icon
- **Translation consolidation** — `home_screen.dart` calls `TourTranslationHelper` (77 lines of duplicate code removed)
- **Dead files deleted** — `home_page_flutter_map.dart`, `api_config.dart`
- **Compile fixes** — missing `endpoints.dart` import in `my_tours_screen`, duplicate prefs in `treats_screen`

**Target commit:** `4aa8382` (or later — `cb7540e` is docs only on top)
**Version:** `2.1.1+9`  **Branch:** `services-migration`
**No pubspec bump needed** — Mobile Kiro already at `2.1.1+9`.
**No iOS-specific changes** — no `Info.plist`, no new pods.

**Roles:**
- **[SIR MICHAEL]** — orchestrator. Switches KVM, runs smoke test, syncs Windows afterward.
- **[MAC MINI Q]** — pulls latest, runs `pod install`, builds, installs. No pubspec bump.

---

## Step 0 — [SIR MICHAEL] Eject USB, carry to Mac Mini, switch KVM

## Step 1 — [SIR MICHAEL on Mac Mini] Launch Q

Paste:
> Read `@/Volumes/USB DISK/Audioura/assignments/mac_mini_assignments.md` and execute the A#83 assignment at the top. Follow STOP conditions; skip steps labelled `[SIR MICHAEL]`.

## Step 2 — [MAC MINI Q] Pull latest

```bash
cd ~/Development/Audioura-build
git pull origin services-migration
```

**Expected:** fast-forward to commit `4aa8382` or later (`cb7540e`).

If pull fails with "local changes would be overwritten" — STOP and report. Do not `git reset --hard`.

## Step 3 — [MAC MINI Q] Spot-check BEFORE building ⚠️ REQUIRED

```bash
cd ~/Development/Audioura-build/development/audio_tour_app

# 3a — pubspec at 2.1.1+9
grep "^version:" pubspec.yaml
# Expected: version: 2.1.1+9

# 3b — user_id in tour generation body (cloud auth fix)
grep -n "user_id" lib/screens/tour_generator_screen.dart | head -8
# Expected: at least 2 matches in tourData map

# 3c — hardcoded 5012/5017 URLs are GONE
grep -n "5012\|5017" lib/screens/tour_generator_screen.dart
# Expected: zero matches

# 3d — newsStatusUrl helper in endpoints.dart
grep -n "newsStatusUrl\|news-status" lib/config/endpoints.dart
# Expected: at least 1 match

# 3e — treats/voice/tourEditing in Service enum
grep -n "treats\|voice\|tourEditing" lib/config/endpoints.dart
# Expected: 3 matches

# 3f — TourTranslationHelper import in home_screen.dart
grep -n "TourTranslationHelper\|tour_translation_helper" lib/screens/home_screen.dart
# Expected: at least 1 match

# 3g — _pollTimer is GONE
grep -n "_pollTimer" lib/screens/tour_generator_screen.dart
# Expected: zero matches

# 3h — signing intact
grep -E 'PRODUCT_BUNDLE_IDENTIFIER|DEVELOPMENT_TEAM' \
  ios/Runner.xcodeproj/project.pbxproj | sort -u
# Expected: com.glikfamily.audioura and 4HGRU6TKGQ
```

If 3a fails — STOP, wrong commit.
If 3c shows any 5012/5017 — STOP, hardcoded URLs still present.
If 3g shows any `_pollTimer` — STOP, will fail to compile.

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

`flutter analyze` warnings in `audio_handler.dart`, `map_page.dart`, `subscription_management_screen.dart`, `widget_test.dart` — known dead files, **non-blocking**, proceed.

If build FAILS with signing error — open Xcode:
```bash
open ~/Development/Audioura-build/development/audio_tour_app/ios/Runner.xcworkspace
```
Runner → Signing & Capabilities → Automatically manage signing ✅ → Team: Mikhail Glik (4HGRU6TKGQ) → Bundle ID: `com.glikfamily.audioura` → Quit Xcode → re-run Step 5.

## Step 6 — [SIR MICHAEL] Smoke test on iPhone ⚠️ STOP HERE FOR Q

⚠️ **Have cloud URL (`https://api.audioura.com`) and API Key ready before starting cloud tests.**

### Cloud mode — primary focus (Tests 1–5)

**Test 1 — Cloud tour generation (previously failed A#82 Test 8):**
1. About → switch to **Cloud** → enter URL `https://api.audioura.com` + API Key → Save.
2. Leave gateway path routing **unchecked**.
3. Generate a new English tour.
4. **Expected:** `200` response — no `401 auth_required`. Spinner polls, tour opens automatically.

**Test 2 — Cloud newsletter processing:**
1. In Cloud mode → Audio mode → process a newsletter URL.
2. **Expected:** Succeeds, OR shows clean orange snackbar for paywalled (402) sources. No crash.

**Test 3 — Cloud news article download:**
1. In Cloud mode → download a news article.
2. **Expected:** Downloads via `api.audioura.com/news-download/<id>`. Appears in Listen.

**Test 4 — News article playback:**
1. Open the downloaded article → WebView loads → audio plays.

**Test 5 — Cloud translation:**
1. In Cloud mode → generate a tour with translation requested.
2. **Expected:** Translated versions appear in Listen. OR mark NOT_TESTED — not a blocker.

### v2.1.1+8 feature regressions (Tests 6–7)

**Test 6 — Account Deletion UI:**
1. About → scroll down → **Danger Zone** → "Delete My Account" red button visible.
2. Tap → confirmation dialog appears → tap **Cancel** → nothing deleted.
3. ⚠️ Do NOT confirm deletion.

**Test 7 — Existing-tour Translation:**
1. Listen page → find a non-translated tour → purple translate icon visible.
2. Tap → language dialog appears with 10 options.
3. Mark NOT_TESTED if no suitable tour available — not a blocker.

### Local mode regression (Test 8)

**Test 8 — Local WiFi regression:**
1. About → switch back to **Local WiFi**.
2. Generate a tour on WiFi → works normally.
3. Audio mode → process newsletter / generate news → works normally.
4. **Expected:** No regression from URL migration.

### Standard regressions (Tests 9–12)

**Test 9 — Mic (A#78):** Listen tab → tap mic → listening dialog opens, no permission snackbar.

**Test 10 — Refresh (A#77b):** Listen tab → Refresh → no black screen.

**Test 11 — POI map button:** Tour player → tap map icon → TourMapScreen opens.

**Test 12 — Cloud-gated features:** In Cloud mode → navigate to Treats/Voice/Tour Editing sections.
**Expected:** Clean message "only available on WiFi" — not an error crash.

Tell Q "Smoke test passes, proceed to Step 7" when done. Report each test result.

## Step 7 — [MAC MINI Q] Verify git state — no commit needed

```bash
cd ~/Development/Audioura-build
git status
# Expected: nothing to commit (or only untracked files)
git log --oneline -3
# Confirm 4aa8382 or cb7540e is present
```

If `git status` shows modified tracked files — STOP and report before committing anything.

## Step 8 — [MAC MINI Q] Copy results and eject

```bash
echo "A#83 Final Results:" > ~/Desktop/a83_results.txt
echo "Date: $(date)" >> ~/Desktop/a83_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a83_results.txt
echo "Test 1  Cloud tour generation (no 401): [YES/NO]" >> ~/Desktop/a83_results.txt
echo "Test 2  Cloud newsletter (clean 402 or success): [YES/NO]" >> ~/Desktop/a83_results.txt
echo "Test 3  Cloud news article download: [YES/NO]" >> ~/Desktop/a83_results.txt
echo "Test 4  News article playback: [YES/NO]" >> ~/Desktop/a83_results.txt
echo "Test 5  Cloud translation: [YES/NO/NOT_TESTED]" >> ~/Desktop/a83_results.txt
echo "Test 6  Account Deletion UI: [YES/NO]" >> ~/Desktop/a83_results.txt
echo "Test 7  Existing-tour Translation icon: [YES/NO/NOT_TESTED]" >> ~/Desktop/a83_results.txt
echo "Test 8  Local WiFi regression: [YES/NO]" >> ~/Desktop/a83_results.txt
echo "Test 9  Mic regression: [YES/NO]" >> ~/Desktop/a83_results.txt
echo "Test 10 Refresh regression: [YES/NO]" >> ~/Desktop/a83_results.txt
echo "Test 11 POI map button: [YES/NO]" >> ~/Desktop/a83_results.txt
echo "Test 12 Cloud-gated features message: [YES/NO]" >> ~/Desktop/a83_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a83_results.txt
cp ~/Desktop/a83_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 9 — [MAC MINI Q] Report Results

> "Assignment 83 final complete. Build: [SUCCESS/FAILED]. Cloud generation (T1): [YES/NO]. Cloud newsletter (T2): [YES/NO]. Cloud news download (T3): [YES/NO]. News playback (T4): [YES/NO]. Cloud translation (T5): [YES/NO/NOT_TESTED]. Delete UI (T6): [YES/NO]. Translate icon (T7): [YES/NO/NOT_TESTED]. Local regression (T8): [YES/NO]. Mic (T9): [YES/NO]. Refresh (T10): [YES/NO]. POI map (T11): [YES/NO]. Cloud gate msg (T12): [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

## Step 10 — [SIR MICHAEL, back on Windows] Sync

```cmd
cd C:\Users\micha\eclipse-workspace\AudioTours\development
git pull origin services-migration
```
Verify `audio_tour_app\pubspec.yaml` shows `version: 2.1.1+9`.

---

# T: 06/2026 - A#82 — Build v2.1.1+8 — SUPERSEDED by A#83
**Status**: ⏭️ SUPERSEDED — never built on iPhone. All v2.1.1+8 features included in A#83.

---

# T: 06/2026 - A#81 — Build v2.1.1+7 — SUPERSEDED by A#83
**Status**: ⏭️ SUPERSEDED — never built. All changes included in A#83.

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
