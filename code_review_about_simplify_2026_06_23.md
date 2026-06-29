# Claude Code Review — About Screen: Hide Cloud Fields, Bake Defaults (commit `bcaa3fd`)

**Date:** 2026-06-23
**Branch:** `services-migration`
**Commit:** `bcaa3fd`
**ClickUp task:** 86aj6ynjp

---

## What was done

Simplified the About screen for production: cloud mode users see no configuration fields. API key, cloud base URL, and path-routing are baked into the build.

### Changes to `lib/config/endpoints.dart`

1. **Fresh install defaults to Cloud mode** — all `prefs.getString('server_mode') ?? 'local'` changed to `?? 'cloud'` (4 locations: `base()`, `newsDownloadUrl()`, `newsStatusUrl()`, `apiHeaders()`)

2. **Baked cloud base URL:**
```dart
static const _defaultCloudBaseUrl = 'https://api.audioura.com';
```
`base()` falls back to this when the pref is empty (which it is on fresh install).

3. **Baked API key via `--dart-define`:**
```dart
static const _builtInApiKey = String.fromEnvironment('GATEWAY_API_KEY');
```
`apiHeaders()` uses this when the stored pref is empty. Key is injected at build time — never in source.

4. **Path prefixes hardcoded OFF** — removed the `usePrefix` branch entirely. `base()` always returns bare `cloudBase` in cloud mode.

### Changes to `lib/screens/about_screen.dart`

1. **Default `_serverMode = 'cloud'`** (was `'local'`)
2. **Removed cloud fields UI** — the entire `if (_serverMode == 'cloud') Column(...)` block with API Key, Cloud Base URL, and path-routing checkbox removed (~80 lines)
3. **Replaced with simple status text:**
```dart
if (_serverMode == 'cloud') const Padding(
  padding: EdgeInsets.only(top: 8),
  child: Text('✅ Cloud mode active — connected to api.audioura.com', ...),
),
```
4. **Local WiFi mode unchanged** — Server IP field still visible and editable when user switches to Local

---

## Build command (for the key)

```bash
flutter build apk --release --dart-define=GATEWAY_API_KEY=<your-key-here>
```

The build script (`build_flutter_clean.sh`) should be updated to include this flag. The actual key value is NOT in the repo.

---

## Test criteria

- [ ] Fresh install → app is in Cloud mode, loads tours/news with no fields to fill
- [ ] About screen shows "✅ Cloud mode active" — no API Key / URL / checkbox fields visible
- [ ] Tap Local WiFi → Server IP field appears, editable, defaults to 192.168.0.218
- [ ] Tap back to Cloud → fields disappear again
- [ ] Cloud tour generation works (key comes from `--dart-define`)
- [ ] If built WITHOUT `--dart-define`, key is empty string → gateway returns 401 (expected, not a crash)
- [ ] Pending device test: full E2E on fresh install

---

## Verdict requested
Approve.
