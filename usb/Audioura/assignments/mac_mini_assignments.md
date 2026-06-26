# Mac Mini Assignment Instructions
## iOS Development Task Execution

# T: 06/2026 - A#84 — Build v2.1.1+18 for App Store / TestFlight (First App Store Release)

**Goal:** Build v2.1.1+18 as a **release archive** for App Store Connect / TestFlight upload. This is NOT a dev install build — it produces a signed IPA for submission. iPhone has never been built past v1.2.9+71, so this single assignment also serves as the first full production build.

⚠️ **This build is DIFFERENT from all previous assignments:**
- Uses `flutter build ipa --release` (NOT `build_install_launch.sh`)
- Requires `--dart-define=GATEWAY_API_KEY="aura-gw-360721-880288"` — without it every cloud call returns 401
- Must be signed with distribution profile (not development)
- Final step is upload to App Store Connect via Xcode Organizer or `xcrun altool`

**What this build delivers over v1.2.9+71 (all versions since last iPhone build):**
- Fresh install defaults to Cloud mode — no manual URL/key entry needed
- API key baked in via `--dart-define` (not stored in prefs)
- All cloud HTTP requests send `X-API-Key` (tours-near, downloads, status, newsletters, everything)
- Friendly error messages — no raw 401 shown to users
- Translation failure modal dialog
- Listen page overflow menu (⋮) — translate/edit/delete/report options
- Report this tour — prefilled mailto from overflow menu
- Account deletion — iOS pops to root with "Please reopen" message
- Treats tab — "Samples for the future" banner, real backend calls
- 402 subscription_required handled gracefully
- News cloud paths all correct
- Poll hardening, re-entry guard, translation consolidation (all v2.1.1+9 fixes)
- `.env` removed — no bundled secrets

**Target commit:** `700d579`  **Version:** `2.1.1+18`  **Branch:** `services-migration`
**iOS bundle ID:** `com.glikfamily.audioura` (Android uses `com.audioura.audiotours` — different)
**No pubspec bump needed.**

**Roles:**
- **[SIR MICHAEL]** — App Store Connect setup (must be done BEFORE Mac Mini Q uploads), smoke test on device, final upload approval.
- **[MAC MINI Q]** — pulls latest, builds release archive, installs on device for smoke test, then uploads to TestFlight.

---

## Step 0 — [SIR MICHAEL] App Store Connect setup ⚠️ DO THIS BEFORE MAC MINI BUILD

Before Mac Mini Q can upload anything, the app record must exist in App Store Connect:

1. Go to **appstoreconnect.apple.com** → sign in with `glikfamily@gmail.com`
2. Click **+** → New App
3. Fill in:
   - Platform: **iOS**
   - Name: **Audioura**
   - Primary Language: **English (U.S.)**
   - Bundle ID: **com.glikfamily.audioura** (select from dropdown — must match Xcode)
   - SKU: **audioura-1**
4. Complete **App Privacy** details (required before submission)
5. Tell Mac Mini Q "App Store Connect record created, proceed" when done

Also generate an **App-Specific Password** for the Apple ID (needed for `xcrun altool` upload):
- Go to **appleid.apple.com** → Sign-In and Security → App-Specific Passwords → Generate
- Label it "Mac Mini Audioura Upload"
- Save the password — Mac Mini Q will need it

## Step 1 — [SIR MICHAEL] Eject USB, carry to Mac Mini, switch KVM

## Step 2 — [SIR MICHAEL on Mac Mini] Launch Q

Paste:
> Read `@/Volumes/USB DISK/Audioura/assignments/mac_mini_assignments.md` and execute the A#84 assignment at the top. Follow STOP conditions; skip steps labelled `[SIR MICHAEL]`.

## Step 3 — [MAC MINI Q] Pull latest

```bash
cd ~/Development/Audioura-build
git pull origin services-migration
```

**Expected:** fast-forward to commit `700d579` or later.

## Step 4 — [MAC MINI Q] Spot-check BEFORE building ⚠️ REQUIRED

```bash
cd ~/Development/Audioura-build/development/audio_tour_app

# 4a — pubspec at 2.1.1+18
grep "^version:" pubspec.yaml
# Expected: version: 2.1.1+18

# 4b — no hardcoded 5012/5017 in tour_generator_screen
grep -n "5012\|5017" lib/screens/tour_generator_screen.dart
# Expected: zero matches

# 4c — _pollTimer is GONE
grep -n "_pollTimer" lib/screens/tour_generator_screen.dart
# Expected: zero matches

# 4d — GATEWAY_API_KEY dart-define wired up (reads from env)
grep -rn "GATEWAY_API_KEY\|fromEnvironment" lib/config/ | head -5
# Expected: at least 1 match showing dart-define is read

# 4e — signing intact
grep -E 'PRODUCT_BUNDLE_IDENTIFIER|DEVELOPMENT_TEAM' \
  ios/Runner.xcodeproj/project.pbxproj | sort -u
# Expected: com.glikfamily.audioura and 4HGRU6TKGQ

# 4f — no .env file bundled
ls .env 2>/dev/null && echo "FOUND - STOP" || echo "NOT PRESENT - OK"
# Expected: NOT PRESENT - OK
```

If 4a fails — STOP, wrong commit.
If 4b or 4c shows matches — STOP, stale code.
If 4f shows FOUND — STOP, do not build with bundled secrets.

## Step 5 — [MAC MINI Q] pod install

```bash
cd ~/Development/Audioura-build/development/audio_tour_app/ios
pod install
cd ..
```

## Step 6 — [MAC MINI Q] Verify Xcode signing for DISTRIBUTION

```bash
open ~/Development/Audioura-build/development/audio_tour_app/ios/Runner.xcworkspace
```

In Xcode:
1. Select **Runner** target → **Signing & Capabilities**
2. Confirm **Automatically manage signing** ✅
3. Confirm **Team: Mikhail Glik (4HGRU6TKGQ)**
4. Confirm **Bundle Identifier: com.glikfamily.audioura**
5. Switch scheme from **Debug** to **Release** (top bar → scheme selector)
6. Quit Xcode

## Step 7 — [MAC MINI Q] Build release archive (IPA)

```bash
cd ~/Development/Audioura-build/development/audio_tour_app
flutter clean && flutter pub get
flutter build ipa --release --dart-define=GATEWAY_API_KEY="aura-gw-360721-880288"
```

**Expected:** Build completes with output similar to:
```
Built build/ios/ipa/audioura.ipa
```

`flutter analyze` warnings in dead files — **non-blocking**, proceed.

If build FAILS with signing error:
```bash
open ios/Runner.xcworkspace
```
Runner → Signing & Capabilities → Automatically manage signing ✅ → Team: 4HGRU6TKGQ → quit Xcode → re-run Step 7.

If build FAILS with `--dart-define` error — try without quotes:
```bash
flutter build ipa --release --dart-define=GATEWAY_API_KEY=aura-gw-360721-880288
```

## Step 8 — [MAC MINI Q] Install on iPhone for smoke test

Install the release build on the iPhone for a quick pre-submission smoke test:

```bash
# Install the IPA directly to the connected iPhone
xcrun devicectl device install app \
  --device F9D6F807-D301-59EE-B574-5747D617D82C \
  build/ios/ipa/audioura.ipa
```

If `devicectl` fails, use `ios-deploy` or open Xcode → Window → Devices and Simulators → drag IPA onto device.

STOP and tell Sir Michael the build is installed. Wait for smoke test result.

## Step 9 — [SIR MICHAEL] Smoke test on iPhone ⚠️ STOP HERE FOR Q

⚠️ **App should default to Cloud mode with no manual URL/key entry needed.**

**Test 1 — Cloud tour generation:**
Launch app → generate a tour → no 401, tour generates and opens automatically.

**Test 2 — Cloud news/newsletter:**
Audio mode → process newsletter → download article → playback works.

**Test 3 — Translation:**
Generate a tour with translation → works. If translation unavailable → modal dialog shown (not silent English fallback).

**Test 4 — Account deletion:**
About → Delete My Account → confirmation → tap Delete → iOS pops to root with "Please reopen the app to finish resetting." message. ⚠️ Only test with a throwaway account.

**Test 5 — Report tour:**
Listen page → open overflow menu (⋮) on a tour → Report → email compose opens prefilled.

**Test 6 — Treats tab:**
Navigate to Treats → shows "Samples for the future" banner + real backend content.

**Test 7 — Map/POI:**
Open a walking tour → tap POI map icon → TourMapScreen opens.

**Test 8 — Mic/Voice:**
Listen tab → tap mic → listening dialog opens, no permission snackbar.

Tell Q "Smoke test passes, proceed to Step 10" when done. Report any failures.

## Step 10 — [MAC MINI Q] Upload to TestFlight via Xcode Organizer

```bash
open ios/Runner.xcworkspace
```

In Xcode:
1. Menu → **Product → Archive**
   - If archive already exists from Step 7, skip to step 2
   - Wait for archive to complete
2. **Window → Organizer** opens automatically
3. Select the `2.1.1 (18)` archive → click **Distribute App**
4. Choose **App Store Connect** → **Next**
5. Choose **Upload** → **Next**
6. Leave all options default → **Next** → **Next**
7. Click **Upload**
8. Wait for upload to complete — Xcode will show "Upload Successful"

**Alternative — command line upload (if Organizer upload fails):**
```bash
# Sir Michael provides the app-specific password
xcrun altool --upload-app \
  -f build/ios/ipa/audioura.ipa \
  -t ios \
  -u glikfamily@gmail.com \
  -p <app-specific-password>
```

STOP and tell Sir Michael the upload status.

## Step 11 — [SIR MICHAEL] TestFlight activation in App Store Connect

After upload succeeds:
1. Go to **appstoreconnect.apple.com** → Audioura app → **TestFlight** tab
2. Wait for build to finish processing (~5–15 minutes)
3. Once processed → click build → **Add to Group** → add yourself as internal tester
4. Install via TestFlight app on iPhone
5. Verify app version shows `2.1.1 (18)` in TestFlight

## Step 12 — [MAC MINI Q] Copy results and eject

```bash
echo "A#84 Results:" > ~/Desktop/a84_results.txt
echo "Date: $(date)" >> ~/Desktop/a84_results.txt
echo "Release archive built: [YES/NO]" >> ~/Desktop/a84_results.txt
echo "IPA path: build/ios/ipa/audioura.ipa" >> ~/Desktop/a84_results.txt
echo "Test 1  Cloud tour generation: [YES/NO]" >> ~/Desktop/a84_results.txt
echo "Test 2  Cloud news/newsletter: [YES/NO]" >> ~/Desktop/a84_results.txt
echo "Test 3  Translation + modal dialog: [YES/NO]" >> ~/Desktop/a84_results.txt
echo "Test 4  Account deletion iOS pop: [YES/NO/NOT_TESTED]" >> ~/Desktop/a84_results.txt
echo "Test 5  Report tour email: [YES/NO]" >> ~/Desktop/a84_results.txt
echo "Test 6  Treats tab: [YES/NO]" >> ~/Desktop/a84_results.txt
echo "Test 7  Map/POI: [YES/NO]" >> ~/Desktop/a84_results.txt
echo "Test 8  Mic/Voice: [YES/NO]" >> ~/Desktop/a84_results.txt
echo "TestFlight upload: [SUCCESS/FAILED/PENDING]" >> ~/Desktop/a84_results.txt
echo "Overall: [SUCCESS/PARTIAL/FAILED]" >> ~/Desktop/a84_results.txt
cp ~/Desktop/a84_results.txt "/Volumes/USB DISK/Audioura/results/"
diskutil eject "/Volumes/USB DISK"
```

## Step 13 — [MAC MINI Q] Report Results

> "Assignment 84 complete. Archive built: [YES/NO]. Cloud generation (T1): [YES/NO]. Cloud news (T2): [YES/NO]. Translation (T3): [YES/NO]. Account deletion (T4): [YES/NO/NOT_TESTED]. Report tour (T5): [YES/NO]. Treats (T6): [YES/NO]. Map/POI (T7): [YES/NO]. Mic (T8): [YES/NO]. TestFlight upload: [SUCCESS/FAILED/PENDING]. Overall: [SUCCESS/PARTIAL/FAILED]."

## Step 14 — [SIR MICHAEL, back on Windows] Sync

```cmd
cd C:\Users\micha\eclipse-workspace\AudioTours\development
git pull origin services-migration
```
Verify `audio_tour_app\pubspec.yaml` shows `version: 2.1.1+18`.

---

# T: 06/2026 - A#83 — Build v2.1.1+9 — SUPERSEDED by A#84
**Status**: ⏭️ SUPERSEDED — never built on iPhone. All v2.1.1+9 features included in A#84.

---

# T: 06/2026 - A#82 — Build v2.1.1+8 — SUPERSEDED by A#84
**Status**: ⏭️ SUPERSEDED — never built on iPhone. All changes included in A#84.

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
