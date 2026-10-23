# SUBMISSION — LOCAL-750: Community retest round 3

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-750-community-round3`
**Base:** `subscribed` @ `ed8fe7ac` (verified `git merge-base --is-ancestor ed8fe7ac HEAD` → 0)
**code_sha (base):** `ed8fe7acf22d304419604bb0d0352fd27fc15264`
**Cost:** **$0.00** (no TTS/LLM/DB calls; live proof was file-based rendering)

Michael's retest (2026-10-23 17:10–17:45; community 10, iPhone = organiser USER-41659366,
Pixel-4 = member USER-281301397) surfaced three defects. All three are fixed, each behind a
red→green test that fails on `ed8fe7ac` and passes after.

---

## A. Second edit of a re-downloaded community tour saved to the wrong id (404)

**Was:** `edit_tour_screen.dart` derived the backend id from the LAST PATH SEGMENT of
`tourData['path']` — UUID-in-folder, else a numeric folder tail, else the **whole folder name**.
A tour re-downloaded from the community page has folder `<safeName>_<editTourId>` whose tail
(`13ed30d1`) is neither a UUID nor numeric, so the save POSTed the folder name →
`POST /tour/the_episode_1_…_13ed30d1/update-multiple-stops 404` (×3).

**Fix:** a top-level pure function `deriveBackendTourId(tourData)`:
- a **community tour** (`community_id` present) → prefer the record's numeric `server_tour_id`
  outright (the server edits community tours in place by numeric id, LOCAL-745);
- otherwise keep a path-derived **UUID** or **numeric** id;
- otherwise fall back to `server_tour_id`;
- otherwise return `null` and the save aborts with a clear message — **it never POSTs a folder
  name**.

`_saveAllChanges` now calls it; the dead `_extractTourId` helper was removed.

**Files:** `audio_tour_app/lib/screens/edit_tour_screen.dart`

**Red test:** `audio_tour_app/test/local750_backend_tour_id_test.dart` (6 cases). The marquee
case is Michael's record (path `…_13ed30d1`, `server_tour_id: "716"`, `community_id: 10`) →
`deriveBackendTourId` returns `"716"`, so the request goes to `/tour/716/…`. Red on base because
`deriveBackendTourId` does not exist there.

---

## B. An edited tour's page now looks exactly like a generated one

**Was:** the generator (`tour_generation_modernized.generate_html_with_external_audio`) and the
editor (`tour_editing_phase2.create_clean_html`) each wrote their **own** per-stop markup, page
header and CSS, so they drifted: the editor put the map sign at the **end** of the title, dropped
the **"Audio N"** suffix, and used a generic `<h1>Audio Tour</h1>`.

**Fix:** the per-stop block, the page header and the page CSS now live **once** in
`tour_html_map.py` and **both** services call it:
- `build_stop_block(stop_num, text, cat)` → `<div class="audio-item"><h3>{first line}: Audio N</h3>`
  then the **map button (right after the `<h3>`)** then `<audio id="audio-{N-1}">`;
- `build_page_header(tour_name)` → `<h1>{tour name}</h1>` (title-cased);
- `PAGE_CSS` + `SHARED_VOICE_CONTROL_SCRIPT` (binds via `querySelectorAll('audio')`, so it is
  id-scheme agnostic and the edited page's voice control keeps working);
- `build_tour_page_html(tour_name, stops, cat)` renders the whole page; the editor passes the
  real (renumbered) stop numbers so `audio_<n>.mp3` / `openMap(<n>)` stay correct.

`create_clean_html(tour_path, final_stops, tour_name=None)` keeps its old 2-arg signature
(derives the name from the folder when omitted) so LOCAL-747 stays green.
`Dockerfile.modernized` already copies `tour_html_map.py`; the edit service already imported that
module at base, so no Dockerfile change is needed.

**Files:** `tour_html_map.py`, `tour_generation_modernized.py`, `tour_editing_phase2.py`

**Red test:** `tests/test_local750_edited_page_matches_generated.py` (16 checks): `: Audio N` in
every stop name, the map button before the `<audio>`, `<h1>` = the tour name, and the edited and
generated **stop blocks are byte-for-byte identical** for the same 3 stops. Red on base (the
editor had no `tour_name` kwarg and wrote `stop-item` markup with no `: Audio N`). LOCAL-747's
`tests/test_local747_edit_save_html_and_download.py` stays green (9/9).

**Screenshots (live proof, see below):** `docs/local750/generated_page.png` and
`docs/local750/edited_page.png` are **pixel-identical** (same SHA).

---

## C. Members now SEE the messages, and new tours arrive without restarting

**Was:** a new/updated community tour produced **only** a silent, low-importance system
notification (channel `community_new_tours`, `Importance.low`) — nothing popped up, nothing
showed in the app. And the sync ran only on app start/resume, so a tour created while Michael
stayed in the app (735) was never fetched.

**Fix:**
1. **In-app messages (foreground).** New `foreground_community_messages.dart`:
   a global `communityScaffoldMessengerKey` (wired onto `MaterialApp`), a pure routing policy
   `CommunityMessageRouter.target(isForeground)` → in-app vs system, and `routeCommunityMessage`
   which shows an in-app **SnackBar with a "View" action** (reusing `PendingListenOpen`) when the
   app is foreground, and falls back to the quiet **system notification** when backgrounded (or if
   no messenger is mounted yet — the message is never dropped). `main.dart` wires the
   `onRefreshMessage` / `onNewTourAnnouncement` seams through it; a "View" is offered for an
   updated tour (already on phone) and for a new tour only when it was auto-downloaded.
2. **Proactive sync.** `AppSyncCoordinator` now runs the community sync every **5 minutes while
   foreground** (`foregroundSyncInterval`, gated by the pure `shouldRunForegroundTick`), stops the
   timer on pause, and exposes `syncNow()`. The Communities **hub** (`initState`) and a
   **community page** (`initState`, via the injectable `onOpenSync` seam) both call it. Overlap is
   impossible: `CommunityToursSync.run` already self-guards (`_running`).
3. **Listen refresh.** New `saved_tours_refresh.dart` (`SavedToursRefresh.tick`); the sync fires a
   new `onToursChanged` seam when it downloaded/refreshed anything, `main.dart` bumps the notifier,
   and `my_tours_screen.dart` listens and reloads — so a synced tour appears **without leaving the
   Listen page**.

**Files:** `audio_tour_app/lib/services/foreground_community_messages.dart` (new),
`audio_tour_app/lib/services/saved_tours_refresh.dart` (new),
`audio_tour_app/lib/services/app_sync_coordinator.dart`,
`audio_tour_app/lib/services/community_tours_sync.dart`,
`audio_tour_app/lib/services/community_background.dart`,
`audio_tour_app/lib/main.dart`,
`audio_tour_app/lib/screens/communities_hub_screen.dart`,
`audio_tour_app/lib/screens/community_page_screen.dart`,
`audio_tour_app/lib/screens/my_tours_screen.dart`.

**Red tests:**
- `audio_tour_app/test/local750_foreground_message_test.dart` (6): foreground → in-app SnackBar
  with a working **View** that opens the tour; background → system notification; no-messenger →
  fallback; no-id → no View.
- `audio_tour_app/test/local750_community_open_sync_test.dart` (1): opening a community page
  triggers exactly one sync.
- `audio_tour_app/test/local750_foreground_timer_test.dart` (5): the tick runs only in the
  foreground, the interval is 5 minutes, and a second `run()` while one is in flight is a no-op.

The `onRefreshMessage` seam gained an optional `{int? tourId}` (so the in-app View can open the
refreshed tour); the two existing tests that stub it were updated to the new signature and stay
green.

---

## D. Kept (no regression)

"On this phone" opens the tour, selectable community-page text, 🚲 for biking, auto-update of an
edited tour, organiser-only Edit — all untouched. Verified by the unchanged, still-green
`community_*` tests and the preserved `canEditTour` gate.

---

## Verification

- **Edit-service (Python):** `tests/test_local747_edit_save_html_and_download.py` → **9/9**;
  `tests/test_local750_edited_page_matches_generated.py` → **16/16**. `py_compile` OK on all three
  touched modules.
- **B red proven at base:** reverting the three prod `.py` files to `ed8fe7ac` makes the B test
  fail (`TypeError: create_clean_html() got an unexpected keyword argument 'tour_name'`); restored.
- **`flutter analyze`:** no new errors/warnings in touched files (the only 3 warnings
  — unused `flutter_inappwebview`/`path_provider` imports and `_originalStops` — pre-exist on
  `ed8fe7ac`, confirmed via `git stash`). New files are analysis-clean. Total issues 1382 (branch)
  vs 1396 (base) — fewer (removed dead `_extractTourId`).
- **`flutter test` baseline:** **958 passed, 7 failed**. All 7 failures are
  `local109_swipe_e2e_test.dart` (`SocketException: Connection refused` — requires a live server),
  the documented known baseline. **No new failures.** The 15 new Dart tests pass.

## Live test (B visual proof) — $0, zero shared-state impact

Ran the **real** production functions `generate_html_with_external_audio` and `create_clean_html`
for the same 3-stop biking tour (`Harbor Bike Loop`, folder `harbor_bike_loop_13ed30d1` mimicking
Michael's re-downloaded folder). Heavy deps were mocked only to import the edit module (same as the
tests). **No TTS/LLM calls, no database, no containers touched, nothing written to
`/Users/micha/Audioura/tours`** — all output went to a temp dir, screenshots copied to
`docs/local750/`.

- `generated.html` and `edited.html` are **100% byte-identical** (`diff` empty; both 6364 bytes).
- Rendered both with headless Chrome at 390×900 → `generated_page.png` and `edited_page.png` are
  **pixel-identical** (same SHA `f75edaf2…`). The screenshot shows `<h1>` = *Harbor Bike Loop*,
  stop names `Stop N: Historic Place N: Audio N`, and the 🚲 button right after each title.

A/C are pure-logic fixes proven by unit tests. No iOS simulator was booted and the only connected
device is **Michael's iPhone (installing there is forbidden)**, so no on-device A/C run was
performed; a full live edit-service/DB run was deliberately avoided (it would cost money and write
shared rows).

### Containers / row counts

- The 14 running `audioura-*` containers and `tour-editing-phase2-1` were left **running and
  untouched**; **no container was created, renamed, or replaced**; no `-p audioura` port was used.
- My live proof wrote **no database tables** (file-based only). Therefore **every table's row
  count is unchanged** before/after (nothing was inserted, updated, or deleted). No
  `DELETE FROM audio_tours`, no deletes of purchase-bearing rows.

## Process

Committed only the touched/created files listed above to `LOCAL-750-community-round3` (no
`git add -A`). Did not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE`,
`.continuous_dev/`, `SUBSCRIBED_COMMUNICATION_01.MD`, or `legal/`.
