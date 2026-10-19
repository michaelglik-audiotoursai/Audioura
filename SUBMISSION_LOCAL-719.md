# LOCAL-719 — View always opens a player (D677 addendum 1)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-719-view-consistent` (from `subscribed` = `1d3c419f`)
**Base verified:** `git merge-base --is-ancestor 1d3c419f HEAD` → exit 0.
**Version:** `2.4.30+74` → **`2.4.30+75`** (build +1).

## Why

Michael (2026-10-19): *"if we start playing when one tour with a translation is
downloaded, we should start playing when multiple tours are downloaded too, maybe the
first one; in any case the behaviour should be consistent."*

LOCAL-716B (D358) made the download snackbar's **View** open a player for a SINGLE
downloaded tour (picking the right language copy across the original and its
translations), but for SEVERAL tours it only switched to Listen and highlighted the
newest — it opened nothing. That is the inconsistency. D677 addendum 1 makes **View
ALWAYS open a player.**

## Build — what View does now

- **One tour** → that tour, in the language just downloaded (LOCAL-716B logic, unchanged).
- **Several tours** → the **FIRST tour in the order the user selected them**, in the
  language just downloaded. "First" is the first id in the ordered list the caller
  passes; the caller adds a tour's id only AFTER it saved, so a tour that **failed to
  download is absent** and the **first that succeeded** opens. The planner also skips an
  offered id that matches no saved entry, so a vanished save never strands View.
- The other tours of the batch are still highlighted (the existing ~2 s amber highlight)
  when the user returns to Listen — that is the caller's unchanged fallback path.

### One decision function, unit-tested

`audio_tour_app/lib/utils/view_after_download.dart` — `planViewAfterDownload` is the ONE
place that decides which copy View opens. It is dependency-free (no Flutter, no
SharedPreferences, no http), tested directly with plain maps.

- **Before:** `planViewAfterDownload({entries, downloadedTourCount, wantedServerId,
  listeningLanguage})` — returned `highlightNewest` whenever `downloadedTourCount != 1`.
- **After:** `planViewAfterDownload({entries, downloadedTourIds, listeningLanguage})` —
  walks `downloadedTourIds` (ordered by selection), opens the first id that has a saved
  entry via the unchanged language rule (`_planForTour`), and only returns
  `highlightNewest` when NO offered id matches any saved entry (or none were offered).

### Plumbing

- `deep_link_service.dart` — `PendingListenOpenRequest` now carries `tourIds`
  (ordered list); `tourId` is a getter returning the first (kept for the single-tour
  "Open"/"View" callers). New `offerBatch(tourIds, {language})`; `offer()` delegates to
  it, so the existing single-id call sites are untouched.
- `home_screen.dart` — the batch snackbar's View now calls
  `PendingListenOpen.instance.offerBatch(downloadedTourIds, language: viewLanguage)` —
  it always offers, never null.
- `my_tours_screen.dart` — `_consumePendingListenOpen` reads `req.tourIds` and calls the
  new planner signature; the no-silent-miss log now lists all offered ids.

### Fix found during the live test — the saved record needed `server_tour_id`

The first live run hit a **"View miss"**: the snackbar offers the NUMERIC server id
(`tour['id']` from the map listing, e.g. `1`), but a plain downloaded original's saved
record stored only `tour_id = <edit id>` (a non-numeric string like `2027698c`) and **no
`server_tour_id`**, so the matcher could tie nothing to the offered id and View fell back
to highlighting. Root cause was in the on-phone record contract, not the planner.

Fix: `TourDownloadService.saveTourToMyTours` now stamps
`'server_tour_id': tourId.toString()` on the record. This is the id the planner matches
on AND the numeric id the player keys `/unlock-state` on (LOCAL-677B), and it matches the
established `DownloadedTourMeta.resolveServerTourId` contract (`downloaded_tour_meta_test`
already expects `server_tour_id` on records). After the fix the match works and the
player opens.

## Tests

`audio_tour_app/test/view_after_download_test.dart` (rewritten for the new signature),
covering every required case:

- 1 tour; 1 tour + translation; 1 tour + two translations (listening-language, else first
  downloaded); 1 tour no translation.
- **3 tours → opens the first selected** (saved order ≠ selection order; the first id in
  the list opens).
- **3 tours where the first selected failed → opens the first that succeeded** (the failed
  tour's id is absent; also tolerates a stray offered id that matched nothing).
- Several tours, first selected had a translation → opens that tour in the language just
  downloaded.
- No ids / none match / all-blank → highlight newest.

`audio_tour_app/test/downloaded_message_and_listen_open_test.dart` — added `offerBatch`
tests (ordered ids, `tourId` = first, trimming/blank-dropping, empty → highlightNewest);
the existing real-widget `MyToursScreen._consumePendingListenOpen` tests still pass
through the new plumbing.

**Full `flutter test`: 721 passed, 6 failed.** The 6 are the pre-existing baseline — all
in `test/local109_swipe_e2e_test.dart` (`SocketException: Connection refused`; they need a
live server). Nothing new. `flutter analyze` on `view_after_download.dart` and
`deep_link_service.dart`: no issues; 0 errors in the edited screens (remaining lints are
pre-existing in those large files).

## Live test (Android emulator only — `emulator-5554`, AVD `local715_test`)

Never installed on any phone. Michael's Pixel-4 (`99251FFAZ002YY`) and iPhone were
connected the whole time and never touched — every `adb`/`install`/`input` command
targeted `-s emulator-5554`. The APK was built with
`--dart-define=DEBUG_SERVER_IP=10.0.2.2` to use the **already-running local Docker
backend** through the emulator's host alias (read-only: no container was started,
stopped, renamed, or written to; no live-DB writes). The debug signing keystore
(`android/app/debug.keystore`) was generated locally and is **gitignored** (not
committed). The emulator was shut down with `adb -s emulator-5554 emu kill` when done.

Steps: set GPS to Nice (`adb emu geo fix 7.270 43.695`); in-app Search `*Nice*` opened the
**"Select Tours"** dialog; selected **2** tours — first **Palais Lascaris, Nice (museum)**,
second a *Musée des arts asiatiques* translation; pressed **Download Selected (2)**.
Result: the first (Palais Lascaris) saved, the second failed its resolve (409) — so
`downloadedTourIds = ['1']`. Tapping **View** opened the **TOUR_PLAYER on "Palais Lascaris,
Nice, France - Museum Tour"** (the first selected that succeeded) with *"Auto-start command
executed"* and **no "View miss"** in the log — exactly D677 addendum 1 ("several → the
first that succeeded, in the language just downloaded").

Screenshots in `submission_screens/`:

1. **`local719_select_2_tours.png`** — the Select Tours dialog with 2 tours checked
   ("Download Selected (2)").
2. **`local719_batch_downloaded_snackbar_view.png`** — the post-download snackbar with the
   **View** button (and LOCAL-717's failure report for the one that failed).
3. **`local719_view_opened_first_tour_player.png`** — View opened the **first** tour's
   player ("Palais Lascaris … Museum Tour", audio stops, 0:00 / 1:53).

## Files

- `audio_tour_app/lib/utils/view_after_download.dart` — planner rewritten to always open
  the first offered id that has a saved entry (ordered selection; language rule unchanged).
- `audio_tour_app/lib/services/deep_link_service.dart` — `PendingListenOpenRequest.tourIds`
  (+`tourId` getter); `offerBatch`; `offer` delegates.
- `audio_tour_app/lib/screens/home_screen.dart` — batch snackbar View → `offerBatch`.
- `audio_tour_app/lib/screens/my_tours_screen.dart` — `_consumePendingListenOpen` uses the
  new planner signature + ordered ids.
- `audio_tour_app/lib/services/tour_download_service.dart` — stamp `server_tour_id` on the
  saved record (the live-test fix).
- `audio_tour_app/pubspec.yaml` — `2.4.30+74` → `2.4.30+75`.
- `audio_tour_app/test/view_after_download_test.dart`,
  `audio_tour_app/test/downloaded_message_and_listen_open_test.dart` — tests.
- `submission_screens/local719_*.png` — live-test screenshots.

No changes to DECISIONS, CLAUDE, BACKLOG, WORK_QUEUE or `.continuous_dev`.
