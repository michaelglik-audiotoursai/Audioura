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
"📱 MOBILE APP AMAZON-Q - I've read both files. Current version on branch is v2.1.1+5 (poll hardening complete: mounted guard after http.get, 4xx snackbar, _pollTimer dispose, non-200 handling, maxTransientErrors=6, handleTransient closure). Latest commit `14f11eb`. Ready for Ubuntu build."

## 🚫 OWNERSHIP BOUNDARIES — CRITICAL
- ✅ **MY files**: `remind_mobile_ai.md`, `code_review_v*.md`, files in `amazon-q-communications/`
- ❌ **NOT MY files**: `remind_ios_ai.md` (iOS Amazon-Q only), `mac_mini_assignments.md` (iOS Amazon-Q only)
- ❌ **NEVER write to** `remind_ios_ai.md` or `D:\Audioura\assignments\mac_mini_assignments.md`
- ✅ **To communicate with iOS Amazon-Q**: write a file in `amazon-q-communications\audiotours\requirements\`

## CURRENT PROJECT STATUS
**Project**: Audioura Android APK
**Version on branch**: v2.1.1+5 ✅ committed on `services-migration` (latest commit `14f11eb`)
**iPhone**: On v1.2.9+71 (iOS Q built — A#78 mic fix)
**Android**: ✅ v2.1.1+5 fully complete — ready for Ubuntu build
**iOS Q current task**: No active task assigned
**Branch**: `services-migration`
**Android Application ID**: `com.audioura.app`
**Server**: `192.168.0.218` (Docker services on Windows laptop)

## RECENT VERSION HISTORY (latest first)
- **v2.1.1+5** — Poll hardening (all Claude review fixes applied, 2 commits):
  - `mounted` guard after `http.get` in poll callback — prevents setState after dispose if user leaves mid-await (Q4 real gap)
  - Other 4xx: red snackbar "Tour generation unavailable right now" instead of silent spinner clear (Q3)
  - `_pollTimer` promoted to State field — `_pollTimer?.cancel()` added to `dispose()` (Q1 leak fix)
  - Non-200 HTTP responses handled (Q2 critical): 429 → stop + quota snackbar; 5xx → `handleTransient()`; other 4xx → log + stop + snackbar
  - `maxTransientErrors` raised `3 → 6` (~60s tolerance matching observed DNS outage)
  - Duplicate SocketException/ClientException handlers → `handleTransient` local closure (DRY)
  - `maxAttempts = 90` overall cap confirmed ✅
- **v2.1.1+4** — Poll resilience fix:
  - `_pollAndAutoDownload` in `tour_generator_screen.dart`: `SocketException` / `http.ClientException` caught separately — keep polling, log warning, do NOT mark failed
  - Tolerates up to 3 consecutive transient errors before soft give-up
  - Soft give-up: shows orange snackbar "Tour may still be generating — check My Tours shortly", clears spinner, does NOT write `failed` status, leaves `tour_id_$jobId` mapping intact
  - Successful poll resets transient error counter
  - Background poll (`background_tour_monitor.dart`, `background_service.dart`) already resilient — no changes needed
- **v2.1.1+3** — M2+M3 complete + Blocker A + Blocker B:
  - `Endpoints.apiHeaders()` — injects `X-API-Key` in cloud mode only, reads `gateway_api_key` from SharedPreferences
  - Both `/generate-complete-tour` POSTs + `/tour-status` POST use `apiHeaders()`
  - `translation_service.dart` migrated from hardcoded `:5030` LAN IP → `Endpoints.url(Service.translation)` + `apiHeaders()`
  - API key field added to About screen (obscured, cloud section, never committed)
  - 9 raw-SQL/dead files deleted (949 lines)
  - Finding 2 noted: `rows_affected: 0` in cloud until `/user` gateway route deployed (services dep)
- **v2.1.1+2** — M1 complete: all 11 orchestrator/mapDelivery URLs migrated, runtime crash fixed (`apiBaseUrl as String` cast), all `print()` replaced with `DebugLogHelper`, dead locals removed
- **v2.1.1+1** — Major version restart: Claude review fixes — Q1 cloud prefix flag, Q2 dead param removal, Q3 rename, Q5 DEV ONLY guards
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

### v2.1.1+3 — M2+M3 + Blocker A + Blocker B
**M2**: `tour_status_service.dart` → `POST /tour-status` via `Endpoints.url(Service.orchestrator)`, keyed on `tour_xxx` tour_id, logs `rows_affected` with ⚠️ on 0
**M3**: `about_screen.dart` gateway URL hint + status text updated, checkbox label clarified (prefixes stay OFF)
**Blocker A**: `Endpoints.apiHeaders(Service s)` — `{'Content-Type': 'application/json'}` in local; adds `X-API-Key` from `gateway_api_key` SharedPreferences in cloud. Applied to: both `/generate-complete-tour` POSTs, `/tour-status` POST, `/translate-with-audio` POST. API key field added to About screen (obscured, cloud section only).
**Blocker B**: `translation_service.dart` — `config.dart` import removed, hardcoded `http://$serverIp:5030` → `Endpoints.url(Service.translation, '/translate-with-audio')` + `apiHeaders()`
**Files deleted**: 9 total — 6 raw-SQL services + `test_update_api.dart` + 2 stale root-level copies (949 lines)
**Finding 2 (services dep)**: `rows_affected: 0` in cloud until `/user` gateway route + user-api deployed — generation/download unaffected
**Review doc**: `code_review_v2.1.1.3_final.md` — 2 questions (Q1: empty key warning, Q2: SharedPreferences cleanup)

### v2.1.1+2 — M1 Complete + Full Cleanup
**Feature**: M1 fully complete. All 11 tour/orchestrator/map-delivery call sites across 3 files route through `Endpoints`. Runtime crash fixed. All `print()` eliminated.
**Files**: `tour_generator_screen.dart`, `background_service.dart`, `background_tour_monitor.dart`
**11 migrated sites**: foreground POST, status poll, status+download in `_autoDownloadAndPlay`, coordinates in `_saveTourInfo`, background POST, `_processAdditionalLanguages` (mapDelivery), `_downloadBackgroundTour` (status+download), `background_service` status+download, `background_tour_monitor` status+download
**Runtime crash fixed**: `apiBaseUrl as String` cast in `background_tour_monitor.checkBackgroundTourStatus` — key absent from JSON since v2.1.1+1, was throwing TypeError on every backgrounded tour
**Dead code removed**: `apiBaseUrl` reads and `serverIp` locals in `background_service.dart` and `background_tour_monitor.dart`
**print() eliminated**: 14 in `tour_generator_screen.dart`, 7 in `background_service.dart` — all → `DebugLogHelper.addDebugLog()`
**Deferred**: news (`:5012`) and newsletter (`:5017`) — services not yet on Cloud Run
**Review doc**: `code_review_v2.1.1.2_final.md` — 2 questions for Claude (Q1 style, Q2 confirm deferrals)
**M2 status**: blocked on Kiro's K1 REST endpoint contract (`POST /tour-status` on orchestrator)

### v2.1.1+2 — Version Correction + M1 Partial
**Version**: Corrected backwards bump (`2.1.2+1` → `2.1.1+2`) — build number only, no new functionality.
**M1 partial applied**:
- `_downloadBackgroundTour` status + download → `Endpoints.url(Service.orchestrator, ...)`
- `_processAdditionalLanguages` → `Endpoints.url(Service.mapDelivery, '/download-tour/$translatedId')`
- Dead `apiBaseUrl` read + dead `serverIp` local removed from `background_service.dart`
- Compile blocker fixed: `prefs` re-added to `_processAdditionalLanguages`
**Files**: `tour_generator_screen.dart`, `background_service.dart`, `pubspec.yaml`

### v2.1.1+1 — Claude Review Fixes (Major Version Restart)
**Q1 — Cloud path prefix fix** (`endpoints.dart` + `about_screen.dart`):
- `Endpoints.base()` now reads `cloud_use_path_prefixes` bool (default `false`).
- `false` (interim/default): returns bare `cloudBase` — no prefix. Works against bare Cloud Run per-service hosts.
- `true` (future gateway): appends `_cloudPaths[s]`. Enable only when `audioura.com` gateway is deployed.
- About screen: added "Use gateway path routing" checkbox in cloud section, wired to `cloud_use_path_prefixes`.

**Q2 — Removed dead `serverIp` param** (`home_screen.dart`):
- Removed `serverIp` parameter from `_downloadTranslatedVersions()` signature.
- Updated both callers: `_downloadSingleTour` and `_downloadSingleTourSilent`.
- No behavior change — method body already used only `Endpoints.url()` internally.

**Q3 — Renamed `processUri2`** (`home_screen.dart`):
- Renamed `processUri2` → `processUri` in `_processNewsletterUrl`. Cosmetic only — separate method scope from `_processNewsletterWithUrl`.

**Q5 — DEV ONLY warning comments** (`direct_db_update.dart`, `api_tester.dart`):
- Added `// ⚠️ DEV ONLY — NEVER expose on Cloud Run` header comments to both files.
- Files intentionally NOT migrated to `Endpoints` — they use `server_ip` directly, making them unreachable off-WiFi.

**Q4** — No action. `SharedPreferences.getInstance()` is a cached singleton — confirmed non-issue.

**Review doc**: `code_review_v2.1.1.1.md` — 5 new questions for Claude (see NEXT ACTION below).

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

## 🔄 NEXT ACTION

### 1. Ubuntu build for v2.1.1+5 — READY TO BUILD ✅
**Status**: ✅ All Claude fixes applied and committed (`14f11eb`) — no more review needed
**Prerequisite**: Enter `gateway-api-key` (from Secret Manager) in About → cloud → API Key field, set `cloud_base_url = https://api.audioura.com`, path-routing OFF

### ⚠️ QUEUED FIXES FOR NEXT BUILD (v2.1.1+6)
**Q1 — Empty API key warning** (Claude recommendation, medium priority):
- In `apiHeaders()`: when `mode == 'cloud'` and key is empty → `DebugLogHelper.addDebugLog('Cloud mode but gateway_api_key not set — request will 401; set it in About')`
- When any cost-endpoint returns 401 → surface user-facing message: "Set your API key in About settings"
**Q2 — SharedPreferences cleanup** (low priority, defer):
- Clean up `tour_id_$jobId` / `request_$jobId` keys after terminal status reached
- Prevents unbounded growth over time
**Voice commands** (future, not current sprint):
- Voice commands are 100% on-device (speech-to-text → command parsing → execution), no services involved
- Multi-language voice command support NOT yet implemented — future enhancement only

### 2. Smoke tests for v2.1.1+5 (after Ubuntu build)
1. Local WiFi foreground generation (regression — `rows_affected: 1`)
2. Cloud foreground generation — simulate network blip during poll → expect orange snackbar, NOT failed status
3. Cloud multi-language generation
4. Cloud backgrounded tour

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
