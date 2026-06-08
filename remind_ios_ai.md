# iOS AudioTours AI Context Reminder
## 🍎 iOS Amazon-Q Recovery Guide — POST-COMPACTION ENTRY POINT

### 🪪 **IDENTITY — ALWAYS START WITH THIS**
Every response in a new session must begin with:
**🍎 iOS AMAZON-Q**
This is required so the user can identify which Amazon-Q tab they are talking to.

---

### ✅ **CURRENT STATE — v2.1.1+3 READY TO BUILD ON iPHONE**

- iPhone last confirmed on **v1.2.9+71** (A#78 mic fix — smoke test passed)
- **A#80 is ready to build** — v2.1.1+3 iOS parity with Android. Android has fully tested both Local WiFi AND Cloud. No iOS-only code changes needed beyond `Info.plist` already updated at `52d8282`.
- **API Key field** is in the About screen as a **temporary development tool** — Sir Michael enters the gateway API key manually during testing. Will be removed in a future version (customers cannot be expected to know the key).

---

### 🎯 **IMMEDIATE NEXT STEPS**

#### A#80 — Build v2.1.1+3 on iPhone ⚠️ READY TO BUILD

**What this delivers over v1.2.9+71:**
- Dual-environment networking: Local WiFi (default) and Cloud (HTTPS)
- `Endpoints` resolver — all service calls route through a single resolver per active mode
- `Endpoints.apiHeaders()` sends `X-API-Key` in cloud mode (reads `gateway_api_key` from SharedPreferences)
- `tour_status_service.dart` — REST via `Endpoints(Service.orchestrator)` + `apiHeaders()`, keyed on `tour_xxx` tour_id
- `TranslationService` — migrated to `Endpoints.url(Service.translation)` + `apiHeaders()` — cloud multi-language works
- About screen: Local/Cloud toggle + cloud URL field + API Key field (temporary) + gateway path routing checkbox (leave unchecked)
- Inter-service auth tokens on all edges, OpenAI + AWS secret key fixes
- Dead files removed: `test_update_api.dart` + raw-SQL files
- `NSLocalNetworkUsageDescription` in `Info.plist` (commit `52d8282`)

**Mac Mini runs:**
```bash
cd ~/Development/Audioura-build
git pull origin services-migration
# Verify: grep "^version:" development/audio_tour_app/pubspec.yaml → 2.1.1+3
cd development/audio_tour_app/ios && pod install
cd .. && flutter clean && flutter pub get
cd "/Volumes/USB DISK/Audioura/scripts" && ./build_install_launch.sh
# STOP for Sir Michael smoke test — Local WiFi + Cloud both
# NO pubspec commit — version already at 2.1.1+3
```

**Smoke tests (7):**
1. Local mode (WiFi) → tours load from `192.168.0.218`. About shows Local by default.
2. Local WiFi tour generation → generates, appears in Listen tab.
3. About tab → Local/Cloud toggle present. Switch to Cloud → URL + API Key fields appear.
4. Cloud mode → enter URL + API Key → download/generate tour → plays.
5. Cloud multi-language translation → completes (NOT_TESTED acceptable — not a blocker).
6. Mic regression (A#78) → no "permission required" snackbar.
7. Refresh regression (A#77b) → no black screen. General regression: tour audio, news article, POI map.

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
- **Windows dev tree**: `C:\Users\micha\eclipse-workspace\AudioTours\development\` — IS a git clone. Q edits iOS-only files + planning docs here. Never commits Dart code.
- **USB mirror**: `usb/Audioura/` mirrors `D:\Audioura\`. After editing: `copy usb\Audioura\assignments\mac_mini_assignments.md D:\Audioura\assignments\`
- **OLD repo**: `~/Development/AudioTours/` — BROKEN, never use
- **pubspec**: `2.1.1+3` (Android Q bumped — iOS Q never bumps independently)
- **Head commit**: `049bb35` — Cloud generation verified with real audio

#### Version history
| Version | Assignment | Status |
|---------|-----------|--------|
| 1.2.9+68 | A#76 POI map button fix | ✅ |
| 1.2.9+69 | A#77 wrong Refresh fix | ⚠️ BUILT BUT FAILED |
| 1.2.9+70 | A#77b Listen Refresh black screen fix | ✅ |
| 1.2.9+71 | A#78 mic permission fix + dead import | ✅ |
| 2.1.1+1 | A#79 dual-environment — superseded by A#80 | ⏭️ SKIPPED |
| **2.1.1+3** | **A#80 cloud fully working + API key + auth** | **⏳ READY TO BUILD** |

#### Git operation ownership
| Operation | Who | Where |
|---|---|---|
| `git pull` + build + `git push` (pubspec bump) | Mac Mini Q | `~/Development/Audioura-build/` |
| Edit + commit iOS-only files + planning docs | Windows Q | `C:\Users\micha\eclipse-workspace\AudioTours\development\` |
| Dart code changes + version bumps | Android Q | per assignment |
| `git pull` to sync after pushes | Sir Michael (Windows) | Windows dev tree |

⚠️ Android Q must NOT edit `remind_ios_ai.md` — unauthorized edit reverted at `e5c103d`.

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
- **iPhone**: v1.2.9+71 (A#80 parity build pending)
- **All shipped features**: Tour clustering, location search, tour search, newsletter system, subscription, language selector, about screen, settings persistence, location permissions, keyboard dismissal, download spinner fix, microphone voice control, translation (ru/fr/zh), walking tour map, per-stop map focus, coordinate jitter, museum single-POI map guard, mode-switch fix, stale tour/news path healing, brick-red app icon, app name "Audioura", InAppWebView v6, map icon on Listen page, POI tap → TourMapScreen via `openMap` JS handler, Listen page Refresh in-place reload, Listen page mic permission fix.
- **New in v2.1.1+3** (pending A#80 build): Dual-environment Local/Cloud networking, `Endpoints` resolver, `X-API-Key` header, `TranslationService` cloud migration, About screen toggle + API Key field.

---

### 🔄 **WORKFLOW RULES**
1. Assignments: Windows Q writes to `usb/Audioura/assignments/mac_mini_assignments.md` → copies to USB → commits + pushes → Mac Mini Q pulls + executes.
2. iOS-only file changes (`Info.plist`, `Podfile`): Windows Q edits + commits + pushes → Mac Mini pulls.
3. Dart code changes: Android Q commits. Windows Q never touches `lib/`.
4. After parity build: no pubspec commit needed (Android Q already bumped it).
5. **LF FILES**: `home_screen.dart`, `tour_generator_screen.dart`, `my_tours_screen.dart` — `fsReplace` FAILS on Windows. Python patch scripts only.
6. **PYTHON OUTPUT**: stdout is unreliable in `executeBash`. Write to `D:\Audioura\results\<file>.txt`, read with `type`.
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
- `_manualRefresh()` — **A#77b**: in-place `_loadAppMode()`, no navigation teardown
- `_setupVoiceCommands()` — sole mic permission acquisition via `_speechToText.initialize()`
- `_startVoiceSearch()` — **A#78**: no `Permission.microphone.request()`, no `permission_handler` import. `listen()` has `onResult` + `listenFor: 10s` — `onStatus` not wired (auto-dismiss not implemented, deferred)

#### about_screen.dart
- **v2.1.1+x**: Local/Cloud toggle, cloud base URL field, **API Key field** (temporary — reads/writes `gateway_api_key` in SharedPreferences), gateway path routing checkbox (leave unchecked).

#### tour_player_screen.dart (CRLF)
- `addJavaScriptHandler('openMap')` in `onWebViewCreated` — **A#76**
- `initialSettings: InAppWebViewSettings(...)` — v6 API ✅

#### news_player_screen.dart (CRLF)
- `_getIndexUrl()` heals stale container paths. `FutureBuilder<String>` wraps WebView body. v6 API ✅

#### tour_map_screen.dart (CRLF)
- `focusStopIndex` (int?, 1-based). `_applyCoordJitter()`. Single-POI guard.

#### main_screen.dart (CRLF)
- `_buildBody()` switch — never wrap in IndexedStack. `_listenTabVersion` key for Listen reload.

#### home_screen.dart (LF — Python edits only)
- Download + translation logic.

#### lib/config/endpoints.dart
- `Endpoints.base(Service)` — returns local `http://ip:port` or cloud URL per `server_mode`
- `Endpoints.url(Service, path)` — full URI
- `Endpoints.apiHeaders(Service)` — `Content-Type` always; adds `X-API-Key` in cloud mode from `gateway_api_key` pref

---

### 📋 **OPEN ITEMS**
1. **A#80** ⚠️ READY TO BUILD — v2.1.1+3. Local WiFi + Cloud. See Immediate Next Steps.
2. **API Key field removal** — About screen manual API Key input is temporary. Future assignment: remove field, embed/auto-supply key. Customers must never see it.
3. **Dialog auto-dismiss** — `_startVoiceSearch()` dialog doesn't auto-close on 10s timeout. `onStatus` not wired. Never implemented, not a regression. Deferred.
4. **ISSUE-SERVICES-NEWSLETTER** — `get_articles_by_newsletter_id` returns only 2 of 5 articles. Awaiting Kiro. Not iOS.
5. **ISSUE-061** — Translated tours → 404. Awaiting Services fix.
6. **NF4 (LOW)** — `openMap` handler bare-int widening.
7. **NF5 (LOW)** — `Colors.blue.withOpacity(0.6)` → `.withValues(alpha: 0.6)`.
8. **OSM tiles** — swap to Stadia Maps or Mapbox before App Store.
9. **Dead files** — delete `audio_handler.dart`, `map_page.dart`, `subscription_management_screen.dart`.

---

### ⚠️ **CRITICAL TECHNICAL NOTES**
- **Version numbering**: iOS and Android share `pubspec.yaml`. Android Q owns version bumps. iOS Q never bumps independently.
- **Parity rule**: Both platforms always build the same commit on `services-migration`. No iOS-specific Dart forks.
- **iOS-only files**: `ios/Runner/Info.plist`, `ios/Runner.xcodeproj/`, `ios/Podfile` — Windows Q may edit these. Everything in `lib/` is shared.
- **API Key (temporary)**: `Endpoints.apiHeaders()` reads `gateway_api_key` from SharedPreferences and sends as `X-API-Key` in cloud mode only. About screen has a manual entry field. Field will be removed once key is embedded.
- **LF files**: `home_screen.dart`, `tour_generator_screen.dart`, `my_tours_screen.dart` — `fsReplace` FAILS. Python only.
- **CRLF files**: `tour_map_screen.dart`, `tour_player_screen.dart`, `main_screen.dart`, `news_player_screen.dart` — `fsReplace` works.
- **Python stdout**: always empty in `executeBash`. Write to `D:\Audioura\results\<name>.txt`, read with `type`.
- **InAppWebView**: v6 API only — `initialSettings: InAppWebViewSettings(...)`. v5 `initialOptions` BANNED.
- **ATS**: Flutter `package:http` bypasses iOS ATS. Local HTTP works without plist entry. Cloud is HTTPS.
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
| `lib/screens/about_screen.dart` | Local/Cloud toggle + API Key field (temporary). |
| `lib/screens/main_screen.dart` | Tab navigation. CRLF. |
| `lib/screens/tour_player_screen.dart` | `openMap` JS handler. CRLF. |
| `lib/screens/news_player_screen.dart` | Path healing + FutureBuilder. CRLF. |
| `lib/screens/tour_map_screen.dart` | Map screen. Jitter + single-POI guard. CRLF. |
| `lib/screens/tour_generator_screen.dart` | Translation + player navigation. LF. |
| `lib/screens/debug_log_viewer_screen.dart` | `DebugLogHelper` class. |
| `lib/config/endpoints.dart` | `Endpoints` resolver — base URL + apiHeaders with X-API-Key. |
| `lib/services/tour_status_service.dart` | Tour status REST via Endpoints. |
| `lib/services/translation_service.dart` | Translation via Endpoints (cloud-ready). |
| `lib/config.dart` | `Config.defaultServerIp = '192.168.0.218'` |
| `ios/Runner/Info.plist` | iOS permissions + `NSLocalNetworkUsageDescription`. |
| `usb/Audioura/assignments/mac_mini_assignments.md` | Mac Mini task queue. A#80 at top. |
| `git_source_control_for_q.md` | Git rules — READ before any git operation. |
| `android_q_onboarding.md` | Android Q full onboarding doc. |

---

### 🤖 **ANDROID PARITY**
- Android bundle ID: `com.audioura.app` (iOS: `com.glikfamily.audioura`)
- Android is on v2.1.1+3 — A#80 brings iPhone to same version
- Version sync: Android Q bumps `pubspec.yaml` → iOS Q pulls + builds same commit
- iOS Q never bumps version independently
- ⚠️ Android Q must NOT edit `remind_ios_ai.md` — this file is iOS Q's domain only

---

**Last Updated**: 2026-06-06 — v107.0. pubspec at `2.1.1+3`. Android fully tested Local WiFi + Cloud (Sir Michael entered API key in About screen). A#80 ready to build on iPhone. API Key field in About is temporary — future assignment will remove it. Both prior cloud blockers confirmed fixed in current code (`Endpoints.apiHeaders` + `TranslationService` migration).
**iOS Amazon-Q Version**: 107.0
