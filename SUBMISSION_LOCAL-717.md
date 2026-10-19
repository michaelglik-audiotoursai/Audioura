# LOCAL-717 — Search "word*" = tour names only; batch download reports failures; "updated to version N" (D677)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-717-search-and-download-honesty` (from `subscribed` = `4235f353`)
**Base verified:** `git merge-base --is-ancestor 4235f353 HEAD` → exit 0.
**Version:** `2.4.30+73` → `2.4.30+74` (build +1).

## The three problems (D677, Michael's restaurant-tour test, 2026-10-19)

1. **Search "restaurant\*" moved the map to a far-away place.** The trailing `*` was the
   user's "search tour NAMES" signal, but the text search still geocoded and a found
   PLACE always wins (D662), so the map relocated to a place called "Restaurant" instead
   of listing the restaurant tours.
2. **A three-tour download said "2 tours downloaded…" and dropped the third silently.**
   Tour 370 downloaded then failed `/tour/370/resolve` (409) and vanished with no word.
   The server-side split-store cause is already fixed (D677 §1); the app must still never
   hide a failure.
3. **Regenerating the same request updated tour 370 to version 2, but nothing said so.**
   The completion message only ever said "Tour ready!", so Michael went looking for a
   second tour that never existed.

## What changed

### 1. A trailing `*` is a tour-name search ONLY — never a place

**`lib/utils/search_dispatch.dart`** (the pure, UI-free search brain):

- `SearchDispatch.text` gained a `bool tourNameOnly`. `classifySearchInput` sets it
  `true` when the trimmed input's **last character** is `*` ("restaurant\*", "Boston\*",
  "restaurant tour\*"). Only a *trailing* `*` is the signal — a `*` in the middle
  ("walking\*tour") stays an ordinary text search that also tries the geocoder.
- `resolveTextSearch` gained a `nameOnly` flag and a new outcome
  `TextSearchOutcome.noNamedTours`. For a name-only search a place can **never** win
  (the caller does not even call the geocoder); no tours matched → `noNamedTours` rather
  than `nothing`.

**`lib/screens/home_screen.dart`** — `_dispatchTextSearch` now takes the whole
`SearchDispatch`. When `tourNameOnly` is true it passes `null` for the geocoder future
(the geocoder is never consulted) and `nameOnly: true` to `resolveTextSearch`. The new
`noNamedTours` case shows `"No tours named '<text>…'"` (the trailing `*` is stripped so
the message names what the user typed). Inputs without `*` keep D662 behaviour exactly.

The "starts-with" match is the existing one: `_searchTours` converts `*`→`.*`, so
`restaurant*` queries `/search-tours?pattern=restaurant.*` — a starts-with match.

### 2. A batch download never drops a tour silently

**`lib/utils/downloaded_message.dart`** — new optional `List<String> downloadFailures`.
When non-empty it appends `". N couldn't be downloaded: <name>, <name>"` after the
success clause, with the count agreeing. The existing per-tour **translation** failures
(`failures` map, "Some translations failed: …") are untouched and independent.

| Input | Output |
|---|---|
| `downloaded: 2, downloadFailures: ['Boston — Restaurant Tour']` | `2 tours downloaded and are now on your Listen page. 1 couldn't be downloaded: Boston — Restaurant Tour` |
| `downloaded: 1, downloadFailures: ['Boston — Restaurant Tour']` | `1 tour downloaded and is now on your Listen page. 1 couldn't be downloaded: Boston — Restaurant Tour` |
| `downloaded: 0, downloadFailures: ['Boston — Restaurant Tour']` | `No new tours downloaded - all selected tours were already on your phone. 1 couldn't be downloaded: Boston — Restaurant Tour` |
| `downloaded: 2, downloadFailures: ['Tour A','Tour B']` | `… 2 couldn't be downloaded: Tour A, Tour B` |

**`lib/screens/home_screen.dart`** — `_downloadMultipleTours`: a tour is counted as
downloaded ONLY after `_downloadSingleTourSilent` returns without throwing (the resolve/
save failure throws). The catch that previously said `// Continue with next tour`
silently now **collects** the tour's short title into `downloadFailures`, logs the full
reason to `DebugLogHelper` (`HOME: DOWNLOAD FAILED for "<title>" (id=…): <exception>`),
and passes `downloadFailures` to `downloadedMessage`. Because the snackbar is shown
whenever any download was attempted, a 0-saved/all-failed batch still reports every
failure.

**`lib/services/tour_download_service.dart`** — the single save path. On a non-200
`/tour/<id>/resolve` it now logs the raw HTTP status + body
(`DOWNLOAD_SVC: /tour/<id>/resolve FAILED status=409 body=…`) before throwing, so a
dropped tour (tour 370's 409) is findable in the logs on both the batch and the single
path.

### 3. "Updated to version N" when a generation replaces an existing tour

**Server — `tour_orchestrator_service.py`** (noted here as a server change):

- `store_audio_tour`'s result dict now carries `version_no`: `1` for a fresh insert;
  for a replacement, `next_version + 1` (the OLD content is archived as `next_version`,
  so the live row is `next_version + 1` — Michael's tour 370: old v1 archived → live v2);
  for a byte-identical cache hit, the current `MAX(version_no)+1`.
- The orchestrator reads `version_no` + the `replaced` action and sets
  `ACTIVE_JOBS[job_id]["version_no"] / ["replaced"] / ["tour_title"]`.
- `GET /status/<job_id>` surfaces `version_no`, `replaced` and `tour_title` on a
  completed job — in both the in-memory (thread mode, what the local stack uses) and the
  database (cloud_tasks) response. Older jobs that never set the fields omit them.

**App — `lib/utils/generation_completion_message.dart`** (new, pure): given a job-status
map it returns `"Updated your tour '<short title>' — now version N"` when
`replaced == true && version_no >= 2`, else the default `"Tour ready! Opening now..."`.
A fresh insert (version 1) or a payload with no version info is a new tour, not an
update. **`lib/screens/tour_generator_screen.dart`** `_autoDownloadAndPlay` uses it with
the location the user typed as the fallback title.

### 4. Version — `2.4.30+73` → `2.4.30+74`.

## Tests

**Dart (all passing):**

- `test/search_dispatch_test.dart` — the four ticket cases: `restaurant*`, `Boston*`,
  `restaurant tour*` classify as `text` + `tourNameOnly`; `Boston` (no star) stays
  `text`/not name-only (keeps D662); plus a mid-string `*` is NOT the signal, and the
  name-only outcome table (tours → `toursOnly`; none → `noNamedTours`; a place can never
  win).
- `test/downloaded_message_and_listen_open_test.dart` — the failure-message goldens:
  1 ok + 1 failed, 2 ok + 1 failed (the D677 example string), 0 ok + 1 failed, 2 ok +
  2 failed, and download-failure + translation-failure together.
- `test/generation_completion_message_test.dart` (new) — "updated to version 2" (the
  D677 case), version 3, fallback title, a `String` version_no, a brand-new tour → the
  default message, and the `replaced`-but-version-1 guard.

**Python (orchestrator changed) — `tests/test_local717_job_status_version.py` (new,
4/4 pass):** `GET /status/<job_id>` carries `version_no` / `replaced` / `tour_title`
for a regenerated tour, is version 1 / not replaced for a brand-new tour, omits the
fields for a legacy job, and pins the `next_version + 1` arithmetic. Run via the Flask
`app.test_client()` against a mocked `ACTIVE_JOBS` entry; `py_compile` clean.

**Full `flutter test`: 714 passed, 6 failed.** The 6 failures are the pre-existing
baseline — all in `test/local109_swipe_e2e_test.dart` (`SocketException: Connection
refused`; they need a live server). Nothing new. `flutter analyze`: no errors; the three
new/util files report 0 issues; the remaining info/warning lints are pre-existing in the
large screen files.

## Live test (Android emulator only — `emulator-5554`, AVD `local715_test`)

Never installed on any phone (Michael's Pixel-4 and iPhone were connected the whole time
and never touched — only the emulator). Cloud mode is behind an app-attestation gate a
debug emulator build cannot satisfy ("Audioura couldn't connect securely"), so the APK
was rebuilt with `--dart-define=DEBUG_SERVER_IP=10.0.2.2` to use the **already-running
local Docker backend** via the emulator's host alias. No server was started, stopped,
renamed or `-p audioura`; the `audioura-*` containers were only read through the app. No
live-DB writes. The debug signing keystore (`android/app/debug.keystore`) was generated
locally and is **gitignored** (not committed). The emulator was shut down with
`adb -s emulator-5554 emu kill` when done.

Verified (screenshots in `submission_screens/`):

1. **`local717_search_dialog.png`** — the single search box with its examples, showing
   the tour-name `*` patterns.
2. **`local717_search_restaurant_star.png`** — searching **`restaurant*`** opens the
   found-tours dialog **"Select Tours (4 available)"** listing the restaurant tours. The
   map did **not** relocate to a far-away place called "Restaurant" — the D677 §3 bug is
   fixed. (`/search-tours?pattern=restaurant.*` on the local map-delivery returns those
   4 tours.)

## Files

- `audio_tour_app/lib/utils/search_dispatch.dart` — trailing-`*` → `tourNameOnly`;
  `resolveTextSearch` `nameOnly` + `noNamedTours`.
- `audio_tour_app/lib/screens/home_screen.dart` — name-only dispatch + "No tours named";
  batch download failure collection + logging.
- `audio_tour_app/lib/utils/downloaded_message.dart` — `downloadFailures`.
- `audio_tour_app/lib/services/tour_download_service.dart` — log resolve HTTP status+body.
- `audio_tour_app/lib/utils/generation_completion_message.dart` (new) — "Updated … now
  version N".
- `audio_tour_app/lib/screens/tour_generator_screen.dart` — use the completion helper.
- `tour_orchestrator_service.py` (**server change**) — `version_no` in `store_audio_tour`
  result; `version_no`/`replaced`/`tour_title` into `ACTIVE_JOBS` and `GET /status`.
- `audio_tour_app/pubspec.yaml` (+1 → `2.4.30+74`).
- `audio_tour_app/test/search_dispatch_test.dart`,
  `audio_tour_app/test/downloaded_message_and_listen_open_test.dart`,
  `audio_tour_app/test/generation_completion_message_test.dart` (new),
  `tests/test_local717_job_status_version.py` (new).
- `submission_screens/local717_search_restaurant_star.png`,
  `submission_screens/local717_search_dialog.png` (live-test screenshots).

No changes to DECISIONS, CLAUDE, BACKLOG, WORK_QUEUE or `.continuous_dev`.
