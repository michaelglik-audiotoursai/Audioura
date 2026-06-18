# Mac Mini Assignment Instructions
## iOS Development Task Execution

# T: 06/2026 - A#83 — Build v2.1.1+9 on iPhone (Cloud Hotfix — auth_required + news URLs)

**Goal:** Build v2.1.1+9 on iPhone. This is a **hotfix** on top of v2.1.1+8. A#82 smoke testing found two cloud-mode failures (Tests 8 and 9). All 10 other tests passed — local mode, UI features, and regressions are fine. This build fixes both cloud failures and re-runs only the failed tests plus local regressions.

**What changed since v2.1.1+8 (3 commits):**

| Commit | Fix |
|--------|-----|
| `2836d7b` | `user_id` added to tour generation body (both foreground + background) — fixes 401 `auth_required` in cloud. `Endpoints.url()` replaces 4 hardcoded news/newsletter local URLs. `newsStatusUrl()` added to `endpoints.dart`. |
| `ea9fd95` | pubspec bumped to `2.1.1+9` |
| `f72ee23` | Compile fix — `userId` not in scope in `_downloadAndSaveNews`, reads from prefs |

**Target commit:** `f72ee23`  **Version:** `2.1.1+9`  **Branch:** `services-migration`
**No pubspec bump needed** — Mobile Kiro already at `2.1.1+9`.
**No iOS-specific changes** — no `Info.plist`, no pods added.

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

**Expected:** fast-forward to commit `f72ee23` or later.

If pull fails with "local changes would be overwritten" — STOP and report. Do not `git reset --hard`.

## Step 3 — [MAC MINI Q] Spot-check BEFORE building ⚠️ REQUIRED

```bash
cd ~/Development/Audioura-build/development/audio_tour_app

# 3a — pubspec at 2.1.1+9
grep "^version:" pubspec.yaml
# Expected: version: 2.1.1+9

# 3b — user_id included in tour generation (cloud auth fix)
grep -n "user_id" lib/screens/tour_generator_screen.dart | head -10
# Expected: at least 2 matches in tourData map (foreground + background generation)

# 3c — newsStatusUrl helper exists in endpoints.dart
grep -n "newsStatusUrl\|news-status" lib/config/endpoints.dart
# Expected: at least 1 match

# 3d — hardcoded 5012/5017 URLs are GONE from tour_generator_screen
grep -n "5012\|5017" lib/screens/tour_generator_screen.dart
# Expected: zero matches (all replaced with Endpoints.url())

# 3e — signing intact
grep -E 'PRODUCT_BUNDLE_IDENTIFIER|DEVELOPMENT_TEAM' \
  ios/Runner.xcodeproj/project.pbxproj | sort -u
# Expected: com.glikfamily.audioura and 4HGRU6TKGQ
```

If 3a fails — STOP, wrong commit.
If 3d shows any 5012 or 5017 matches — STOP, hardcoded URLs still present, cloud news will fail.

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

## Step 6 — [SIR MICHAEL] Smoke test on iPhone ⚠️ STOP HERE FOR Q

⚠️ **Have the cloud URL (`https://api.audioura.com`) and API Key ready before starting Tests 1 and 2.**

### Previously-failed cloud tests (primary focus)

**Test 1 — Cloud tour generation (was Test 8 in A#82 — previously FAILED):**
1. About tab → switch to **Cloud** → enter URL `https://api.audioura.com` + API Key → Save both.
2. Leave gateway path routing checkbox **unchecked**.
3. Generate a new English tour.
4. **Expected:** Generation succeeds. No 401 `auth_required` error. Spinner polls, tour opens automatically.
5. Check debug log — should NOT contain `auth_required`. Should show `200` on generation POST.

**Test 2 — Cloud news (was Test 9 in A#82 — previously FAILED):**
1. Still in Cloud mode → switch to **Audio mode**.
2. Process newsletter OR generate a news article.
3. **Expected:** News/newsletter request hits `api.audioura.com` (not `192.168.0.218`). Article generates/downloads. Playback works.
4. Check debug log — should show cloud URLs (`api.audioura.com`), not local IP.

### Local mode regressions

**Test 3 — Local WiFi tour generation:**
1. About tab → switch back to **Local WiFi**.
2. Generate a new tour on WiFi.
3. **Expected:** Tour generates normally. No regression from URL changes.

**Test 4 — Local news/newsletter:**
1. In Local WiFi mode → Audio mode → process newsletter or generate news.
2. **Expected:** News hits `192.168.0.218:5012/5017` as before. No regression.

### Spot regression checks

**Test 5 — Mic (A#78):** Tap mic icon → listening dialog, no permission snackbar.
**Test 6 — Refresh (A#77b):** Listen page Refresh → no black screen.
**Test 7 — Account Deletion UI:** About → Danger Zone → Delete button visible → Cancel works.

Tell Q "Smoke test passes, proceed to Step 7" when done. Report each test result.

## Step 7 — [MAC MINI Q] Verify git state — no commit needed

```bash
cd ~/Development/Audioura-build
git status
# Expected: nothing to commit (or only untracked files)
git log --oneline -3
# Confirm f72ee23 or later is HEAD
```

If `git status` shows modified tracked files — STOP and report before committing anything.

## Step 8 — [MAC MINI Q] Copy results and eject

```bash
echo "A#83 Results:" > ~/Desktop/a83_results.txt
echo "Date: $(date)" >> ~/Desktop/a83_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a83_results.txt
echo "Test 1  Cloud tour generation (no 401): [YES/NO]" >> ~/Desktop/a83_results.txt
echo "Test 2  Cloud news/newsletter: [YES/NO/NOT_TESTED]" >> ~/Desktop/a83_results.txt
echo "Test 3  Local WiFi tour generation: [YES/NO]" >> ~/Desktop/a83_results.txt
echo "Test 4  Local news/newsletter: [YES/NO]" >> ~/Desktop/a83_results.txt
echo "Test 5  Mic regression: [YES/NO]" >> ~/Desktop/a83_results.txt
echo "Test 6  Refresh regression: [YES/NO]" >> ~/Desktop/a83_results.txt
echo "Test 7  Account Deletion UI present: [YES/NO]" >> ~/Desktop/a83_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a83_results.txt
cp ~/Desktop/a83_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 9 — [MAC MINI Q] Report Results

> "Assignment 83 complete. Build: [SUCCESS/FAILED]. Cloud generation no 401 (T1): [YES/NO]. Cloud news (T2): [YES/NO/NOT_TESTED]. Local generation (T3): [YES/NO]. Local news (T4): [YES/NO]. Mic regression (T5): [YES/NO]. Refresh regression (T6): [YES/NO]. Delete UI (T7): [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

## Step 10 — [SIR MICHAEL, back on Windows] Sync

```cmd
cd C:\Users\micha\eclipse-workspace\AudioTours\development
git pull origin services-migration
```
Verify `audio_tour_app\pubspec.yaml` shows `version: 2.1.1+9`.

---

# T: 06/2026 - A#82 — Build v2.1.1+8 — SUPERSEDED by A#83
**Status**: ⏭️ SUPERSEDED — never built on iPhone. A#83 includes all v2.1.1+8 features plus cloud hotfix.

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
