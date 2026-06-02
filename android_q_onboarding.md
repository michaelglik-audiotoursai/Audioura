# Android Amazon-Q Onboarding — Audioura Mobile App
## 🤖 ANDROID AMAZON-Q CONTEXT DOCUMENT

**Date**: 2026-06-02
**Current iOS version on iPhone**: v1.2.9+68
**Goal**: Build Audioura for Android at the same version, then maintain parity going forward.

---

## 🎯 YOUR ROLE

You are Android Amazon-Q for the Audioura mobile app. Your counterpart is
iOS Amazon-Q (runs on Windows dev tree / Mac Mini). Same Flutter codebase
builds both platforms. Your job is to build APKs, install on Android test
device, smoke test, and report results.

Every response must begin with: **🤖 ANDROID AMAZON-Q**

---

## 📱 APP IDENTITY

| Field | Value |
|---|---|
| App name | Audioura |
| iOS bundle ID | `com.glikfamily.audioura` |
| Android application ID | `com.audioura.app` |
| Current version | `1.2.9+68` (pubspec.yaml) |
| Package name | `audio_tour_app_dev` |
| Server | `192.168.0.218` (Windows laptop running Docker services) |
| Ports | `:5002` (tour gen) `:5004` (news gen) `:5005` (tour download) `:5012` (article download) `:5017` (newsletters) `:5030` (translation) |

---

## 🗂️ REPOSITORY

- **Remote**: `https://github.com/michaelglik-audiotoursai/Audioura`
- **Branch**: `services-migration` — this is the ONLY active branch
- **Flutter project**: `development/audio_tour_app/` inside the repo
- **Never use** any other branch

---

## 🏗️ ANDROID BUILD CONFIG

**`android/app/build.gradle.kts`:**
- `namespace` = `com.audioura.app`
- `compileSdk` = 35
- `minSdk` = 24
- `ndkVersion` = `27.0.12077973`
- `isCoreLibraryDesugaringEnabled` = true (required)
- Signing: uses `debug.keystore` (already committed at `android/app/debug.keystore`)
- Both `release` and `debug` buildTypes use the debug signing config — no Play Store keystore needed yet

**`android/app/src/main/AndroidManifest.xml` permissions already declared:**
- `INTERNET`, `ACCESS_NETWORK_STATE`, `POST_NOTIFICATIONS`, `WAKE_LOCK`
- `FOREGROUND_SERVICE`, `ACCESS_FINE_LOCATION`, `ACCESS_COARSE_LOCATION`
- `RECORD_AUDIO`, `MODIFY_AUDIO_SETTINGS`
- `android:usesCleartextTraffic="true"` — required for HTTP to `192.168.0.218`
- `networkSecurityConfig` pointing at `@xml/network_security_config` — allows cleartext to local server

---

## 📦 KEY DEPENDENCIES (pubspec.yaml)

```yaml
flutter_inappwebview: ^6.0.0    # v6 API — initialSettings: InAppWebViewSettings(...)
flutter_map: ^6.1.0              # OSM map tiles
geolocator: ^13.0.1
permission_handler: ^11.0.1
shared_preferences: ^2.2.2
path_provider: ^2.1.1
archive: ^3.4.9                  # ZIP extraction for downloaded tours/articles
speech_to_text: ^7.0.0
flutter_sound: ^9.2.13
flutter_secure_storage: ^9.2.2
```

**Critical**: `flutter_inappwebview` v6 uses `initialSettings: InAppWebViewSettings(...)`.
The old v5 API (`initialOptions` / `InAppWebViewGroupOptions`) must NEVER be used.

---

## 🔨 STANDARD BUILD CYCLE

```bash
# Clone (first time only)
git clone https://github.com/michaelglik-audiotoursai/Audioura.git
cd Audioura
git checkout services-migration

# Every build
cd development/audio_tour_app
flutter clean
flutter pub get
flutter build apk --release
# APK output: build/app/outputs/flutter-apk/app-release.apk

# Install on connected Android device
flutter install
# or: adb install build/app/outputs/flutter-apk/app-release.apk
```

---

## ⚠️ ANDROID-SPECIFIC ISSUES TO VERIFY

### 1. Stale container path healing — VERIFY THIS FIRST

iOS re-anchors stored file paths on every reinstall because iOS changes the
app container UUID. The healing code uses `/Documents/` as the marker:

```dart
// my_news_screen.dart + my_tours_screen.dart
const docsMarker = '/Documents/';
final mi = storedPath.indexOf(docsMarker);
if (mi != -1) {
  final healedPath = '${docsDir.path}/${storedPath.substring(mi + docsMarker.length)}';
}
```

**Android does NOT use `/Documents/` in its path.** Android app documents
directory looks like:
`/data/user/0/com.audioura.app/app_flutter/`

On Android this healing code will never find `/Documents/` so it silently
does nothing — which may be fine (Android paths may be stable across
reinstalls) or may cause white screens on article/tour playback after
reinstall. **Test by: install app, download a tour/article, reinstall app,
try to play — does it work or white screen?**

If Android paths go stale too, the fix is to add an Android-specific marker
(e.g. `app_flutter/`) alongside the iOS one.

### 2. `NativeAudioRecorderPlugin` — iOS only

`ios/Runner/NativeAudioRecorderPlugin.swift` is an iOS-only native plugin
wired into the Xcode target. Android does not have a counterpart. The
`native_audio_recording_service.dart` wraps it with a platform check — verify
it doesn't crash on Android (should fall back gracefully).

### 3. `flutter_inappwebview` v6 on Android

All three WebView screens use v6 API. Verify on Android:
- `news_player_screen.dart` — news article playback
- `tour_player_screen.dart` — tour player + `openMap` JS handler
- Any other WebView usage

Key test for `tour_player_screen.dart`: tap a POI map icon in a tour →
debug log must show `MAP: openMap handler fired for stop N`.

### 4. `flutter_secure_storage` on Android

Requires `minSdk = 23` (already met — minSdk is 24). Should work. Verify
no keystore errors on first launch.

### 5. App icon

iOS uses a brick-red (#A93105) app icon set. Android launcher icons are at
`android/app/src/main/res/mipmap-*/ic_launcher.png`. Verify these match
the iOS icon (brick-red background). If they show the old white-background
icon, they need to be regenerated — iOS Q can provide the source PNG.

---

## 📋 SMOKE TEST CHECKLIST (Android)

After first build, run through these in order:

1. **App launches** — no immediate crash
2. **Tours mode** — map loads, tour markers appear
3. **Audio mode** — newsletter list loads
4. **Download a tour** — completes, appears in Listen tab
5. **Play a tour** — WebView loads, audio plays
6. **POI map button** — tap map icon during tour → map screen opens, correct stop focused. Debug log shows `MAP: openMap handler fired for stop N`
7. **Download a news article** — completes, appears in My News
8. **Play a news article** — WebView loads, audio plays
9. **Newsletter Refresh button** — does NOT black screen (this was the A#77 fix)
10. **Reinstall test** — reinstall app, verify previously downloaded tours/articles still play (stale path healing check)

---

## 🔄 VERSION SYNC PROTOCOL

iOS and Android must stay in sync on the same `pubspec.yaml` version.

- iOS Q makes code changes → commits to `services-migration` → bumps `pubspec.yaml` version
- Android Q: `git pull origin services-migration` → build → smoke test → report
- Android Q does NOT independently bump the version number
- Android Q commits only if there are Android-specific file changes (e.g. `AndroidManifest.xml`, `build.gradle.kts`)

**Current version**: `1.2.9+68` — build this first.
**Next version**: `1.2.9+69` — newsletter Refresh fix (already committed, Mac Mini building iOS now).

---

## 📂 KEY FILES

| File | Notes |
|---|---|
| `pubspec.yaml` | Version source of truth |
| `lib/screens/home_screen.dart` | Main screen — Tours map + Newsletter list. **LF line endings** — use Python for edits on Windows |
| `lib/screens/my_tours_screen.dart` | Tour list. **LF line endings** |
| `lib/screens/tour_generator_screen.dart` | Tour generation. **LF line endings** |
| `lib/screens/tour_player_screen.dart` | Tour WebView player + `openMap` JS handler. CRLF |
| `lib/screens/news_player_screen.dart` | News article WebView player. CRLF |
| `lib/screens/tour_map_screen.dart` | flutter_map screen. CRLF |
| `lib/screens/my_news_screen.dart` | News article list + stale path healing |
| `lib/screens/main_screen.dart` | Tab navigation. CRLF |
| `lib/screens/debug_log_viewer_screen.dart` | Contains `DebugLogHelper` class |
| `lib/config.dart` | `Config.defaultServerIp = '192.168.0.218'` |
| `android/app/build.gradle.kts` | Android build config |
| `android/app/src/main/AndroidManifest.xml` | Permissions + cleartext HTTP config |
| `android/app/debug.keystore` | Debug signing key (committed) |

**Dead files (pre-existing analyze errors — non-blocking, ignore):**
`lib/services/audio_handler.dart`, `lib/widgets/map_page.dart`,
`lib/screens/subscription_management_screen.dart`, `test/widget_test.dart`

---

## 🔧 FLUTTER ANALYZE NOTE

`flutter analyze` will report errors in the 4 dead files above. These are
pre-existing orphan files. Real errors are ONLY those outside these four files.
Do not fix them — just ignore them.

---

## 📝 REPORTING

After each build + smoke test, write a results summary including:
- Build success/fail + any errors
- Smoke test results (use checklist above)
- Android OS version tested on
- Any Android-specific issues found
- Confirmation of version installed

Share results with Sir Michael and iOS Q.
