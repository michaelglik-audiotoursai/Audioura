# SUBMISSION — LOCAL-716B: View after "tour + translation" opens the tour, in the language just downloaded

**Branch:** `LOCAL-716B-view-translation` (from `subscribed` = `b10556bd`)
**Agent:** Mac Mini Kiro
**App version:** `2.4.30+72` → `2.4.30+73`
**Base verified:** `git merge-base --is-ancestor b10556bd HEAD` exits 0.

## The bug (Michael, Pixel-4, 2.4.30+72)

He downloaded ONE tour with its Russian translation. The snackbar message was
right — "1 tour downloaded with 1 translation … is" — but **View** only showed
the Listen list and opened nothing.

The ticket guessed Home offered a `null` id because a translation added a second
id (`downloadedTourIds.length == 1` test). That part was already per-tour on this
base, so the id (the original's, 117 in my live run) WAS offered. The real cause
was downstream, and I confirmed it on the emulator by dumping `saved_tours`:

- The English original saves with `tour_id = "117"`.
- The Russian translation saves (via `TourTranslationHelper._saveTranslatedTour`)
  with `tour_id = server_tour_id = "437"` — its OWN translated row id — and
  `parent_tour_id = null` (the `/tour/<id>/resolve` endpoint was unavailable).

So **no stored field on the translation linked it to the offered id 117**.
`_consumePendingListenOpen` matched only `tour_id`/`server_tour_id`, found the
English original (or, with English deselected, nothing), and either opened the
wrong language or returned **silently**. Both the "open nothing" and the "open
English, not the language I just downloaded" failures come from this.

## Required behaviour, delivered

1. **Count tours, not files.** An original plus its translations is ONE tour for
   both the message (`downloadedMessage`, already correct) and View
   (`downloadedTourIds` holds one id per tour; the snackbar offers that single id
   or `null` for several).
2. **View, for exactly one tour, opens the language just downloaded:**
   - exactly one translation → that translation (Russian, here);
   - several translations → the one matching the listening language if present,
     else the first one downloaded (oldest `created`);
   - no translation → the original.
3. **Several tours → switch to Listen, scroll to and briefly highlight the newest**
   (~2 s amber flash). The newest is found by `created` timestamp, not by trusting
   "it's at the top" — though `_tours` IS newest-first (the saved list reversed,
   new entries appended), so it lands at the top too.
4. **No silent miss.** A miss is logged via `DebugLogHelper` (the offered id, the
   language, and every saved tour's ids) and falls back to the highlight path.
5. **Version +1:** `+72 → +73`.

## The fix

### 1. Link the translation to its parent — the real root cause
`lib/services/tour_translation_helper.dart`
- `downloadTranslatedVersions` already knows the parent's server id (`tourId`,
  117). I thread it into `_saveTranslatedTour` as `parentServerTourId` and stamp
  **`parent_server_tour_id`** onto the translation's saved record. This is the
  stable link from a translation back to the id the snackbar offers.
- Also stamp **`language`** (the target code, e.g. `ru`) on the translation —
  until now the language lived only in the directory name, so nothing could pick
  the right language copy. (`home_screen._saveTourToMyToursTranslated`, a dead
  legacy path, also gets `language` for consistency.)

### 2. A pure planner decides what View does
`lib/utils/view_after_download.dart` (new, dependency-free, fully unit-tested)
- `planViewAfterDownload(entries, downloadedTourCount, wantedServerId,
  listeningLanguage)` → `openEntry(index)` or `highlightNewest()`.
- `_belongsToTour` matches an entry on `server_tour_id`, `tour_id`, OR
  `parent_server_tour_id` — so both the original AND its translations tie to the
  one offered id.
- Rules: one translation → it; several → listening-language match, else oldest
  `created`; none → original; several tours / no id / no match → `highlightNewest`.
- `newestEntryIndex(entries)` picks the latest `created` for the highlight path.

### 3. The request carries the language
`lib/services/deep_link_service.dart`
- `PendingListenOpenRequest` gains `language` and `highlightNewest`.
- `offer(tourId, language, highlightNewest)` normalises a blank language to null
  and implies `highlightNewest` when there is no id.

### 4. Home offers the id + language, counting tours
`lib/screens/home_screen.dart`
- The bulk-download "View" offers `singleTourId` (one id per tour) and
  `viewLanguage` — the first non-English selected language (the translation the
  user chose), else the saved `listening_language`, else English — plus the
  highlight flag when several tours were downloaded.

### 5. My Tours consumes via the planner, logs misses, highlights
`lib/screens/my_tours_screen.dart`
- `_consumePendingListenOpen` runs the planner against the loaded `_tours`;
  `openEntry` opens that row's player (the same `_openTourPlayer` a tap uses);
  otherwise it logs the miss via `DebugLogHelper` and calls `_highlightNewestTour`.
- `_highlightNewestTour` scrolls the newest row into view and flashes it amber for
  ~2 s (`_highlightIndex` + `_highlightTimer`), cleared in a new `dispose()` that
  also disposes the scroll controller (now attached to the tours `ListView`).

## Tests

`test/view_after_download_test.dart` (new) — the planner goldens:
- one tour + 1 translation → opens the translation;
- one tour + original + 1 translation → opens the translation;
- one tour + 2 translations → opens the listening-language one;
- one tour + 2 translations, no language match → first downloaded (oldest);
- one tour, no translation → opens the original;
- **matcher:** a translation (own ids 1042, `parent_server_tour_id` 42) is found
  from the offered original id 42 — the Pixel-4 miss;
- several tours / no id / no match → `highlightNewest`;
- `newestEntryIndex`.

`test/downloaded_message_and_listen_open_test.dart` (extended):
- `offer` carries the language; blank → null; no id implies `highlightNewest`;
- a widget test proving a translation entry (own ids + `parent_server_tour_id`)
  opens its player from the offered ORIGINAL id;
- the miss case falls to the highlight path (and is consumed once).

Test fixtures use the **real** save shape verified on the emulator (translation's
own ids + `parent_server_tour_id`), not an assumed one.

**Full `flutter test`: `+693 -6`.** The 6 failures are all in
`test/local109_swipe_e2e_test.dart` (SocketException — the baseline live-server
suite). No other failures.

## Live test (Android emulator only)

Emulator `emulator-5554` only; **Michael's Pixel-4, Pixel-7 and iPhone were never
touched** — every command targeted `-s emulator-5554`, and the emulator was killed
with `adb -s emulator-5554 emu kill` when done. Built with the live gateway key
(`--dart-define=GATEWAY_API_KEY`, fingerprint `1b56f014a180`, from
`~/Audioura/build_secrets.env`). No server change.

Flow: selected English + Русский, checked one tour, Download.
- Server: original tour **243**, saved Russian translation **247**.
- Snackbar: **"1 tour downloaded with 1 translation and is now on your Listen
  page"** — ONE tour, correct agreement.
- Tapped **View** → the log shows
  `TOUR_PLAYER: Using mobile file URL: …/tours/__ru_247/index.html` and the
  **Russian player** rendered: title "Тур по ресторанам в Ньютоне, штат
  Массачусетс - экскурсия по музею", stops "Кафе G в Музее науки: Аудио 1" etc.

A first emulator run (tour 117 / translation 437) reproduced the ORIGINAL bug
(View opened the English copy); after adding `parent_server_tour_id` the second
run (243 / 247) opened Russian — direct before/after evidence on device.

## Notes
- `android/app/debug.keystore` was absent in this worktree (the debug signing
  config needs it); I copied the standard one from `~/.android/debug.keystore`
  (alias `androiddebugkey`). It is **git-ignored** and NOT committed.
- No change to DECISIONS, CLAUDE, BACKLOG, WORK_QUEUE or `.continuous_dev`.
- No server change.

## Files
- `lib/services/tour_translation_helper.dart` — `parent_server_tour_id` + `language`.
- `lib/utils/view_after_download.dart` — new pure planner/matcher.
- `lib/services/deep_link_service.dart` — request carries language + highlight.
- `lib/screens/home_screen.dart` — View offers id + language, counts tours.
- `lib/screens/my_tours_screen.dart` — planner consume, miss log, highlight path.
- `pubspec.yaml` — `2.4.30+72` → `2.4.30+73`.
- `test/view_after_download_test.dart` — new planner tests.
- `test/downloaded_message_and_listen_open_test.dart` — language/highlight + Pixel-4 open.
