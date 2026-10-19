# SUBMISSION — LOCAL-714: Community tours download in the background (D675 part 2)

**Branch:** `LOCAL-714-background-download` (from `subscribed` = 0fb16a19 — the
merged LOCAL-713)
**Version:** 2.4.29+69 → **2.4.30+70** (patch +1, build +1)

LOCAL-713 gave the server **new-tours** endpoint, the saved **listening
language**, the community-page **Download**, and the **sync-on-open** baseline.
This task makes the **same** sync run when the app is **closed**, with the
member's permission:

- a **join question** (on a free join and after a pass purchase) that opts a
  community into auto-download;
- **Android** — a `workmanager` periodic task (every 6 h) that runs the **SAME**
  planner + downloader as the sync on open;
- **iOS** — a BGTaskScheduler app-refresh that only **CHECKS** and posts **one
  quiet local notification**; downloads happen at the next app open.

One sync implementation, called from both the app-open path and the background
worker (D675: "One implementation, called from both").

---

## 1. The join question (app)

`lib/screens/community_page_screen.dart`.

After a **free join** (`_joinFree`) and after a **successful pass purchase**
(`_buyPass`), a dialog asks, verbatim:

> "Download this community's new tours automatically? Only on Wi-Fi, when your
> phone isn't busy."  — **Yes** / **Not now**

- **Yes** sets `auto_download_<id>` (the per-community switch LOCAL-713's planner
  reads), asks for **notification permission** (the ONLY place permission is
  requested — D675 part 2 §3), and (re)registers the background task.
- **Not now** leaves the switch OFF (the default).

The community page also shows, for a member/owner, an **auto-download switch**
plus **"Also on mobile data"** (off by default — Wi-Fi/unmetered only). Toggling
either persists the pref and re-registers the task so its network constraint
matches.

---

## 2. Android — WorkManager periodic task

`lib/services/community_background.dart` + `lib/main.dart`.

- `main()` calls `Workmanager().initialize(callbackDispatcher)` then
  `registerCommunitySyncTask()`.
- `registerCommunitySyncTask` registers a **periodic task every 6 h** with
  `Constraints`:
  - `networkType`: **unmetered** (Wi-Fi/ethernet) unless the member allowed
    mobile data, in which case **connected** (any network);
  - `requiresBatteryNotLow: true`;
  - `requiresStorageNotLow: true`;
  - `ExistingPeriodicWorkPolicy.update` (idempotent; constraint changes apply).
- The worker (`runAndroidBackgroundSync`) applies the explicit **< 1 GB free →
  skip** gate (D675 part 2 §2) and then runs **`CommunityToursSync.instance.run()`
  — the exact same shared planner (`SyncPlanner.plan`) and downloader
  (`TourDownloadService`) the sync-on-open uses.** Nothing is duplicated.
- The entry point `callbackDispatcher` is `@pragma('vm:entry-point')` (kept by
  tree-shaking) and dispatches: Android → the shared sync (download); iOS → the
  check-only path.

### Plugin pin (floor protection, as `app_links` was pinned)

`workmanager: 0.9.3` — pinned (no caret), SDK floor exactly `>=3.5.0 <4.0.0`
(this project's Dart 3.5 floor), Flutter `>=3.32.0`. It is the last 0.9.x before
the 0.10.x line; it uses the **v2 Android embedding** (the older 0.5.x referenced
the removed v1 `ShimPluginRegistry`/`registerWith` and no longer compiles on the
current Flutter toolchain). A caret range would pull 0.10.x and raise the floor —
hence the exact pin, documented inline in `pubspec.yaml`. The Dart API
(`Workmanager().initialize` / `registerPeriodicTask` / `Constraints` /
`NetworkType`) is the classic one.

`timezone: ^0.9.0` — promoted from a transitive dependency of
`flutter_local_notifications` so the single morning notification can be
zoned-scheduled; matches the version already resolved (0.9.4; 0.11+ needs Dart
3.10, above the floor).

---

## 3. iOS — BGTaskScheduler app refresh (CHECK only)

`lib/services/community_background.dart` (`runIosBackgroundCheck`),
`lib/services/community_notifications.dart`, `ios/Runner/AppDelegate.swift`,
`ios/Runner/Info.plist`.

- The iOS background path only **CHECKS** `/communities/new-tours` (never
  downloads in the background). If there is anything new in an opted-in
  community, it posts **ONE quiet local notification** — e.g. **"2 new tours
  from Demo Boston Walkers"**. The download happens at the next app open
  (713's sync).
- **Quiet hours** 23:00–07:30 local are respected: a check that finds new tours
  during quiet hours **queues** the single notification for the next **07:30**
  (pure `quietHoursGate`), via `zonedSchedule`.
- **Notification permission** is requested only on **Yes** to auto-download
  (`CommunityNotifications.requestPermissionOnOptIn`), never at app launch.
- `Info.plist`: `UIBackgroundModes` gains **`fetch`** (+ `processing`);
  **`BGTaskSchedulerPermittedIdentifiers`** = `com.audioura.community_tours_sync`.
- `AppDelegate.swift`: `import workmanager_apple`;
  `WorkmanagerPlugin.setPluginRegistrantCallback`,
  `registerPeriodicTask(withIdentifier: "com.audioura.community_tours_sync")`,
  `registerLaunchHandlers()` (0.9.x federated iOS API).
- iOS deployment target bumped **13.0 → 14.0** (Podfile + `project.pbxproj` +
  Podfile `post_install`) because `workmanager_apple` requires 14.0.

---

## 4. One sync implementation, called from both

`lib/services/community_tours_sync.dart` is unchanged in policy: it still fetches
`/communities/new-tours`, runs the pure `SyncPlanner.plan(...)`, downloads via
`TourDownloadService`, and advances `since` only after the downloads succeed. The
only addition is two **static injection seams** (`fetchNewTours`, `download`,
defaulting to the real endpoint client and the single download path) so the
background entry point and the tests call the **identical** `run()` — never a
second path.

---

## Tests

**Dart** `test/community_background_test.dart` (16 tests, pure/hermetic — no
device, no WorkManager, no real HTTP, no notification plugin):

- **the background entry point runs the SHARED planner + downloader** — `run()`
  with a stubbed `fetchNewTours` + `download`, and the pure `SyncPlanner`
  selecting the opted-in new tour;
- **NOTHING runs when every auto-download switch is OFF** — the planner plans
  nothing, `run()` downloads nothing, and the iOS check posts nothing;
- **the quiet-hours gate** — midday/09:00 notify now; 23:30 defers to 07:30
  tomorrow; 02:00 defers to 07:30 today; the 23:00/07:30 boundaries;
- **the notification text for 1 vs N tours** — "1 new tour from X" (singular),
  "2 new tours from X" (plural), and the "and N other communities" summary;
- plus the **< 1 GB** storage gate (clears at exactly 1 GiB; an unmeasurable
  `-1` is "not enough").

**Full `flutter test`:** `+645 -6`. The **6** failures are exactly the baseline
`test/local109_swipe_e2e_test.dart` live-server tests (SocketException — no
server on the test host); no new failures. (713's baseline was the same 6.)

---

## Live test — Android (Pixel 4, API 33), app CLOSED

Debug build pointed at the Mac's dev stack:
`flutter build apk --debug --dart-define=DEBUG_SERVER_IP=192.168.0.136`, installed
on the attached Pixel 4 (device `user_id = USER-281301397`). (A standard
`android/app/debug.keystore` was generated — gitignored, alias
`androiddebugkey`, not a secret — to sign the debug APK.)

Setup harness `live_local714_bg_setup.py` (own harness; is_test rows only;
cleanup by captured id guarded by `is_test`; never touches a non-is_test row;
never renames/stops a container). The test community tours were sourced from a
real, downloadable tour (id 557) so the whole **download → resolve → save** chain
runs for real (557 resolves clean to edit id `181e5ca1`).

**Proof the BACKGROUND worker downloaded a tour with the app not in the
foreground:**

1. Device state reset: `auto_download_2 = true`, `since` = a fixed timestamp,
   `saved_tours` empty.
2. App launched, then **backgrounded with HOME** (the launcher
   `NexusLauncherActivity` is the resumed activity — Audioura is not in the
   foreground; the process survives, as a closed-but-scheduled app would).
3. A **new** is_test community tour (id 710, "LOCAL714 — Closed-App Tour") was
   created server-side **after** the stored `since`, so only the background run
   could pick it up.
4. The WorkManager job was visible in JobScheduler as
   `JOB #u0a473/7 … NetworkRequest NOT_METERED&INTERNET … Delay=+5h53m` — i.e.
   the unmetered + ~6 h periodic constraints from §2.
5. Forced:  `adb shell cmd jobscheduler run -f com.audioura.audiotours 7`
   → `Running job [FORCED]`.
6. The **background isolate** then (app not foregrounded):
   - `GET /communities/new-tours?user_id=USER-281301397&since=…` → 200
   - `GET /download-tour/710?user_id=USER-281301397` → **200** (real zip)
   - `GET /tour/710/resolve` → **200** (edit id `181e5ca1`)
   - the tour **appeared in Listen**: the device's `saved_tours` now contained
     **"LOCAL714 — Closed-App Tour"** (tour_id `181e5ca1`, 5 stops);
   - `community_tours_since` advanced to the run's `server_time`
     (`2026-10-19T04:16:55…`) — only after the download succeeded.

**Row counts (is_test only; restored after):**

```
BEFORE:  audio_tours=493  community_memberships=0  is_test=423
DURING:  created is_test community tours (708/709/710) + 1 active test
         membership for USER-281301397 in community 2
AFTER cleanup (by captured id, guarded is_test=TRUE):
         audio_tours=493  community_memberships=0  is_test=423   ← matches BEFORE
```

No leftover rows; only is_test rows were created and deleted.

## Live test — iOS

**Build only** (no install — LEAD installs):
`flutter build ios --debug --no-codesign` →
`✓ Built build/ios/iphoneos/Runner.app`. The AppDelegate workmanager_apple
registration, the Info.plist BGTaskScheduler/UIBackgroundModes keys, and the
14.0 deployment target all compile.

---

## Files

**App (new):** `lib/services/community_background.dart`,
`lib/services/community_notifications.dart`,
`test/community_background_test.dart`.

**App (changed):** `lib/services/community_tours_sync.dart` (injection seams —
same `run()`), `lib/screens/community_page_screen.dart` (join question +
switches), `lib/main.dart` (WorkManager init + register), `pubspec.yaml`
(version 2.4.30+70, `workmanager: 0.9.3`, `timezone: ^0.9.0`),
`pubspec.lock`.

**iOS:** `ios/Runner/AppDelegate.swift`, `ios/Runner/Info.plist`,
`ios/Podfile`, `ios/Podfile.lock`, `ios/Runner.xcodeproj/project.pbxproj`.

**macOS (generated):** `macos/Flutter/GeneratedPluginRegistrant.swift`
(automatic `WorkmanagerPlugin.register` line from `pub get`).

**Harness:** `live_local714_bg_setup.py` (repo root).

Did **not** edit DECISIONS / CLAUDE / BACKLOG / WORK_QUEUE / .continuous_dev.
The generated `android/app/debug.keystore` is gitignored and not committed.
