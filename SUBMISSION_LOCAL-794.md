# SUBMISSION — LOCAL-794: Download-in-another-language blocks the whole app for ~2.5 min and the spinner never ends

**Branch:** `LOCAL-794-translate-download-wait`
**Base:** subscribed (`7d0fdf4d`) — verified `git merge-base --is-ancestor 7d0fdf4d HEAD` exits 0.
**Found by:** Michael, iPhone TestFlight 83, 2026-10-27 ~19:45 ET: Home → tour 465 (Massage & spa near Ben Thanh) → download in Russian. "Takes way too long … about 3 minutes, and the spinning wheel does not let me go anywhere in the app." Addendum ~19:56: "It is still going" (>10 min). Addendum ~20:1x: after a force-quit the Russian tour WAS on Listen — so the download and save completed; the hang is in the UI after the save.

## The bug

`HomeScreen._downloadSingleTour` put up an **app-blocking modal** (`showDialog(barrierDismissible: false)`) for the whole download+translate, then a second blocking modal for the translation. That barrier is what "does not let me go anywhere in the app."

Two separate waits sat behind that barrier:

1. **The ~2.5-min gap** between the translate `200` (server: new tour 469 at 19:45:40) and the `download-tour/469` GET (19:48:10). The server needed ~17 s; ~150 s were spent inside the app.
2. **The never-ending spinner.** After a *successful* save the modal was never dismissed on some paths: the dialog was dismissed with `Navigator.of(context).pop()` using the **HomeScreen's own context**, so if that screen was gone (tab switch, rebuild) the `pop()` targeted a dead context and the barrier stayed up forever. Every `await` in the flow also lacked a timeout, and `_resolveParentEditTourId`'s `http.get` had **no timeout at all** (a cold tour-id-resolution start could stall the flow — a prime suspect for the 2.5-min gap).

## The fix

### 1. No app-blocking spinner — a background progress row instead

**New `lib/services/translate_download_manager.dart`:**
- `TranslateDownloadController` — a global singleton `ValueNotifier<TranslateDownloadJob?>` (the same plugin-free pattern as `PendingListenOpen` / `SavedToursRefresh`). `active == null` ⇒ the row is hidden. `start/setPhase/cancel/finish`.
- `TranslateDownloadManager.run(...)` — sequences the steps **off any screen's BuildContext**, so it cannot be orphaned when HomeScreen is disposed. It uses the global `communityScaffoldMessengerKey` for the completion SnackBar and `PendingListenOpen` for the "Play" action, exactly like the existing community-message path.

**New `lib/widgets/translate_download_progress_banner.dart`** — renders the current phase label + an indeterminate bar + **Cancel**. Hosted by **`MainScreen`** at the top of the body, **outside** the per-tab `IndexedStack` (like the bottom bar), so it shows one persistent row that **survives tab switches** while the user keeps using every tab.

**`home_screen.dart` `_downloadSingleTour` rewritten:** the English copy (small, fast — Michael's log: 0.33 s, 2 MB) is pulled **inline with no barrier dialog**, keeping its `402` pay / members-only gate (those need the screen context). The slow part (translate + per-language ZIP + save) is handed to `TranslateDownloadManager.instance.run(...)` via `unawaited(...)` and the method returns immediately — tabs stay usable.

### 2. A timeout on every await; every exit path clears the row

`TranslateDownloadManager` wraps the whole job in `jobTimeout` (6 min), bounds the previously-unbounded resolve step at `stepTimeout` (20 s), and keeps the existing `120 s` ZIP-GET and `5 min` translate-POST timeouts. The run body is in a `try { … } finally { ctrl.finish(); }`, so **success, per-language failure, a thrown step, a timeout and a cancel all clear the row exactly once** — the barrier can never be left up again.

### 3. Start the ZIP download immediately after a completed translate (no timer/poll)

`TourTranslationHelper.downloadTranslatedVersions` already issues the `download-tour` GET the instant the translate response says `completed` (no timer, no poll). The manager calls it straight after the resolve step. The unit test pins the order `resolve → translate(download-tour)`.

### 4. Listen updates with no manual refresh + a "Play" SnackBar

Every save goes through `SavedToursStore.save`, which bumps `SavedToursRefresh` (LOCAL-787) — `MyToursScreen` listens and reloads itself. On completion the manager shows **"Russian version ready — Play"** (English-only: **"Tour downloaded — Play"**) with a Play action that opens the tour on Listen.

### 5. Measurement instrumentation (to confirm the real cause on a live run)

`tour_translation_helper.dart` now logs timestamped `TRANSLATE/MEASURE` markers around the `download-tour` URL build, `apiHeaders`, the ZIP GET (ms + bytes) and `_saveTranslatedTour` (ms), so a live sim/emulator run prints exactly which await consumes time. `DebugLogHelper` is capped at 75 lines (checked — it is not itself the gap).

## Files changed

- **NEW** `lib/services/translate_download_manager.dart` — background manager + global progress controller.
- **NEW** `lib/widgets/translate_download_progress_banner.dart` — the app-wide progress row.
- `lib/screens/main_screen.dart` — hosts the banner above the tab stack.
- `lib/screens/home_screen.dart` — `_downloadSingleTour` rewritten (no modal; background translate).
- `lib/services/tour_translation_helper.dart` — timeouts preserved + `TRANSLATE/MEASURE` instrumentation.
- **NEW** `test/translate_download_manager_local794_test.dart` — unit tests.
- **NEW** `test/translate_download_background_local794_test.dart` — widget tests.

## Tests

**Unit (`translate_download_manager_local794_test.dart`, 7 tests, all pass):**
- success: `resolve → translate` order (download-tour issued immediately after translate completes), row cleared, "Russian version ready" told;
- English-only: no translate call, "Tour downloaded", row cleared;
- per-language failure, thrown-step **error**, and **cancel** each clear the row;
- a second job is refused while one is active (one row, one translate POST);
- phase transitions `translating → savingTranslations`.

**Widget (`translate_download_background_local794_test.dart`, 5 tests, all pass):**
- no job ⇒ no row;
- while a job runs: the row shows, **no `ModalBarrier` blocks the app**, the **tab bar is usable** (tap Listen → index changes), and the **row survives the tab switch**;
- `finish()` removes the row (no stuck spinner);
- Cancel asks the job to stop;
- a completion bump reaches the Listen tab so it reloads without a manual refresh.

**Full `flutter test`:** 8 failures, **identical to the clean baseline** (6 live-server `local109_swipe_e2e` + `storied_compat_guard` + `storied_compat_screens_404`, all pre-existing environment tests). **No new failures, no regressions** (verified by diffing the failure set against a `git stash -u` clean-tree run). `flutter analyze` on the changed files reports no new errors/warnings (only pre-existing `info` lints).

## Live test

Not run here (no simulator/emulator session in this environment). The instrumentation above is in place so the simulator + emulator run against Subscribed Preview can confirm the real cause of the 2.5-min gap and verify tap-to-playable ≤ 30 s with the progress row visible while switching tabs. Paid-API cap $0.50 respected (no live paid calls made).
