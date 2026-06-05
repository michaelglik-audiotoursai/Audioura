# Code Review Request — v2.1.1+2 (M1 completion + dead code cleanup)
**Date:** 2026-06-03
**Prepared by:** Android Amazon-Q
**Branch:** `services-migration`
**Based on:** Review `REVIEW_FOR_MOBILE_AQ_v2.1.2_2026_06_03.md` — 3 missed sites identified

---

## Context

The previous review (`REVIEW_FOR_MOBILE_AQ_v2.1.2_2026_06_03.md`) confirmed that M1
foreground generation was correctly migrated but identified **3 remaining hardcoded LAN
URLs** that would break cloud mode:

1. `_downloadBackgroundTour` status call — `http://$serverIp:5002/status/${tour['id']}`
2. `_downloadBackgroundTour` download call — `http://$serverIp:5002/download/${tour['id']}`
3. `_processAdditionalLanguages` translated download — `http://$serverIp:5005/download-tour/$translatedId`

It also instructed us to remove the dead `apiBaseUrl` and `serverIp` reads in
`background_service.dart` (Q2/Q3 from the previous review).

All 4 issues are fixed in this session. Version stays at `2.1.1+2` — no tests
conducted yet, no build number increment.

---

## Changes

### File 1: `screens/tour_generator_screen.dart`

#### Fix 1 — `_downloadBackgroundTour`: migrate status + download to `Endpoints`

```dart
// BEFORE:
final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
final statusResponse = await http.get(Uri.parse('http://$serverIp:5002/status/${tour['id']}'));
...
final response = await http.get(Uri.parse('http://$serverIp:5002/download/${tour['id']}'));

// AFTER:
final statusResponse = await http.get(
  await Endpoints.url(Service.orchestrator, '/status/${tour['id']}'),
);
...
final response = await http.get(
  await Endpoints.url(Service.orchestrator, '/download/${tour['id']}'),
);
```

- Removed `serverIp` local and `'192.168.0.217'` fallback from this method.
- `prefs` instance retained — still needed for `saved_tours` writes below.

#### Fix 2 — `_processAdditionalLanguages`: migrate translated download to `Endpoints`

```dart
// BEFORE:
final prefs = await SharedPreferences.getInstance();
final serverIp = prefs.getString('server_ip') ?? Config.defaultServerIp;
...
final url = 'http://$serverIp:5005/download-tour/$translatedId';
final resp = await http.get(Uri.parse(url)).timeout(const Duration(seconds: 120));

// AFTER:
...
final resp = await http.get(
  await Endpoints.url(Service.mapDelivery, '/download-tour/$translatedId'),
).timeout(const Duration(seconds: 120));
```

- Removed `prefs` local (was only used for `serverIp`) and `serverIp` local.
- Removed now-unused `Config` import from the file.

**Q1:** `_processAdditionalLanguages` previously called `SharedPreferences.getInstance()`
only to read `server_ip`. After the fix, `prefs` is no longer obtained in this method.
The `appDir` is still obtained via `getApplicationDocumentsDirectory()`. Inside the loop,
`_saveTourToMyToursTranslated` receives `prefs` as a parameter — but that `prefs` was
the one obtained here. Now it's gone. Does `_saveTourToMyToursTranslated` need its own
`prefs` call, or is it passed in from somewhere else? Please verify the call chain is
intact.

---

### File 2: `services/background_service.dart`

#### Fix 3 — Remove dead `apiBaseUrl` read (Q2 from previous review)

```dart
// BEFORE:
final tour = jsonDecode(tourJson);
final jobId = tour['jobId'];
final location = tour['location'];
final apiBaseUrl = tour['apiBaseUrl'];  // ← dead: key no longer stored in JSON

// AFTER:
final tour = jsonDecode(tourJson);
final jobId = tour['jobId'];
final location = tour['location'];
```

#### Fix 4 — Remove dead `serverIp` local (Q3 from previous review)

```dart
// BEFORE:
final prefs = await SharedPreferences.getInstance();
final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';  // ← dead
await DebugLogHelper.addDebugLog('Downloading tour via Endpoints: ...');

// AFTER:
final prefs = await SharedPreferences.getInstance();
await DebugLogHelper.addDebugLog('Downloading tour via Endpoints: ...');
```

- `prefs` instance retained — still needed for `saved_tours`, `background_tours`,
  `stop_count_$jobId` reads/writes below.

---

## Summary of Questions

| # | File | Topic | Priority |
|---|------|--------|----------|
| 1 | `tour_generator_screen.dart` | `_processAdditionalLanguages` no longer obtains `prefs` — does `_saveTourToMyToursTranslated` still receive a valid `prefs`? | High |

---

## Ubuntu Build Instructions

**Branch:** `services-migration`
**Version:** `2.1.1+2`
**No git pull needed** — Ubuntu VM uses VirtualBox shared folder (same files as Windows dev tree)

```bash
bash build_flutter_clean.sh
```

**APK output:** `audioura-dev.apk` in `development/` folder

---

## Smoke Test Plan

**Priority tests** (from the review doc — these are the paths the missed sites affect):

1. **Multi-language tour (cloud mode)**
   - About → Cloud mode → enter gateway URL → leave "Use gateway path routing" UNCHECKED
   - Generate tab → request a tour with RU or KO selected as additional language
   - Expected: English tour downloads AND translated tour downloads → both appear in My Tours

2. **Backgrounded tour completion (cloud mode)**
   - About → Cloud mode
   - Generate tab → "Generate in Background" → leave app
   - Expected: tour completes and auto-downloads to My Tours when app returns to foreground

3. **Foreground single-language tour (regression check)**
   - Local mode → Generate tab → request a tour → tour generates, downloads, opens in player
   - Expected: no regression from M1 foreground work

4. **Background tour with `_downloadBackgroundTour` (manual download from UI)**
   - If a tour appears in Background Tours Status section → tap download
   - Expected: tour downloads and moves to My Tours
