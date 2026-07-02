# iOS AudioTours AI Context Reminder
## 🍎 iOS Amazon-Q Recovery Guide — POST-COMPACTION ENTRY POINT

### 🪪 **IDENTITY — ALWAYS START WITH THIS**
Every response in a new session must begin with:
**🍎 iOS AMAZON-Q**
This is required so the user can identify which Amazon-Q tab they are talking to.

---

### ✅ **CURRENT STATE — v2.2.0+1 STORIED RELEASE READY TO BUILD**

- iPhone last confirmed on **v1.2.9+71** (A#78 mic fix — smoke test passed)
- **A#85 is ready to build** — v2.2.0+1 from `storied` branch. Supersedes A#84 (v2.1.1+18, never built). First App Store / TestFlight submission build.
- **Branch is `storied`** — NOT `services-migration`. Flutter app root is `audio_tour_app/` (not `development/audio_tour_app/`).
- **API key baked in** via `--dart-define=GATEWAY_API_KEY="aura-gw-360721-880288"` — no manual entry needed. App defaults to Cloud mode on fresh install.
- **Mobile Kiro** (Kiro IDE) replaced Android Amazon-Q (Eclipse) as of 2026-06-08.
- **App Attestation iOS native (Phase 4)** NOT yet implemented — `MissingPluginException` handled gracefully, never blocks. Future assignment.
- ⚠️ **Sir Michael must create App Store Connect record + App-Specific Password BEFORE upload step** (bundle ID `com.glikfamily.audioura`, SKU `audioura-1`).

---

### 🎯 **IMMEDIATE NEXT STEPS**

#### A#85 — Build v2.2.0+1 Storied Release ⚠️ READY TO BUILD

⚠️ **DIFFERENT BUILD PROCESS — `storied` branch, release archive, TestFlight upload.**

**What this delivers over v1.2.9+71:**
- All v2.1.1+18 Beta features: cloud-first defaults, baked-in API key, all cloud URLs sending `X-API-Key`, translation modal, overflow menu (⋮), Report tour, Treats tab, Account deletion iOS flow, 402 handling, full URL audit
- **NEW — Onboarding Personalization:** "What brings you here?" on first launch, 4 choices, saves `narrative_tone`, never shows again
- **NEW — App Attestation Dart stubs:** MethodChannel `com.audioura.app/attestation` wired, iOS native side pending (graceful fallback)

**Target commit:** `2962fe5` (or later `0045823`)  **pubspec:** `2.2.0+1`  **Branch:** `storied`

**Mac Mini runs:**
```bash
cd ~/Development/Audioura-build
git pull origin services-migration
# Verify: grep "^version:" development/audio_tour_app/pubspec.yaml → 2.1.1+8
cd development/audio_tour_app/ios && pod install
cd .. && flutter clean && flutter pub get
cd "/Volumes/USB DISK/Audioura/scripts" && ./build_install_launch.sh
```

**Build command:**
```bash
# From ~/Development/Audioura-build/audio_tour_app/ on storied branch
flutter build ipa --release --dart-define=GATEWAY_API_KEY="aura-gw-360721-880288"
```

**Smoke tests (9):**
1. Onboarding — "What brings you here?" on fresh install, 4 choices, never repeats
2. Cloud tour generation — no 401, generates automatically
3. Cloud news/newsletter — processes, downloads, plays
4. Translation — works; failure shows modal dialog
5. Account deletion — iOS pops to root with restart message
6. Report tour — overflow menu → Report → email compose opens
7. Treats tab — banner + real content
8. Map/POI — TourMapScreen opens
9. Mic/Voice — no permission snackbar

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
- **pubspec**: `2.2.0+1` (Mobile Kiro bumped — `storied` branch)
- **Head commit**: `0045823` (storied branch) — storied_mode ALTER + audio_tours INSERT fix

#### Version history
| Version | Assignment | Status |
|---------|-----------|--------|
| 1.2.9+68 | A#76 POI map button fix | ✅ |
| 1.2.9+69 | A#77 wrong Refresh fix | ⚠️ BUILT BUT FAILED |
| 1.2.9+70 | A#77b Listen Refresh black screen fix | ✅ |
| 1.2.9+71 | A#78 mic permission fix + dead import | ✅ |
| 2.1.1+1–+3 | A#79/A#80 dual-environment — superseded | ⏭️ SKIPPED |
| 2.1.1+6–+7 | A#81 poll hardening — superseded | ⏭️ SKIPPED |
| 2.1.1+8 | A#82 4 new features — superseded | ⏭️ SKIPPED |
| 2.1.1+9–+18 | A#83/A#84 cloud fixes + App Store prep — superseded | ⏭️ SKIPPED |
| **2.2.0+1** | **A#85 Storied release — onboarding + attestation stubs + TestFlight** | **⏳ READY TO BUILD** |

#### Git operation ownership
| Operation | Who | Where |
|---|---|---|
| `git pull` + build + `git push` (pubspec bump) | Mac Mini Q | `~/Development/Audioura-build/` |
| Edit + commit iOS-only files + planning docs | Windows Q | `C:\Users\micha\eclipse-workspace\AudioTours\development\` |
| Dart code changes + version bumps | Mobile Kiro | per assignment |
| `git pull` to sync after pushes | Sir Michael (Windows) | Windows dev tree |

⚠️ Mobile Kiro must NOT edit `remind_ios_ai.md` — this file is iOS Q's domain only.

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
- **Android agent**: Mobile Kiro (Kiro IDE) — replaced Android Amazon-Q as of 2026-06-08
- **Cloud URL**: `https://api.audioura.com` (hint in About screen)

---

### 📱 **APP STATUS**
- **iPhone**: v1.2.9+71 (A#85 Storied build pending → v2.2.0+1)
- **All shipped features**: Tour clustering, location search, tour search, newsletter system, subscription, language selector, about screen, settings persistence, location permissions, keyboard dismissal, download spinner fix, microphone voice control, translation (ru/fr/zh), walking tour map, per-stop map focus, coordinate jitter, museum single-POI map guard, mode-switch fix, stale tour/news path healing, brick-red app icon, app name "Audioura", InAppWebView v6, map icon on Listen page, POI tap → TourMapScreen via `openMap` JS handler, Listen page Refresh in-place reload, Listen page mic permission fix.
- **New in v2.2.0+1** (pending A#85 build): Cloud-first defaults, baked-in API key, all cloud URLs sending X-API-Key, translation modal, overflow menu, Report tour, Treats tab, Account deletion iOS flow, 402 handling, full URL audit, onboarding personalization, App Attestation Dart stubs.

---

### 🔄 **WORKFLOW RULES**
1. Assignments: Windows Q writes to `usb/Audioura/assignments/mac_mini_assignments.md` → copies to USB → commits + pushes → Mac Mini Q pulls + executes.
2. iOS-only file changes (`Info.plist`, `Podfile`): Windows Q edits + commits + pushes → Mac Mini pulls.
3. Dart code changes: Mobile Kiro commits. Windows Q never touches `lib/`.
4. After parity build: no pubspec commit needed (Mobile Kiro already bumped it).
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
- `_startVoiceSearch()` — **A#78**: no `Permission.microphone.request()`. `onStatus` not wired (auto-dismiss deferred)
- **v2.1.1+8**: Purple translate icon on non-translated tours → `TourTranslationHelper.translateTour()`

#### tour_generator_screen.dart (LF — Python edits only)
- **v2.1.1+6/+7**: `Future.delayed` self-scheduling poll loop. `_pollTimer` GONE.
- `if (_isGenerating) return;` guard in `_generateTour` + `_generateTourBackground`
- `unawaited(pollLoop().catchError(...))` — resets `_isGenerating` on crash
- `translation_failed` orange snackbar

#### about_screen.dart (CRLF)
- Local/Cloud toggle, cloud URL field, **API Key field** (temporary), gateway path routing checkbox
- **v2.1.1+8**: Danger Zone section — red "Delete My Account" button, two-step confirm, server-first DELETE

#### lib/config/endpoints.dart
- `Endpoints.base(Service)` — local `http://ip:port` or cloud URL per `server_mode`
- `Endpoints.url(Service, path)` — full URI
- `Endpoints.apiHeaders(Service, {requestBody})` — `Content-Type` always; `X-API-Key` + `X-App-Attestation` stub in cloud mode
- `Endpoints.newsDownloadUrl(id)` — `/news-download/<id>` cloud, `/download/<id>` local
- `Endpoints.newsStatusUrl(id)` — `/news-status/<id>` cloud, `/status/<id>` local
- New Service entries: `treats` (:5007), `voice` (:5008), `tourEditing` (:5022) — cloud-gated

#### lib/services/tour_translation_helper.dart (NEW in v2.1.1+8)
- Shared logic for existing-tour translation from Listen page

#### lib/services/app_attestation_service.dart (NEW in v2.1.1+8)
- Platform stubs, returns null. iOS Phase 4 (native Swift MethodChannel) is future work.
- Channel: `com.audioura.app/attestation`, Method: `getAssertion`, Args: `{'nonce': String}`

#### tour_player_screen.dart (CRLF)
- `addJavaScriptHandler('openMap')` in `onWebViewCreated` — **A#76**
- `initialSettings: InAppWebViewSettings(...)` — v6 API ✅

#### news_player_screen.dart (CRLF)
- `_getIndexUrl()` heals stale container paths. `FutureBuilder<String>`. v6 API ✅

#### tour_map_screen.dart (CRLF)
- `focusStopIndex` (int?, 1-based). `_applyCoordJitter()`. Single-POI guard.

#### main_screen.dart (CRLF)
- `_buildBody()` switch — never wrap in IndexedStack. `_listenTabVersion` key for Listen reload.

---

### 📋 **OPEN ITEMS**
1. **A#85** ⚠️ READY TO BUILD — v2.2.0+1 Storied release. `storied` branch. See Immediate Next Steps.
   - Sir Michael: create App Store Connect record + App-Specific Password BEFORE upload step (Step 10).
2. **App Attestation Phase 4** — iOS native Swift MethodChannel (`com.audioura.app/attestation`). Blocked on Android Phase 3 (Play Integrity) validation first. Future assignment — Windows Q will need to edit `ios/` Swift files.
3. **API Key field removal** — About screen manual API Key input is temporary. Future: embed/auto-supply key.
4. **Dialog auto-dismiss** — `_startVoiceSearch()` dialog doesn't auto-close on 10s timeout. `onStatus` not wired. Deferred.
5. **ISSUE-SERVICES-NEWSLETTER** — `get_articles_by_newsletter_id` returns only 2 of 5 articles. Awaiting Kiro.
6. **ISSUE-061** — Translated tours → 404. Awaiting Services fix.
7. **NF4 (LOW)** — `openMap` handler bare-int widening.
8. **NF5 (LOW)** — `Colors.blue.withOpacity(0.6)` → `.withValues(alpha: 0.6)`.
9. **OSM tiles** — swap to Stadia Maps or Mapbox before App Store.
10. **Dead files** — delete `audio_handler.dart`, `map_page.dart`, `subscription_management_screen.dart`.

---

### ⚠️ **CRITICAL TECHNICAL NOTES**
- **Version numbering**: iOS and Android share `pubspec.yaml`. Mobile Kiro owns version bumps. iOS Q never bumps independently.
- **Parity rule**: Both platforms always build the same commit on `services-migration`. No iOS-specific Dart forks.
- **iOS-only files**: `ios/Runner/Info.plist`, `ios/Runner.xcodeproj/`, `ios/Podfile` — Windows Q may edit these. Everything in `lib/` is shared.
- **API Key (temporary)**: `Endpoints.apiHeaders()` reads `gateway_api_key` from SharedPreferences and sends as `X-API-Key` in cloud mode only. Field will be removed once key is embedded.
- **LF files**: `home_screen.dart`, `tour_generator_screen.dart`, `my_tours_screen.dart` — `fsReplace` FAILS. Python only.
- **CRLF files**: `tour_map_screen.dart`, `tour_player_screen.dart`, `main_screen.dart`, `news_player_screen.dart`, `about_screen.dart` — `fsReplace` works.
- **Python stdout**: always empty in `executeBash`. Write to `D:\Audioura\results\<name>.txt`, read with `type`.
- **InAppWebView**: v6 API only — `initialSettings: InAppWebViewSettings(...)`. v5 `initialOptions` BANNED.
- **ATS**: Flutter `package:http` bypasses iOS ATS. Local HTTP works without plist entry. Cloud is HTTPS.
- **pod install**: always run after `git pull` on Mac Mini before building.
- **DebugLogHelper**: in `lib/screens/debug_log_viewer_screen.dart`.
- **unawaited()**: requires `import 'dart:async'`.
- **`_pollTimer` is GONE**: removed in v2.1.1+6. Any reference = compile error. Do not reintroduce.
- **App Attestation stubs**: `AppAttestationService` returns null — Phase 4 iOS native work is pending. Do not attempt to implement Swift side until Android Phase 3 is validated.

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
| `lib/screens/my_tours_screen.dart` | Tours/news list. LF. A#77b + A#78. v2.1.1+8: translate icon. |
| `lib/screens/tour_generator_screen.dart` | Tour generation + poll loop. LF. v2.1.1+6/+7 poll rewrite. |
| `lib/screens/about_screen.dart` | Local/Cloud toggle + API Key + Danger Zone delete. CRLF. |
| `lib/screens/main_screen.dart` | Tab navigation. CRLF. |
| `lib/screens/tour_player_screen.dart` | `openMap` JS handler. CRLF. |
| `lib/screens/news_player_screen.dart` | Path healing + FutureBuilder. CRLF. |
| `lib/screens/tour_map_screen.dart` | Map screen. Jitter + single-POI guard. CRLF. |
| `lib/screens/debug_log_viewer_screen.dart` | `DebugLogHelper` class. |
| `lib/config/endpoints.dart` | `Endpoints` resolver — base URL + apiHeaders + newsDownloadUrl. |
| `lib/services/tour_status_service.dart` | Tour status REST via Endpoints. |
| `lib/services/translation_service.dart` | Translation via Endpoints (cloud-ready). |
| `lib/services/tour_translation_helper.dart` | NEW v2.1.1+8 — Listen-page translation logic. |
| `lib/services/app_attestation_service.dart` | NEW v2.1.1+8 — Attestation stubs (null). |
| `lib/config.dart` | `Config.defaultServerIp = '192.168.0.218'` |
| `ios/Runner/Info.plist` | iOS permissions + `NSLocalNetworkUsageDescription`. |
| `usb/Audioura/assignments/mac_mini_assignments.md` | Mac Mini task queue. A#85 at top. |
| `git_source_control_for_q.md` | Git rules — READ before any git operation. |

---

### 🤖 **ANDROID PARITY (Mobile Kiro)**
- Android bundle ID: `com.audioura.app` (iOS: `com.glikfamily.audioura`)
- Mobile Kiro replaced Android Amazon-Q as of 2026-06-08 — same codebase, same branch
- Version sync: Mobile Kiro bumps `pubspec.yaml` → iOS Q pulls + builds same commit
- iOS Q never bumps version independently
- ⚠️ Mobile Kiro must NOT edit `remind_ios_ai.md` — this file is iOS Q's domain only

---

**Last Updated**: 2026-06-30 — v113.0. pubspec at `2.2.0+1` on `storied` branch (HEAD `0045823`). iPhone on v1.2.9+71. A#85 Storied release assignment written — takes iPhone from v1.2.9+71 to v2.2.0+1 in one build + TestFlight upload. Supersedes A#84 (never built). New features: onboarding personalization + App Attestation Dart stubs. Flutter app root on storied branch is `audio_tour_app/` not `development/audio_tour_app/`.
**iOS Amazon-Q Version**: 113.0
