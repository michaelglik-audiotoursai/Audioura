# iOS AudioTours AI Context Reminder
## 🍎 iOS Amazon-Q Recovery Guide — POST-COMPACTION ENTRY POINT

### 🪪 **IDENTITY — ALWAYS START WITH THIS**
Every response in a new session must begin with:
**🍎 iOS AMAZON-Q**
This is required so the user can identify which Amazon-Q tab they are talking to.

---

### ✅ **CURRENT STATE — v1.2.9+71 BUILT, SMOKE TEST IN PROGRESS**

- iPhone running **v1.2.9+70** (A#77b complete) ✅
- **v1.2.9+71 has been built by Mac Mini** — A#78 fix installed on iPhone. Smoke test in progress (Sir Michael).
- **A#79 is defined** — dialog-hang hardening + lazy re-init for `_startVoiceSearch()`. NOT yet started.

---

### 🎯 **IMMEDIATE NEXT STEPS**

#### Waiting on: A#78 smoke test result from Sir Michael
Mac Mini built v1.2.9+71. Sir Michael is running smoke tests:
1. Mic dialog opens without snackbar ← primary fix
2. Say nothing for 10s → observe if dialog auto-closes ← observe-only (see A#79 note below)
3. Listen Refresh no black screen ← A#77b regression
4. General regression (tour audio, news article, POI map)

If smoke test passes → A#78 is COMPLETE. Update this doc to v106.0 and mark A#78 done.
If smoke test fails → diagnose and write A#78c patch.

#### A#79 — Dialog-hang hardening (DEFINED, NOT YET STARTED)
**Background — auto-dismiss investigation (2026-06-02):**
The smoke test showed the dialog does NOT auto-close after 10s of silence. This was investigated and confirmed as **never implemented** — not a regression. The `listen()` call has only `onResult` + `listenFor: Duration(seconds: 10)`. When `listenFor` elapses with no speech, `speech_to_text` fires a status change to `"done"`/`"notListening"` internally, but `onStatus` is not wired in the app, so nothing dismisses the dialog. Cancel button works correctly. This is acceptable for v1.2.9+71 — no fix needed before ship.

**A#79 scope (from Claude sign-off):**
1. `try/catch` around `_speechToText.listen()` → on error: pop dialog, `_stopListening()`, brief message.
2. Wire `onStatus` callback into `_speechToText.listen()` — dismiss dialog + reset `_isListening` on `"done"`/`"notListening"`.
3. Auto-dismiss aligned with `listenFor` so silence closes the dialog.
4. Lazy re-init in `_startVoiceSearch()` when `!_speechEnabled` (handles init-race).
5. `mounted` guards on `_handleVoiceSearchCommand` and `_stopListening` after `await`s.

**Target:** v1.2.9+72. Write patch after A#78 smoke test confirmed.

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
- **Windows dev tree**: `C:\Users\micha\eclipse-workspace\AudioTours\development\` — IS a git clone, branch `services-migration`. Q edits files here, commits planning/directives docs. Never commits code — Mac Mini does that.
- **USB mirror in git**: `usb/Audioura/` in Windows dev tree mirrors `D:\Audioura\`. After editing, copy to USB: `copy usb\Audioura\assignments\mac_mini_assignments.md D:\Audioura\assignments\`
- **OLD repo**: `~/Development/AudioTours/` — BROKEN, never use
- **pubspec.yaml**: `1.2.9+71` after Mac Mini build of A#78.

#### Git operation ownership
| Operation | Who | Where |
|---|---|---|
| `git pull` + build + `git push` | Mac Mini Q | `~/Development/Audioura-build/` |
| Edit + commit directives/planning docs + code fixes | Windows Q | `C:\Users\micha\eclipse-workspace\AudioTours\development\` |
| `git pull` to sync after Mac Mini pushes | Sir Michael (Windows) | Windows dev tree |

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
- **iPhone**: v1.2.9+71 (smoke test in progress) ⏳
- **All shipped features**: Tour clustering, location search, tour search, newsletter system, subscription, language selector, about screen, settings persistence, location permissions, keyboard dismissal, download spinner fix, microphone voice control, translation (ru/fr/zh), walking tour map, per-stop map focus, coordinate jitter, museum single-POI map guard, mode-switch fix, stale tour/news path healing, brick-red app icon, app name "Audioura", InAppWebView v6, map icon on Listen page, POI tap → TourMapScreen via `openMap` JS handler, Listen page Refresh in-place reload, Listen page mic permission fix.

---

### 🔄 **WORKFLOW RULES**
1. Assignments: Windows Q writes directives to `usb/Audioura/assignments/mac_mini_assignments.md` → copies to USB → commits + pushes → Mac Mini Q pulls + executes.
2. Code fixes on Windows: edit in `development/audio_tour_app/lib/` → commit → push → Mac Mini pulls + builds.
3. After successful build: Mac Mini commits pubspec bump + pushes. Windows does `git pull` to sync.
4. **LF FILES**: `home_screen.dart`, `tour_generator_screen.dart`, `my_tours_screen.dart` — `fsReplace` FAILS on Windows. Python patch scripts only.
5. **PYTHON OUTPUT**: stdout is unreliable in `executeBash`. Always write results to `D:\Audioura\results\<file>.txt` and read back with `executeBash` `type D:\Audioura\results\<name>.txt`. Writing to dev tree path does NOT reliably work.
6. Read `git_source_control_for_q.md` before any git operation.

---

### 🏗️ **BUILD PROCESS**
```bash
cd ~/Development/Audioura-build
git pull origin services-migration
cd development/audio_tour_app
flutter clean && flutter pub get
cd "/Volumes/USB DISK/Audioura/scripts"
./build_install_launch.sh
```
- `flutter analyze` issues in dead files only (`audio_handler.dart`, `map_page.dart`, `subscription_management_screen.dart`, `test/widget_test.dart`) — non-blocking.
- If `git push` blocked by GitHub secret scanning — STOP, report, never click "Allow secret".
- If push rejected (fetch first) — Mac Mini pushed while Windows was working. Do `git pull origin services-migration` then push again.

---

### 🗺️ **KEY SCREEN ARCHITECTURE**

#### my_tours_screen.dart (LF — Python edits only)
- Shows tours (Tours mode) or news articles (Audio mode) depending on `_appMode`
- `_loadAppMode()` → routes to `_loadTours()` or `_loadNews()` — called by `initState` and `_manualRefresh`
- `_healTourPaths()` — heals stale container paths in saved_tours
- `_detectMapTours()` — checks `audio_1.txt` for `Coordinates:` to show map icon
- `_manualRefresh()` — **A#77b**: `Future<void>`, logs, `if (!mounted) return`, calls `_loadAppMode()`. No navigation teardown.
- `_setupVoiceCommands()` — calls `_speechToText.initialize()` in `initState`. Sole mic permission acquisition.
- `_startVoiceSearch()` — **A#78**: `Permission.microphone.request()` block removed. `permission_handler` import removed. Guards only on `!_speechEnabled`. `listen()` has `onResult` + `listenFor: 10s` — no `onStatus` wired (auto-dismiss not implemented — by design for now, A#79 will add it).
- ⚠️ Known pre-existing: Refresh while in Select Articles mode may RangeError if list size changes. Not a blocker.

#### tour_player_screen.dart (CRLF)
- `addJavaScriptHandler('openMap')` registered in `onWebViewCreated` — **A#76**
- `openMap` handler: `args[0]['stop']` → `int` → pushes `TourMapScreen(focusStopIndex: stopIndex)`
- Uses `initialSettings: InAppWebViewSettings(...)` — v6 API ✅

#### news_player_screen.dart (CRLF)
- `_getIndexUrl()` heals stale container paths at WebView launch
- `FutureBuilder<String>` wraps WebView body, `_indexUrlFuture` cached in `initState`
- `initialSettings: InAppWebViewSettings(...)` — v6 API ✅

#### tour_map_screen.dart (CRLF)
- `focusStopIndex` (int?, 1-based) — focuses map on specific stop
- `_applyCoordJitter()` — offsets duplicate-coord POIs ~0.00008°
- Single-POI guard: `if (points.length == 1) { _mapController.move(points.first, 15); return; }`
- Coordinates regex: `RegExp(r'Coordinates:\s*([-\d.]+)\s*,\s*([-\d.]+)')` (space-tolerant)

#### main_screen.dart (CRLF)
- `_buildBody()` switch — **never** wrap in IndexedStack (regression risk)
- `_listenTabVersion` + `MyToursScreen(key: ValueKey(_listenTabVersion))` — preserves Listen reload

#### home_screen.dart (LF — Python edits only)
- Download + translation logic
- Newsletter Refresh handler in `_buildNewsletterView` — **A#77**: `setState(_isLoading=true)` removed

---

### 📋 **OPEN ITEMS**
1. **A#78** ⏳ SMOKE TEST IN PROGRESS — v1.2.9+71. Built by Mac Mini. Sir Michael testing mic fix.
2. **A#79** DEFINED — v1.2.9+72. Dialog-hang hardening for `_startVoiceSearch()`. Write patch after A#78 confirmed. See "Immediate Next Steps" above for full scope.
3. **Android A#78 parity** — `android_assignment_a78_2026_06_02.md` written. Give to Android Q.
4. **ISSUE-SERVICES-NEWSLETTER** — `get_articles_by_newsletter_id` returns only 2 of 5 articles for newsletter 280. Filed. Awaiting Kiro. NOT an iOS bug.
5. **ISSUE-061** — Translated tours in `/tours-near/` → 404. Filed for Services. iOS work follows after server fix.
6. **NF4 (LOW)** — `openMap` handler bare-int widening. Two-line fix.
7. **NF5 (LOW)** — `Colors.blue.withOpacity(0.6)` → `.withValues(alpha: 0.6)`.
8. **OSM tiles** — swap to Stadia Maps or Mapbox before App Store.
9. **Dead files** — delete `audio_handler.dart`, `map_page.dart`, `subscription_management_screen.dart` so `flutter analyze` is a clean signal.

---

### 🔄 **RECENT ASSIGNMENT HISTORY**
- **A#76**: ✅ v1.2.9+68 — POI map button fix + map icon restore. Commit `f2bb356`. 2026-06-01.
- **A#77**: ⚠️ v1.2.9+69 BUILT BUT FAILED — fixed wrong Refresh button. Black screen persisted.
- **A#77b**: ✅ v1.2.9+70 CONFIRMED ON iPHONE — `_manualRefresh()` replaced with in-place `_loadAppMode()`. Commit `4948178`. 2026-06-02.
- **A#78**: ⏳ v1.2.9+71 BUILT — removed redundant `Permission.microphone.request()` + dead import. Commits `df6b61b` + `92d0175`. Smoke test in progress. 2026-06-02.

---

### ⚠️ **CRITICAL TECHNICAL NOTES**
- **LF files**: `home_screen.dart`, `tour_generator_screen.dart`, `my_tours_screen.dart` — `fsReplace` FAILS. Python only.
- **CRLF files**: `tour_map_screen.dart`, `tour_player_screen.dart`, `main_screen.dart`, `news_player_screen.dart` — `fsReplace` works.
- **Python stdout**: always empty in `executeBash`. Write to `D:\Audioura\results\<name>.txt`, read back with `executeBash` `type D:\Audioura\results\<name>.txt`.
- **InAppWebView**: v6 API only — `initialSettings: InAppWebViewSettings(...)`. v5 `initialOptions` is BANNED.
- **Stale container paths**: iOS reassigns UUID on reinstall. Tours healed in `_healTourPaths()`. News healed in `my_news_screen._loadNews()` + `news_player_screen._getIndexUrl()`.
- **DebugLogHelper**: defined in `lib/screens/debug_log_viewer_screen.dart`.
- **unawaited()**: requires `import 'dart:async'`.
- **Config class**: `lib/config.dart` — `Config.defaultServerIp = '192.168.0.218'`.
- **Dialog auto-dismiss**: `_startVoiceSearch()` dialog does NOT auto-close on timeout — `onStatus` never wired. Cancel works. This is by design until A#79.

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
```

---

### 📂 **KEY FILES**
| File | Purpose |
|------|---------| 
| `lib/screens/home_screen.dart` | Download + translation logic. LF. |
| `lib/screens/my_tours_screen.dart` | Tours/news list. LF. A#77b: `_manualRefresh()` fixed. A#78: mic permission + import fixed. |
| `lib/screens/my_news_screen.dart` | News list. Heals stale paths in `_loadNews()`. |
| `lib/screens/main_screen.dart` | Tab navigation. CRLF. `_buildBody()` switch. |
| `lib/screens/tour_player_screen.dart` | `openMap` JS handler. CRLF. |
| `lib/screens/news_player_screen.dart` | `_getIndexUrl()` path healing + FutureBuilder. CRLF. |
| `lib/screens/tour_map_screen.dart` | Map screen. Jitter + single-POI guard. CRLF. |
| `lib/screens/tour_generator_screen.dart` | Translation + player navigation. LF. |
| `lib/screens/debug_log_viewer_screen.dart` | `DebugLogHelper` class lives here. |
| `lib/config.dart` | `Config.defaultServerIp = '192.168.0.218'` |
| `usb/Audioura/assignments/mac_mini_assignments.md` | Mac Mini task queue. Copy to `D:\Audioura\assignments\` before Mac Mini run. |
| `git_source_control_for_q.md` | Git rules — READ before any git operation. |
| `android_assignment_a78_2026_06_02.md` | Android Q parity build instructions for v1.2.9+71. |
| `android_q_onboarding.md` | Android Q full onboarding — give to Android Q first time. |
| `ISSUE_SERVICES_NEWSLETTER_ARTICLES_INCOMPLETE.md` | Services bug filed for Kiro. |
| `ISSUE-061_TRANSLATED_TOURS_IN_DOWNLOAD_LIST.md` | Services bug: translated tour 404. |

---

### 🤖 **ANDROID PARITY**
- Android bundle ID: `com.audioura.app` (iOS is `com.glikfamily.audioura`)
- `android/app/build.gradle.kts` — minSdk 24, compileSdk 35, debug keystore committed
- Onboarding doc: `android_q_onboarding.md` — give to Android Q on first session
- Per-build assignment: `android_assignment_a78_2026_06_02.md` — give to Android Q for v1.2.9+71
- **Key risk**: stale path healing uses `/Documents/` marker (iOS-specific). Android Q must verify with reinstall test.
- **Version sync**: iOS Q bumps `pubspec.yaml` → Android Q pulls + builds. Android Q never bumps independently.

---

**Last Updated**: 2026-06-02 — v105.0. v1.2.9+71 built by Mac Mini (A#78 mic fix). Smoke test in progress. A#79 dialog-hang hardening defined. Android parity assignment written. Dialog auto-dismiss confirmed never implemented (not a regression) — deferred to A#79.
**iOS Amazon-Q Version**: 105.0
