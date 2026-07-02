# iOS AudioTours AI Context Reminder
## 🍎 iOS Amazon-Q Recovery Guide — POST-COMPACTION ENTRY POINT

### 🪪 **IDENTITY — ALWAYS START WITH THIS**
Every response in a new session must begin with:
**🍎 iOS AMAZON-Q**
This is required so the user can identify which Amazon-Q tab they are talking to.

---

### ✅ **CURRENT STATE — v2.2.0+1 STORIED RELEASE READY TO BUILD**

- iPhone last confirmed on **v1.2.9+71** (A#78 mic fix — smoke test passed 2026-06-02)
- **A#85 is the active assignment** — v2.2.0+1 from `storied` branch. First App Store / TestFlight submission build.
- **Branch is `storied`** — NOT `services-migration`
- **Flutter app root on Mac Mini** is `~/Development/Audioura-build/audio_tour_app/` — NOT `development/audio_tour_app/`
- **API key baked in** via `--dart-define=GATEWAY_API_KEY="aura-gw-360721-880288"` — app defaults to Cloud mode on fresh install, no manual entry needed
- **Mobile Kiro** (Kiro IDE) replaced Android Amazon-Q as of 2026-06-08
- **App Attestation iOS native (Phase 4)** NOT yet implemented — `MissingPluginException` handled gracefully, never blocks
- ⚠️ **Sir Michael must create App Store Connect record + App-Specific Password BEFORE upload step**

---

### 🎯 **IMMEDIATE NEXT STEPS**

#### A#85 — Build v2.2.0+1 Storied Release ⚠️ READY TO BUILD

**Sir Michael pre-requisites (do BEFORE Mac Mini build):**
1. **appstoreconnect.apple.com** → New App → iOS → Name: **Audioura** → Bundle ID: **com.glikfamily.audioura** → SKU: **audioura-1** → complete App Privacy details
2. **appleid.apple.com** → Sign-In and Security → App-Specific Passwords → Generate → label "Mac Mini Audioura Upload" → save it

**What this delivers over v1.2.9+71 (all changes since last iPhone build):**
- Cloud-first defaults, API key baked in via dart-define, all cloud URLs send `X-API-Key`
- Friendly error messages, translation failure modal dialog
- Listen page overflow menu (⋮) — translate/edit/delete/report
- Report this tour — prefilled mailto
- Account deletion — iOS pops to root with "Please reopen" message
- Treats tab — "Samples for the future" banner + real backend
- 402 subscription_required handled gracefully
- Full hardcoded URL audit, poll hardening, re-entry guard
- **NEW — Onboarding Personalization:** "What brings you here?" on first launch, 4 choices (🎨 Art & Culture, 📖 History, 👨👩👧 Family Fun, ✈️ First-time Visitor + Skip), saves `narrative_tone`, never shows again after first choice
- **NEW — App Attestation Dart stubs:** MethodChannel `com.audioura.app/attestation` wired, iOS native side pending (graceful null fallback)

**Target commit:** `2962fe5` (or later `0045823`)  **pubspec:** `2.2.0+1`  **Branch:** `storied`

**Mac Mini build sequence:**
```bash
cd ~/Development/Audioura-build
git fetch origin
git checkout storied
git pull origin storied
# Verify: grep "^version:" audio_tour_app/pubspec.yaml → 2.2.0+1
cd audio_tour_app/ios && pod install && cd ..
flutter clean && flutter pub get
flutter build ipa --release --dart-define=GATEWAY_API_KEY="aura-gw-360721-880288"
# Install on device for smoke test:
xcrun devicectl device install app \
  --device F9D6F807-D301-59EE-B574-5747D617D82C \
  build/ios/ipa/audioura.ipa
# After smoke test passes — upload to TestFlight:
xcrun altool --upload-app -f build/ios/ipa/audioura.ipa \
  -t ios -u glikfamily@gmail.com -p <app-specific-password>
```

**Smoke tests (9) — uninstall old app first (onboarding only shows on fresh install):**
1. Onboarding — "What brings you here?" on fresh install, 4 choices, never repeats on relaunch
2. Cloud tour generation — no 401, generates automatically (no manual URL/key entry)
3. Cloud news/newsletter — processes, downloads, plays
4. Translation — works; failure shows modal dialog (not silent fallback)
5. Account deletion — About → Delete → iOS pops to root with restart message
6. Report tour — overflow menu (⋮) → Report → email compose opens prefilled
7. Treats tab — "Samples for the future" banner + real content
8. Map/POI — tour player → tap map icon → TourMapScreen opens
9. Mic/Voice — Listen tab → tap mic → listening dialog, no permission snackbar

**TestFlight after smoke test passes:**
- Xcode Organizer alternative: `open ios/Runner.xcworkspace` → Product → Archive → Distribute App → App Store Connect → Upload

---

### 🔑 **GIT / BUILD STATE**

```
GitHub (remote)
  repo: michaelglik-audiotoursai/Audioura
  Active branch: storied (v2.2.0+1)
  Beta branch:   services-migration (v2.1.1+18 — superseded for iOS)

Mac Mini clone                    Windows dev tree
~/Development/Audioura-build/     C:\Users\micha\eclipse-workspace\AudioTours\development\
branch: storied                   branch: storied (after sync)
app root: audio_tour_app/         (reference + planning docs only)
```

- **Mac Mini build clone**: `~/Development/Audioura-build/`, currently on `storied` branch
- **Flutter app on Mac Mini**: `~/Development/Audioura-build/audio_tour_app/` ⚠️ NOT `development/audio_tour_app/`
- **Windows dev tree**: `C:\Users\micha\eclipse-workspace\AudioTours\development\` — git clone. iOS Q edits iOS-only files + planning docs here. Never commits Dart code.
- **USB drive**: currently on **drive E:** (moved from D:). Mirror path: `usb/Audioura/`. After editing assignments: `copy usb\Audioura\assignments\mac_mini_assignments.md E:\Audioura\assignments\`
- **OLD repo**: `~/Development/AudioTours/` — BROKEN, never use
- **pubspec**: `2.2.0+1` (Mobile Kiro bumped, `storied` branch)
- **Head commit (storied)**: `0045823` — storied_mode ALTER + audio_tours INSERT fix (on top of `2962fe5` v2.2.0+1 tag)
- **Head commit (services-migration)**: `e9e6909` — v113.0 planning docs

#### Version history
| Version | Assignment | Status |
|---------|-----------|--------|
| 1.2.9+68–+71 | A#76–A#78 POI map, Refresh fix, mic fix | ✅ BUILT |
| 2.1.1+1–+18 | A#79–A#84 dual-env, cloud fixes, App Store prep | ⏭️ ALL SKIPPED |
| **2.2.0+1** | **A#85 Storied — onboarding + TestFlight** | **⏳ READY TO BUILD** |

#### Git operation ownership
| Operation | Who | Where |
|---|---|---|
| checkout `storied` + build + upload | Mac Mini Q | `~/Development/Audioura-build/` |
| Edit iOS-only files + planning docs | Windows iOS Q | `C:\Users\micha\eclipse-workspace\AudioTours\development\` |
| Dart code changes + version bumps | Mobile Kiro | `storied` branch |
| Sync after pushes | Sir Michael (Windows) | Windows dev tree |

⚠️ Mobile Kiro must NOT edit `remind_ios_ai.md` — iOS Q's domain only.

---

### 🚀 **QUICK CONTEXT RECOVERY**
- **Mission**: iOS Amazon-Q for Audioura LLC mobile app
- **App name**: Audioura (`com.glikfamily.audioura`)
- **Device**: iPhone 16, UDID `F9D6F807-D301-59EE-B574-5747D617D82C`, iOS 18.3.1
- **Apple Dev account**: `glikfamily@gmail.com`, Team ID `4HGRU6TKGQ`, paid license valid until April 7 2027
- **Certificate**: Apple Development: Mikhail Glik (`594584F3D3BC571D94A822A2158871CA13898701`)
- **Flutter UDID** (provisioning): `00008140-000558A902BA801C`
- **Local network**: iPhone → Windows laptop Docker services at `192.168.0.218:5002/5004/5005/5030`
- **Cloud URL**: `https://api.audioura.com`
- **Gateway API key**: `aura-gw-360721-880288` (baked in via dart-define — never commit to git)
- **Build environment**: Mac Mini M4 + Xcode 16
- **Android agent**: Mobile Kiro (Kiro IDE)
- **Android bundle ID**: `com.audioura.audiotours` (iOS keeps `com.glikfamily.audioura`)

---

### 📱 **APP STATUS**
- **iPhone installed**: v1.2.9+71
- **Pending build**: v2.2.0+1 (A#85)
- **All shipped features** (v1.2.9+71 and earlier): Tour clustering, location search, tour search, newsletter system, subscription, language selector, about screen, settings persistence, location permissions, keyboard dismissal, download spinner fix, microphone voice control, translation (ru/fr/zh), walking tour map, per-stop map focus, coordinate jitter, museum single-POI map guard, mode-switch fix, stale tour/news path healing, brick-red app icon (#A93105), app name "Audioura", InAppWebView v6, map icon on Listen page, POI tap → TourMapScreen via `openMap` JS handler, Listen page Refresh in-place reload, mic permission fix.
- **New in v2.2.0+1** (pending A#85): Cloud-first defaults, baked-in API key, all cloud URLs send X-API-Key, translation modal, overflow menu (⋮), Report tour, Treats tab, Account deletion iOS flow, 402 handling, full URL audit, poll hardening, onboarding personalization, App Attestation Dart stubs.

---

### 🔄 **WORKFLOW RULES**
1. Assignments: Windows Q writes to `usb/Audioura/assignments/mac_mini_assignments.md` → copies to `E:\Audioura\assignments\` → commits + pushes → Mac Mini Q pulls + executes.
2. iOS-only file changes (`Info.plist`, `Podfile`, Swift files): Windows Q edits + commits + pushes → Mac Mini pulls.
3. Dart code changes: Mobile Kiro commits. Windows Q never touches `lib/`.
4. No pubspec bump needed after parity build — Mobile Kiro already bumped it.
5. **LF FILES**: `home_screen.dart`, `tour_generator_screen.dart`, `my_tours_screen.dart` — `fsReplace` FAILS on Windows. Python patch scripts only.
6. **PYTHON OUTPUT**: stdout unreliable in `executeBash`. Write to `E:\Audioura\results\<file>.txt`, read with `type`.
7. **USB drive is E:** (moved from D: — update any scripts referencing D:\Audioura).

---

### 🏗️ **BUILD PROCESS (storied branch)**
```bash
cd ~/Development/Audioura-build
git fetch origin && git checkout storied && git pull origin storied
cd audio_tour_app/ios && pod install && cd ..   # always after pull
flutter clean && flutter pub get
# Dev install (smoke test):
flutter build ios --release --dart-define=GATEWAY_API_KEY="aura-gw-360721-880288"
# App Store / TestFlight archive:
flutter build ipa --release --dart-define=GATEWAY_API_KEY="aura-gw-360721-880288"
```
- `flutter analyze` warnings in dead files (`audio_handler.dart`, `map_page.dart`, `subscription_management_screen.dart`, `widget_test.dart`) — non-blocking.
- `MissingPluginException` for `com.audioura.app/attestation` — expected, non-blocking (iOS native not yet implemented).
- If push rejected: `git pull origin storied` then push again.
- Never click "Allow secret" if GitHub secret scanning blocks a push.

---

### 🗺️ **KEY SCREEN ARCHITECTURE**

#### my_tours_screen.dart (LF — Python edits only)
- `_manualRefresh()` — in-place `_loadAppMode()`, no navigation teardown (A#77b)
- `_setupVoiceCommands()` — sole mic permission via `_speechToText.initialize()`
- `_startVoiceSearch()` — no `Permission.microphone.request()` (A#78). `onStatus` not wired (auto-dismiss deferred)
- Purple translate icon on non-translated tours → `TourTranslationHelper.translateTour()`
- Overflow menu (⋮) — translate/edit/delete/report options

#### tour_generator_screen.dart (LF — Python edits only)
- `Future.delayed` self-scheduling poll loop — `_pollTimer` COMPLETELY GONE (compile error if reintroduced)
- `if (_isGenerating) return;` re-entry guard in `_generateTour` + `_generateTourBackground`
- `unawaited(pollLoop().catchError(...))` — resets `_isGenerating` on crash
- `translation_failed` orange snackbar
- `user_id` included in tour generation body (fixes cloud 401 `auth_required`)
- All news/newsletter URLs use `Endpoints.url()` — no hardcoded `5012`/`5017`

#### about_screen.dart (CRLF)
- Local/Cloud toggle, cloud URL field, API Key field (temporary), gateway path routing checkbox
- Danger Zone — red "Delete My Account", two-step confirm, server-first DELETE, iOS pops to root

#### lib/config/endpoints.dart
- `Endpoints.base(Service)` — local `http://ip:port` or cloud URL per `server_mode`
- `Endpoints.url(Service, path)` — full URI
- `Endpoints.apiHeaders(Service, {requestBody})` — `Content-Type` always; `X-API-Key` + `X-App-Attestation` stub in cloud mode
- `Endpoints.newsDownloadUrl(id)` — `/news-download/<id>` cloud, `/download/<id>` local
- `Endpoints.newsStatusUrl(id)` — `/news-status/<id>` cloud, `/status/<id>` local
- Service enum includes: `treats` (:5007), `voice` (:5008), `tourEditing` (:5022) — cloud-gated with clean messages

#### lib/services/app_attestation_service.dart
- Dart MethodChannel stub — returns null. iOS native Phase 4 pending.
- Channel: `com.audioura.app/attestation`, Method: `getAssertion`, Args: `{'nonce': String}`

#### lib/screens/onboarding_screen.dart (NEW v2.2.0+1)
- Shows on first launch only. 4 persona choices. Saves `narrative_tone` to SharedPreferences.

#### tour_player_screen.dart (CRLF)
- `addJavaScriptHandler('openMap')` in `onWebViewCreated` (A#76)
- `initialSettings: InAppWebViewSettings(...)` — v6 API only

#### news_player_screen.dart (CRLF)
- `_getIndexUrl()` heals stale container paths. `FutureBuilder<String>`. v6 API.

#### tour_map_screen.dart (CRLF)
- `focusStopIndex` (int?, 1-based). `_applyCoordJitter()`. Single-POI guard.

#### main_screen.dart (CRLF)
- `_buildBody()` switch — never wrap in IndexedStack. `_listenTabVersion` key for Listen reload.

---

### 📋 **OPEN ITEMS**
1. **A#85** ⚠️ READY TO BUILD — v2.2.0+1 `storied` branch. Sir Michael: App Store Connect record + App-Specific Password first.
2. **App Attestation Phase 4** — iOS native Swift: new file `ios/Runner/AppAttestHandler.swift` + register MethodChannel in `AppDelegate.swift`. Blocked until Android Phase 3 (Play Integrity) validated.
3. **API Key field** — About screen manual entry is temporary dev tool. Future: remove field, embed key.
4. **Dialog auto-dismiss** — `_startVoiceSearch()` 10s timeout doesn't auto-close dialog. `onStatus` not wired. Deferred.
5. **ISSUE-SERVICES-NEWSLETTER** — `get_articles_by_newsletter_id` returns only 2 of 5 articles. Awaiting Kiro.
6. **ISSUE-061** — Translated tours → 404. Awaiting Services fix.
7. **OSM tiles** — swap to Stadia Maps or Mapbox before public App Store release.
8. **Dead files** — delete `audio_handler.dart`, `map_page.dart`, `subscription_management_screen.dart`.

---

### ⚠️ **CRITICAL TECHNICAL NOTES**
- **`storied` branch app root**: `audio_tour_app/` — NOT `development/audio_tour_app/`
- **`_pollTimer` is GONE**: removed in v2.1.1+6. Any reference = compile error. Never reintroduce.
- **GATEWAY_API_KEY dart-define**: CRITICAL — without it every cloud call returns 401. Never commit the key value to git.
- **Version bumps**: Mobile Kiro owns all pubspec bumps. iOS Q never bumps independently.
- **iOS-only files**: `ios/Runner/Info.plist`, `ios/Runner.xcodeproj/`, `ios/Podfile`, future Swift files — Windows Q may edit these. Everything in `lib/` is shared Dart.
- **LF files**: `home_screen.dart`, `tour_generator_screen.dart`, `my_tours_screen.dart` — `fsReplace` FAILS on Windows. Python patch scripts only.
- **CRLF files**: `tour_map_screen.dart`, `tour_player_screen.dart`, `main_screen.dart`, `news_player_screen.dart`, `about_screen.dart` — `fsReplace` works.
- **Python stdout**: always empty in `executeBash`. Write to `E:\Audioura\results\<name>.txt`, read with `type`.
- **InAppWebView**: v6 API only — `initialSettings: InAppWebViewSettings(...)`. v5 `initialOptions` BANNED.
- **ATS**: Flutter `package:http` bypasses iOS ATS. Local HTTP works without plist entry. Cloud is HTTPS.
- **pod install**: always run after branch checkout or pull on Mac Mini.
- **USB drive**: now on **E:** (was D:). All copy commands use `E:\Audioura\`.
- **DebugLogHelper**: in `lib/screens/debug_log_viewer_screen.dart`.
- **unawaited()**: requires `import 'dart:async'`.

---

### 🔧 **TROUBLESHOOTING**
```bash
# iPhone not detected:
sudo launchctl kickstart -k system/com.apple.usbd
# Flutter checks:
flutter doctor -v && flutter devices
# Verify pubspec on Mac Mini (storied branch):
grep "^version:" ~/Development/Audioura-build/audio_tour_app/pubspec.yaml
# Uninstall app from iPhone:
xcrun devicectl device uninstall app --device F9D6F807-D301-59EE-B574-5747D617D82C com.glikfamily.audioura
# Pod issues:
cd ios && pod deintegrate && pod install
# Signing check:
grep -E 'PRODUCT_BUNDLE_IDENTIFIER|DEVELOPMENT_TEAM' \
  ios/Runner.xcodeproj/project.pbxproj | sort -u
# Expected: com.glikfamily.audioura and 4HGRU6TKGQ
```

---

### 📂 **KEY FILES**
| File | Location / Notes |
|------|-----------------|
| `lib/screens/home_screen.dart` | Download + translation. LF. |
| `lib/screens/my_tours_screen.dart` | Tours/news list. LF. Overflow menu. Translate icon. |
| `lib/screens/tour_generator_screen.dart` | Tour generation + poll loop. LF. No `_pollTimer`. |
| `lib/screens/about_screen.dart` | Local/Cloud toggle + Danger Zone delete. CRLF. |
| `lib/screens/onboarding_screen.dart` | NEW v2.2.0+1 — first-launch persona picker. |
| `lib/screens/main_screen.dart` | Tab navigation. CRLF. |
| `lib/screens/tour_player_screen.dart` | `openMap` JS handler. CRLF. |
| `lib/screens/news_player_screen.dart` | Path healing + FutureBuilder. CRLF. |
| `lib/screens/tour_map_screen.dart` | Map screen. Jitter + single-POI guard. CRLF. |
| `lib/screens/debug_log_viewer_screen.dart` | `DebugLogHelper` class. |
| `lib/config/endpoints.dart` | `Endpoints` resolver — all URL + header logic. |
| `lib/services/tour_status_service.dart` | Tour status REST via Endpoints. |
| `lib/services/translation_service.dart` | Translation via Endpoints (cloud-ready). |
| `lib/services/tour_translation_helper.dart` | Listen-page translation logic. |
| `lib/services/app_attestation_service.dart` | Attestation Dart stub (null). Phase 4 pending. |
| `lib/config.dart` | `Config.defaultServerIp = '192.168.0.218'` |
| `ios/Runner/Info.plist` | iOS permissions + `NSLocalNetworkUsageDescription`. |
| `ios/Runner/AppDelegate.swift` | Future: register attestation MethodChannel here. |
| `usb/Audioura/assignments/mac_mini_assignments.md` | Mac Mini task queue. A#85 at top. |
| `git_source_control_for_q.md` | Git rules — READ before any git operation. |

---

### 🤖 **MOBILE KIRO (Android agent)**
- Android bundle ID: `com.audioura.audiotours` (iOS: `com.glikfamily.audioura`)
- Mobile Kiro (Kiro IDE) replaced Android Amazon-Q as of 2026-06-08
- Communicates via `C:\Users\micha\eclipse-workspace\amazon-q-communications\audiotours\requirements\`
- Version sync: Mobile Kiro bumps `pubspec.yaml` → iOS Q reads build request doc → creates Mac Mini assignment
- ⚠️ Mobile Kiro must NOT edit `remind_ios_ai.md`

---

**Last Updated**: 2026-06-30 — v114.0 (post-compaction clean rewrite).
**State**: iPhone on v1.2.9+71. A#85 ready — v2.2.0+1 `storied` branch, release archive + TestFlight upload. USB on E:. Flutter app root on Mac Mini is `audio_tour_app/` (not `development/audio_tour_app/`). Gateway API key baked in via dart-define. App Attestation iOS native (Phase 4) pending future assignment.
**iOS Amazon-Q Version**: 114.0
