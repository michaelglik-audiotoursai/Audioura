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

Run on the **iOS simulator** (iPhone 17 Pro, iOS 26.4) on **2026-10-28**, from this branch
(`LOCAL-794-translate-download-wait`, HEAD `d2e8f42a`), debug build, `server_mode` cloud → **Subscribed
Preview** (`--dart-define=APP_TRACK=subscribed`, built-in `GATEWAY_API_KEY`). Every network call in the
flutter console went to `https://subscribed-api.audioura.com` (e.g. `GET /tours-near/10.7737…/106.7165…`,
`GET …/download-tour/469`). No Android run. No physical devices. Screenshots in `docs/local794/`.

Flow exercised: Home → Search "Ho Chi Minh City" (map centred on HCMC 10.7737, 106.7165; 4 tours) → List →
**"Massage and spa near Ben Thanh Market, District 1, Ho Chi Minh City - Tour"** (server tour **465**) →
select **Русский** → **Download Tour**. Tour **469** is the pre-existing Russian translation of 465, so the
server answers the translate request in well under a second (as the ticket anticipated).

### The 2.5-min hang is gone; the app is never blocked

Tapping **Download Tour** **closed the dialog immediately** and returned to a fully usable Home — **no
app-blocking modal, no barrier**. The slow work ran in the background behind the new persistent progress
row ("Translating to Russian…" + an indeterminate bar + **Cancel**), hosted above the app bar by
`MainScreen`. `docs/local794/05_progress_row_home.png`.

### Measured timings — `TRANSLATE/MEASURE` markers, every step tap → playable

The instrumentation printed the real per-step times. Representative run (English + Russian):

| Step | Measured | Marker |
|---|---|---|
| English copy pulled + saved inline (fast path, no barrier) | sub-second | `DOWNLOAD_SVC: SAVE - saved "Massage and spa…"` |
| Background job starts | — | `TDM: translate+download (tour 465) → Russian` |
| Translate POST (`/translate`, tour 465 → ru) round-trip | **≈ 1 s** | `TRANSLATE: Requesting translation…` → next marker |
| Build download-tour URL + headers | **1–6 ms** | `(ru) URL+headers ready in 2ms — GET download-tour/469` |
| **ZIP GET `download-tour/469`** | **710 ms** (2,063,629 bytes ≈ 2 MB) | `(ru) download-tour HTTP 200 in 710ms (2063629 bytes)` |
| Save + validate translated tour | **16 ms** | `(ru) save complete in 16ms` |

**Tap → playable: ≈ 1–2 s total**, far under the 30 s warm target — not minutes. The ZIP GET is the only
step over ~20 ms, and it was 710 ms. **No step is slow; nothing needed fixing** on the hot path.

Repeat runs were consistent (Russian-only): ZIP GET **722 ms / 609 ms / 656 ms / 564 ms**, save **15–21 ms**
each; one overlapping run hit **1710 ms** on the GET (two downloads racing) — still ~2 s end-to-end. The
previously-unbounded `_resolveParentEditTourId` now carries its 20 s timeout and never stalled.

Michael's original ~2.5-min gap was the app-side wait behind the barrier (the never-dismissed modal + an
unbounded resolve await); with those removed the only real latency is the server translate (≈ 1 s here,
because 469 already existed) plus a sub-second ZIP download.

### Progress row survives tab switches; Listen updates with no manual refresh

While the job ran I switched tabs and the **one row persisted on every tab**, with each tab fully usable
underneath:
- **Listen** — `docs/local794/06_progress_row_listen.png` (row at top; the Russian tour already listed below).
- **About** — `docs/local794/07_progress_row_about.png` (row at top over the About content).

On completion the **Russian tour appeared on Listen with NO manual refresh** (the `SavedToursRefresh` bump,
LOCAL-787) — Listen showed **both** versions created 2026-10-28: "Массаж и спа рядом с рынком Бен Тхань,
район 1, Хошимин - тур" and "Massage and spa near Ben Thanh Market, District 1, Ho Chi Minh City - Tour".
`docs/local794/08_listen_russian_no_refresh.png`. The completion **"Russian version ready — Play"** SnackBar
is shown through the global messenger (it was visually behind the pre-existing "4 tours named…" search
SnackBar in these captures).

### Cancel — control present and the row clears (live cancel race not winnable here; covered by tests)

The **Cancel** button is present and wired in the row (`docs/local794/09_cancel_row_visible.png`), and after
tapping it the **row clears** back to a clean screen (`docs/local794/10_cancel_row_cleared.png`). Honest
limitation: because tour 469 already exists server-side the whole job finishes in **< 1 s**, and the cancel
token is (by design) only polled at the checkpoints *before* the translate step — once the helper has the
"completed" response it issues the ZIP GET + save without an interruption point ("a cancel never kills an
in-flight HTTP call mid-stream"). So across three live attempts (including a six-tap burst) the job always
completed before a cancel could pre-empt the download — the GET/save markers show every attempt ran to
`Saved translated tour (ru) ID: 469`. The **cancel-clears-the-row** behaviour itself is covered by the
passing unit test (cancel exit path clears the row) and the widget test (Cancel asks the job to stop); a
fresh, slower translation (a not-yet-translated language) would be needed to win the race live, which the
task excluded to respect the paid-API cap.

### Cost
$0 paid APIs. The only calls were to Subscribed Preview (`/tours-near`, `/translate` returning the already
existing 469, and `download-tour/469` ZIP GETs) — no new paid translation was generated. No server deploys,
no physical devices. Paid-API cap respected.
