# iOS AudioTours AI Context Reminder
## 🍎 iOS Amazon-Q Recovery Guide — POST-COMPACTION ENTRY POINT

### 🪪 **IDENTITY — ALWAYS START WITH THIS**
Every response in a new session must begin with:
**🍎 iOS AMAZON-Q**
This is required so the user can identify which Amazon-Q tab they are talking to.

---

### ✅ **CURRENT STATE — v2.1.1+3 PARITY BUILD READY FOR MAC MINI**

- iPhone last confirmed on **v1.2.9+71** (A#78 mic fix — smoke test passed)
- **A#80 is ready to build** — v2.1.1+3 iOS parity with Android. All Dart code already in repo from Android Q. No iOS-only file changes. Mac Mini: `git pull` + `pod install` + build. No pubspec bump needed (already at `2.1.1+3`).
- **Version jump**: v1.2.9+71 → v2.1.1+3. This is intentional — Android Q restarted the major version for the dual-environment (Local WiFi / Cloud) release.
- **Full assignment doc**: `amazon-q-communications/audiotours/requirements/IOS_A80_PARITY_BUILD_v2.1.1.3_2026_06_06.md`

---

### 🎯 **IMMEDIATE NEXT STEPS**

#### A#80 — Build v2.1.1+3 on iPhone ⚠️ READY TO BUILD

**What this delivers (since last iPhone build v1.2.9+71):**
- Dual-environment networking: Local WiFi / Cloud toggle in About
- `Endpoints.apiHeaders()` — injects `X-API-Key` from SharedPreferences in cloud mode only
- All cost-bearing POSTs (`/generate-complete-tour`, `/tour-status`, `/translate-with-audio`) send `X-API-Key` in cloud
- `TranslationService` migrated from hardcoded LAN IP → `Endpoints.url(Service.translation)` + `apiHeaders()`
- API key field in About screen (obscured, cloud section, `gateway_api_key` SharedPreferences key)
- 9 dead/raw-SQL files deleted
- All prior fixes (A#77b Refresh, A#78 mic) carried forward

**Before cloud tests**: Enter `gateway-api-key` value (from AWS Secrets Manager) in About → cloud → API Key field. Set `cloud_base_url = https://api.audioura.com`. Leave "Use gateway path routing" unchecked.

**Key fact:** No Dart coding needed. All `lib/` changes are shared Flutter code from Android Q. iOS builds same commit. No iOS-only file changes since `52d8282`.

**Mac Mini runs:**
```bash
cd ~/Development/Audioura-build
git pull origin services-migration
# Verify: grep "^version:" development/audio_tour_app/pubspec.yaml → 2.1.1+3
cd development/audio_tour_app/ios && pod install
cd .. && flutter clean && flutter pub get
cd "/Volumes/USB DISK/Audioura/scripts" && ./build_install_launch.sh
# STOP for Sir Michael smoke test
# NO pubspec commit — version already at 2.1.1+3
```

**Smoke tests (7):**
1. Local WiFi → tours load from `192.168.0.218`. About tab shows Local by default.
2. Local WiFi → generate tour → succeeds, `rows_affected: 1` in logs.
3. Local WiFi → generate + translate (1 language) → succeeds.
4. Cloud → download existing tour → plays.
5. Cloud → user sync → 404 expected (Kiro gateway task — not a failure).
6. Mic regression (A#78) → no "permission required" snackbar.
7. Refresh regression (A#77b) → no black screen.

---

### 🔑 **GIT / BUILD STATE**

```
GitHub (remote)
  repo: michaelglik-audiotoursai/Audioura  branch: services-migration
       ↑ push                    ↓ pull
       |                         |
Mac Mini clone            Windows dev tree
~/Development/            C:\Users\micha\eclipse-workspace\
Audioura-build/           AudioTours\development\
(builds + commits)        (reference/review only)
```

- **Mac Mini build clone**: `~/Development/Audioura-build/`, branch `services-migration`
- **Flutter project on Mac Mini**: `~/Development/Audioura-build/development/audio_tour_app/`
- **Windows dev tree**: `C:\Users\micha\eclipse-workspace\AudioTours\development\` — IS a git clone. Q edits files here, commits planning/directives/iOS-only changes. Never commits Dart code — Mac Mini does that.
- **USB mirror in git**: `usb/Audioura/` mirrors `D:\Audioura\`. After editing: `copy usb\Audioura\assignments\mac_mini_assignments.md D:\Audioura\assignments\`
- **OLD repo**: `~/Development/AudioTours/` — BROKEN, never use
- **pubspec.yaml**: `2.1.1+1` (shared, bumped by Android Q — iOS Q never bumps independently)
- **Head commit**: `52d8282` — NSLocalNetworkUsageDescription added to Info.plist

#### Version history
| Version | Assignment | Status |
|---------|-----------|--------|
| 1.2.9+68 | A#76 POI map button fix | ✅ |
| 1.2.9+69 | A#77 wrong Refresh fix | ⚠️ BUILT BUT FAILED |
| 1.2.9+70 | A#77b Listen Refresh black screen fix | ✅ |
| 1.2.9+71 | A#78 mic permission fix + dead import | ✅ |
| 2.1.1+1 | A#79 dual-environment parity | ⏳ SKIPPED — superseded by A#80 |
| **2.1.1+3** | **A#80 cloud-ready parity (Blocker A+B)** | **⏳ READY TO BUILD** |

#### Git operation ownership
| Operation | Who | Where |
|---|---|---|
| `git pull` + build + `git push` (pubspec bump) | Mac Mini Q | `~/Development/Audioura-build/` |
| Edit + commit directives/iOS-only files | Windows Q | `C:\Users\micha\eclipse-workspace\AudioTours\development\` |
| Dart code changes + version bumps | Android Q or Mac Mini Q | per assignment |
| `git pull` to sync after pushes | Sir Michael (Windows) | Windows dev tree |

---

### 🚀 **QUICK CONTEXT RECOVERY**
- **Mission**: iOS Amazon-Q for Audioura LLC mobile app
- **App name**: Audioura (`com.glikfamily.audioura`)
- **Device**: iPhone 16, UDID `F9D6F807-D301-59EE-B574-5747D617D82C`, iOS 18.3.1
- **Apple Dev**: Team ID `4HGRU6TKGQ`, paid license (glikfamily@gmail.com), valid until April 7 2027
- **Certificate**: Apple Development: Mikhail Glik (`594584F3D3BC571D94A822A2158871CA13898701`)
- **Flutter UDID** (provisioning): `00008140-000558A902BA801C`
- **Network**: iPhone → Windows laptop Docker services at `192.168.0.218:5002/5004/5005/5030`
- **Build environment**: Mac Mini M4 + Xcode 16

---

### 📱 **APP STATUS**
- **iPhone**: v1.2.9+71 (A#79 parity build pending)
- **All shipped features**: Tour clustering, location search, tour search, newsletter system, subscription, language selector, about screen, settings persistence, location permissions, keyboard dismissal, download spinner fix, microphone voice control, translation (ru/fr/zh), walking tour map, per-stop map focus, coordinate jitter, museum single-POI map guard, mode-switch fix, stale tour/news path healing, brick-red app icon, app name "Audioura", InAppWebView v6, map icon on Listen page, POI tap → TourMapScreen via `openMap` JS handler, Listen page Refresh in-place reload, Listen page mic permission fix.
- **New in v2.1.1+1** (pending A#79 build): Dual-environment Local/Cloud networking, `Endpoints` resolver, About screen toggle.

---

### 🔄 **WORKFLOW RULES**
1. Assignments: Windows Q writes directives to `usb/Audioura/assignments/mac_mini_assignments.md` → copies to USB → commits + pushes → Mac Mini Q pulls + executes.
2. iOS-only file changes (e.g. `Info.plist`): Windows Q edits + commits + pushes → Mac Mini pulls.
3. Dart code changes: Android Q or Mac Mini Q commits. Windows Q never touches `lib/`.
4. After successful build: Mac Mini commits pubspec bump + pushes IF version was bumped. For parity builds where pubspec is already correct, no commit needed.
5. **LF FILES**: `home_screen.dart`, `tour_generator_screen.dart`, `my_tours_screen.dart` — `fsReplace` FAILS on Windows. Python patch scripts only.
6. **PYTHON OUTPUT**: stdout is unreliable in `executeBash`. Always write results to `D:\Audioura\results\<file>.txt` and read back with `type D:\Audioura\results\<name>.txt`.
7. Read `git_source_control_for_q.md` before any git operation.

---

### 🏗️ **BUILD PROCESS**
```bash
cd ~/Development/Audioura-build
git pull origin services-migration
cd development/audio_tour_app/ios && pod install   # always run after pull
cd .. && flutter clean && flutter pub get
cd "/Volumes/USB DISK/Audioura/scripts"
./build_install_launch.sh
```
- `flutter analyze` issues in dead files only (`audio_handler.dart`, `map_page.dart`, `subscription_management_screen.dart`, `test/widget_test.dart`) — non-blocking.
- If push rejected (fetch first): `git pull origin services-migration` then push again.
- If push blocked by GitHub secret scanning — STOP, never click "Allow secret".

---

### 🗺️ **KEY SCREEN ARCHITECTURE**

#### my_tours_screen.dart (LF — Python edits only)
- Shows tours (Tours mode) or news articles (Audio mode) depending on `_appMode`
- `_manualRefresh()` — **A#77b**: in-place `_loadAppMode()`, no navigation teardown
- `_setupVoiceCommands()` — sole mic permission acquisition via `_speechToText.initialize()`
- `_startVoiceSearch()` — **A#78**: no `Permission.microphone.request()`, no `permission_handler` import. Guards on `!_speechEnabled`. `listen()` has `onResult` + `listenFor: 10s` — `onStatus` not wired (auto-dismiss not implemented, deferred to future assignment)

#### tour_player_screen.dart (CRLF)
- `addJavaScriptHandler('openMap')` in `onWebViewCreated` — **A#76**
- `initialSettings: InAppWebViewSettings(...)` — v6 API ✅

#### news_player_screen.dart (CRLF)
- `_getIndexUrl()` heals stale container paths. `FutureBuilder<String>` wraps WebView body.
- `initialSettings: InAppWebViewSettings(...)` — v6 API ✅

#### tour_map_screen.dart (CRLF)
- `focusStopIndex` (int?, 1-based). `_applyCoordJitter()`. Single-POI guard.

#### main_screen.dart (CRLF)
- `_buildBody()` switch — never wrap in IndexedStack. `_listenTabVersion` key for Listen reload.

#### home_screen.dart (LF — Python edits only)
- Download + translation logic. Newsletter Refresh handler cleaned up in A#77.

#### about_screen.dart
- **NEW in v2.1.1+1**: Local/Cloud toggle, cloud base URL field, gateway path routing checkbox.

---

### 📋 **OPEN ITEMS**
1. **A#80** ⚠️ READY TO BUILD — v2.1.1+3 iOS parity. `git pull` + `pod install` + build. No pubspec bump. No iOS-only file changes. Full assignment: `IOS_A80_PARITY_BUILD_v2.1.1.3_2026_06_06.md` in communications/requirements.
2. **Dialog auto-dismiss** — `_startVoiceSearch()` dialog does not auto-close on 10s timeout. `onStatus` never wired. Confirmed never implemented (not a regression). Deferred to future assignment.
3. **Android A#79 parity** — Android is already on v2.1.1+1. After iOS A#79 builds, both platforms are in sync.
4. **Cloud tour generation** — not ready on either platform (`:5003` not deployed to cloud). Test existing-tour download only.
5. **ISSUE-SERVICES-NEWSLETTER** — `get_articles_by_newsletter_id` returns only 2 of 5 articles. Awaiting Kiro. Not iOS.
6. **ISSUE-061** — Translated tours → 404. Awaiting Services fix.
7. **NF4 (LOW)** — `openMap` handler bare-int widening. Two-line fix.
8. **NF5 (LOW)** — `Colors.blue.withOpacity(0.6)` → `.withValues(alpha: 0.6)`.
9. **OSM tiles** — swap to Stadia Maps or Mapbox before App Store.
10. **Dead files** — delete `audio_handler.dart`, `map_page.dart`, `subscription_management_screen.dart`.

---

### ⚠️ **CRITICAL TECHNICAL NOTES**
- **Version numbering**: iOS and Android share `pubspec.yaml`. Android Q owns version bumps. iOS Q never bumps independently.
- **Parity rule**: Both platforms always build the same commit on `services-migration`. No iOS-specific Dart forks.
- **iOS-only files**: `ios/Runner/Info.plist`, `ios/Runner.xcodeproj/`, `ios/Podfile` — Windows Q may edit these. Everything in `lib/` is shared.
- **LF files**: `home_screen.dart`, `tour_generator_screen.dart`, `my_tours_screen.dart` — `fsReplace` FAILS. Python only.
- **CRLF files**: `tour_map_screen.dart`, `tour_player_screen.dart`, `main_screen.dart`, `news_player_screen.dart` — `fsReplace` works.
- **Python stdout**: always empty in `executeBash`. Write to `D:\Audioura\results\<name>.txt`, read with `type`.
- **InAppWebView**: v6 API only — `initialSettings: InAppWebViewSettings(...)`. v5 `initialOptions` BANNED.
- **ATS**: Flutter's `package:http` bypasses iOS App Transport Security. Local HTTP (`192.168.0.218`) works without any `NSAppTransportSecurity` plist entry. Cloud mode is HTTPS anyway.
- **pod install**: always run after `git pull` on Mac Mini before building.
- **DebugLogHelper**: in `lib/screens/debug_log_viewer_screen.dart`.
- **unawaited()**: requires `import 'dart:async'`.

---

### 🔧 **TROUBLESHOOTING**
```bash
# iPhone not detected:
sudo launchctl kickstart -k system/com.apple.usbd
# Flutter checks:
flutter doctor -v && flutter devices
# Verify pubspec on Mac Mini:
grep "^version:" ~/Development/Audioura-build/development/audio_tour_app/pubspec.yaml
# Uninstall app:
xcrun devicectl device uninstall app --device F9D6F807-D301-59EE-B574-5747D617D82C com.glikfamily.audioura
# Pod issues:
cd ios && pod deintegrate && pod install
```

---

### 📂 **KEY FILES**
| File | Purpose |
|------|---------|
| `lib/screens/home_screen.dart` | Download + translation. LF. |
| `lib/screens/my_tours_screen.dart` | Tours/news list. LF. A#77b + A#78 fixed. |
| `lib/screens/about_screen.dart` | Local/Cloud toggle (new in v2.1.1+1). |
| `lib/screens/main_screen.dart` | Tab navigation. CRLF. |
| `lib/screens/tour_player_screen.dart` | `openMap` JS handler. CRLF. |
| `lib/screens/news_player_screen.dart` | Path healing + FutureBuilder. CRLF. |
| `lib/screens/tour_map_screen.dart` | Map screen. Jitter + single-POI guard. CRLF. |
| `lib/screens/tour_generator_screen.dart` | Translation + player navigation. LF. |
| `lib/screens/debug_log_viewer_screen.dart` | `DebugLogHelper` class. |
| `lib/config.dart` | `Config.defaultServerIp = '192.168.0.218'` |
| `ios/Runner/Info.plist` | iOS permissions + `NSLocalNetworkUsageDescription` added `52d8282`. |
| `usb/Audioura/assignments/mac_mini_assignments.md` | Mac Mini task queue. A#79 at top. |
| `git_source_control_for_q.md` | Git rules — READ before any git operation. |
| `android_q_onboarding.md` | Android Q full onboarding doc. |
| `android_assignment_a78_2026_06_02.md` | Android Q A#78 parity assignment. |
| `claude_ios_aq_v2.1.1.1_correlated_build_2026_06_03.md` | Claude's parity build instructions. |

---

### 🤖 **ANDROID PARITY**
- Android bundle ID: `com.audioura.app` (iOS: `com.glikfamily.audioura`)
- Android already on v2.1.1+1 — iOS A#79 build brings iPhone to same version
- Version sync: Android Q bumps `pubspec.yaml` → iOS Q pulls + builds same commit
- iOS Q never bumps version independently
- Stale path healing uses `/Documents/` marker (iOS-specific) — Android Q must verify separately

---

**Last Updated**: 2026-06-06 — v107.0. pubspec at `2.1.1+3` (Android Q). iOS A#80 parity build ready: `git pull` + `pod install` + build. No iOS-only file changes since `52d8282`. No Dart changes needed — shared codebase. Full assignment in `IOS_A80_PARITY_BUILD_v2.1.1.3_2026_06_06.md`.
**iOS Amazon-Q Version**: 107.0
