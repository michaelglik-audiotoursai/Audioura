# Mobile App Amazon-Q Context Reminder - POST COMPACTION
## Who you are
1. **Android Amazon-Q**: Responsible for Audioura Android APK build and smoke testing
2. **ANDROID BUILD**: ❌ Cannot build in Windows — Ubuntu VM shared folder, run `bash build_flutter_clean.sh`
3. **iOS BUILD**: ❌ Not your responsibility — handled by iOS Amazon-Q on Mac Mini
4. **Workflow**: Pull latest → build on Ubuntu VM → smoke test → report results
5. **Dev Location**: `C:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app\`
6. **Onboarding doc**: `C:\Users\micha\eclipse-workspace\AudioTours\development\android_q_onboarding.md`
7. **⚠️ IDENTIFICATION REQUIREMENT**: Always start replies with "📱 MOBILE APP AMAZON-Q -"

## 🚨 POST-COMPACTION RECOVERY PROTOCOL
When chat history is compacted, user will ask you to read `remind_ai.md` and `remind_mobile_ai.md`.
**Your Response**:
"📱 MOBILE APP AMAZON-Q - I've read both files. Current version on branch is v1.2.9+72 (dual environment networking). Code is committed and pushed. Awaiting Ubuntu build + smoke test. Claude.AI code review doc `code_review_v1.2.9.72.md` has 5 open questions — ready to review and respond. Ready to continue."

## 🚫 OWNERSHIP BOUNDARIES — CRITICAL
- ✅ **MY files**: `remind_mobile_ai.md`, `code_review_v*.md`, files in `amazon-q-communications/`
- ❌ **NOT MY files**: `remind_ios_ai.md` (iOS Amazon-Q only), `mac_mini_assignments.md` (iOS Amazon-Q only)
- ❌ **NEVER write to** `remind_ios_ai.md` or `D:\Audioura\assignments\mac_mini_assignments.md`
- ✅ **To communicate with iOS Amazon-Q**: write a file in `amazon-q-communications\audiotours\requirements\`

## CURRENT PROJECT STATUS
**Project**: Audioura Android APK
**Version on branch**: v1.2.9+72 ✅ committed on `services-migration`
**iPhone**: On v1.2.9+71 (iOS Q built — A#78 mic fix)
**Android**: ✅ v1.2.9+72 built and committed — awaiting Ubuntu build + smoke test
**iOS Q current task**: No active task assigned
**Branch**: `services-migration`
**Android Application ID**: `com.audioura.app`
**Server**: `192.168.0.218` (Docker services on Windows laptop)

## RECENT VERSION HISTORY (latest first)
- **v1.2.9+72** — Dual environment networking: `Endpoints` resolver, Local/Cloud toggle in About, all services migrated
- **v1.2.9+71** — A#78: mic permission fix (remove redundant `Permission.microphone.request()` from `my_tours_screen.dart`)
- **v1.2.9+70** — (iOS Q — newsletter Refresh fix A#77)
- **v1.2.9+69** — Newsletter Refresh fix (iOS Q)
- **v1.2.9+68** — Fix POI map buttons in tour player (wire `openMap` JS→Dart handler)
- **v1.2.9+67** — Map marker tap hardening (`HitTestBehavior.opaque` in `tour_map_screen.dart`)
- **v1.2.9+66** — Restore map icon on Listen page (lost in Tours_Step_Maps merge)
- **v1.2.9+65** — A#75: migrate `news_player_screen.dart` to InAppWebView v6 (`initialSettings`)
- **v1.2.9+64** — A#73: app icon background color `#A93105` (brick red)
- **v1.2.9+63** — A#72: heal stale iOS container paths for news articles
- **v1.2.9+62** — Fix app name (Audioura) + InAppWebViewSettings v6 migration (other screens)
- **v1.2.9+61** — Fix mode-switch regression: replace `IndexedStack` with `_buildBody()` switch
- **v1.2.9+60** — Fix white screen on single-POI museum tours (`_fitBounds()` guard)

## ✅ KEY FIXES IN RECENT VERSIONS

### v1.2.9+72 — Dual Environment Networking
**Feature**: App can now switch between local WiFi and cloud (cellular) server endpoints at runtime — no rebuild needed.
**New file**: `lib/config/endpoints.dart` — `Endpoints` class with `Service` enum, `base()` and `url()` methods
**Logic**: Reads `server_mode` from SharedPreferences (`'local'` or `'cloud'`). Local = `http://$ip:$port`. Cloud = `$cloudBaseUrl$pathPrefix`.
**About screen**: Added Local/Cloud `ChoiceChip` toggle + editable `cloud_base_url` field. Local mode keeps existing IP field.
**Migrated**: All 13 service call sites in `home_screen.dart`, `about_screen.dart`, `custom_audio_service.dart`
**Review doc**: `code_review_v1.2.9.72.md` — 5 questions for Claude
**Note**: `direct_db_update.dart` and `api_tester.dart` NOT migrated — dev-only, must never be exposed on Cloud Run

### v1.2.9+71 — A#78 Mic Permission Fix
**Bug**: Tapping mic icon on Listen page showed "Microphone permission required" snackbar even after permission already granted
**Root Cause**: Redundant `Permission.microphone.request()` block in `_startVoiceSearch()` conflicted with `speech_to_text` plugin's own permission pathway
**Fix**: Removed redundant `Permission.microphone.request()` block and now-dead `permission_handler` import from `my_tours_screen.dart`
**Files**: `my_tours_screen.dart`, `pubspec.yaml`
**Android note**: `RECORD_AUDIO` still declared in `AndroidManifest.xml` — system dialog appears on first tap (correct), no snackbar on subsequent taps

### v1.2.9+66 — Map Icon Restored on Listen Page
**Bug**: Green map icon missing from tour list — lost when `Tours_Step_Maps` branch was merged
**Fix**: Restored `_tourHasMap`, `_detectMapTours()`, `_healTourPaths()`, and `Icons.map` button in `_buildToursView()`
**File**: `my_tours_screen.dart`
**Behaviour**: Map icon (green) appears per-tour only when `audio_1.txt` contains `Coordinates:` line

### v1.2.9+65 — InAppWebView v6 Migration (news_player_screen.dart)
**Fix**: Migrated `news_player_screen.dart` from deprecated InAppWebView API to v6 `initialSettings`
**File**: `news_player_screen.dart`

### v1.2.9+62 — InAppWebView v6 Migration (other screens)
**Fix**: Migrated remaining screens from deprecated InAppWebView API to v6 `initialSettings`

### v1.2.9+61 — Mode-Switch Regression Fix
**Bug**: Switching Tours↔Audio mode did NOT update Home and Generate pages
**Root Cause**: `IndexedStack` in `main_screen.dart` kept all tab screens permanently mounted — `initState()` never re-ran
**Fix**: Replaced `IndexedStack` with `_buildBody()` switch — Flutter destroys/recreates screen State on every tab switch
**Rule**: NEVER use `IndexedStack` — it prevents `initState()` from re-running on tab switch

### v1.2.9+60 — Museum Map White Screen Fix
**Fix**: 4-line guard in `_fitBounds()` — uses `_mapController.move(points.first, 15)` for single-point case
**File**: `tour_map_screen.dart`

## 🔄 NEXT ACTION: Two parallel items

### 1. Ubuntu build for v1.2.9+72
**Status**: ✅ Code committed and pushed (`5d79a1f`)
**Steps**:
1. Tell user to run `bash build_flutter_clean.sh` on Ubuntu VM
2. Shared folder already has latest — no git pull needed on Ubuntu
3. After install: smoke test checklist from `android_q_onboarding.md` + new dual-network test
4. Key new test: About → toggle to Cloud → enter `https://map-delivery-ixkp5nkrlq-uc.a.run.app` → off WiFi → Home loads tours from cellular
5. Report results

### 2. Respond to Claude.AI code review questions (`code_review_v1.2.9.72.md`)
Five open questions. Answers to provide:

**Q1 — Cloud path prefix double-segment** (`/map-delivery/map-delivery/...`):
The Cloud Run host `map-delivery-xxx.run.app` does NOT route on path prefix — it serves all paths directly. So `_cloudPaths[Service.mapDelivery]` should be `''` (empty string) for the interim single-host-per-service setup. When a gateway is deployed, it becomes `/map-delivery`. **Fix needed**: Make `_cloudPaths` empty string for mapDelivery until gateway exists, OR document that user must set `cloud_base_url` to `https://map-delivery-xxx.run.app` and the `/map-delivery` prefix will need removing. The cleanest interim fix: change `_cloudPaths[Service.mapDelivery]` to `''` and note in About that it will become `/map-delivery` when gateway is live.

**Q2 — `_downloadTranslatedVersions` unused `serverIp` parameter**:
Remove the `serverIp` parameter from the signature and update both callers (`_downloadSingleTour`, `_downloadSingleTourSilent`). Clean fix — no behavior change.

**Q3 — `processUri2` variable name**:
Not a real conflict — `processUri` in `_processNewsletterWithUrl` and `processUri2` in `_processNewsletterUrl` are in different method scopes. Rename `processUri2` → `processUri` in `_processNewsletterUrl`. No conflict at all.

**Q4 — Multiple `SharedPreferences.getInstance()` calls**:
No concern. `SharedPreferences.getInstance()` returns a cached singleton after first load — subsequent calls are synchronous memory reads. No performance issue.

**Q5 — `direct_db_update.dart` / `api_tester.dart` not migrated**:
These are dev-only debug tools. Add a `// ⚠️ DEV ONLY — NEVER expose on Cloud Run` comment at the top of each file. Services team must ensure these endpoints have no public ingress on Cloud Run. No code migration needed — they should NEVER route through cloud mode.

**Action after compaction**: Read `code_review_v1.2.9.72.md`, implement Q2 (remove param) and Q3 (rename var) as code fixes in v1.2.9+73, document Q1 answer in About screen helper text, add Q5 warning comments. Q4 is informational only.

## ⚠️ VERSION SYNC RULE
- iOS Q makes code changes → commits → bumps `pubspec.yaml` version → pushes to `services-migration`
- Android Q: user confirms push → `git pull` on Windows dev tree → Ubuntu shared folder picks it up → build → smoke test → report
- **Android Q does NOT independently bump version numbers**
- **Android Q does NOT push code changes** unless Android-specific files changed (e.g. `AndroidManifest.xml`, `build.gradle.kts`)

## 📡 COMMUNICATION INFRASTRUCTURE

**Between Amazon-Qs**: Two channels:
1. **Direct** — via the user in conversation
2. **Communication Layer** — file-based, committed to git:
   - **Directory**: `c:\Users\micha\eclipse-workspace\amazon-q-communications\audiotours\`
   - **Structure**:
     ```
     amazon-q-communications\audiotours\
     ├── requirements\    ← bug reports, feature requests, cross-Q issues
     ├── specifications\  ← technical specs
     ├── decisions\       ← architectural decisions
     └── issues\          ← active issues being tracked
     ```
   - **Usage**: Write a markdown file in `requirements\` to communicate with Services Amazon-Q or iOS Amazon-Q. They read it on their next session.
   - **iOS Amazon-Q reminder file**: `c:\Users\micha\eclipse-workspace\AudioTours\development\remind_ios_ai.md` — update this to hand off work to iOS Amazon-Q
   - **⚠️ DO NOT write to** `D:\Audioura\assignments\mac_mini_assignments.md` — that is iOS Amazon-Q's document, owned and maintained by iOS Amazon-Q only

## ⚠️ CRITICAL PROCESS NOTES
- **NEVER write to `remind_ios_ai.md`** — iOS Amazon-Q's file only
- **NEVER write to `mac_mini_assignments.md`** — iOS Amazon-Q's file only
- **Always commit `audio_tour_app/lib/` changes to git** after each accepted code change cycle
- **Ubuntu build**: Uses VirtualBox shared folder — same files as Windows dev tree, no git pull needed on Ubuntu
- **Android-specific concern**: Stale path healing uses `/Documents/` marker — may not apply to Android. Test reinstall scenario.

## 🚨 CRITICAL WORKFLOW RULE
**⚠️ NEVER CHANGE CODE WITHOUT APPROVAL**: Always propose plan first, get user approval, then implement
**Workflow**: Analyze → Propose Plan → Get Approval → Implement → User Tests

## 🗺️ A#55 MAP BUTTONS — PENDING (ANDROID, NOT YET IMPLEMENTED)
**Branch**: `Tours_Step_Maps` merged into `Newsletters` — work continues on services-migration
**Status**: C1/C2/C3 confirmed ✅, `_countStops()` bug fix proposed, NOT YET IMPLEMENTED

### 🐛 _countStops() BUG — FIX PROPOSED, NOT YET APPLIED
**Bug**: `_countStops()` breaks loop when ANY stop has no coordinates — misses valid stops after the gap
**Fix**:
1. `_countStops()` → count ALL stops by file existence only
2. New `_getMappableStops()` → returns list of stop indices that have coordinates
3. `_buildMapButtonInjectionScript(List<int>)` → injects only for mappable stops

### 📋 A#55 WHAT CHANGES IN tour_player_screen.dart (NOT YET DONE)
**To Remove**: `_startStopPolling()`, `_stopPollTimer`, `_currentStop`, `_getCurrentStop()`, `_buildStopMapBar()`, `_buildMapNavOverlay()`, `_mapNavButton()`, `bottomNavigationBar`, `Stack` wrapper
**To Add**: `addJavaScriptHandler('openMap')` in `onWebViewCreated`, `_getMappableStops()`, `_buildMapButtonInjectionScript(List<int>)`, JS injection call in `onLoadStop`
**To Keep**: `_hasMap`, `_checkForMap()`, `_countStops()` (simplified), `_stopCount`, `_openMapForStop(int)`

## CRITICAL DEBUGGING LIMITATION
**❌ NO CONSOLE/FILE PRINTING**: Mobile apps cannot use `print()`, console.log, or file writing
**✅ ONLY MOBILE APP LOGS WORK**: Use `DebugLogHelper.addDebugLog()` for all debugging output

## CRITICAL REMINDERS
- ❌ **NEVER attempt APK build in Windows** — Always requires Ubuntu VM
- ❌ **NEVER attempt iOS build in Windows** — Always requires Mac Mini
- 🌿 **All commits go to services-migration branch** — NOT main branch
- 🔄 **Version Management**: Only increment version for functional changes, not build fixes
- ⚠️ **BUILD ERROR RULE**: NEVER increment version numbers when fixing build errors

## KEY ARCHITECTURAL FACTS
- **Map Library**: `flutter_map: ^6.1.0` with OpenStreetMap — no API keys, no cost
- **WebView**: `flutter_inappwebview` v6 — use `initialSettings` (not deprecated `initialOptions`), use `addJavaScriptHandler` for JS↔Dart
- **Debug Logging**: `DebugLogHelper.addDebugLog()` — never `print()`
- **Tour files**: stored at `app_flutter/tours/<tour_id>/`, audio files named `audio_N.txt`, `audio_N.mp3`
- **Map POI data**: parsed from `audio_N.txt` files — looks for `Coordinates: lat, lon` line
- **Mode switching**: works because `_buildBody()` returns fresh widget on every tab switch → `initState()` re-runs → `_loadAppMode()` re-reads `app_mode`. NEVER use `IndexedStack`.

## iOS BUILD INFRASTRUCTURE
- **Mac Mini repo**: `~/Development/Audioura-build/` (fresh clone — use for all future builds)
- **Old broken repo**: `~/Development/AudioTours/` — leave untouched, do not push or delete
- **USB scripts path**: `/Volumes/USB DISK/Audioura/scripts/`
- **USB assets path**: `/Volumes/USB DISK/Audioura/assets/`
- **iPhone UDID**: `F9D6F807-D301-59EE-B574-5747D617D82C`
- **Bundle ID**: `com.glikfamily.audioura`
- **Team ID**: `4HGRU6TKGQ`
- **Podfile**: must have `platform :ios, '13.0'` — stored at `D:\Audioura\assets\ios\Podfile`
- **copy_ios_fixes.sh**: copies 22 files from USB assets to Mac Mini, runs flutter analyze
- **build_install_launch.sh**: builds with codesign, installs, launches, monitors for crashes
- **iOS signing issue**: Xcode must have "Automatically manage signing" checked with Team `4HGRU6TKGQ` — open `ios/Runner.xcworkspace` to configure if build fails with provisioning error

## ANDROID BUILD INFRASTRUCTURE
- **Dev tree**: `C:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app\`
- **Build**: Ubuntu VM — `bash build_flutter_clean.sh` (shared folder, no git pull needed)
- **APK output**: `audioura-dev.apk` in `development/` folder
- **Application ID**: `com.audioura.app`
- **Branch**: `services-migration`
- **Signing**: `debug.keystore` committed at `android/app/debug.keystore` — no Play Store keystore needed yet
- **compileSdk**: 35, **minSdk**: 24, **ndkVersion**: `27.0.12077973`

## ENCRYPTION IMPLEMENTATION - VERIFIED SECURE (HISTORICAL)
**Method**: RFC 3526 Diffie-Hellman (2048-bit) → SHA-256 full entropy → AES-128-CBC
**Files**: subscription_encryption_service.dart, subscription_service.dart, subscription_credential_dialog.dart
