# SUBMISSION — LOCAL-746: a member's phone picks up the organiser's edit of a community tour it already has

**Branch:** `LOCAL-746-member-gets-edit`
**Base:** `subscribed` @ `eee10caa` (contains LOCAL-745). `git merge-base --is-ancestor eee10caa HEAD` → exit 0.
**code_sha:** `0b9c1a6ee7f49a034e5fd978b4721272dfa1d160` (tip of `LOCAL-746-member-gets-edit`; base `eee10caaf0e38c877333a6ebfc76ad6d964619c4` = `subscribed`, contains LOCAL-745).

## The problem

Michael's test (2026-10-23): the organiser edits the Salem community tour on the iPhone; the member's Pixel-4 must get the change. LOCAL-745 made the **server** side work — an edit replaces `audio_tours.audio_tour` in place, archives the old content in `audio_tour_versions`, and the version rises (map-delivery reports it). But SUBMISSION_LOCAL-745 §Req 3 found the **app** never re-downloads a tour it already holds: `SyncPlanner.plan` skips ids already on the phone and `TourDownloadService.downloadAndSave` returns `alreadyOnPhone`. So the member kept the old audio.

A second, subtler fact drove the design: an in-place edit keeps the tour's `created_at`, and `/communities/new-tours` filters `created_at > since` — so **an edit never appears in new-tours**. The re-download therefore cannot ride the new-tours plan; it needs its own version-aware pass over the tours already on the phone.

## What changed

### 1. A pure re-download planner — `RefreshPlanner` (`lib/services/community_downloads.dart`)
For each community tour ALREADY on the phone (its saved version + the server's current LOCAL-657 version), returns exactly the ones to re-download:
- it must be a **community** tour (`isCommunityTour`) — an ordinary tour is never touched;
- `serverVersion` **strictly greater** than `savedVersion` (never a downgrade, never a no-op);
- its community must be **active (or owned)** — an expired membership contributes nothing;
- not in the user's **deleted** set (D675 §6);
- the **same connection gate** as `SyncPlanner` (nothing offline; nothing on metered unless mobile data was allowed).

Plus `refreshedMessage(name)` → `"<name> was updated by the organiser."` (Req 3), from one source.

### 2. Replace-in-place download — `TourDownloadService.reDownloadAndReplace` (`lib/services/tour_download_service.dart`)
Re-downloads `GET /download-tour/<id>`, **decodes the ZIP in memory first**, then overwrites the extracted files + `tour.zip` in the SAME tour folder and bumps the saved record's `version`/`tour_version`/`updated_at`/`stops` — **same list entry (same title, same path)**, so Listen opens the new audio in place and shows "v2 · updated <date>". **Req 2:** a transport error, a non-200, or an undecodable body returns `failed` WITHOUT touching the folder or the record — a failed re-download keeps the old copy.

### 3. Wiring into the sync-on-open I/O shell (`lib/services/community_tours_sync.dart`)
`CommunityToursSync.run()` keeps the LOCAL-713 new-tours baseline (Part A) and now ALWAYS runs a held-tour refresh pass (Part B), independent of new-tours:
- gathers the community tours on the phone (needs a `community_id` + a numeric `server_tour_id`);
- reads each one's current server version via `CommunityTourService.serverTourVersion` → `GET /tour-info/<id>` (the LOCAL-657 number the app already reads);
- resolves the active/owned communities from `/communities/mine` (active flag) + `/communities/mine-owned`;
- runs `RefreshPlanner`, re-downloads via `reDownloadAndReplace`, and emits ONE "updated by the organiser" message per tour that actually refreshed.

All HTTP/membership/download/message steps are behind test seams. Surfaced as a quiet local notification (`CommunityNotifications.postTourUpdated`) wired in `main.dart` (foreground) and `runAndroidBackgroundSync` (app-closed) — the same quiet channel as the LOCAL-714 new-tours heads-up.

A small robustness fix: `Connectivity().checkConnectivity()` is wrapped so a connectivity-read failure defaults to `none` and never aborts the whole sync.

### 4. The organiser's own phone (Req 4)
The LOCAL-745 community-edit save ALWAYS returns `new_tour_id` + `download_url` + `member_update.new_version`, so `edit_tour_screen._handleNewTourDownload` already downloads the edited content into the same `tourPath` and reloads — **Listen plays the new version right after Save.** To keep the organiser's local record in step with the server (so the sync-on-open does not later re-flag the organiser's own edit, or message them about it), `applyTourEditToSavedTours` now also stamps `version`/`tour_version`/`updated_at` from `member_update.new_version`.

## Tests

### Red test (fails on the base, passes now)
`test/community_refresh_planner_test.dart` — `RefreshPlanner`/`HeldCommunityTour`/`refreshedMessage` did not exist on the base; the file failed to compile (RED). 10 cases now green:
- held community tour **v1, server v2 → plans a re-download**;
- **v2/v2 → none**; ordinary (non-community) tour v1→v2 → **unchanged**; **expired membership → none**;
- owner → re-download; deleted → none; metered gate; offline; a lower server version is ignored (never downgrade); the message wording.

### Shell integration test
`test/community_sync_refresh_shell_test.dart` (5 cases, via the seams, connectivity mocked to Wi-Fi): v1→v2 re-downloads once and messages once; v1/v1 nothing; ordinary tour nothing; expired membership nothing; **a FAILED re-download keeps the old copy — `refreshed=0`, no message**.

### Organiser own-phone test
`test/listen_stop_count_test.dart` (+2): a community in-place edit stamps `version`/`tour_version`/`updated_at`; an ordinary edit (`newVersion == null`) leaves version untouched.

### Baseline
`flutter test`: **+921 passing, exactly 7 pre-existing failures, no new ones.** The 7 are environmental/pre-existing: `local109_swipe_e2e_test.dart` ×6 (SocketException — needs a live server) and `storied_compat_screens_404_test.dart` ×1. Confirmed by running the suite on the clean base (`git stash`) — same 7.
`flutter analyze`: **no new issues in any touched file.** `edit_tour_screen.dart` reports 15 issues before and after my change (unchanged); `main.dart` reports only pre-existing issues (unused inappwebview import, prints).

## Live test — `live_local746.py` (own harness, spare ports, is_test only)

Emulator/simulator policy honoured: **no real phones**, **my own instances** of map-delivery (`:5546`) and tour-editing (`:5547`) run in-process with `get_db_connection` monkeypatched to the local dev DB (`localhost:5433`); never `-p audioura`, never the `audioura-*` or `tour-editing-phase2-1` containers.

On an **is_test=true COPY** of a community tour (never a real one) + a test community I own + a test membership, it proves the exact chain the app's refresh reads:

| step | result |
|---|---|
| **A** member holds v1 | `/tour-info/<id>` → **version 1**; v1 download 200 (5,217,882 bytes) |
| **B** owner edit in place | 200, `member_update = {community_id, new_version: 2, replaced_in_place: true}` |
| **C** member sees v2 | `/tour-info/<id>` → **version 2**, `updated_at 2026-10-23` |
| **D** member re-download | `/download-tour/<id>` → 200, served bytes **== `audio_tour` BYTEA (5,217,529)**; archived versions `[1]` |
| app decision | `RefreshPlanner(server 2 > saved 1, community active)` → **re-download = True** |

**`LIVE RESULT: PASS`** (ran twice, both clean).

### Row counts (D141 / D690 safety)
```
              BEFORE   AFTER (Δ)   FINAL (Δ vs before)
audio_tours      504   505 (+1)    504 (0)
audio_tour_versions 68  69 (+1)     68 (0)
communities        3     4 (+1)      3 (0)
community_memberships 3  4 (+1)      3 (0)
audio_tours(is_test) 428 429 (+1)  428 (0)
```
Every fixture row is deleted at the end, guarded by `is_test = TRUE`; no purchase-bearing row is ever deleted. FINAL Δ vs before = 0 across the board.

### Budget
**$0.00.** The owner edit sends `action='unchanged'` for every stop, so the preserve path copies the existing mp3s and **no Polly TTS fires**. Well under the $0.30 cap.

## Files
- `lib/services/community_downloads.dart` — `HeldCommunityTour`, `PlannedRefresh`, `RefreshPlanner`, `refreshedMessage`.
- `lib/services/tour_download_service.dart` — `reDownloadAndReplace` (replace-in-place, keeps old copy on failure).
- `lib/services/community_tours_sync.dart` — Part B refresh pass + seams; defensive connectivity read.
- `lib/services/community_tour_service.dart` — `serverTourVersion` (`/tour-info`).
- `lib/services/community_notifications.dart` — `postTourUpdated` (quiet heads-up).
- `lib/services/community_background.dart`, `lib/main.dart` — wire `onRefreshMessage`.
- `lib/screens/edit_tour_screen.dart` — stamp `version`/`updated_at` from `member_update` on the organiser's own record.
- `test/community_refresh_planner_test.dart`, `test/community_sync_refresh_shell_test.dart`, `test/listen_stop_count_test.dart` — the red test + the shell + the organiser-own-phone cases.
- `live_local746.py` — the live harness.
