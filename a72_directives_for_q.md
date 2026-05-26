# A#72 Directives for Q — News Article White Screen (Stale Container Path Healing)

**Date:** 2026-05-25
**Author:** Claude IO
**Consumer:** Mac Mini Amazon-Q. Q reads this file at `~/Development/Audioura-build/development/a72_directives_for_q.md` after `git pull origin Newsletters` on the Mac Mini. **Sir Michael does not give this file to Q directly** — Q pulls it from GitHub as part of A#72 Step 3.

**Sir Michael's only action on this file:** commit it from Windows and push to GitHub. That is A#72 Step 0 in `mac_mini_assignments.md`. After the push, this file is hands-off until the next code-review cycle.

**Scope:** Two source files. Strictly mirrors the A#56 tour-path healing pattern.

---

## 0. Verification finding from A#71 (read this first)

Commit `11113c5` ("v1.2.9+62 - Fix app name (Audioura) + InAppWebViewSettings v6 migration") only modified `audio_tour_app/ios/Runner/Info.plist` and `audio_tour_app/pubspec.yaml`. **It did not modify `audio_tour_app/lib/screens/news_player_screen.dart`.** The v5 → v6 migration claimed in the commit message did not occur.

`news_player_screen.dart` line 267 still uses the v5 API:

```dart
initialOptions: InAppWebViewGroupOptions(
```

`flutter_inappwebview: ^6.0.0` is forward-compatible with the v5 API (build still succeeds, only deprecation warnings), so this is not a blocker. It is, however, evidence we cannot rely on past commit messages without re-reading the diff.

A#72 will leave the v5 → v6 migration alone unless it falls out naturally from the FutureBuilder restructuring below. If it does, the assignment commit message will be explicit about what changed.

---

## 1. Root cause (confirmed from A#71 device log)

```
NEWS: File exists: false
NEWS: ERROR - index.html does not exist at path!
WebView error: "Ignoring request to load this main resource because it is outside the sandbox"
```

Saved article entries in SharedPreferences key `saved_news` contain absolute paths that embed the iOS container UUID at the time the article was downloaded (e.g. `/var/mobile/Containers/Data/Application/32B5E81E-.../Documents/news/<article_dir>`). iOS reassigns the container UUID on every app reinstall, so those stored paths become invalid. The WebView correctly refuses to load a file outside the current sandbox, producing a white screen.

This is the **same bug as A#56**, which already fixed it for tours in `my_tours_screen.dart` (`_loadTours`) and `tour_player_screen.dart` (`_getIndexUrl`). A#72 applies the identical pattern to the news article path.

---

## 2. Fix — File 1 of 2

**File:** `audio_tour_app/lib/screens/my_news_screen.dart`

### 2.1 Add imports

At the top of the file (after the existing imports), the file currently has:

```dart
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import 'dart:io';

import 'news_player_screen.dart';
```

Change to:

```dart
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:path_provider/path_provider.dart';
import 'dart:convert';
import 'dart:io';

import 'news_player_screen.dart';
import 'debug_log_viewer_screen.dart';
```

(Adds `path_provider` for `getApplicationDocumentsDirectory()` and `debug_log_viewer_screen` for `DebugLogHelper`.)

### 2.2 Rewrite `_loadNews()`

The current `_loadNews()` (lines 25–34) is:

```dart
Future<void> _loadNews() async {
  final prefs = await SharedPreferences.getInstance();
  final news = prefs.getStringList('saved_news') ?? [];

  setState(() {
    _news = news.map((article) => jsonDecode(article) as Map<String, dynamic>).toList();
  });


}
```

Replace with (mirrors `_loadTours()` in `my_tours_screen.dart` lines 612–666):

```dart
Future<void> _loadNews() async {
  final prefs = await SharedPreferences.getInstance();
  final news = prefs.getStringList('saved_news') ?? [];

  await DebugLogHelper.addDebugLog('NEWS: Loading ${news.length} articles from storage');

  // A#72: heal stale container paths. iOS reassigns the app container UUID on
  // reinstall, so an article's stored absolute path can point at an old
  // container that is now outside the sandbox (white screen on playback).
  // Re-anchor each path to the current Documents directory on load.
  final docsDir = await getApplicationDocumentsDirectory();
  const docsMarker = '/Documents/';

  final parsed = <Map<String, dynamic>>[];
  int healed = 0;
  for (final articleJson in news) {
    try {
      final article = jsonDecode(articleJson) as Map<String, dynamic>;
      final storedPath = article['path'];
      if (storedPath is String) {
        final mi = storedPath.indexOf(docsMarker);
        if (mi != -1) {
          final healedPath =
              '${docsDir.path}/${storedPath.substring(mi + docsMarker.length)}';
          if (healedPath != storedPath) {
            article['path'] = healedPath;
            healed++;
          }
        }
      }
      parsed.add(article);
    } catch (e) {
      await DebugLogHelper.addDebugLog('NEWS: Skipping corrupt article entry: $e');
    }
  }
  if (healed > 0) {
    await DebugLogHelper.addDebugLog('NEWS: Healed $healed stale container path(s)');
  }

  await DebugLogHelper.addDebugLog('NEWS: Loaded ${parsed.length} valid articles (${news.length - parsed.length} skipped)');

  setState(() {
    _news = parsed;
  });
}
```

Note: unlike tours, the news list is *not* `.reversed.toList()` here — the existing build uses `ListView.builder(... reverse: true, ...)` on line 112, so display order is unchanged.

### 2.3 Acceptance for File 1

- Open Audio mode → My News. Old articles should still appear in the list.
- Tap any old article. The article opens to its content (verified separately under File 2).
- Debug log shows `NEWS: Loading N articles from storage` and, on a phone with stale paths, `NEWS: Healed N stale container path(s)`.

---

## 3. Fix — File 2 of 2

**File:** `audio_tour_app/lib/screens/news_player_screen.dart`

### 3.1 Add import

After the existing imports, add `path_provider`. Current imports (lines 1–8):

```dart
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:async';
import 'dart:io';
import 'dart:convert';
import '../services/voice_control_service_news.dart';
import 'debug_log_viewer_screen.dart';
```

Change to:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:path_provider/path_provider.dart';
import 'dart:async';
import 'dart:io';
import 'dart:convert';
import '../services/voice_control_service_news.dart';
import 'debug_log_viewer_screen.dart';
```

### 3.2 Add `_getIndexUrl()` method and cache the future

Mirrors `_getIndexUrl()` in `tour_player_screen.dart` lines 43–64, with one important deviation: unlike `TourPlayerScreen`, `NewsPlayerScreen` calls `setState` frequently during voice control (e.g. `_isListening = false` at lines 70–72). If `FutureBuilder` is given a fresh future on every rebuild, the WebView is liable to be torn down and reloaded mid-playback. To prevent that, the future is computed **once** in `initState` and stored in a `late final` field.

#### 3.2.a — Add the cached-future field

Inside `_NewsPlayerScreenState`, near the other instance fields (just below `String _displayTitle = '';` around line 28), add:

```dart
late final Future<String> _indexUrlFuture;
```

#### 3.2.b — Initialize it in `initState`

Current `initState` (lines 30–36):

```dart
@override
void initState() {
  super.initState();
  _displayTitle = widget.articleTitle; // Default to original title
  _initializeVoiceControl();
  _loadShortTitle();
}
```

Replace with:

```dart
@override
void initState() {
  super.initState();
  _displayTitle = widget.articleTitle; // Default to original title
  _indexUrlFuture = _getIndexUrl(); // A#72: compute once, reuse across rebuilds
  _initializeVoiceControl();
  _loadShortTitle();
}
```

#### 3.2.c — Add the `_getIndexUrl()` method

Insert inside `_NewsPlayerScreenState`, immediately after `_loadShortTitle()` (around line 53):

```dart
Future<String> _getIndexUrl() async {
  // A#72: heal stale container path. iOS reassigns the app container UUID on
  // reinstall, so the stored article path can point at an old container that
  // is now outside the sandbox (white screen). Re-anchor it to the current
  // Documents directory before building the file URL.
  String articlePath = widget.articlePath;
  const docsMarker = '/Documents/';
  final mi = articlePath.indexOf(docsMarker);
  if (mi != -1) {
    final docsDir = await getApplicationDocumentsDirectory();
    final healedPath =
        '${docsDir.path}/${articlePath.substring(mi + docsMarker.length)}';
    if (healedPath != articlePath) {
      await DebugLogHelper.addDebugLog('NEWS_PLAYER: Healed stale container path');
      articlePath = healedPath;
    }
  }
  final fileUrl = 'file://$articlePath/index.html';
  await DebugLogHelper.addDebugLog('NEWS_PLAYER: Using file URL: $fileUrl');
  return fileUrl;
}
```

### 3.3 Wrap the WebView body in a `FutureBuilder<String>`

Current body block (lines 265–296):

```dart
body: InAppWebView(
  initialUrlRequest: URLRequest(url: WebUri('file://${widget.articlePath}/index.html')),
  initialOptions: InAppWebViewGroupOptions(
    crossPlatform: InAppWebViewOptions(
      javaScriptEnabled: true,
      mediaPlaybackRequiresUserGesture: false, // CRITICAL: Enable audio autoplay
      useShouldOverrideUrlLoading: false,
      useOnLoadResource: false,
    ),
    android: AndroidInAppWebViewOptions(
      useHybridComposition: true,
      allowContentAccess: true,
      allowFileAccess: true,
    ),
    ios: IOSInAppWebViewOptions(
      allowsInlineMediaPlayback: true,
      allowsAirPlayForMediaPlayback: true,
    ),
  ),
  onWebViewCreated: (controller) async {
    webController = controller;
    await DebugLogHelper.addDebugLog('NEWS: InAppWebView created, controller set');
    await DebugLogHelper.addDebugLog('NEWS: Loading file: file://${widget.articlePath}/index.html');

    // Verify file exists before loading
    final indexFile = File('${widget.articlePath}/index.html');
    final exists = await indexFile.exists();
    await DebugLogHelper.addDebugLog('NEWS: File exists before WebView load: $exists');

    if (!exists) {
      await DebugLogHelper.addDebugLog('NEWS: ERROR - index.html file does not exist at path!');
    }
  },
  // ... onLoadStop, onLoadError, etc. unchanged
),
```

Replace with:

```dart
body: FutureBuilder<String>(
  future: _indexUrlFuture, // A#72: cached in initState; do NOT call _getIndexUrl() here
  builder: (context, snapshot) {
    if (!snapshot.hasData) {
      return const Center(child: CircularProgressIndicator());
    }
    final fileUrl = snapshot.data!;
    // Derive the (possibly healed) directory path from the URL for file-existence checks below.
    final healedDir = fileUrl
        .replaceFirst('file://', '')
        .replaceAll(RegExp(r'/index\.html$'), '');
    return InAppWebView(
      initialUrlRequest: URLRequest(url: WebUri(fileUrl)),
      initialOptions: InAppWebViewGroupOptions(
        crossPlatform: InAppWebViewOptions(
          javaScriptEnabled: true,
          mediaPlaybackRequiresUserGesture: false, // CRITICAL: Enable audio autoplay
          useShouldOverrideUrlLoading: false,
          useOnLoadResource: false,
        ),
        android: AndroidInAppWebViewOptions(
          useHybridComposition: true,
          allowContentAccess: true,
          allowFileAccess: true,
        ),
        ios: IOSInAppWebViewOptions(
          allowsInlineMediaPlayback: true,
          allowsAirPlayForMediaPlayback: true,
        ),
      ),
      onWebViewCreated: (controller) async {
        webController = controller;
        await DebugLogHelper.addDebugLog('NEWS: InAppWebView created, controller set');
        await DebugLogHelper.addDebugLog('NEWS: Loading file: $fileUrl');

        // Verify file exists before loading (against the healed path).
        final indexFile = File('$healedDir/index.html');
        final exists = await indexFile.exists();
        await DebugLogHelper.addDebugLog('NEWS: File exists before WebView load: $exists');

        if (!exists) {
          await DebugLogHelper.addDebugLog('NEWS: ERROR - index.html file does not exist at path!');
        }
      },
      onLoadStop: (controller, url) async {
        // ... existing body unchanged
      },
      onLoadError: (controller, url, code, message) async {
        // ... existing body unchanged
      },
      // ... rest of callbacks unchanged
    );
  },
),
```

**Preserve verbatim** the existing bodies of `onLoadStop`, `onLoadError`, `androidOnPermissionRequest`, and any other callbacks currently attached to `InAppWebView`. The `// ... existing body unchanged` comments in the snippet above are placeholders only — the real code from lines ~298–360 must remain inside the new `InAppWebView` widget. The spot-check (assignment Step 4e) grep-counts these callbacks; if any are missing, do not commit.

### 3.4 Out of scope for A#72

- `_loadShortTitle()` (line 38), `next/previous` navigation handlers (around lines 437–535), and `_showHelpDialog`'s `helpFile` access (line 577) still read `widget.articlePath` directly. With File 1 in place, the path arriving at `NewsPlayerScreen` from `MyNewsScreen` is already healed, so these will succeed in the normal flow. Healing them defensively is a follow-up (A#74 candidate), not required for the white-screen fix.
- The v5 → v6 `InAppWebView` API migration (`initialOptions` → `initialSettings`) is **not** part of A#72. Doing it now would conflate two changes and obscure the white-screen fix in the commit history.

### 3.5 Acceptance for File 2

- Tap any article (especially one downloaded before the last app reinstall): article loads to its content, no white screen, audio is reachable.
- Debug log shows `NEWS_PLAYER: Healed stale container path` (when path was stale) and `NEWS: File exists before WebView load: true`.

---

## 4. Combined acceptance test (manual, on iPhone 16)

1. Audio mode → My News tab.
2. Tap each of at least 3 articles, including at least one that was on the phone before today's reinstall.
3. Each article must display its content (text + audio controls). No white screens. No "outside the sandbox" WebView error.
4. In About → debug log viewer: confirm both `NEWS: Healed N stale container path(s)` (from `_loadNews`) and `NEWS_PLAYER: Healed stale container path` (from `_getIndexUrl`) appear at least once. On a phone where the container UUID happens to be unchanged, the heal-count line may show 0 and the per-screen heal log may not appear — that is correct behavior.

---

## 5. Files changed in commit

- `audio_tour_app/lib/screens/my_news_screen.dart`
- `audio_tour_app/lib/screens/news_player_screen.dart`
- `audio_tour_app/pubspec.yaml` (version bump: `1.2.9+62` → `1.2.9+63`)

Commit message:

```
v1.2.9+63 - A#72: heal stale iOS container paths for news articles

Mirrors A#56 (tours). News article paths stored in SharedPreferences
under `saved_news` embed the iOS app container UUID, which iOS
reassigns on reinstall, producing white screens with WebView error
"outside the sandbox". Re-anchors paths to the current
Documents directory on load (my_news_screen._loadNews) and again
defensively at WebView launch (news_player_screen._getIndexUrl).
```

---

## 6. Q failure modes to avoid on this assignment

- **Do not** "also" migrate `initialOptions` → `initialSettings` in this commit. That is a separate concern. If you believe it should be done, raise it as a question — do not silently roll it in.
- **Do not** edit `_loadShortTitle`, `next/previous` navigation handlers, or `_showHelpDialog` in this commit. They are out of scope per §3.4.
- **Do not** trust line numbers in §2.2 / §3.2 / §3.3 blindly. Verify by `grep -n` for the unique strings (`Future<void> _loadNews()`, `Future<void> _loadShortTitle()`, `body: InAppWebView`) before editing.
- After editing, run `flutter analyze` against just the two changed files. Expect zero new errors. (Pre-existing ~95 errors in dead/orphan files are noise — see `build_process_for_ios_q.md`.)

