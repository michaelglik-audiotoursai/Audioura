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
When chat history is compacted, user will ask you to read `android_q_onboarding.md` and `remind_mobile_ai.md`.
**Your Response**:
"📱 MOBILE APP AMAZON-Q - I've read both files. Current version is v1.2.9+68, Android build pending on Ubuntu VM. Ready to build."

## 🚫 OWNERSHIP BOUNDARIES — CRITICAL
- ✅ **MY files**: `remind_mobile_ai.md`, `code_review_v*.md`, files in `amazon-q-communications/`
- ❌ **NOT MY files**: `remind_ios_ai.md` (iOS Amazon-Q only), `mac_mini_assignments.md` (iOS Amazon-Q only)
- ❌ **NEVER write to** `remind_ios_ai.md` or `D:\Audioura\assignments\mac_mini_assignments.md`
- ✅ **To communicate with iOS Amazon-Q**: write a file in `amazon-q-communications\audiotours\requirements\`

## CURRENT PROJECT STATUS
**Project**: Audioura Android APK
**Version**: v1.2.9+68 ✅ COMMITTED on `services-migration` branch
**Android**: 🔄 Build pending on Ubuntu VM
**iOS**: Handled by iOS Amazon-Q — currently building v1.2.9+69 on Mac Mini
**Branch**: `services-migration`
**Android Application ID**: `com.audioura.app`
**Server**: `192.168.0.218` (Docker services on Windows laptop)

## RECENT VERSION HISTORY (latest first)
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

### v1.2.9+68 — POI Map Buttons Fixed in Tour Player
**Bug**: Tapping POI map icons during tour playback did nothing — no map opened, no error in logs
**Root Cause**: Server HTML emits `<button onclick="openMap(N)">` calling `flutter_inappwebview.callHandler('openMap', {stop:N})`. Flutter side never registered the `'openMap'` handler — silent no-op.
**Fix**: Added `controller.addJavaScriptHandler(handlerName: 'openMap')` in `onWebViewCreated` in `TourPlayerScreen`. Handler parses stop number, pushes `TourMapScreen` with `focusStopIndex`.
**Files**: `tour_player_screen.dart` (import + handler), `pubspec.yaml`
**Log confirmation**: `MAP: openMap handler fired for stop N` appears when POI icon tapped
**Note**: v1.2.9+67 (`HitTestBehavior.opaque` in `tour_map_screen.dart`) was an incorrect initial diagnosis — kept as minor hardening per Claude code review

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

## 🔄 NEXT ACTION: Build v1.2.9+68 on Ubuntu VM
**Step 1**: Switch to Ubuntu VM
**Step 2**: `bash build_flutter_clean.sh` (shared folder already has latest — no git pull needed)
**Step 3**: Install APK, run smoke test checklist from `android_q_onboarding.md`
**Step 4**: Report results — especially POI map button test and stale path healing test
**APK output**: `audioura-dev.apk` in `development/` folder (shared folder = Windows `C:\Users\micha\eclipse-workspace\AudioTours\development\audioura-dev.apk`)

## ⚠️ VERSION SYNC RULE
- iOS Q makes code changes → commits → bumps `pubspec.yaml` version
- Android Q: `git pull` on Windows dev tree → Ubuntu VM picks up via shared folder → build → smoke test
- **Android Q does NOT independently bump version numbers**
- Next version after +68 is **v1.2.9+69** (newsletter Refresh fix — iOS Q committing now)

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
