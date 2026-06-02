# iOS AudioTours AI Context Reminder
## 🍎 iOS Amazon-Q Recovery Guide — POST-COMPACTION ENTRY POINT

### 🪪 **IDENTITY — ALWAYS START WITH THIS**
Every response in a new session must begin with:
**🍎 iOS AMAZON-Q**
This is required so the user can identify which Amazon-Q tab they are talking to.

---

### ✅ **CURRENT STATE — v1.2.9+70 ON iPHONE, A#78 READY TO BUILD**

- iPhone running **v1.2.9+70** (A#77b complete — Listen page Refresh black screen fixed) ✅
- **A#78 fix already in git on `services-migration`** — Listen page microphone voice search fix in `my_tours_screen.dart` (commit `df6b61b`). Targets v1.2.9+71. Needs Mac Mini build.

---

### 🎯 **IMMEDIATE NEXT STEPS**

#### A#78 — Build v1.2.9+71 ⚠️ READY TO BUILD
**Bug:** On the Listen page (Audio mode), tapping the microphone icon showed "Microphone permission required" snackbar and did nothing. Voice search inside individual news articles worked fine.

**Root cause:** `_setupVoiceCommands()` calls `_speechToText.initialize()` which acquires mic permission internally via iOS speech framework. Then `_startVoiceSearch()` called `Permission.microphone.request()` again via the `permission_handler` plugin — a separate permission pathway. iOS considers the permission already handled; `permission_handler` sees it as denied → snackbar → return.

**Fix (commit `df6b61b`):** Removed the redundant `Permission.microphone.request()` block from `_startVoiceSearch()` in `my_tours_screen.dart`. `_speechEnabled == true` (set by `initialize()`) is sufficient proof mic is available.

**Mac Mini runs:**
```bash
cd ~/Development/Audioura-build
git pull origin services-migration
sed -i '' 's/^version: 1.2.9+70/version: 1.2.9+71/' development/audio_tour_app/pubspec.yaml
cd development/audio_tour_app && flutter clean && flutter pub get
cd "/Volumes/USB DISK/Audioura/scripts" && ./build_install_launch.sh
# STOP for Sir Michael smoke test
# After smoke test passes: git add pubspec.yaml && git commit -m "v1.2.9+71" && git push origin services-migration
```

**Smoke tests:**
1. Audio mode → Listen tab → tap microphone icon → Listening dialog appears immediately, no "Microphone permission required" snackbar.
2. Say a word → dialog closes → article list filters. Debug log shows `LISTEN: Voice search ...`.
3. Listen page Refresh → list reloads, no black screen (A#77b regression check).
4. Tour audio plays, news article loads, POI map icon opens TourMapScreen.

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
- **pubspec.yaml**: `1.2.9+70` on Mac Mini and dev tree (synced after A#77b). Next build bumps to +71.

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
- **iPhone**: v1.2.9+70 ✅
- **All shipped features**: Tour clustering, location search, tour search, newsletter system, subscription, language selector, about screen, settings persistence, location permissions, keyboard dismissal, download spinner fix, microphone voice control, translation (ru/fr/zh), walking tour map, per-stop map focus, coordinate jitter, museum single-POI map guard, mode-switch fix, stale tour/news path healing, brick-red app icon, app name "Audioura", InAppWebView v6, map icon on Listen page, POI tap → TourMapScreen via `openMap` JS handler, Listen page Refresh in-place reload.

---

### 🔄 **WORKFLOW RULES**
1. Assignments: Windows Q writes directives to `usb/Audioura/assignments/mac_mini_assignments.md` → copies to USB → commits + pushes → Mac Mini Q pulls + executes.
2. Code fixes on Windows: edit in `development/audio_tour_app/lib/` → commit → push → Mac Mini pulls + builds.
3. After successful build: Mac Mini commits pubspec bump + pushes. Windows does `git pull` to sync.
4. **LF FILES**: `home_screen.dart`, `tour_generator_screen.dart`, `my_tours_screen.dart` — `fsReplace` FAILS on Windows. Use Python patch script via `fsWrite` + `executeBash`.
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
- `_setupVoiceCommands()` — calls `_speechToText.initialize()` in `initState`. This is the only mic permission acquisition needed.
- `_startVoiceSearch()` — **A#78**: `Permission.microphone.request()` block removed. Guards only on `!_speechEnabled`.
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
1. **A#78** ⚠️ READY TO BUILD — v1.2.9+71. Listen page mic voice search fix in `my_tours_screen.dart` committed at `df6b61b`. Mac Mini: `git pull` + bump pubspec to +71 + build.
2. **ISSUE-SERVICES-NEWSLETTER** — `get_articles_by_newsletter_id` returns only 2 of 5 articles for newsletter 280. Filed in `ISSUE_SERVICES_NEWSLETTER_ARTICLES_INCOMPLETE.md`. Awaiting Kiro. NOT an iOS bug.
3. **ISSUE-061** — Translated tours in `/tours-near/` → 404. Filed for Services. iOS work follows after server fix.
4. **NF4 (LOW)** — `openMap` handler bare-int widening. Two-line fix.
5. **NF5 (LOW)** — `Colors.blue.withOpacity(0.6)` → `.withValues(alpha: 0.6)`.
6. **OSM tiles** — swap to Stadia Maps or Mapbox before App Store.
7. **Dead files** — delete `audio_handler.dart`, `map_page.dart`, `subscription_management_screen.dart` so `flutter analyze` is a clean signal.

---

### 🔄 **RECENT ASSIGNMENT HISTORY**
- **A#76**: ✅ v1.2.9+68 — POI map button fix + map icon restore. Commit `f2bb356`. 2026-06-01.
- **A#77**: ⚠️ v1.2.9+69 BUILT BUT FAILED — fixed wrong Refresh button (`home_screen.dart`). Black screen persisted.
- **A#77b**: ✅ v1.2.9+70 CONFIRMED ON iPHONE — `_manualRefresh()` replaced with in-place `_loadAppMode()` reload. Commit `4948178`. 2026-06-02.
- **A#78**: ⚠️ READY TO BUILD — v1.2.9+71. Removed redundant `Permission.microphone.request()` from `_startVoiceSearch()`. Commit `df6b61b`. 2026-06-02.

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
| `lib/screens/my_tours_screen.dart` | Tours/news list. LF. A#77b: `_manualRefresh()` fixed. A#78: mic permission fixed. |
| `lib/screens/my_news_screen.dart` | News list. Heals stale paths in `_loadNews()`. |
| `lib/screens/main_screen.dart` | Tab navigation. CRLF. `_buildBody()` switch. |
| `lib/screens/tour_player_screen.dart` | `openMap` JS handler. CRLF. |
| `lib/screens/news_player_screen.dart` | `_getIndexUrl()` path healing + FutureBuilder. CRLF. |
| `lib/screens/tour_map_screen.dart` | Map screen. Jitter + single-POI guard. CRLF. |
| `lib/screens/tour_generator_screen.dart` | Translation + player navigation. LF. |
| `lib/screens/debug_log_viewer_screen.dart` | `DebugLogHelper` class lives here. |
| `lib/config.dart` | `Config.defaultServerIp = '192.168.0.218'` |
| `usb/Audioura/assignments/mac_mini_assignments.md` | Mac Mini task queue. A#78 block at top. Copy to `D:\Audioura\assignments\` before Mac Mini run. |
| `git_source_control_for_q.md` | Git rules — READ before any git operation. |
| `ISSUE_SERVICES_NEWSLETTER_ARTICLES_INCOMPLETE.md` | Services bug filed for Kiro. |
| `ISSUE-061_TRANSLATED_TOURS_IN_DOWNLOAD_LIST.md` | Services bug: translated tour 404. |
| `android_q_onboarding.md` | Give to Android Q for parity builds. |

---

### 🤖 **ANDROID PARITY**
- Android bundle ID: `com.audioura.app` (iOS is `com.glikfamily.audioura`)
- `android/app/build.gradle.kts` — minSdk 24, compileSdk 35, debug keystore committed
- Onboarding doc: `android_q_onboarding.md` — give to Android Q
- **Key risk**: stale path healing uses `/Documents/` marker (iOS-specific). Android Q must verify with reinstall test.
- **Version sync**: iOS Q bumps `pubspec.yaml` → Android Q pulls + builds. Android Q never bumps independently.

---

**Last Updated**: 2026-06-02 — v104.0. iPhone on v1.2.9+70 (A#77b complete). A#78 ready to build as v1.2.9+71 — removed redundant `Permission.microphone.request()` from `_startVoiceSearch()` in `my_tours_screen.dart` (commit `df6b61b`). pubspec at `1.2.9+70`.
**iOS Amazon-Q Version**: 104.0
