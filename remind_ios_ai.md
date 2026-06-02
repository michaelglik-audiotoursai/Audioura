# iOS AudioTours AI Context Reminder
## 🍎 iOS Amazon-Q Recovery Guide — POST-COMPACTION ENTRY POINT

### 🪪 **IDENTITY — ALWAYS START WITH THIS**
Every response in a new session must begin with:
**🍎 iOS AMAZON-Q**
This is required so the user can identify which Amazon-Q tab they are talking to.

---

### ✅ **CURRENT STATE — v1.2.9+68 ON iPHONE, A#77b READY TO BUILD**

- iPhone running **v1.2.9+68** (A#76 complete — POI map button fix + map icon restore) ✅
- **A#77b fix already in git on `services-migration`** — Listen page Refresh black screen fix in `my_tours_screen.dart` (commit `4948178`). Targets v1.2.9+70. Needs Mac Mini build.
- **v1.2.9+69 was built but smoke test failed** — A#77 fixed the wrong Refresh button (`home_screen.dart`). Real cause was in `my_tours_screen.dart`. See A#77b below.

---

### 🎯 **IMMEDIATE NEXT STEPS**

#### A#77b — Build v1.2.9+70 ⚠️ READY TO BUILD
**Root cause of black screen:** `_manualRefresh()` in `my_tours_screen.dart` called `Navigator.of(context).pop()` which disposed the State. The `addPostFrameCallback` `if (mounted)` then evaluated false → `pushReplacement` never ran → screen gone, nothing replaced it → black screen.

**Fix (commit `4948178`):** `_manualRefresh()` replaced with in-place reload:
```dart
Future<void> _manualRefresh() async {
  await DebugLogHelper.addDebugLog('LISTEN: Manual refresh triggered');
  if (!mounted) return;
  await _loadAppMode();
}
```
Call site: `onPressed: () => _manualRefresh()`, tooltip: `'Refresh'`

**Claude review:** ✅ Approved. `onPressed` type is valid Dart. Double-tap re-entrancy harmless. Selection-mode crash risk is pre-existing, not a blocker.

**Mac Mini runs:**
```bash
cd ~/Development/Audioura-build
git pull origin services-migration
sed -i '' 's/^version: 1.2.9+69/version: 1.2.9+70/' development/audio_tour_app/pubspec.yaml
cd development/audio_tour_app && flutter clean && flutter pub get
cd "/Volumes/USB DISK/Audioura/scripts" && ./build_install_launch.sh
# STOP for Sir Michael smoke test
# After smoke test passes: git add pubspec.yaml && git commit -m "v1.2.9+70" && git push origin services-migration
```

**Smoke tests:**
1. Audio mode → Listen tab → tap Refresh → list reloads in place, no black screen. Log must show `LISTEN: Manual refresh triggered` then `LISTEN: Loading N articles` then `LISTEN: Successfully loaded N articles`.
2. Enter Select Articles mode → select some → tap Refresh → no crash, list reloads cleanly.
3. Newsletter tab → tap Refresh → no black screen (regression check for +69 fix).
4. Open a tour → audio plays normally. Open a news article → no white screen. Tap POI map icon → TourMapScreen opens.

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
- **NEVER** push from `~/Development/AudioTours/`

#### Git operation ownership
| Operation | Who | Where |
|---|---|---|
| `git pull` + build + `git push` | Mac Mini Q | `~/Development/Audioura-build/` |
| Edit + commit directives/planning docs | Windows Q | `C:\Users\micha\eclipse-workspace\AudioTours\development\` |
| `git pull` to sync after Mac Mini pushes | Sir Michael (Windows) | Windows dev tree |

**Current pubspec.yaml**: `1.2.9+69` (bumped by A#77, not yet +70 — Mac Mini bumps to +70 during A#77b build)

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
- **iPhone**: v1.2.9+68 ✅
- **All shipped features**: Tour clustering, location search, tour search, newsletter system, subscription, language selector, about screen, settings persistence, location permissions, keyboard dismissal, download spinner fix, microphone voice control, translation (ru/fr/zh), walking tour map, per-stop map focus, coordinate jitter, museum single-POI map guard, mode-switch fix, stale tour/news path healing, brick-red app icon, app name "Audioura", InAppWebView v6, map icon on Listen page, POI tap → TourMapScreen via `openMap` JS handler.

---

### 🔄 **WORKFLOW RULES**
1. Assignments: Windows Q writes directives to `usb/Audioura/assignments/mac_mini_assignments.md` → copies to USB → commits + pushes → Mac Mini Q pulls + executes.
2. Code fixes on Windows: edit in `development/audio_tour_app/lib/` → commit → push → Mac Mini pulls + builds.
3. After successful build: Mac Mini commits pubspec bump + pushes. Windows does `git pull` to sync.
4. **LF FILES**: `home_screen.dart`, `tour_generator_screen.dart`, `my_tours_screen.dart` — `fsReplace` FAILS on Windows. Use Python patch script via `fsWrite` + `executeBash`.
5. **PYTHON OUTPUT**: stdout is unreliable — always write results to `D:\Audioura\results\<file>.txt` and read back with `executeBash` `type` command.
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

---

### 🗺️ **KEY SCREEN ARCHITECTURE**

#### my_tours_screen.dart (LF — Python edits only)
- Shows tours (Tours mode) or news articles (Audio mode) depending on `_appMode`
- `_loadAppMode()` → routes to `_loadTours()` or `_loadNews()` — called by `initState` and `_manualRefresh`
- `_healTourPaths()` — heals stale container paths in saved_tours
- `_detectMapTours()` — checks `audio_1.txt` for `Coordinates:` to show map icon
- `_manualRefresh()` — **A#77b**: `Future<void>`, logs, `if (!mounted) return`, calls `_loadAppMode()`. No navigation teardown.
- ⚠️ Known pre-existing: Refresh while in Select Articles mode may cause RangeError if list size changes. Not a blocker.

#### tour_player_screen.dart (CRLF)
- `addJavaScriptHandler('openMap')` registered in `onWebViewCreated` — **A#76**: was missing, causing silent drop of all POI taps
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
- `_downloadTranslatedVersions()`, `_resolveParentEditTourId()`, `_saveTourToMyToursTranslated()`
- Newsletter Refresh handler in `_buildNewsletterView` — **A#77 (+69)**: `setState(_isLoading=true)` removed (correct cleanup)

---

### 📋 **OPEN ITEMS**
1. **A#77b** ⚠️ READY TO BUILD — v1.2.9+70. See IMMEDIATE NEXT STEPS above.
2. **ISSUE-SERVICES-NEWSLETTER** — `get_articles_by_newsletter_id` returns only 2 of 5 articles for newsletter 280. Filed in `ISSUE_SERVICES_NEWSLETTER_ARTICLES_INCOMPLETE.md`. Awaiting Kiro. NOT an iOS bug.
3. **ISSUE-061** — Translated tours in `/tours-near/` → 404. Filed for Services. iOS work follows after server fix.
4. **NF4 (LOW)** — `openMap` handler bare-int widening. Two-line fix.
5. **NF5 (LOW)** — `Colors.blue.withOpacity(0.6)` → `.withValues(alpha: 0.6)`.
6. **OSM tiles** — swap to Stadia Maps or Mapbox before App Store.
7. **Dead files** — delete `audio_handler.dart`, `map_page.dart`, `subscription_management_screen.dart` so `flutter analyze` is a clean signal.

---

### 🔄 **RECENT ASSIGNMENT HISTORY**
- **A#75**: ✅ v1.2.9+65 — InAppWebView v6 migration in `news_player_screen.dart`. 2026-06-01.
- **A#76**: ✅ v1.2.9+68 — POI map button fix (`openMap` JS handler registered in `TourPlayerScreen`) + map icon restore on Listen page. Commit `f2bb356`. 2026-06-01.
- **A#77**: ⚠️ v1.2.9+69 BUILT BUT FAILED — removed `setState(_isLoading=true)` from newsletter Refresh in `home_screen.dart`. Correct cleanup but wrong screen — black screen persisted.
- **A#77b**: ⚠️ READY TO BUILD — v1.2.9+70. `_manualRefresh()` in `my_tours_screen.dart` replaced with in-place `_loadAppMode()` reload. Commit `4948178`. Claude approved.

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
| `lib/screens/my_tours_screen.dart` | Tours/news list. LF. A#77b: `_manualRefresh()` fixed. |
| `lib/screens/my_news_screen.dart` | News list. Heals stale paths in `_loadNews()`. |
| `lib/screens/main_screen.dart` | Tab navigation. CRLF. `_buildBody()` switch. |
| `lib/screens/tour_player_screen.dart` | `openMap` JS handler. CRLF. |
| `lib/screens/news_player_screen.dart` | `_getIndexUrl()` path healing + FutureBuilder. CRLF. |
| `lib/screens/tour_map_screen.dart` | Map screen. Jitter + single-POI guard. CRLF. |
| `lib/screens/tour_generator_screen.dart` | Translation + player navigation. LF. |
| `lib/screens/debug_log_viewer_screen.dart` | `DebugLogHelper` class lives here. |
| `lib/config.dart` | `Config.defaultServerIp = '192.168.0.218'` |
| `usb/Audioura/assignments/mac_mini_assignments.md` | Mac Mini task queue. A#77b block at top. Copy to `D:\Audioura\assignments\` before Mac Mini run. |
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

**Last Updated**: 2026-06-02 — v103.0. iPhone on v1.2.9+68. A#77b ready to build as v1.2.9+70 — `_manualRefresh()` in `my_tours_screen.dart` replaced with `_loadAppMode()` in-place reload (commit `4948178`, Claude approved). pubspec in dev tree at `1.2.9+69` (Mac Mini bumps to +70 during build).
**iOS Amazon-Q Version**: 103.0
