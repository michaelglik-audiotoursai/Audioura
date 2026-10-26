# SUBMISSION — LOCAL-773

**App — first launch crashes in Home's `_loadAppMode` (setState after dispose); stale startup banner**

- **Agent:** Mac Mini Kiro
- **Branch:** `LOCAL-773-home-mounted-guard`
- **Base:** `subscribed` @ `85af16c4` (`git merge-base --is-ancestor 85af16c4 HEAD` → exit 0)
- **Found by:** GCloud_Storied on Play build 2.4.31+77 (emulator, API 36), 2026-10-26

---

## 1. The crash, and why every fresh install hits it

First-launch logcat:

```
Unhandled Exception: Null check operator used on a null value
  at State.setState  (_HomeScreenState._loadAppMode, home_screen.dart ~325)
```

`_HomeScreenState._loadAppMode()` awaits SharedPreferences, `DeviceService.getUserId`,
`_loadLocationHistory` and `_loadCustomLocation`, then calls `setState` with **no `mounted`
check**. On a fresh install Home has already been disposed by the time those awaits resolve,
so the `setState` fires on a defunct `State` and throws (in release the null `_element` →
"Null check operator used on a null value"; the same bug asserts "setState() called after
dispose()" in a debug build). The rest of the load (`_loadNewsletters` / `_initializeMap`) is
then skipped.

### Why Home is disposed on first launch (Build step 3 — report)

Root cause is in `lib/main.dart`, `_AudioTourAppState` — **not** in Home:

1. `_onboardingComplete` is initialised to `true` ("assume complete until loaded"), so the
   first `build()` renders `MainScreen` → `HomeScreen` **immediately** (an optimistic render
   that avoids a blank frame).
2. `initState` calls `_checkOnboarding()`, which `await`s `SharedPreferences` and reads
   `onboarding_complete`. On a fresh install that key is **false**, so it `setState`s and the
   root rebuilds with `home = OnboardingScreen`.
3. That rebuild **disposes the already-mounted `HomeScreen`** while Home's own
   `initState → _loadAppMode()` async chain is still in flight. When Home's awaits resolve,
   its unguarded `setState` runs on the disposed state → the crash.

Testers install fresh, so all of them race through this exact ordering.

**Navigation decision:** the optimistic-render-then-correct pattern is intentional (it avoids
a visible blank/extra frame before onboarding is known) and is not *plainly* wrong, so per the
ticket I did **not** change navigation. The correct, minimal fix is the `mounted` guards that
Flutter itself recommends for "setState from a later callback".

---

## 2. Build step 1 — `home_screen.dart`: `mounted` guard before every `setState` after an `await`

I swept the whole file, not just line 325. Added `if (!mounted) return;` (and, where a
`BuildContext` is also used after the await, the same guard covers that) immediately before
each `setState` that follows an `await` and was previously unguarded. **15** sites:

| Guard line | Protected `setState` | Method |
|---|---|---|
| 325 (+331) | 331 | `_loadAppMode` — **the reported crash site** |
| 349 | 350 | `_loadCustomLocation` |
| 416 | 417 | `_initializeMap` |
| 435 | 436 | `_getCurrentLocation` (permission denied) |
| 445 | 446 | `_getCurrentLocation` (denied forever) |
| 481 | 482 | `_getCurrentLocation` (catch) |
| 500 | 501 | `_loadCachedTours` |
| 903 | 904 | `_loadNearbyTours` (server-error branch, `_connectionError`) |
| 1541 | 1542 | `_useCustomLocation` (trailing `_isLoading = false`) |
| 1563 | 1564 | `_resetToCurrentLocation` (trailing `_isLoading = false`) |
| 3285 | 3286 | `_loadNewsletters` (success) |
| 3293 | 3304 | `_loadNewsletters` (server-error branch — context + setState) |
| 3311 | 3322 | `_loadNewsletters` (catch — context + setState) |
| 3337 | 3338 | `_loadCachedNewsletters` |
| 4613 | 4615 | `home_location` FAB `onPressed` (after `Geolocator.getCurrentPosition`) |

Sites that were **already** safe were left unchanged:

- Already guarded: lines 187, 209 (`if (!mounted) return`), 465, 826, 908 (`if (mounted)`),
  and the filter setters at 1013/1033/1041/1051 (`if (!mounted) return`).
- Synchronous (no `await` before the `setState`): `_useCustomLocation` entry (1510),
  `_resetToCurrentLocation` entry (1548), the newsletter `PopupMenuButton.onSelected` (4640).

*(Line numbers are post-edit.)*

## 3. Build step 2 — the other first-launch screens (sweep)

Checked onboarding, plan/paywall, and the main shell for `setState`-after-`await`. **No changes
were needed** — each was already correct:

- `lib/screens/onboarding_screen.dart` — a `StatelessWidget`; no `setState` at all.
- `lib/screens/plan_screen.dart` — every `setState` after an `await` is already guarded
  (`_resolveStubMode`, `_load`, `_buy`, `_joinQueue`, `_submitCode` all use
  `if (!mounted) return;` / `if (mounted)`).
- `lib/screens/main_screen.dart` — the `setState`s are synchronous UI callbacks or already
  guarded (`_onListenOpenRequested`, `_initializeNotifications`, `_refreshModeForTab`).
- `lib/main.dart` `_checkOnboarding` already uses `if (mounted) setState(...)`.

## 4. Build step 2 (banner) — `main.dart`: real version, never hard-coded

Replaced

```dart
print('=== AUDIOTOURS DEV v1.2.9+61 STARTING ===');
```

with a value read from `package_info_plus` (already a direct dependency — used by
`about_screen.dart` and `error_handler_service.dart`), with a defensive fallback so startup is
never blocked:

```dart
String versionTag;
try {
  final info = await PackageInfo.fromPlatform();
  versionTag = 'v${info.version}+${info.buildNumber}';
} catch (e) {
  versionTag = '(version unavailable)';
}
print('=== AUDIOURA $versionTag STARTING ===');
```

The banner now always matches the installed build (e.g. `=== AUDIOURA v2.4.31+77 STARTING ===`)
— no hard-coded version string.

---

## 5. Tests

### New widget test — `test/home_dispose_before_load_local773_test.dart`

Pumps `HomeScreen`, then disposes it **before** the async load finishes, exactly as the root
does on a fresh install. To make the race deterministic it holds the `device_info_plus`
platform-channel reply open with a `Completer` (fresh install → no cached `user_id` → the
`_loadAppMode` await parks at `DeviceService.getUserId()`), disposes Home, then releases the
reply and flushes with `runAsync`. Errors routed through `FlutterError.onError` are collected;
`FlutterError.onError` is restored before any `expect`.

Asserts:
- **No `setState`-after-dispose error** ("setState() called after dispose()" / "Null check
  operator used on a null value").
- `_initializeMap` is **not** reached — its first line logs
  `HOME: Starting map initialization` to the persisted `debug_logs`, which must stay absent.

Verified:
- **RED on base** (guard removed): `Actual: [setState() called after dispose():
  _HomeScreenState#…(lifecycle state: defunct, not mounted)]`.
- **GREEN on the branch** (guard present): all assertions pass.

### `flutter analyze` — no new issues

Compared the analyzer output for `lib/main.dart` + `lib/screens/home_screen.dart` on base vs
branch: **zero new diagnostics** (`comm -13` of the sorted outputs shows only the summary-count
line). The total actually **dropped 306 → 304** (the banner is now one `print` instead of the
old one). The new test file analyzes clean.

### Existing app tests — green, base vs branch

Full suite on the branch: **+1124 / −7**. The 7 failures are environmental and
**identical on base** (verified by stashing the two source changes and re-running):
- 6 × `local109_swipe_e2e_test.dart` — real-server end-to-end tests; `SocketException:
  Connection refused` (they need the LOCAL backend running).
- 1 × `storied_compat_screens_404_test.dart` — Storied gateway 404 case (same network
  dependency).

None of the 7 touch `home_screen.dart`, `main.dart`, or onboarding/plan/shell. The 44
home/plan/main-shell widget tests all pass.

---

## 6. Live test (Android emulator) — NOT run by this agent

Per D/LOCAL-714 the live test is Android-emulator-only and must never touch Michael's phones.
This change is a crash fix verified by the red/green widget test above and by `flutter analyze`.
The emulator fresh-install check (clear app data → launch → logcat has no `Null check operator`,
banner shows the real version, against the LOCAL stack 192.168.0.187 with `APP_TRACK=subscribed`)
should be run on the emulator before promotion. The code change makes the first-launch path
exception-free and the banner version-accurate.

---

## Files changed

- `audio_tour_app/lib/screens/home_screen.dart` — 15 `mounted` guards before `setState`-after-`await`.
- `audio_tour_app/lib/main.dart` — dynamic startup banner from `package_info_plus` (+ import).
- `audio_tour_app/test/home_dispose_before_load_local773_test.dart` — new red/green widget test.

No navigation change. No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE,
`.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, or GCLOUD_STORIED_START_HERE.md.
No deletions.
