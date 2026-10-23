# SUBMISSION — LOCAL-748: Community tours on the phone

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-748-community-tour-links`
**Base:** `subscribed` @ `7332bfb5` (verified: `git merge-base --is-ancestor 7332bfb5 HEAD` → exit 0)
**code_sha:** HEAD of `LOCAL-748-community-tour-links` at push (parent `7332bfb5`; this
commit is the branch tip — verify with `git rev-parse LOCAL-748-community-tour-links`).

---

## What Michael hit (2026-10-23, community 10 "Salem TV show funs", tours 716 & 733)

1. "On this phone ✓" was a dead label — it should be a **link that opens the tour**.
2. After **Download** on the community page the tour did not appear on Listen until the
   snackbar **View** was tapped — it should appear automatically.
3. **The organiser's edit never reached the member.** The community-page Download called
   `TourDownloadService.downloadAndSave(tourId)` with **no `sourceItem`**, so the saved
   record got no `community_id` / `version`. `CommunityToursSync._heldCommunityTourRecords`
   skips records without `community_id`, so LOCAL-746's refresh never saw the tour.
4. The community page's text could not be selected/copied.
5. **No announcement** on the member's phone when the organiser adds a tour.

---

## Changes (7 files, `lib` only)

| File | Change |
|---|---|
| `services/community_downloads.dart` | **New pure helpers** (unit-tested, no app): `communityTourSourceItem()`, `stampCommunityIdOnSavedRecords()`, `NewTourAnnouncement`, `newTourMessage()`, `planNewTourAnnouncements()`, `kAnnouncedNewTourIdsPrefKey`. |
| `services/communities_models.dart` | `CommunityInviteTourOption` gains `version` (default 1) + `updatedAt`, parsed in `fromJson`, so the page can pass them as `sourceItem`. |
| `screens/community_page_screen.dart` | (a) `_downloadCommunityTour` now passes `sourceItem` (community_id/version/updated_at) and **auto-offers the tour to Listen** on success; (b) `_maybeDownloadPendingTour` passes `sourceItem` with the community id; (c) `_load()` **stamps old records** via `stampCommunityIdOnSavedRecords`; (d) "On this phone" row is an `InkWell` (key `open_tour_<id>`) + `ListTile.onTap` that **opens the player** via `PendingListenOpen`; (e) body wrapped in **`SelectionArea`** (text selectable; buttons still work). |
| `services/community_tours_sync.dart` | New seams `fetchOwnedCommunityIds` + `onNewTourAnnouncement`; `run()` tracks `autoDownloadedIds` and calls `_announceNewTours()`, which uses the pure policy, emits one message per new tour, and records announced ids in prefs (once per tour, never for the user's own community). |
| `services/community_notifications.dart` | New `postNewTourAvailable()` — the quiet "New community tour" heads-up. |
| `services/community_background.dart` | Wires `onNewTourAnnouncement` for the Android background worker. |
| `main.dart` | Wires `onNewTourAnnouncement` on app start. |

`TourDownloadService.saveTourToMyTours` already reads `sourceItem['community_id' | 'version'
| 'updated_at']` (LOCAL-745) — **no change needed there**; the fix is feeding it the
sourceItem at the community-page call sites (the exact gap in the ticket).

**No server change.** The record's `community_id` is `c.id` (always known on the page), and
the held-tour refresh reads the live server version via `/tour-info`, so the fix is entirely
app-side. (`CommunityInviteTourOption.version` defaults to 1 when the listing omits it.)

---

## Red tests (fail on 7332bfb5, pass on this branch)

3 new files, **20 tests**, all passing on the branch:

- `test/community_downloads_local748_test.dart` (14) — the pure helpers:
  `communityTourSourceItem`, `stampCommunityIdOnSavedRecords` (stamps bare records; leaves
  already-stamped / foreign / versioned records alone), `newTourMessage`,
  `planNewTourAnnouncements` (announce once; never for an owned community).
- `test/community_sync_announce_local748_test.dart` (4) — the sync shell: a new tour the
  member does **not** own → one "New tour in …" message; a tour in a community the member
  **owns** → no message; announced at most once across two runs; **stamp → RefreshPlanner
  re-download** end-to-end (a bare record is skipped; after stamping, the same run
  re-downloads it when the server version rose).
- `test/community_page_local748_test.dart` (2) — a widget test proving the `open_tour_716`
  row fires `PendingListenOpen('716')` ("On this phone" is a link), and a service test
  driving the **real** `TourDownloadService.downloadAndSave(716, sourceItem: …)` and reading
  the saved record back → `community_id == 10`, `version == 2` (on 7332bfb5 these were
  absent).

### Red proof
With the 7 `lib` changes stashed (tests kept), `flutter test` on the three new files fails
to compile — `Error: Method not found: 'communityTourSourceItem'` etc. — i.e. RED. Restoring
`lib` makes all 20 pass.

### Full suite
`flutter test` → **941 passed, 7 failed**. All 7 failures are in
`test/local109_swipe_e2e_test.dart` (`SocketException: Connection refused` to `localhost` —
they need a live backend). These are the **documented 7 pre-existing baseline failures**; no
new failures introduced.

### Analyze
`flutter analyze` on the 10 touched files → only **pre-existing** issues (unused import at
`main.dart:3`, `avoid_print` in `main.dart`, deprecated `Radio` at
`community_page_screen.dart:1412-1413` inside the untouched `_ReportToAudiouraSheet`). **No
new issues in any touched region.**

---

## Live test (iOS simulator only — Michael's phone never touched)

- Target: **iOS simulator iPhone 17** (`76941285-…`). The physical "Mikhail Glik's iPhone"
  is connected but was **never** installed to / touched (LEAD owns device installs).
- `flutter build ios --simulator --debug` → **Xcode build done, `Runner.app` built** (the
  whole app compiles & links with the changes).
- Installed + launched on the simulator (pid 42386), boots clean to the onboarding screen,
  **no crash**. Screenshot: `/tmp/local748_shots/01_launch.png`.
- Simulator shut down afterwards. Build-generated `ios/Podfile.lock` reverted (not committed).

**Full server-backed end-to-end deferred to the LEAD field-test gate.** Driving the complete
flow (seed community 10 + tours 716/733, organiser edit → member reopen → "… updated by the
organiser"; new-tour announcement) needs a dedicated `-p local748` stack with its own
Postgres and the generation/edit pipeline. That exceeds the ≤ $0.20 budget and risks
colliding with the already-running shared `audioura-*` infra (and another agent's
`local747-edit`), which the ticket forbids touching. The exact code paths are instead proven
by the 20 automated tests above, including a real `downloadAndSave` round-trip and the
stamp→refresh integration.

### Row counts
No database tables were written by this work. The app-side change only writes the on-device
`saved_tours` SharedPreferences list (not a DB table). No `DELETE FROM audio_tours`, no
deletes of purchase-bearing rows (D690). No server/DB migration. → **No table row counts to
report (0 tables written).**

---

## Budget
≈ **$0.00**. Everything local: the iOS simulator and the Flutter toolchain on this Mac Mini,
and Docker already running from prior work. No cloud resources created or called.

## Process compliance
- Branched from `subscribed` @ `7332bfb5` (never from `origin/*`); ancestor check passes.
- Committed to `LOCAL-748-community-tour-links` with an explicit file list (never `git add -A`).
- Did not edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
  SUBSCRIBED_COMMUNICATION_01.MD, or `legal/`.
- Simulator shut down when done.
