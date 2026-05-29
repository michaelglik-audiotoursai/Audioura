# Mobile App Amazon-Q Context Reminder - POST COMPACTION
## Who you are
1. **Mobile App Amazon-Q**: Responsible for Audioura mobile app (Android + iOS iPhone)
2. **ANDROID BUILD**: ❌ Cannot build in Windows — Ubuntu VM shared folder, run `bash build_flutter_clean.sh`
3. **iOS BUILD**: ❌ Cannot build in Windows — Mac Mini with `build_install_launch.sh`
4. **Workflow**: Propose → Get approval → Implement → User builds
5. **Dev Location**: `C:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app\`
6. **iOS Scripts**: `D:\Audioura\scripts\` — copied to USB for Mac Mini execution
7. **iOS Assignments**: `D:\Audioura\assignments\mac_mini_assignments.md`
8. **⚠️ IDENTIFICATION REQUIREMENT**: Always start replies with "📱 MOBILE APP AMAZON-Q -"

## 🚨 POST-COMPACTION RECOVERY PROTOCOL
When chat history is compacted, user will ask you to read @remind_ai.md and @remind_mobile_ai.md.
**Your Response**:
"📱 MOBILE APP AMAZON-Q - I've read both reminder files. Current version is v1.2.9+66, committed and pushed to services-migration branch on GitHub. Map icon restored on Listen page. Android build v1.2.9+66 needed on Ubuntu VM. Ready to continue."

## CURRENT PROJECT STATUS
**Project**: Audioura Mobile App — iOS iPhone + Android
**Version**: v1.2.9+66 ✅ COMMITTED, PUSHED to GitHub (services-migration branch)
**iOS**: 🔄 Build pending on Mac Mini (v1.2.9+66 not yet built for iPhone)
**Android**: 🔄 Build pending on Ubuntu VM (v1.2.9+66 not yet built for Android)
**Branch**: services-migration
**Bundle ID**: `com.glikfamily.audioura`
**App Name**: Audioura

## RECENT VERSION HISTORY (latest first)
- **v1.2.9+66** — Restore map icon on Listen page (lost in Tours_Step_Maps merge)
- **v1.2.9+65** — A#75: migrate `news_player_screen.dart` to InAppWebView v6 (`initialSettings`)
- **v1.2.9+64** — A#73: app icon background color `#A93105` (brick red)
- **v1.2.9+63** — A#72: heal stale iOS container paths for news articles
- **v1.2.9+62** — Fix app name (Audioura) + InAppWebViewSettings v6 migration (other screens)
- **v1.2.9+61** — Fix mode-switch regression: replace `IndexedStack` with `_buildBody()` switch
- **v1.2.9+60** — Fix white screen on single-POI museum tours (`_fitBounds()` guard)

## ✅ KEY FIXES IN RECENT VERSIONS

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

## 🔄 NEXT ACTION: Build v1.2.9+66
**Android**: Ubuntu VM — `bash build_flutter_clean.sh` (shared folder, no git pull needed)
**iOS**: Mac Mini — new assignment needed (A#76)

## ⚠️ CRITICAL PROCESS NOTES
- **NEVER apply changes only to `D:\Audioura\assets\` staging copy** without also committing to git dev tree
- **Always commit `audio_tour_app/lib/` changes to git after each accepted cycle**
- **Mac Mini broken repo**: Leave `~/Development/AudioTours/` untouched. All future iOS builds use `~/Development/Audioura-build/`
- **Ubuntu build**: Uses VirtualBox shared folder — same files as Windows dev tree, no git pull needed

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
- **APK output**: `audioura-dev.apk`
- **Branch**: services-migration

## ENCRYPTION IMPLEMENTATION - VERIFIED SECURE (HISTORICAL)
**Method**: RFC 3526 Diffie-Hellman (2048-bit) → SHA-256 full entropy → AES-128-CBC
**Files**: subscription_encryption_service.dart, subscription_service.dart, subscription_credential_dialog.dart
