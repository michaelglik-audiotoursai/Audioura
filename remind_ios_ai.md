# iOS AudioTours AI Context Reminder
## 🍎 iOS Amazon-Q Recovery Guide — POST-COMPACTION ENTRY POINT

### 🪪 **IDENTITY — ALWAYS START WITH THIS**
Every response in a new session must begin with:
**🍎 iOS AMAZON-Q**
This is required so the user can identify which Amazon-Q tab they are talking to.

---

### ✅ **CURRENT STATE — v1.2.9+65 ON iPHONE, A#76 STAGED (v1.2.9+68), A#77 FIX READY**

- iPhone running **v1.2.9+65** (A#75 complete — InAppWebView v6 migration) ✅
- A#76 staged — targets v1.2.9+68. Covers three versions (+66, +67, +68). Critical fix: `openMap` JS handler was never registered in `TourPlayerScreen` — POI map buttons silently did nothing.
- All three commits already in git on `services-migration`. Mac Mini needs: `git pull` + build only.
- **A#77 fix coded (Windows, not yet committed)** — newsletter Refresh black screen fixed in `home_screen.dart`. Targets v1.2.9+69. Waiting for A#76 build to complete first.

---

### 🎯 **IMMEDIATE NEXT STEPS**

#### A#76 — Build v1.2.9+68 ⚠️ READY TO BUILD
**What changed (+66 → +67 → +68):**
- +66: `my_tours_screen.dart` — map icon (`Icons.map`) restored on Listen page per-tour
- +67: `tour_map_screen.dart` — `HitTestBehavior.opaque` on marker GestureDetector (wrong diagnosis, kept as hardening)
- +68: `tour_player_screen.dart` — `addJavaScriptHandler('openMap')` registered in `onWebViewCreated` — **the real fix**

**Root cause:** `flutter_inappwebview` silently drops `callHandler('openMap')` if no handler is registered. `TourPlayerScreen` never registered it. Server HTML was always correct.

**Key test:** After build, tap a POI map icon in tour player → debug log must show `MAP: openMap handler fired for stop N`.

**Mac Mini runs:**
```bash
cd ~/Development/Audioura-build
git pull origin services-migration
# Spot-checks: pubspec at +68, openMap in tour_player_screen.dart, Icons.map in my_tours_screen.dart
# Verify Xcode signing
cd development/audio_tour_app
flutter clean && flutter pub get
cd "/Volumes/USB DISK/Audioura/scripts"
./build_install_launch.sh
# STOP for Sir Michael smoke test
# After smoke test passes: git push origin services-migration (commits already in git)
```

---

### 🗂️ **USB MIRROR IN GIT (NEW)**

The USB drive contents (`D:\Audioura\`) are now mirrored into git at:
`C:\Users\micha\eclipse-workspace\AudioTours\development\usb\Audioura\`

What's tracked:
- `usb/Audioura/assignments/` — `mac_mini_assignments.md` + individual assignment docs
- `usb/Audioura/assets/` — all Dart screens, services, widgets, pubspec, Podfile, Info.plist
- `usb/Audioura/scripts/` — all build and diagnostic shell scripts
- `usb/Audioura/archive/` — old assignment walkthroughs
- `usb/Audioura/claude_analysis/` — analysis docs
- `usb/Audioura/.gitignore` — excludes `results/`, `verify/`, macOS dot-files

`results/` is NOT tracked (hundreds of build logs — too large).

**Workflow:** Edit files in `usb/Audioura/` → `git commit` + `git push` → copy to USB when needed:
```cmd
copy C:\Users\micha\eclipse-workspace\AudioTours\development\usb\Audioura\assignments\mac_mini_assignments.md D:\Audioura\assignments\
```

---

### 🔑 **GIT / BUILD STATE**

#### Three locations — two are git repos
```
GitHub (remote)
  repo: michaelglik-audiotoursai/Audioura  branch: services-migration
       ↑ push                    ↓ pull
       |                         |
Mac Mini clone            Windows dev tree
~/Development/            C:\Users\micha\eclipse-workspace\
Audioura-build/           AudioTours\development\
(builds + commits)        (reference/review — git pull after Mac Mini push)
       ↑
  copy_ios_fixes.sh copies files here (legacy workflow — see note below)
       |
USB Staging Area  ← Q writes fixes here
D:\Audioura\assets\
(NOT a git repo)
```

**⚠️ WORKFLOW CHANGE (A#72+)**: New assignments no longer use `copy_ios_fixes.sh`. Instead:
- Sir Michael commits directives doc to Windows dev tree → pushes to GitHub
- Mac Mini Q does `git pull` → reads directives → edits files directly in `~/Development/Audioura-build/development/` → commits + pushes
- `copy_ios_fixes.sh` is legacy (used in A#71 and earlier)

- **Mac Mini build clone**: `~/Development/Audioura-build/`, branch `services-migration` ✅
- **Flutter project path**: `~/Development/Audioura-build/development/audio_tour_app/`
- **Windows dev tree**: `C:\Users\micha\eclipse-workspace\AudioTours\development\` — IS a git clone, branch `services-migration`
- **USB assets** (`D:\Audioura\assets\`): NOT a git repo — legacy staging area only
- **OLD repo**: `~/Development/AudioTours/` — BROKEN, do NOT use
- **Remote**: `https://github.com/michaelglik-audiotoursai/Audioura.git`
- **Last confirmed commit**: A#73 brick-red icon (v1.2.9+64)
- **NEVER** push from `~/Development/AudioTours/`

#### Git operation ownership
| Operation | Who | Where | When |
|---|---|---|---|
| `git pull origin services-migration` | Mac Mini (Q) | `~/Development/Audioura-build/` | Start of every assignment |
| `git add / commit / push` | Mac Mini (Q) | `~/Development/Audioura-build/` | After successful build + test |
| `git pull origin services-migration` | Sir Michael (Windows) | `C:\Users\micha\eclipse-workspace\AudioTours\development\` | After Mac Mini pushes |
| Any git operation | USB `D:\Audioura\assets\` | — | **NEVER** — not a git repo |

---

### 🚀 **QUICK CONTEXT RECOVERY**
- **Mission**: iOS Amazon-Q for Audioura LLC mobile app
- **App name**: Audioura (com.glikfamily.audioura)
- **Device**: iPhone 16, UDID `F9D6F807-D301-59EE-B574-5747D617D82C`, iOS 18.3.1
- **Apple Dev**: Team ID `4HGRU6TKGQ`, paid license (Order W1583339145, glikfamily@gmail.com), valid until April 7 2027
- **Certificate**: Apple Development: Mikhail Glik (594584F3D3BC571D94A822A2158871CA13898701)
- **Flutter UDID** (provisioning): `00008140-000558A902BA801C`
- **Repo**: `https://github.com/michaelglik-audiotoursai/Audioura`
- **Network**: iPhone → Windows laptop Docker services at `192.168.0.218:5002/5004/5005/5030`
- **Build environment**: Mac Mini M4 + Xcode 16, project at `~/Development/Audioura-build/development/audio_tour_app`

---

### 📱 **APP STATUS**
- **Current version on iPhone**: v1.2.9+65 ✅ (A#75 — InAppWebView v6 migration)
- **pubspec.yaml in dev tree**: `1.2.9+65` ✅
- **All features in +65**: Tour clustering, location search, tour search, newsletter system, subscription, language selector, about screen, settings persistence, location permissions, keyboard dismissal, download spinner fix, microphone voice control, translation (ru/fr/zh), walking tour map, per-stop map focus, coordinate jitter, museum single-POI map guard, mode-switch fix, stale tour path healing, stale news article path healing, brick-red app icon, app name "Audioura", InAppWebView v6 in all WebView screens
- **New in +66/+67/+68 (staged):** Map icon restored on Listen page (+66). `HitTestBehavior.opaque` on map markers (+67, hardening). `openMap` JS handler registered in `TourPlayerScreen` (+68, real POI tap fix).

---

### 🔄 **WORKFLOW RULES (current)**
1. **New workflow (A#72+)**: Sir Michael commits directives to Windows dev tree → pushes → Mac Mini Q pulls → edits directly in clone → commits + pushes. No USB copy script.
2. **Legacy workflow (A#71 and earlier)**: `copy_ios_fixes.sh` copied 23 files from USB assets to Mac Mini. Still works but no longer the primary workflow.
3. `build_install_launch.sh` — proven stable. Points at `~/Development/Audioura-build/development/audio_tour_app`.
4. Every new assignment = directives doc committed to Windows dev tree + pushed before Mac Mini starts.
5. After successful build → `git add` changed files → `git commit` → `git push origin services-migration`.
6. **LF FILES**: `home_screen.dart`, `tour_generator_screen.dart`, `my_tours_screen.dart` — `fsReplace` FAILS on Windows. Use Python script via `fsWrite` + `executeBash`.
7. **PYTHON OUTPUT**: Not visible in stdout. Write result to file, read with `fsRead`.
8. **Windows dev tree IS a git repo** — `git pull` works at `C:\Users\micha\eclipse-workspace\AudioTours\development\`. Q never commits from there — Mac Mini only.
9. **Read `git_source_control_for_q.md` before any git work** — `C:\Users\micha\eclipse-workspace\AudioTours\development\git_source_control_for_q.md`

---

### 🏗️ **BUILD PROCESS**
- Build from: `~/Development/Audioura-build/`, branch `services-migration`
- Flutter project: `~/Development/Audioura-build/development/audio_tour_app/`
- Old `~/Development/AudioTours/` repo is BROKEN — never use it
- Standard build cycle:
  ```bash
  cd ~/Development/Audioura-build
  git pull origin services-migration
  cd development/audio_tour_app
  flutter clean
  flutter pub get
  cd "/Volumes/USB DISK/Audioura/scripts"
  ./build_install_launch.sh
  ```
- `flutter analyze` reports issues in dead files only (`audio_handler.dart`, `map_page.dart`, `subscription_management_screen.dart`, `test/widget_test.dart`). Real errors are only those OUTSIDE these four files.
- If `git push` blocked by GitHub secret scanning — STOP and report. Never click "Allow secret".

---

### 🗺️ **MAP FEATURE ARCHITECTURE**

#### tour_map_screen.dart (CRLF — fsReplace works)
- Full-screen `flutter_map` with OSM tiles
- `TourPoi` class: `index`, `name`, `type`, `address`, `coords`
- `focusStopIndex` (int?) — 1-based, matches audio_N.txt numbering
- `_focusPoi()` — exact index match; fallback nearest by GPS
- `_fitBounds({bool forceFitAll = false})` — NF6: `if (forceFitAll) _fittedWithLocation = true`
- **A#60**: `if (points.length == 1) { _mapController.move(points.first, 15); return; }` — single-POI guard
- Marker color: `poi.index == next?.index` (NF7)
- **NF3**: AppBar title shows `"Tour — Stop N"` only when `_pois.any((p) => p.index == widget.focusStopIndex)`
- **A#59 NF8**: `_applyCoordJitter(pois)` — offsets duplicate-coord POIs ~0.00008°
- Coordinates regex: `RegExp(r'Coordinates:\s*([-\d.]+)\s*,\s*([-\d.]+)')` (space-tolerant)

#### tour_player_screen.dart (CRLF)
- All injection code removed. Kept: `addJavaScriptHandler('openMap')` + `_openMapForStop()`
- `openMap` handler: registered in `onWebViewCreated` — `args[0]['stop']` parsed as int, fallback `int.tryParse`. Logs `MAP: openMap handler fired for stop N`. Pushes `TourMapScreen(focusStopIndex: stopIndex)`.
- Uses `initialSettings: InAppWebViewSettings(...)` — v6 API ✅
- **A#76 +68**: `import 'tour_map_screen.dart'` added. `addJavaScriptHandler('openMap')` registered — was missing before, causing silent drop of all POI tap events.

#### news_player_screen.dart (CRLF — A#72 + A#75)
- **A#72**: `_getIndexUrl()` heals stale container paths. `FutureBuilder<String>` wraps WebView body. `late final Future<String> _indexUrlFuture` cached in `initState`.
- **A#75**: `initialSettings: InAppWebViewSettings(...)` — v6 API ✅ (complete, v1.2.9+65)
- `onReceivedError` — v6 callback ✅

#### my_tours_screen.dart (LF — Python edits only)
- **A#56**: `_healTourPaths()` present, `_tourHasMap` declared, `_detectMapTours()` called

#### my_news_screen.dart (A#72)
- `_loadNews()` heals stale container paths for news articles
- Mirrors A#56 pattern: extracts `/news/<folder>` suffix, prepends current `getApplicationDocumentsDirectory()`

#### main_screen.dart (CRLF — in copy script)
- **A#62**: `_buildBody()` switch replaces `IndexedStack` — fixes Tours↔Audio mode switching
- `_listenTabVersion` + `MyToursScreen(key: ValueKey(_listenTabVersion))` — Listen reload preserved
- **DO NOT wrap `_buildBody()` in IndexedStack** — that was the regression

---

### 🌍 **TRANSLATION FEATURE ARCHITECTURE**

#### API Contract
```
POST http://192.168.0.218:5030/translate-with-audio
Body: { "content_id": <int>, "content_type": "tour", "languages": ["ru", "fr"] }
Response: { "status": "completed", "translations": { "ru": { "id": 170 }, "fr": { "id": 171 } } }
GET http://192.168.0.218:5005/download-tour/<translated_id>  → ZIP file
```

#### Key Functions in home_screen.dart
- `_downloadTranslatedVersions(tourId, languages, serverIp, parentEditTourId)` — M8 shared method
- `_resolveParentEditTourId(downloadTourId, prefs)` — port 5025, only for original English tours
- `_saveTourToMyToursTranslated(...)` — saves translated tour directly, no resolution call
- `_extractTranslatedIds(result)` — handles both server response shapes
- `_countTourStops(zipBytes)` — defaults to 10 with log

---

### 📋 **OPEN ITEMS**
1. **A#76** ⚠️ STAGED — Build v1.2.9+68. Three versions bundled: +66 (map icon on Listen page), +67 (`HitTestBehavior.opaque` hardening), +68 (`openMap` JS handler registered in `TourPlayerScreen` — real POI tap fix). All commits in git. Mac Mini: `git pull` + build only. Key test: `MAP: openMap handler fired for stop N` in debug log.
2. **A#77** ⚠️ FIX CODED — Newsletter Refresh black screen fix in `home_screen.dart` (Windows dev tree only, not yet committed to git). Targets v1.2.9+69. Requires Mac Mini directives doc before build.
3. **ISSUE-SERVICES-NEWSLETTER** — `get_articles_by_newsletter_id` returns only 2 of 5 articles for newsletter 280. Filed in `ISSUE_SERVICES_NEWSLETTER_ARTICLES_INCOMPLETE.md`. Awaiting Kiro fix. NOT an iOS bug — log confirms phone never received more than 2 IDs.
4. **ISSUE-061** — Translated tours in `/tours-near/` → 404 on direct download. Filed for Services. Future iOS assignment follows after server fix.
5. **NF4 (LOW)** — `openMap` handler bare-int widening. Two-line fix.
6. **NF5 (LOW)** — `Colors.blue.withOpacity(0.6)` → `.withValues(alpha: 0.6)`.
7. **Coordinates keyword** — Must stay English in all translated `audio_N.txt`.
8. **OSM tiles** — swap to Stadia Maps or Mapbox before App Store.
9. **ISSUE-060** — Museum tours directions reference streets. Deferred.
10. **Dead files backlog** — delete `audio_handler.dart`, `map_page.dart`, `subscription_management_screen.dart` so `flutter analyze` becomes a clean signal.

---

### 🔄 **ASSIGNMENT HISTORY**
- **A#27–A#35**: ✅ iOS build barrier + mic permission (v1.2.9+22→+30)
- **A#36–A#44**: ✅ Translation feature built end-to-end (v1.2.9+31→+39)
- **A#45–A#46**: ✅ Build fixes, edit_tour_screen inlined (v1.2.9+40→+41)
- **A#47**: ✅ v1.2.9+43 — real translation in tour generator
- **A#48**: ✅ v1.2.9+45 — save-then-remove pattern
- **A#49**: ✅ v1.2.9+47 — suppress English auto-play, navigate to translated player
- **A#49c**: ✅ v1.2.9+49 — spinner + flicker gate
- **A#50**: ✅ v1.2.9+50 — walking tour map on Listen page
- **A#52**: ✅ v1.2.9+52 — per-stop map focus (focusStopIndex)
- **A#55**: ✅ v1.2.9+55 — per-stop map icons via JS handler
- **A#58**: ✅ v1.2.9+58 — A#56 + A#57 + NF3
- **A#59**: ✅ v1.2.9+59/+60 — NF8 jitter + IndexedStack Listen reload
- **A#60**: ✅ v1.2.9+60 — single-POI `_fitBounds` guard
- **A#61–A#62**: [CANCELLED] — old repo was broken. Superseded by A#63+.
- **A#63**: ✅ Fresh clone `~/Development/Audioura-build/`, branch `services-migration`
- **A#64**: ✅ iOS signing fixed (bundle ID `com.glikfamily.audioura`, team `4HGRU6TKGQ`)
- **A#65**: ✅ `dart:async` import fix in `my_tours_screen.dart`
- **A#66**: ✅ flutter analyze errors confirmed non-blocking (dead files only)
- **A#67**: ✅ `assets/icons/` removed from pubspec, `.env` committed
- **A#68**: ✅ `NativeAudioRecorderPlugin.swift` wired into Xcode target
- **A#69**: ✅ Reset to complete build config (commit `74a8c04`), first successful build
- **A#70**: ✅ v1.2.9+61 CONFIRMED ON iPHONE — stale path healing + real Audioura icon. 2026-05-24.
- **A#71**: ✅ v1.2.9+62 — app name "Audioura" fixed (Info.plist). White screen NOT fixed (wrong diagnosis — real cause was stale paths, not v5 API). Commit `11113c5`.
- **A#72**: ✅ v1.2.9+63 — news article white screen FIXED. `my_news_screen._loadNews()` heals stale paths. `news_player_screen._getIndexUrl()` heals defensively at WebView launch. FutureBuilder wraps WebView. 2026-05-26.
- **A#73**: ✅ v1.2.9+64 — brick-red (#A93105) app icon. 15 PNGs regenerated via Python script. 2026-05-26.
- **A#74**: ✅ Windows-side git cleanup (Sir Michael only — not a Mac Mini assignment).
- **A#75**: ✅ v1.2.9+65 — InAppWebView v6 migration in `news_player_screen.dart`. No functional change. Built, smoke tested, committed + pushed. 2026-06-01.
- **A#76**: ⚠️ STAGED — v1.2.9+68. Three versions: +66 map icon restore, +67 `HitTestBehavior.opaque` hardening, +68 `openMap` JS handler registered in `TourPlayerScreen` (real POI tap fix). Commits `0d4d46a` (+67) and `7d012d5` (+68) in git on `services-migration`. Build pending.
- **A#77**: ⚠️ FIX CODED — v1.2.9+69. Newsletter Refresh black screen. Root cause: `setState(_isLoading=true)` in refresh handler triggered wrong "Tours" spinner scaffold in Audio mode. Fix: removed that setState call from `_buildNewsletterView` refresh button. `home_screen.dart` patched on Windows dev tree via `patch_newsletter_refresh_fix.py`. NOT yet committed — needs Mac Mini directives doc + build.

---

### ⚠️ **CRITICAL TECHNICAL NOTES**
- **LF files**: `home_screen.dart`, `tour_generator_screen.dart`, `my_tours_screen.dart` — `fsReplace` FAILS. Use Python script via `fsWrite` + `executeBash`.
- **CRLF files**: `tour_map_screen.dart`, `tour_player_screen.dart`, `main_screen.dart`, `news_player_screen.dart` — `fsReplace` works
- **DebugLogHelper**: defined in `lib/screens/debug_log_viewer_screen.dart`
- **unawaited()**: requires `import 'dart:async'`
- **Config class**: `lib/config.dart` — `Config.defaultServerIp = '192.168.0.218'`
- **InAppWebView API**: v6 uses `initialSettings: InAppWebViewSettings(...)`. v5 `initialOptions`/`InAppWebViewGroupOptions` is BANNED.
- **Stale container paths**: iOS reassigns app container UUID on reinstall. Tours healed in `my_tours_screen._healTourPaths()`. News articles healed in `my_news_screen._loadNews()` + `news_player_screen._getIndexUrl()`.
- **pubspec.yaml version**: `1.2.9+65` in dev tree and on iPhone.
- **Flutter project path on Mac Mini**: `~/Development/Audioura-build/development/audio_tour_app/` (has `development/` subdirectory — different from earlier assignments).

---

### 🔧 **TROUBLESHOOTING**
```bash
# iPhone not detected:
sudo launchctl kickstart -k system/com.apple.usbd
# Flutter checks
flutter doctor -v && flutter devices
# Verify pubspec version on Mac Mini:
grep "^version:" ~/Development/Audioura-build/development/audio_tour_app/pubspec.yaml
# Uninstall app completely:
xcrun devicectl device uninstall app --device F9D6F807-D301-59EE-B574-5747D617D82C com.glikfamily.audioura
# Clean build:
cd ~/Development/Audioura-build/development/audio_tour_app && flutter clean && flutter pub get && flutter build ios --release
```

---

### 📂 **KEY FILES**
| File | Purpose |
|------|---------|
| `lib/screens/home_screen.dart` | Download + translation logic. LF. |
| `lib/screens/my_tours_screen.dart` | Tour list. LF. A#56: `_healTourPaths()`. |
| `lib/screens/my_news_screen.dart` | News list. A#72: heals stale article paths in `_loadNews()`. |
| `lib/screens/main_screen.dart` | Tab navigation. CRLF. A#62: `_buildBody()`. |
| `lib/screens/tour_player_screen.dart` | A#57: injection removed, `openMap` handler kept. CRLF. |
| `lib/screens/news_player_screen.dart` | A#72: `_getIndexUrl()` + FutureBuilder. A#75: v6 API. CRLF. |
| `lib/screens/tour_map_screen.dart` | Map screen. A#59: NF8 jitter. A#60: single-POI guard. CRLF. |
| `lib/screens/tour_generator_screen.dart` | Translation + player navigation. LF. |
| `lib/screens/debug_log_viewer_screen.dart` | Contains `DebugLogHelper` class |
| `lib/config.dart` | `Config.defaultServerIp = '192.168.0.218'` |
| `D:\Audioura\assignments\mac_mini_assignments.md` | A#76 block at top. Git mirror: `usb/Audioura/assignments/mac_mini_assignments.md` |
| `C:\Users\micha\eclipse-workspace\AudioTours\development\usb\Audioura\` | Git mirror of full USB contents (assignments, assets, scripts, archive) |
| `D:\Audioura\scripts\build_install_launch.sh` | Proven stable build script |
| `C:\Users\micha\eclipse-workspace\AudioTours\development\build_process_for_ios_q.md` | Build process rules |
| `C:\Users\micha\eclipse-workspace\AudioTours\development\git_source_control_for_q.md` | Git structure — READ BEFORE ANY GIT WORK |
| `C:\Users\micha\eclipse-workspace\AudioTours\development\a75_directives_for_q.md` | A#75 directives for Mac Mini Q |
| `C:\Users\micha\eclipse-workspace\AudioTours\development\ISSUE-061_TRANSLATED_TOURS_IN_DOWNLOAD_LIST.md` | Server fix request for translated tour 404 |
| `C:\Users\micha\eclipse-workspace\AudioTours\development\ISSUE_SERVICES_NEWSLETTER_ARTICLES_INCOMPLETE.md` | Services bug: `get_articles_by_newsletter_id` returns only 2 of 5 articles — filed for Kiro |
| `C:\Users\micha\eclipse-workspace\AudioTours\development\patch_newsletter_refresh_fix.py` | A#77 patch — removes `_isLoading=true` from newsletter refresh handler |

---

**Last Updated**: 2026-06-02 — v98.0. iPhone on v1.2.9+65. A#76 staged (v1.2.9+68, all commits in git). A#77 fix coded in Windows dev tree (home_screen.dart newsletter refresh black screen — removed setState(_isLoading=true) from refresh handler, targets v1.2.9+69). Newsletter issue investigation: 2/5 articles is a SERVICES bug (get_articles_by_newsletter_id returned only 2 IDs — phone never attempted more); filed ISSUE_SERVICES_NEWSLETTER_ARTICLES_INCOMPLETE.md for Kiro. Black screen on Refresh is iOS bug — fixed. Issue C (wrong article content) undecided — services extractor fingerprint matches, Kiro must check server egress log.
**iOS Amazon-Q Version**: 98.0
