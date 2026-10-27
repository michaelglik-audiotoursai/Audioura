# SUBMISSION — LOCAL-787: Listen page shows a new/translated tour at once (not ~30 s later)

**Base:** subscribed (`2dde77dc`)
**Branch:** `LOCAL-787-listen-refresh`
**Cause read from:** origin/subscribed `6578ca89`

## The bug
Michael (Pixel-7, Android 13, 2026-10-27): after "Tour downloaded successfully"
(and after a translation) the Listen page stayed empty for ~30 s, then filled.
He first thought the download had failed.

## Root cause
`SavedToursRefresh` (`lib/services/saved_tours_refresh.dart`, LOCAL-750 C) is the
signal `MyToursScreen` listens to in order to reload the Listen list in place.
But of the many writers of the `saved_tours` pref, only the community sync
(via `main.dart`'s `CommunityToursSync.onToursChanged`) ever bumped it. Twelve
other writers wrote `saved_tours` **without** bumping:

`tour_generator_screen` (×4), `my_tours_screen` (×4), `community_page_screen`
(×3), `tour_download_service` (×2), `edit_tour_screen`, `home_screen`,
`tour_download`... etc. — the download path included. So after a plain download
the Listen page reloaded only on some later unrelated event (hence the ~30 s).

Two more sources of staleness:
* A write from a **background isolate** (`background_service`,
  `background_tour_monitor`) can't bump the UI isolate's notifier at all.
* `SharedPreferences` caches **per isolate**, so even when the main isolate
  reloads it can read a stale list after a background write unless it calls
  `prefs.reload()` first.

## The fix

### 1. One writer: `SavedToursStore.save`
New `lib/services/saved_tours_store.dart`:

```dart
static Future<bool> save(SharedPreferences prefs, List<String> tours,
    {bool bumpRefresh = true}) async {
  final ok = await prefs.setStringList(key, tours);
  if (bumpRefresh) SavedToursRefresh.instance.bump();
  return ok;
}
```

Every `setStringList('saved_tours', …)` in `lib/` was replaced with
`SavedToursStore.save(...)`. A write and its refresh are now one step; forgetting
to bump is no longer possible. (`bumpRefresh: false` is used by the two
background-isolate writers — where the bump can't cross isolates anyway — and by
`MyToursScreen`'s own in-screen prune/heal/delete writes, which already update
the screen directly and would otherwise cause a re-entrant reload.)

A grep guard test fails the build if any file except the helper writes the pref
directly.

### 2. `MyToursScreen` also reloads on resume and on Listen-tab-select
Background-isolate writes can't bump across isolates, so `MyToursScreen`:
* now `implements WidgetsBindingObserver` and reloads on
  `AppLifecycleState.resumed`;
* and `main_screen.dart` forces the Listen tab's root to rebuild (`_loadTours`
  runs) whenever the Listen tab **becomes selected** (`_switchToTab`).

### 3. `prefs.reload()` before reading
`_loadTours` now calls `await prefs.reload()` before reading `saved_tours`, so a
background-isolate write is seen by the main isolate.

## Files changed
Helper + 13 modified lib files:
* `lib/services/saved_tours_store.dart` (new)
* `lib/screens/my_tours_screen.dart` — observer, resume reload, `prefs.reload()`, helper
* `lib/screens/main_screen.dart` — force Listen reload on tab select
* `lib/screens/{tour_generator_screen,community_page_screen,home_screen,edit_tour_screen}.dart` — helper
* `lib/services/{tour_download_service,tour_translation_helper,downloaded_tour_meta,map_service,community_tours_sync}.dart` — helper
* `lib/services/{background_service,background_tour_monitor}.dart` — helper, `bumpRefresh: false`

## Tests
New:
* `test/saved_tours_store_refresh_test.dart` — render `MyToursScreen` on an empty
  list, call `SavedToursStore.save([tour])`, and the row appears after one reload
  cycle (no 30 s timer). Also asserts the tick bumps, and that `bumpRefresh:false`
  does **not** bump.
* `test/no_raw_saved_tours_write_test.dart` — scans `lib/**.dart` and fails if any
  file other than the helper calls `setStringList('saved_tours', …)`.

Existing targeted tests still pass: `listen_stop_count_test`,
`downloaded_message_and_listen_open_test`, `voice_listen_options_local752_test`.

### Full `flutter test` — branch vs baseline (NEW failures only)
| | passed | failed |
|---|---|---|
| **Branch LOCAL-787** | 1148 | 8 |
| **Baseline (origin/subscribed `6578ca89`, worktree `/Users/micha/audioura-subscribed-local`)** | 1145 | 8 |

**Zero NEW failures.** The same 8 failures appear in BOTH runs, with identical
test names — all pre-existing and environment/live-server dependent, unrelated to
this change:
* `local109_swipe_e2e_test.dart` — 6 real-server end-to-end tests
* `storied_compat_guard_test.dart` — 1 (D661 lib/ server-call guard)
* `storied_compat_screens_404_test.dart` — 1 (Storied gateway)

The **+3** passing delta is exactly the 3 new test cases added here.

## Live test (Android emulator only)
Android **emulator** `emulator-5554` (AVD `local715_test`, Android 14). Michael's
physical Pixel 4 and iPhone were **never** touched. Debug build
(`--dart-define=DEBUG_SERVER_IP=10.0.2.2`) against the already-running Mac docker
stack; the shared `audioura-*` containers were used (not modified) only to
download an existing **published FREE** tour → **$0 paid-API**.

Flow: onboarding Skip → disclaimer "Got it" → grant location → set emulator geo to
Boston → Home shows nearby tours → **Listen tab EMPTY** ("No tours yet. Generate
your first tour!") → Home → List → open FREE "Faneuil Hall Marketplace … Walking
Tour" → **Download Tour** → "Downloading tour…" then the snackbar "1 tour
downloaded and is now on your Listen page" → switch to **Listen** → the row
"Faneuil Hall Marketplace … — 3 stops · Created: 2026-10-27" **is there**, no 30 s
wait.

Screenshots (in `docs/local787/`):
* `listen_before_empty.png` — Listen page empty before the download
* `home_downloading.png` — "Downloading tour…" + "1 tour downloaded and is now on your Listen page"
* `listen_after_row.png` — the downloaded tour on the Listen page immediately

## Process notes
Branched from HEAD (`2dde77dc`); `git merge-base --is-ancestor 2dde77dc HEAD`
passes. No `git add -A` (files staged explicitly). No edits to DECISIONS.md,
CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, or GCLOUD_STORIED_START_HERE.md. No
DELETE of anything. One heavy build only (the debug APK). The signing
`debug.keystore` used for the emulator build is git-ignored and is not committed.
