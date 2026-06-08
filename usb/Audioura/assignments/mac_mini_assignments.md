# Mac Mini Assignment Instructions
## iOS Development Task Execution

# T: 06/2026 - A#80 — Build v2.1.1+3 iOS (Local WiFi Parity with Android)

**Goal:** Build v2.1.1+3 on iPhone. Parity build — all Dart changes are shared Flutter code from Android Q. iOS task is build-and-verify LOCAL WiFi mode only. **Cloud testing is explicitly excluded** — two mobile-side blockers (no `X-API-Key` header, `TranslationService` bypasses `Endpoints`) must be fixed by Android Q in a future version before cloud smoke tests run.

**What this build delivers over v2.1.1+1:**
- `tour_status_service.dart` rewritten — clean REST via `Endpoints(Service.orchestrator)`, keyed on `tour_xxx` tour_id
- `test_update_api.dart` and all 9 dead raw-SQL files deleted — dangling import resolved
- About-screen text: `cloud_use_path_prefixes` stays `false` (confirmed correct)
- SharedPreferences key cleanup (minor)

**Cloud blockers (NOT iOS's job — Android Q owns these for v2.1.1+4):**
- Blocker A: No `X-API-Key` header on cost-bearing POSTs → gateway 401s in cloud mode
- Blocker B: `TranslationService` still hardcodes `192.168.0.218:5030` → cloud multi-language fails

**Roles:**
- **[SIR MICHAEL]** — orchestrator. Switches KVM, runs smoke test (LOCAL WiFi only), syncs Windows afterward.
- **[MAC MINI Q]** — pulls latest, verifies signing, runs `pod install`, builds, installs. No pubspec bump (already at `2.1.1+3`).

**Version target:** v2.1.1+3  **Branch:** `services-migration`

---

## Step 0 — [SIR MICHAEL] Eject USB, carry to Mac Mini, switch KVM

## Step 1 — [SIR MICHAEL on Mac Mini] Launch Q

Paste:
> Read `@/Volumes/USB DISK/Audioura/assignments/mac_mini_assignments.md` and execute the A#80 assignment at the top. Follow STOP conditions; skip steps labelled `[SIR MICHAEL]`.

## Step 2 — [MAC MINI Q] Pull latest

```bash
cd ~/Development/Audioura-build
git pull origin services-migration
```

**Expected:** fast-forward to at least commit `049bb35`.

## Step 3 — [MAC MINI Q] Spot-check BEFORE building ⚠️ REQUIRED

```bash
cd ~/Development/Audioura-build/development/audio_tour_app

# 3a — pubspec at 2.1.1+3
grep "^version:" pubspec.yaml
# Expected: version: 2.1.1+3

# 3b — NSLocalNetworkUsageDescription present
grep -n "NSLocalNetworkUsageDescription" ios/Runner/Info.plist
# Expected: 1 match

# 3c — test_update_api.dart is GONE
find lib/ -name "test_update_api.dart"
# Expected: no output

# 3d — tour_status_service uses Endpoints (not raw serverIp)
grep -n "Endpoints\|Service.orchestrator" lib/services/tour_status_service.dart
# Expected: at least 1 match

# 3e — signing intact
grep -E 'PRODUCT_BUNDLE_IDENTIFIER|DEVELOPMENT_TEAM' \
  ios/Runner.xcodeproj/project.pbxproj | sort -u
# Expected: com.glikfamily.audioura and 4HGRU6TKGQ
```

If 3a fails or 3c shows the file still exists, STOP and report to iOS Q.

## Step 4 — [MAC MINI Q] pod install

```bash
cd ~/Development/Audioura-build/development/audio_tour_app/ios
pod install
```

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

⚠️ **LOCAL WiFi ONLY — do NOT test Cloud mode. Cloud blockers not yet fixed.**

**Test 1 — Local mode default (on WiFi):**
1. Launch app → Home tab.
2. **Expected:** Tours load from `192.168.0.218`. No errors.
3. About tab → mode shows **Local** by default.

**Test 2 — About screen toggle present:**
1. About tab → Local/Cloud toggle visible.
2. Switch to Cloud → URL field appears. Leave gateway path routing checkbox **unchecked**.
3. Switch back to Local → URL field disappears.
4. ⚠️ Do NOT test tour generation or download in Cloud mode — stop here.

**Test 3 — Local WiFi tour generation:**
1. On WiFi → generate a new tour.
2. **Expected:** Tour generates, status updates, tour appears in Listen tab.

**Test 4 — A#78 regression (mic):**
1. Audio mode → Listen tab → tap microphone icon.
2. **Expected:** Listening dialog opens. No "Microphone permission required" snackbar.

**Test 5 — A#77b regression (Refresh):**
1. Listen tab → tap Refresh.
2. **Expected:** List reloads, no black screen.

**Test 6 — General regression:**
1. Open a tour → audio plays.
2. Open a news article → loads.
3. POI map icon → TourMapScreen opens.

Tell Q "Smoke test passes, proceed to Step 7" when done. Report each test result.

## Step 7 — [MAC MINI Q] No pubspec commit needed — version already at 2.1.1+3

```bash
cd ~/Development/Audioura-build
git status
# Expected: nothing to commit (or only untracked files)
git log --oneline -3
# Confirm 049bb35 or later is present
```

If `git status` shows modified tracked files — STOP and report before committing anything.

## Step 8 — [MAC MINI Q] Copy results and eject

```bash
echo "A#80 Results:" > ~/Desktop/a80_results.txt
echo "Date: $(date)" >> ~/Desktop/a80_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a80_results.txt
echo "Local mode tours load (Test 1): [YES/NO]" >> ~/Desktop/a80_results.txt
echo "About Local/Cloud toggle present (Test 2): [YES/NO]" >> ~/Desktop/a80_results.txt
echo "Local WiFi tour generation works (Test 3): [YES/NO/NOT_TESTED]" >> ~/Desktop/a80_results.txt
echo "Mic no permission snackbar (Test 4): [YES/NO]" >> ~/Desktop/a80_results.txt
echo "Listen Refresh no black screen (Test 5): [YES/NO]" >> ~/Desktop/a80_results.txt
echo "General regression clean (Test 6): [YES/NO]" >> ~/Desktop/a80_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a80_results.txt
cp ~/Desktop/a80_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 9 — [MAC MINI Q] Report Results

> "Assignment 80 complete. Build: [SUCCESS/FAILED]. Local mode works: [YES/NO]. Toggle present: [YES/NO]. Local generation: [YES/NO/NOT_TESTED]. Mic regression: [YES/NO]. Refresh regression: [YES/NO]. General regression: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

## Step 10 — [SIR MICHAEL, back on Windows] Sync

```cmd
cd C:\Users\micha\eclipse-workspace\AudioTours\development
git pull origin services-migration
```
Verify `audio_tour_app\pubspec.yaml` shows `version: 2.1.1+3`.

---

# T: 06/2026 - A#80 — Build v2.1.1+3 iOS (Full Parity with Android — Local WiFi + Cloud)

**Goal:** Build v2.1.1+3 on iPhone. Full parity build — Local WiFi and Cloud both tested and working on Android. iOS just needs to build the same commit.

**What this build delivers over v2.1.1+1:**
- `tour_status_service.dart` rewritten — REST via `Endpoints(Service.orchestrator)` + `Endpoints.apiHeaders()`, keyed on `tour_xxx` tour_id
- `TranslationService` migrated to `Endpoints.url(Service.translation)` + `Endpoints.apiHeaders()` — cloud multi-language works
- `Endpoints.apiHeaders()` sends `X-API-Key` header in cloud mode (reads from `SharedPreferences('gateway_api_key')`)
- About screen: API Key field present — user enters the key manually (temporary — field will be removed once key is baked in)
- Dead files removed: `test_update_api.dart` + raw-SQL files
- Inter-service auth tokens on all service edges
- OpenAI + AWS secret key fixes

**About the API Key field:** Customers cannot be expected to know the gateway API key, so the About screen's API Key input is a **temporary development tool**. It will be removed in a future version once the key is embedded or handled automatically. For now: Sir Michael enters the key during smoke testing.

**Roles:**
- **[SIR MICHAEL]** — orchestrator. Switches KVM, runs smoke test (both Local WiFi and Cloud), syncs Windows afterward.
- **[MAC MINI Q]** — pulls latest, verifies signing, runs `pod install`, builds, installs. No pubspec bump (already at `2.1.1+3`).

**Version target:** v2.1.1+3  **Branch:** `services-migration`

---

## Step 0 — [SIR MICHAEL] Eject USB, carry to Mac Mini, switch KVM

## Step 1 — [SIR MICHAEL on Mac Mini] Launch Q

Paste:
> Read `@/Volumes/USB DISK/Audioura/assignments/mac_mini_assignments.md` and execute the A#80 assignment at the top. Follow STOP conditions; skip steps labelled `[SIR MICHAEL]`.

## Step 2 — [MAC MINI Q] Pull latest

```bash
cd ~/Development/Audioura-build
git pull origin services-migration
```

**Expected:** fast-forward to at least commit `049bb35`.

## Step 3 — [MAC MINI Q] Spot-check BEFORE building ⚠️ REQUIRED

```bash
cd ~/Development/Audioura-build/development/audio_tour_app

# 3a — pubspec at 2.1.1+3
grep "^version:" pubspec.yaml
# Expected: version: 2.1.1+3

# 3b — NSLocalNetworkUsageDescription present
grep -n "NSLocalNetworkUsageDescription" ios/Runner/Info.plist
# Expected: 1 match

# 3c — Endpoints.apiHeaders sends X-API-Key in cloud mode
grep -n "X-API-Key\|apiHeaders\|gateway_api_key" lib/config/endpoints.dart
# Expected: matches for all three

# 3d — TranslationService uses Endpoints (not hardcoded IP)
grep -n "Endpoints\|Service.translation" lib/services/translation_service.dart
# Expected: at least 2 matches

# 3e — test_update_api.dart is GONE
ls lib/services/test_update_api.dart 2>/dev/null && echo FOUND || echo GONE
# Expected: GONE

# 3f — signing intact
grep -E 'PRODUCT_BUNDLE_IDENTIFIER|DEVELOPMENT_TEAM' \
  ios/Runner.xcodeproj/project.pbxproj | sort -u
# Expected: com.glikfamily.audioura and 4HGRU6TKGQ
```

If 3a fails or 3e shows FOUND, STOP and report to iOS Q.

## Step 4 — [MAC MINI Q] pod install

```bash
cd ~/Development/Audioura-build/development/audio_tour_app/ios
pod install
```

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

**Test 1 — Local mode (on WiFi):**
1. Launch app → Home tab.
2. **Expected:** Tours load from `192.168.0.218`. No errors.
3. About tab → mode shows **Local** by default.

**Test 2 — Local WiFi tour generation:**
1. On WiFi, generate a new tour.
2. **Expected:** Tour generates, status updates, tour appears in Listen tab.

**Test 3 — Cloud mode:**
1. About tab → switch to **Cloud**, enter cloud base URL.
2. Enter the **API Key** in the API Key field.
3. Leave gateway path routing checkbox **unchecked**.
4. Generate or download an existing tour.
5. **Expected:** Tour downloads/generates and plays.

**Test 4 — Cloud multi-language (if available):**
1. In Cloud mode, generate a tour and request a translation.
2. **Expected:** Translation completes (uses cloud translation service, not LAN IP).
3. Mark NOT_TESTED if translation not exercised — not a blocker.

**Test 5 — A#78 regression (mic):**
1. Audio mode → Listen tab → tap microphone icon.
2. **Expected:** Listening dialog opens. No "Microphone permission required" snackbar.

**Test 6 — A#77b regression (Refresh):**
1. Listen tab → tap Refresh.
2. **Expected:** List reloads, no black screen.

**Test 7 — General regression:**
1. Open a tour → audio plays.
2. Open a news article → loads.
3. POI map icon → TourMapScreen opens.

Tell Q "Smoke test passes, proceed to Step 7" when done.

## Step 7 — [MAC MINI Q] No pubspec commit needed — version already at 2.1.1+3

```bash
cd ~/Development/Audioura-build
git status
# Expected: nothing to commit (or only untracked files)
git log --oneline -3
# Confirm 049bb35 or later is present
```

If `git status` shows modified tracked files — STOP and report before committing anything.

## Step 8 — [MAC MINI Q] Copy results and eject

```bash
echo "A#80 Results:" > ~/Desktop/a80_results.txt
echo "Date: $(date)" >> ~/Desktop/a80_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a80_results.txt
echo "Local mode tours load (Test 1): [YES/NO]" >> ~/Desktop/a80_results.txt
echo "Local WiFi tour generation (Test 2): [YES/NO]" >> ~/Desktop/a80_results.txt
echo "Cloud mode tour download/generate (Test 3): [YES/NO]" >> ~/Desktop/a80_results.txt
echo "Cloud multi-language (Test 4): [YES/NO/NOT_TESTED]" >> ~/Desktop/a80_results.txt
echo "Mic no permission snackbar (Test 5): [YES/NO]" >> ~/Desktop/a80_results.txt
echo "Listen Refresh no black screen (Test 6): [YES/NO]" >> ~/Desktop/a80_results.txt
echo "General regression clean (Test 7): [YES/NO]" >> ~/Desktop/a80_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a80_results.txt
cp ~/Desktop/a80_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 9 — [MAC MINI Q] Report Results

> "Assignment 80 complete. Build: [SUCCESS/FAILED]. Local mode: [YES/NO]. Local generation: [YES/NO]. Cloud mode: [YES/NO]. Cloud translation: [YES/NO/NOT_TESTED]. Mic regression: [YES/NO]. Refresh regression: [YES/NO]. General regression: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

## Step 10 — [SIR MICHAEL, back on Windows] Sync

```cmd
cd C:\Users\micha\eclipse-workspace\AudioTours\development
git pull origin services-migration
```
Verify `audio_tour_app\pubspec.yaml` shows `version: 2.1.1+3`.

---

# T: 06/2026 - A#79 — Build v2.1.1+1 iOS (Dual-Environment Parity with Android)

**Goal:** Build v2.1.1+1 on iPhone. This is a **parity build** — all Dart changes are already in the shared codebase from Android Q's work. iOS task is to build the same commit and verify iOS-specific behaviour.

**What this build delivers:**
- Dual-environment networking: Local WiFi (default, `192.168.0.218`) and Cloud (user-supplied HTTPS URL)
- About screen: Local/Cloud toggle + cloud base URL field + gateway path routing checkbox
- `Endpoints` resolver — all service calls route through a single resolver based on the active mode
- A#77b Listen page Refresh fix (already shipped in prior iOS build, regression check only)
- A#78 mic permission fix (already shipped in prior iOS build, regression check only)
- `NSLocalNetworkUsageDescription` added to `Info.plist` for iOS 14+ local network hygiene (commit `52d8282`)

**Key fact:** No Dart re-implementation needed. All `lib/` changes are shared Flutter code already committed by Android Q. iOS builds the same source and gets everything automatically.

**Roles:**
- **[SIR MICHAEL]** — orchestrator. Switches KVM, runs smoke test, syncs Windows afterward.
- **[MAC MINI Q]** — pulls latest, verifies signing, runs `pod install`, builds, installs, commits nothing (pubspec already at `2.1.1+1`).

**Version target:** v2.1.1+1  **Branch:** `services-migration`

---

## Step 0 — [SIR MICHAEL] Eject USB, carry to Mac Mini, switch KVM

## Step 1 — [SIR MICHAEL on Mac Mini] Launch Q

Paste:
> Read `@/Volumes/USB DISK/Audioura/assignments/mac_mini_assignments.md` and execute the A#79 assignment at the top. Follow STOP conditions; skip steps labelled `[SIR MICHAEL]`.

## Step 2 — [MAC MINI Q] Pull latest

```bash
cd ~/Development/Audioura-build
git pull origin services-migration
```

**Expected:** fast-forward to at least commit `52d8282` (NSLocalNetworkUsageDescription) which is on top of `4c8c040` (v2.1.1+1 Android fixes).

## Step 3 — [MAC MINI Q] Spot-check BEFORE building ⚠️ REQUIRED

```bash
cd ~/Development/Audioura-build/development/audio_tour_app

# 3a — pubspec at 2.1.1+1
grep "^version:" pubspec.yaml
# Expected: version: 2.1.1+1

# 3b — NSLocalNetworkUsageDescription present in Info.plist
grep -n "NSLocalNetworkUsageDescription" ios/Runner/Info.plist
# Expected: 1 match

# 3c — Endpoints class exists (dual-environment resolver)
grep -rn "class Endpoints" lib/
# Expected: 1 match in lib/services/ or lib/config/

# 3d — About screen has Local/Cloud toggle
grep -rn "Local\|Cloud\|cloudUrl\|cloud_url" lib/screens/about_screen.dart | head -5
# Expected: several matches confirming toggle UI is present

# 3e — signing intact
grep -E 'PRODUCT_BUNDLE_IDENTIFIER|DEVELOPMENT_TEAM' \
  ios/Runner.xcodeproj/project.pbxproj | sort -u
# Expected: com.glikfamily.audioura and 4HGRU6TKGQ
```

If 3a or 3b fails, STOP and report to iOS Q. If 3c or 3d shows nothing, STOP — the shared Dart may not have pulled correctly.

## Step 4 — [MAC MINI Q] pod install

```bash
cd ~/Development/Audioura-build/development/audio_tour_app/ios
pod install
```

No new pods expected, but required after any pull that touches the Flutter plugin graph.

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

**Test 1 — Local mode (default, on WiFi):**
1. Launch app → Home tab.
2. **Expected:** Tours load from local server (`192.168.0.218`). No errors.
3. About tab → confirm mode shows **Local** by default.

**Test 2 — About screen Local/Cloud toggle:**
1. About tab → find the Local/Cloud environment toggle.
2. **Expected:** Toggle is present, default is Local.
3. Switch to **Cloud** → a cloud base URL input field appears.
4. Leave the "gateway path routing" checkbox **unchecked**.
5. Switch back to **Local** → field disappears.

**Test 3 — Cloud mode, existing tour download (off WiFi if possible):**
1. Switch to **Cloud** in About tab, paste the cloud base URL: `https://[your-cloud-run-url]`.
2. Download an **existing** tour (do not attempt to generate a new one — cloud generation not ready).
3. **Expected:** Tour downloads from R2 storage and appears in Listen tab.
4. Tap tour → audio plays.
5. ⚠️ If no cloud URL is available yet, mark this test NOT_TESTED — not a blocker.

**Test 4 — A#78 regression (mic):**
1. Audio mode → Listen tab → tap microphone icon.
2. **Expected:** Listening dialog opens. No "Microphone permission required" snackbar.

**Test 5 — A#77b regression (Refresh):**
1. Listen tab → tap Refresh.
2. **Expected:** List reloads in place. No black screen.

**Test 6 — General regression:**
1. Open a tour → audio plays.
2. Open a news article → loads.
3. POI map icon → TourMapScreen opens.

Tell Q "Smoke test passes, proceed to Step 7" when done. Report which tests passed/failed/not_tested.

## Step 7 — [MAC MINI Q] No pubspec commit needed — version already at 2.1.1+1

The pubspec was already bumped by Android Q. Do NOT bump it again.

Verify remote is up to date:
```bash
cd ~/Development/Audioura-build
git status
# Expected: nothing to commit, working tree clean (or only untracked files)
git log --oneline -3
# Confirm 52d8282 (NSLocalNetworkUsageDescription) is present
```

If `git status` shows modified tracked files — STOP and report to iOS Q before committing anything.

## Step 8 — [MAC MINI Q] Copy results and eject

```bash
echo "A#79 Results:" > ~/Desktop/a79_results.txt
echo "Date: $(date)" >> ~/Desktop/a79_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a79_results.txt
echo "Local mode tours load (Test 1): [YES/NO]" >> ~/Desktop/a79_results.txt
echo "About Local/Cloud toggle present (Test 2): [YES/NO]" >> ~/Desktop/a79_results.txt
echo "Cloud mode tour download+play (Test 3): [YES/NO/NOT_TESTED]" >> ~/Desktop/a79_results.txt
echo "Mic no permission snackbar (Test 4): [YES/NO]" >> ~/Desktop/a79_results.txt
echo "Listen Refresh no black screen (Test 5): [YES/NO]" >> ~/Desktop/a79_results.txt
echo "General regression clean (Test 6): [YES/NO]" >> ~/Desktop/a79_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a79_results.txt
cp ~/Desktop/a79_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 9 — [MAC MINI Q] Report Results

> "Assignment 79 complete. Build: [SUCCESS/FAILED]. Local mode works: [YES/NO]. Local/Cloud toggle present: [YES/NO]. Cloud download: [YES/NO/NOT_TESTED]. Mic regression: [YES/NO]. Refresh regression: [YES/NO]. General regression: [YES/NO]. Overall: [SUCCESS/PARTIAL/FAILED]."

## Step 10 — [SIR MICHAEL, back on Windows] Sync

```cmd
cd C:\Users\micha\eclipse-workspace\AudioTours\development
git pull origin services-migration
```
Verify `audio_tour_app\pubspec.yaml` shows `version: 2.1.1+1`.

---

# T: 06/2026 - A#78 — Build v1.2.9+71 (Listen Page Microphone Voice Search Fix)

**Goal:** Build v1.2.9+71 on iPhone. Two commits already in `services-migration` — `df6b61b` (A#78 fix) and `92d0175` (A#78b import cleanup per Claude review Q2).

**What changed:**

| Version | File | Change | Commit |
|---------|------|--------|--------|
| +71 | `my_tours_screen.dart` | Removed redundant `Permission.microphone.request()` block from `_startVoiceSearch()` | `df6b61b` |
| +71 | `my_tours_screen.dart` | Removed now-dead `permission_handler` import (line 8) — Claude review Q2 | `92d0175` |
| +71 | `pubspec.yaml` | `1.2.9+70` → `1.2.9+71` | Mac Mini bumps |

**Root cause:** `_setupVoiceCommands()` calls `_speechToText.initialize()` which internally acquires microphone permission via iOS's speech recognition framework. Then `_startVoiceSearch()` called `Permission.microphone.request()` again via the `permission_handler` plugin — a different permission pathway. iOS considers the permission already handled; `permission_handler` sees it as denied from its own perspective and returns not-granted. Fix: remove the redundant block. `_speechEnabled == true` (set by `initialize()`) is sufficient proof the mic is available.

**Roles:**
- **[SIR MICHAEL]** — orchestrator. Switches KVM, runs smoke test, syncs Windows afterward.
- **[MAC MINI Q]** — pulls latest, bumps pubspec, builds, commits.

**Version target:** v1.2.9+71  **Branch:** `services-migration`

---

## Step 0 — [SIR MICHAEL] Eject USB, carry to Mac Mini, switch KVM

## Step 1 — [SIR MICHAEL on Mac Mini] Launch Q

Paste:
> Read `@/Volumes/USB DISK/Audioura/assignments/mac_mini_assignments.md` and execute the A#78 assignment at the top. Follow STOP conditions; skip steps labelled `[SIR MICHAEL]`.

## Step 2 — [MAC MINI Q] Pull latest

```bash
cd ~/Development/Audioura-build
git pull origin services-migration
```

**Expected:** fast-forward that includes commit `df6b61b` (A#78 fix).

## Step 3 — [MAC MINI Q] Spot-check BEFORE building ⚠️ REQUIRED

```bash
cd ~/Development/Audioura-build/development/audio_tour_app

# 3a — pubspec at +70
grep "^version:" pubspec.yaml
# Expected: version: 1.2.9+70

# 3b — confirm Permission.microphone.request() block is GONE
grep -n "microphone.request\|Microphone permission required" lib/screens/my_tours_screen.dart
# Expected: zero matches

# 3c — confirm _speechEnabled guard still present
grep -n "_speechEnabled" lib/screens/my_tours_screen.dart
# Expected: at least 2 matches (declaration + guard in _startVoiceSearch)

# 3d — confirm permission_handler import is GONE (Claude review Q2 — commit 92d0175)
grep -n "permission_handler" lib/screens/my_tours_screen.dart
# Expected: zero matches
```

If 3b or 3d shows any match, STOP and report.

## Step 4 — [MAC MINI Q] Bump pubspec to +71

```bash
sed -i '' 's/^version: 1.2.9+70/version: 1.2.9+71/' pubspec.yaml
grep "^version:" pubspec.yaml
# Must print: version: 1.2.9+71
```

## Step 5 — [MAC MINI Q] Verify Xcode signing

```bash
grep -E 'PRODUCT_BUNDLE_IDENTIFIER|DEVELOPMENT_TEAM' \
  ios/Runner.xcodeproj/project.pbxproj | sort -u
```
**Expected:** `com.glikfamily.audioura` and `4HGRU6TKGQ`

## Step 6 — [MAC MINI Q] Clean rebuild, install, launch

```bash
cd ~/Development/Audioura-build/development/audio_tour_app
flutter clean && flutter pub get
cd "/Volumes/USB DISK/Audioura/scripts"
./build_install_launch.sh
```

**Expected:** `FINAL VERDICT: SUCCESS`. STOP and tell Sir Michael.

## Step 7 — [SIR MICHAEL] Smoke test on iPhone (STOP HERE FOR Q)

**Test 1 — Microphone voice search (primary fix):**
1. Audio mode → Listen tab.
2. Tap the **microphone icon** in the AppBar.
3. **Expected:** Listening dialog appears immediately. No "Microphone permission required" snackbar.
4. Say something (e.g. "Boston"). Expected: dialog closes, article list filters.
5. Check debug log: `LISTEN: Voice search ...` line should appear.

**Test 1b — Dialog timeout / no-speech (Claude review Q3 fast follow — observe only, not a blocker):**
1. Tap microphone icon → Listening dialog appears.
2. Say nothing for ~10 seconds.
3. **Observe:** Does the dialog auto-close, or does it stay open with a permanent spinner? Log the result.
4. Not a blocker for v1.2.9+71 — report outcome for A#79 planning.

**Test 2 — Regression:**
1. Listen page Refresh → list reloads, no black screen (A#77b regression).
2. Open a tour → audio plays. Open a news article → loads. POI map icon → TourMapScreen opens.

Tell Q "Smoke test passes, proceed to Step 8" if Tests 1 and 2 pass (Test 1b is observe-only).

## Step 8 — [MAC MINI Q] Commit and push

```bash
cd ~/Development/Audioura-build
git add development/audio_tour_app/pubspec.yaml
git commit -m "v1.2.9+71 — A#78 bump pubspec (mic fix in df6b61b)"
git push origin services-migration
```

## Step 9 — [MAC MINI Q] Copy results and eject

```bash
echo "A#78 Results:" > ~/Desktop/a78_results.txt
echo "Date: $(date)" >> ~/Desktop/a78_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a78_results.txt
echo "Mic dialog opens without permission error: [YES/NO]" >> ~/Desktop/a78_results.txt
echo "Voice search filters articles: [YES/NO]" >> ~/Desktop/a78_results.txt
echo "Dialog auto-closes on 10s timeout (observe only): [YES/NO/NOT_TESTED]" >> ~/Desktop/a78_results.txt
echo "Listen Refresh no black screen (A#77b regression): [YES/NO]" >> ~/Desktop/a78_results.txt
echo "git push: [SUCCESS/FAILED]" >> ~/Desktop/a78_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a78_results.txt
cp ~/Desktop/a78_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 10 — [MAC MINI Q] Report Results

> "Assignment 78 complete. Build: [SUCCESS/FAILED]. Mic opens without error: [YES/NO]. Voice search works: [YES/NO]. Dialog timeout auto-close: [YES/NO/NOT_TESTED]. A#77b regression: [YES/NO]. git push: [SUCCESS/FAILED]. Overall: [SUCCESS/PARTIAL/FAILED]."

## Step 11 — [SIR MICHAEL, back on Windows] Sync

```cmd
cd C:\Users\micha\eclipse-workspace\AudioTours\development
git pull origin services-migration
```
Verify `pubspec.yaml` shows `version: 1.2.9+71`.

---

# T: 06/2026 - A#77b — Build v1.2.9+70 (Listen Page Refresh Black Screen — Real Fix)

**Goal:** Build v1.2.9+70 on iPhone. Two commits are already in `services-migration` — `4dba042` (A#77 original, +69) and `4948178` (A#77b real fix, +70). Mac Mini needs to pull, bump pubspec to +70, build, and smoke test.

**Background — why two commits:**
- A#77 (+69) removed `setState(_isLoading=true)` from the Newsletter screen's Refresh handler in `home_screen.dart`. That was a correct cleanup but NOT the cause of the black screen.
- The actual black screen came from the **Listen page** (`my_tours_screen.dart`) — its `_manualRefresh()` called `Navigator.of(context).pop()` to remove the screen, then tried `pushReplacement` in a `addPostFrameCallback`. But once popped, `mounted == false`, so the re-push never ran. Screen gone, nothing replaced it → black screen.
- A#77b (`4948178`) replaces that broken pop/push dance with a simple `await _loadAppMode()` in-place reload.

**What changed:**

| Version | File | Change |
|---------|------|--------|
| +69 | `home_screen.dart` | Removed `setState(() { _isLoading = true; })` from newsletter Refresh in `_buildNewsletterView` (correct cleanup, not the black screen cause) |
| +69 | `pubspec.yaml` | `1.2.9+68` → `1.2.9+69` |
| +70 | `my_tours_screen.dart` | `_manualRefresh()` replaced — no more pop/pushReplacement. Now: log + `if (!mounted) return` + `await _loadAppMode()` |
| +70 | `pubspec.yaml` | `1.2.9+69` → `1.2.9+70` |

**Root cause of black screen:** `_manualRefresh()` called `Navigator.of(context).pop()` first, which disposed the State. The `addPostFrameCallback` condition `if (mounted)` then evaluated false — the re-push never ran. The Listen page was gone with nothing in its place.

**Roles:**
- **[SIR MICHAEL]** — orchestrator. Switches KVM, runs smoke test, syncs Windows afterward.
- **[MAC MINI Q]** — pulls latest, bumps pubspec, builds, commits.

**Version target:** v1.2.9+70  **Branch:** `services-migration`  **Time:** ~20 minutes

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

# 3a — pubspec still at +69 (not yet bumped to +70)
grep "^version:" pubspec.yaml
# Expected: version: 1.2.9+69

# 3b — confirm NEW _manualRefresh is in place (in-place reload, no pop)
grep -n "_manualRefresh\|_loadAppMode\|addPostFrameCallback" lib/screens/my_tours_screen.dart
# Expected:
#   line ~53: Future<void> _manualRefresh() async {
#   line ~56: await _loadAppMode();
#   line ~62: _loadAppMode();   (from initState)
#   NO addPostFrameCallback line

# 3c — confirm Navigator.of(context).pop() is GONE from _manualRefresh
grep -n "Navigator.of(context).pop" lib/screens/my_tours_screen.dart
# Expected: zero matches (or only in dialog handlers, not in _manualRefresh)

# 3d — confirm LISTEN log line is present
grep -n "LISTEN: Manual refresh triggered" lib/screens/my_tours_screen.dart
# Expected: 1 match
```

If 3b shows `addPostFrameCallback` or 3c shows a pop in `_manualRefresh`, STOP and report.

## Step 4 — [MAC MINI Q] Bump pubspec to +70

```bash
cd ~/Development/Audioura-build/development/audio_tour_app
sed -i '' 's/^version: 1.2.9+69/version: 1.2.9+70/' pubspec.yaml
grep "^version:" pubspec.yaml
# Must print: version: 1.2.9+70
```

If grep does not show `+70`, STOP and report.

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

**Test 1 — Listen page Refresh (primary fix):**
1. Switch to **Audio mode** (so Listen tab shows news articles).
2. Go to **Listen tab**.
3. Tap **Refresh** (the refresh icon in the top AppBar of the Listen page).
4. **Expected:** Article list reloads in place. No black screen. Screen stays intact.
5. Tap Refresh a second time — must stay stable.
6. Black screen or freeze = fix did not land. STOP.
7. Open **About → Debug Log**. Confirm line `LISTEN: Manual refresh triggered` appears, followed by `LISTEN: Loading N articles from storage` / `LISTEN: Successfully loaded N articles`. Absence of these log lines = handler still broken.

**Test 1b — Refresh while in selection mode (Claude Q3 hardening check):**
1. On the Listen tab (Audio mode), tap the checklist icon to enter **Select Articles** mode.
2. Select one or more articles.
3. Tap **Refresh**.
4. **Expected:** Selection mode exits cleanly, list reloads, no crash, no RangeError. If app crashes or freezes — report it (pre-existing risk, not a blocker for v1.2.9+70 but must be logged).

**Test 2 — Newsletter screen Refresh still works:**
1. Tap the **Home/Newsletter tab** (Audio mode).
2. Tap **Refresh** in the newsletter screen (top AppBar).
3. **Expected:** Newsletter list reloads. No black screen.

**Test 3 — Regression:**
1. Open a tour → confirm it still plays audio normally.
2. News tab → tap an article → confirm it loads (no white screen).
3. POI map icon → confirm TourMapScreen still opens.

Tell Q "Smoke test passes, proceed to Step 8" if all three pass.

## Step 8 — [MAC MINI Q] Commit and push (only after Sir Michael confirms Step 7 passed)

```bash
cd ~/Development/Audioura-build
git add development/audio_tour_app/pubspec.yaml
git commit -m "v1.2.9+70 — A#77b bump pubspec (_manualRefresh in-place reload fix)"
git push origin services-migration
```

**Expected:** Push succeeds. If blocked by GitHub secret scanning — STOP and report. Never click "Allow secret".

## Step 9 — [MAC MINI Q] Copy results and eject

```bash
echo "A#77b Results:" > ~/Desktop/a77b_results.txt
echo "Date: $(date)" >> ~/Desktop/a77b_results.txt
echo "Build: [SUCCESS/FAILED]" >> ~/Desktop/a77b_results.txt
echo "Listen page Refresh no black screen: [YES/NO]" >> ~/Desktop/a77b_results.txt
echo "LISTEN: Manual refresh triggered log present: [YES/NO]" >> ~/Desktop/a77b_results.txt
echo "Refresh while in selection mode no crash: [YES/NO/NOT_TESTED]" >> ~/Desktop/a77b_results.txt
echo "Newsletter Refresh no black screen: [YES/NO]" >> ~/Desktop/a77b_results.txt
echo "Tour audio plays (no regression): [YES/NO]" >> ~/Desktop/a77b_results.txt
echo "News article loads (no regression): [YES/NO]" >> ~/Desktop/a77b_results.txt
echo "POI map opens (no regression): [YES/NO]" >> ~/Desktop/a77b_results.txt
echo "git push: [SUCCESS/FAILED]" >> ~/Desktop/a77b_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a77b_results.txt
cp ~/Desktop/a77b_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 10 — [MAC MINI Q] Report Results

> "Assignment 77b complete. Build: [SUCCESS/FAILED]. Listen page Refresh no black screen: [YES/NO]. LISTEN log present: [YES/NO]. Newsletter Refresh clean: [YES/NO]. git push: [SUCCESS/FAILED]. Overall: [SUCCESS/PARTIAL/FAILED]."

## Step 11 — [SIR MICHAEL, back on Windows] Sync

```cmd
cd C:\Users\micha\eclipse-workspace\AudioTours\development
git pull origin services-migration
```

Verify `audio_tour_app\pubspec.yaml` shows `version: 1.2.9+70`.

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
