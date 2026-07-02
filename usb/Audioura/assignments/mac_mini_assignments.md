# Mac Mini Assignment Instructions
## iOS Development Task Execution

# T: 06/2026 - A#85 — Build v2.2.0+1 on iPhone + TestFlight Upload (Storied Release)

**Goal:** Build v2.2.0+1 from the **`storied` branch**, install on iPhone for smoke test, then upload to TestFlight. This supersedes A#84 (v2.1.1+18, `services-migration`, never built). The `storied` branch includes everything from v2.1.1+18 PLUS the new Storied features.

⚠️ **CRITICAL DIFFERENCES from all previous assignments:**
- Branch is **`storied`** — NOT `services-migration`
- Flutter app root is **`~/Development/Audioura-build/audio_tour_app/`** — NOT `development/audio_tour_app/`
- Build command is `flutter build ipa --release` (App Store archive) — NOT `build_install_launch.sh`
- `--dart-define=GATEWAY_API_KEY="aura-gw-360721-880288"` is REQUIRED — without it every cloud call returns 401

**What this delivers over v1.2.9+71 (everything since last iPhone build):**
- All v2.1.1+18 Beta features: cloud-first defaults, baked-in API key, all cloud URLs sending `X-API-Key`, translation modal, overflow menu (⋮), Report tour, Treats tab, Account deletion iOS flow, 402 handling, full URL audit
- **NEW — Onboarding Personalization:** First launch shows "What brings you here?" with 4 choices (🎨 Art & Culture, 📖 History, 👨‍👩‍👧 Family Fun, ✈️ First-time Visitor + Skip). Saves `narrative_tone` → sent in tour generation. Never shows again after first choice.
- **NEW — App Attestation Dart side:** `AppAttestationService` uses MethodChannel `com.audioura.app/attestation`. iOS native Swift side NOT YET implemented — `MissingPluginException` handled gracefully (logs, returns null, never blocks the build or any feature).

**Target commit:** `2962fe5` (or later — `0045823` is on top)
**Version:** `2.2.0+1`  **Branch:** `storied`
**iOS bundle ID:** `com.glikfamily.audioura` (unchanged)
**No pubspec bump needed.**

**Roles:**
- **[SIR MICHAEL]** — App Store Connect setup (Step 0, must be done BEFORE upload), smoke test, TestFlight activation.
- **[MAC MINI Q]** — checkout `storied` branch, build release archive, install on device, upload to TestFlight.

---

## Step 0 — [SIR MICHAEL] App Store Connect setup ⚠️ DO THIS BEFORE MAC MINI UPLOAD STEP

**If not already done from A#84 prep:**

1. Go to **appstoreconnect.apple.com** → sign in with `glikfamily@gmail.com`
2. Click **+** → New App:
   - Platform: **iOS**
   - Name: **Audioura**
   - Primary Language: **English (U.S.)**
   - Bundle ID: **com.glikfamily.audioura**
   - SKU: **audioura-1**
3. Complete **App Privacy** details (required before any upload)
4. Generate an **App-Specific Password** at **appleid.apple.com** → Sign-In and Security → App-Specific Passwords → Generate → label "Mac Mini Audioura Upload" → save it

Tell Mac Mini Q the App-Specific Password when it reaches Step 10.

## Step 1 — [SIR MICHAEL] Eject USB, carry to Mac Mini, switch KVM

## Step 2 — [SIR MICHAEL on Mac Mini] Launch Q

Paste:
> Read `@/Volumes/USB DISK/Audioura/assignments/mac_mini_assignments.md` and execute the A#85 assignment at the top. Follow STOP conditions; skip steps labelled `[SIR MICHAEL]`.

## Step 3 — [MAC MINI Q] Checkout `storied` branch

```bash
cd ~/Development/Audioura-build
git fetch origin
git checkout storied
git pull origin storied
```

**Expected:** HEAD at `2962fe5` or later (`0045823`).

If `git checkout storied` fails with "local changes" — STOP and report. Do not force.

## Step 4 — [MAC MINI Q] Spot-check BEFORE building ⚠️ REQUIRED

```bash
# NOTE: storied branch root is audio_tour_app/ (NOT development/audio_tour_app/)
cd ~/Development/Audioura-build/audio_tour_app

# 4a — pubspec at 2.2.0+1
grep "^version:" pubspec.yaml
# Expected: version: 2.2.0+1

# 4b — onboarding screen exists
ls lib/screens/onboarding_screen.dart 2>/dev/null && echo FOUND || echo MISSING
# Expected: FOUND

# 4c — GATEWAY_API_KEY dart-define wired up
grep -rn "GATEWAY_API_KEY\|fromEnvironment" lib/config/ | head -5
# Expected: at least 1 match

# 4d — no hardcoded 5012/5017 URLs
grep -rn "5012\|5017" lib/screens/tour_generator_screen.dart
# Expected: zero matches

# 4e — signing intact
grep -E 'PRODUCT_BUNDLE_IDENTIFIER|DEVELOPMENT_TEAM' \
  ios/Runner.xcodeproj/project.pbxproj | sort -u
# Expected: com.glikfamily.audioura and 4HGRU6TKGQ

# 4f — NSLocalNetworkUsageDescription present
grep -n "NSLocalNetworkUsageDescription" ios/Runner/Info.plist
# Expected: 1 match
```

If 4a fails — STOP, wrong branch or commit.
If 4b shows MISSING — STOP, onboarding feature not present.
If 4d shows any matches — STOP, hardcoded URLs still present.

## Step 5 — [MAC MINI Q] pod install

```bash
cd ~/Development/Audioura-build/audio_tour_app/ios
pod install
cd ..
```

⚠️ `pod install` is especially important here — switching branches may have changed the pod state.

## Step 6 — [MAC MINI Q] Verify Xcode signing for distribution

```bash
open ~/Development/Audioura-build/audio_tour_app/ios/Runner.xcworkspace
```

In Xcode:
1. Select **Runner** target → **Signing & Capabilities**
2. Confirm **Automatically manage signing** ✅
3. Confirm **Team: Mikhail Glik (4HGRU6TKGQ)**
4. Confirm **Bundle Identifier: com.glikfamily.audioura**
5. Quit Xcode

## Step 7 — [MAC MINI Q] Build release archive (IPA)

```bash
cd ~/Development/Audioura-build/audio_tour_app
flutter clean && flutter pub get
flutter build ipa --release --dart-define=GATEWAY_API_KEY="aura-gw-360721-880288"
```

**Expected:** Build completes with:
```
Built build/ios/ipa/audioura.ipa
```

`flutter analyze` warnings in dead files (`audio_handler.dart`, `map_page.dart`, `subscription_management_screen.dart`, `widget_test.dart`) — **non-blocking**, proceed.

If build FAILS with signing error:
```bash
open ios/Runner.xcworkspace
```
Runner → Signing & Capabilities → Automatically manage signing ✅ → Team: 4HGRU6TKGQ → quit Xcode → re-run Step 7.

If `MissingPluginException` appears in build output for `com.audioura.app/attestation` — this is **expected and non-blocking**. The iOS native side is not yet implemented. Proceed.

## Step 8 — [MAC MINI Q] Install on iPhone for smoke test

```bash
xcrun devicectl device install app \
  --device F9D6F807-D301-59EE-B574-5747D617D82C \
  build/ios/ipa/audioura.ipa
```

If `devicectl` fails, use Xcode → Window → Devices and Simulators → drag IPA onto device.

STOP and tell Sir Michael the build is installed. Wait for smoke test.

## Step 9 — [SIR MICHAEL] Smoke test on iPhone ⚠️ STOP HERE FOR Q

⚠️ **Uninstall the old app first if present** — onboarding only shows on fresh install.

**Test 1 — Onboarding (NEW — primary test):**
1. Launch app for the first time (fresh install).
2. **Expected:** "Welcome to Audioura / What brings you here?" screen appears with 4 choices.
3. Select one (e.g. 📖 History).
4. **Expected:** Onboarding dismisses, app proceeds normally.
5. Kill app and relaunch — **Expected:** onboarding does NOT show again.

**Test 2 — Cloud tour generation:**
1. App should default to Cloud mode — no manual URL/key entry needed.
2. Generate a tour → no 401, tour generates and opens automatically.

**Test 3 — Cloud news/newsletter:**
Audio mode → process newsletter → download article → playback works.

**Test 4 — Translation:**
Generate a tour with translation → works. If unavailable → modal dialog shown (not silent fallback).

**Test 5 — Account deletion:**
About → Delete My Account → confirmation → tap Delete → iOS pops to root with "Please reopen the app to finish resetting." ⚠️ Only test with throwaway account.

**Test 6 — Report tour:**
Listen page → overflow menu (⋮) on a tour → Report → email compose opens prefilled.

**Test 7 — Treats tab:**
Navigate to Treats → "Samples for the future" banner + real content visible.

**Test 8 — Map/POI:**
Open a walking tour → tap POI map icon → TourMapScreen opens.

**Test 9 — Mic/Voice:**
Listen tab → tap mic → listening dialog opens, no permission snackbar.

Tell Q "Smoke test passes, proceed to Step 10" when done. Report any failures.

## Step 10 — [MAC MINI Q] Upload to TestFlight ⚠️ WAIT FOR SIR MICHAEL'S APP-SPECIFIC PASSWORD

```bash
# Sir Michael provides <app-specific-password> from Step 0
xcrun altool --upload-app \
  -f build/ios/ipa/audioura.ipa \
  -t ios \
  -u glikfamily@gmail.com \
  -p <app-specific-password>
```

**Alternative — Xcode Organizer (if altool fails):**
```bash
open ios/Runner.xcworkspace
```
Xcode → Product → Archive → Window → Organizer → select `2.2.0 (1)` archive → Distribute App → App Store Connect → Upload → Next → Next → Upload.

STOP and report upload status to Sir Michael.

## Step 11 — [SIR MICHAEL] TestFlight activation

After upload succeeds:
1. **appstoreconnect.apple.com** → Audioura → **TestFlight** tab
2. Wait for build processing (~5–15 minutes)
3. Once processed → click build → **Add to Group** → add yourself as internal tester
4. Install via TestFlight app on iPhone
5. Verify version shows `2.2.0 (1)` in TestFlight

## Step 12 — [MAC MINI Q] Copy results and eject

```bash
echo "A#85 Results:" > ~/Desktop/a85_results.txt
echo "Date: $(date)" >> ~/Desktop/a85_results.txt
echo "Branch: storied" >> ~/Desktop/a85_results.txt
echo "Release archive built: [YES/NO]" >> ~/Desktop/a85_results.txt
echo "Test 1  Onboarding shows on fresh install: [YES/NO]" >> ~/Desktop/a85_results.txt
echo "Test 1b Onboarding does NOT show on relaunch: [YES/NO]" >> ~/Desktop/a85_results.txt
echo "Test 2  Cloud tour generation (no 401): [YES/NO]" >> ~/Desktop/a85_results.txt
echo "Test 3  Cloud news/newsletter: [YES/NO]" >> ~/Desktop/a85_results.txt
echo "Test 4  Translation + modal dialog: [YES/NO]" >> ~/Desktop/a85_results.txt
echo "Test 5  Account deletion iOS pop: [YES/NO/NOT_TESTED]" >> ~/Desktop/a85_results.txt
echo "Test 6  Report tour email: [YES/NO]" >> ~/Desktop/a85_results.txt
echo "Test 7  Treats tab: [YES/NO]" >> ~/Desktop/a85_results.txt
echo "Test 8  Map/POI: [YES/NO]" >> ~/Desktop/a85_results.txt
echo "Test 9  Mic/Voice: [YES/NO]" >> ~/Desktop/a85_results.txt
echo "TestFlight upload: [SUCCESS/FAILED/PENDING]" >> ~/Desktop/a85_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a85_results.txt
cp ~/Desktop/a85_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 13 — [MAC MINI Q] Report Results

> "Assignment 85 complete. Branch: storied. Archive built: [YES/NO]. Onboarding shows (T1): [YES/NO]. Onboarding no repeat (T1b): [YES/NO]. Cloud generation (T2): [YES/NO]. Cloud news (T3): [YES/NO]. Translation modal (T4): [YES/NO]. Account deletion (T5): [YES/NO/NOT_TESTED]. Report tour (T6): [YES/NO]. Treats (T7): [YES/NO]. Map/POI (T8): [YES/NO]. Mic (T9): [YES/NO]. TestFlight upload: [SUCCESS/FAILED/PENDING]. Overall: [SUCCESS/PARTIAL/FAILED]."

## Step 14 — [SIR MICHAEL, back on Windows] Sync

```cmd
cd C:\Users\micha\eclipse-workspace\AudioTours\development
git fetch origin
git checkout storied
git pull origin storied
```

Verify `audio_tour_app\pubspec.yaml` shows `version: 2.2.0+1`.

---

# T: 06/2026 - A#84 — Build v2.1.1+18 App Store (services-migration) — SUPERSEDED by A#85
**Status**: ⏭️ SUPERSEDED — never built. All v2.1.1+18 features included in A#85 (storied branch).

---

# T: 06/2026 - A#83 — Build v2.1.1+9 — SUPERSEDED by A#85
**Status**: ⏭️ SUPERSEDED — never built. All changes included in A#85.

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
