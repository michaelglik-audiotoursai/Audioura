# SUBMISSION — LOCAL-745: Community tour edit "Save failed" (404) + organiser-only edit + members get the edit

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-745-community-tour-edit`
**Base:** subscribed @ `3e2e7d849e247236d77044d089c976e28c9cc8dd` (verified `git merge-base --is-ancestor 3e2e7d84 HEAD` → 0)
**code_sha:** the single commit on this branch above base 3e2e7d84 (`git rev-parse LOCAL-745-community-tour-edit`)

---

## Summary

Michael (iPhone, 2026-10-23) edited stops 1 & 4 of community tour 716 ("Salem TV
show funs", community 10, owner USER-41659366) and got **"Save failed"**. The
server answered `POST /tour/716/update-multiple-stops` → **404 TOUR_NOT_FOUND**.

Root cause (confirmed): in volume mode `tour_editing_phase2.resolve_tour_to_directory('716')`
returns `None`. `/app/tours` holds only the tour's ZIP
(`audio_tours.zip_filename`), no extracted directory, and the numeric-id path
only matched a few hard-coded keyword directories (harvard/mfa/library). Every
recent tour that lives only as a ZIP was uneditable.

Four things are fixed (server `tour_editing_phase2.py` + Flutter app):

1. **Save works on a ZIP-only tour** — volume mode now resolves via
   `audio_tours.zip_filename` and extracts the ZIP to a work directory; the
   saved result is what download/Listen serve next.
2. **Only the organiser may edit a community tour** — server refuses 403 unless
   the editor owns the community; the app hides Edit for members.
3. **Members get the edit** — an organiser's edit of a community tour is written
   **back onto that community tour row in place**, archiving the old version and
   bumping `version_no`, so the member-facing download + version path (LOCAL-657)
   serves the new content. (Honest member-visibility detail below.)
4. **Real error message** — the app shows the server's `message` instead of
   "Exception: Save Failed".

---

## Files changed

Server:
- `tour_editing_phase2.py`

App:
- `audio_tour_app/lib/screens/my_tours_screen.dart`
- `audio_tour_app/lib/services/tour_editing_service.dart`
- `audio_tour_app/lib/services/tour_download_service.dart`

Tests + live harness (new):
- `tests/test_local745_zip_only_resolve.py`
- `tests/test_local745_organiser_only.py`
- `tests/test_local745_member_update.py`
- `audio_tour_app/test/local745_edit_gate_test.dart`
- `audio_tour_app/test/local745_error_message_test.dart`
- `live_local745.py` (is_test-safe live evidence harness)

No `git add -A`; only the files above were committed. DECISIONS.md, CLAUDE.md,
BACKLOG.md, WORK_QUEUE, `.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD and
`legal/` were not touched.

---

## Requirement 1 — Save works (404 → 200)

`tour_editing_phase2.py`:
- `_zip_filename_for_tour(tour_identifier)` — reads `audio_tours.zip_filename`
  for a numeric id (and maps an edited UUID back to its source via
  `tour_edit_blobs` first). Never raises.
- `_extract_zip_only_tour_to_workdir(tour_identifier)` — the volume-mode sibling
  of the cloud `_resolve_tour_from_db`: extracts that ZIP from `/app/tours` into
  `/app/tours/<stem>_work` (idempotent — rebuilt only when the ZIP is newer or
  the previous extraction is empty). The 716 ZIP is flat
  (`audio_1.txt`…`audio_4.txt`, `audio_*.mp3`, `index.html`, `manifest.json`),
  exactly the layout the bulk-save reader (`tour_path.glob("audio_*.txt")`)
  expects.
- `resolve_tour_to_directory` volume branch now falls back to that extraction
  when neither an exact path nor a keyword directory matches (both for a numeric
  id and, as a last resort, for an edited UUID). The new tour directory + ZIP
  are written into `/app/tours`, so the existing download resolver finds them —
  the saved result IS what download/Listen serve next.

## Requirement 2 — Only the organiser edits a community tour

Server (`tour_editing_phase2._community_edit_block(cur, tour_id, user_id)`,
reusing `community_tours_service.community_tour_tag` + `community_owner`), wired
into `_bulk_save_core` **before** any metering/build:
- ordinary tour (no `community_id`) → allowed (today's rule, unchanged);
- community tour + caller is `communities.owner_user_id` → allowed;
- community tour + different user → **403 `NOT_COMMUNITY_OWNER`**;
- community tour + no user id in the body → **401 `USER_ID_REQUIRED`** (fails
  closed — a community tour is never editable anonymously).

App (`my_tours_screen.dart`): pure `canEditTour(tour, ownedCommunityIds)` hides
the Edit menu item on a community tour unless the device owns that community
(`CommunityTourService.ownedCommunities`). `tour_download_service.dart` now
stamps `community_id` onto the saved-tour record so the gate can see it. The
server remains the source of truth (403); the app just hides a control that
would only fail.

## Requirement 3 — Members get the edit (what the member sees, and when)

Design of the existing paths (verified):
- `/communities/new-tours` returns community originals created after the last
  `since`; the app's `SyncPlanner.plan` **skips tour ids already on the phone**.
  So a brand-new, untagged edit tour would never reach members, and an in-place
  edit (same id) isn't re-delivered by new-tours either.
- The member-facing update channel is the **version path** (LOCAL-606/657):
  map-delivery `/download-tour/<id>` serves `audio_tours.audio_tour`, and the
  version the app shows is `MAX(audio_tour_versions.version_no)+1`.

Fix (`tour_editing_phase2._replace_community_tour_in_place` + wiring in
`_bulk_save_core`): when the edited tour is a **community** tour (numeric id with
`community_id`; ownership already proven by the req-2 gate), after the new ZIP is
built the server:
1. archives the current row content into `audio_tour_versions` as the next
   per-tour `version_no` (append-only, reversible; self-heals the archive
   table/columns/constraint additively like the orchestrator);
2. overwrites `audio_tours.audio_tour` (the BYTEA map-delivery serves), plus
   `zip_filename` and `stops_count`.

The response carries `member_update: {community_id, replaced_in_place, new_version}`.
This is best-effort: a failure here never fails the organiser's own save.

**Exactly what the member sees, and when:**
- A member who does **not yet** have the tour gets the edited content on their
  next `/communities/new-tours` sync / download — they download the live
  `audio_tour`, which is now the edited ZIP, labelled v2.
- A member who **already downloaded** the tour: map-delivery now reports
  version 2 for that id (so `/tours-near` and `/tour-by-code` show v2, and the
  My Tours "v2 · updated …" label will show once re-read).
  **Honest gap:** the current Flutter app has **no automatic re-download of an
  already-downloaded community tour when its version bumps** —
  `SyncPlanner.plan` skips ids already on the phone and
  `TourDownloadService.downloadAndSave` returns `alreadyOnPhone` for a present
  id; I found no `check-versions`-triggered re-fetch. So such a member keeps the
  old audio until they delete + re-download, **or** until a follow-up app change
  adds "re-download on version change". The **server side of the designed path
  is now correct and populated** (content replaced in place, version archived
  and bumped) — the remaining work to auto-refresh an already-held tour is an
  app change, flagged here for a follow-up ticket.

## Requirement 4 — Show the server's message

`tour_editing_service.dart`: new pure `tourEditErrorMessage(body)` prefers
`body['message']`, then `body['error']`, else `'Save failed'`. Wired into
`updateMultipleStops` (400 + all other statuses) and the single-stop
`updateStop`. A 404/403/500 now surfaces the server's own sentence (e.g. "Only
the community organiser can edit this tour.") instead of "Exception: Save Failed".

---

## Tests

### Red-first (each failed before the fix, passes after)

Python (`/usr/bin/python3 -m pytest`, DB `audiotours_test` on :5433):
- `tests/test_local745_zip_only_resolve.py` — a ZIP-only tour resolves to a
  readable directory (was `None` → 404). **2 passed.**
- `tests/test_local745_organiser_only.py` — member edit → 403
  `NOT_COMMUNITY_OWNER`; owner edit → allowed; ordinary tour → allowed for
  anyone. **3 passed.**
- `tests/test_local745_member_update.py` — in-place replace sets
  `audio_tours.audio_tour` to the edited bytes and archives `version_no` 1.
  **1 passed.**
- **Total: 6 passed.**

Dart (`flutter test`):
- `audio_tour_app/test/local745_edit_gate_test.dart` — `canEditTour`
  organiser-only rule (member hidden, organiser shown, ordinary editable,
  String community_id). **5 passed.**
- `audio_tour_app/test/local745_error_message_test.dart` — `tourEditErrorMessage`
  prefers the server message (404/403), falls back, generic last. **4 passed.**

### Regression / baseline
- `audio_tour_app/test/listen_stop_count_test.dart` (imports the changed
  `my_tours_screen.dart`): **13 passed** — my changes compile and don't regress.
- Baseline `tests/test_local657_version_label.py` /
  `tests/test_local606_replace_on_change.py` failures observed in this worktree
  are **pre-existing and unrelated**: proven by `git stash` of my changes — on
  the clean base `map_delivery_service.get_tours_near_location` still fails with
  `not enough values to unpack (expected 24, got 22)` (I did not touch
  map-delivery). `tests/test_tour_editing.py::test_endpoint` is a pre-existing
  pytest mis-collection of a helper function in a hard-coded-LAN-IP integration
  script, not a unit test.

---

## Live test (`live_local745.py`)

Own in-process app on spare port **5522** (never `-p audioura`; never touched
`audioura-*` or `tour-editing-phase2-1`), against the dev DB (`audiotours`), on
an **`is_test=true` COPY of tour 716** (its ZIP copied under a new filename, a
test community I own, `audio_tour` = the 716 ZIP bytes). Tour 716 itself was
never touched.

Results (final clean run):
- **Req 1:** `extracted ZIP-only tour 720 -> …_work`; owner edit **200** — the
  404 is gone.
- **Req 2:** member edit → **403 `NOT_COMMUNITY_OWNER`**; owner edit → **200**.
- **Req 3:** `replaced community tour 720 in place (archived v1, new is v2)`;
  `audio_tour` bytes **2372169 → 2365337** (changed); `audio_tour_versions`
  archived `version_no` **1**; response
  `member_update={community_id:13, new_version:2, replaced_in_place:true}`;
  `stops_count` stays **4**.

Row counts (every touched table), BEFORE → AFTER (fixtures present) → FINAL
(after cleanup):

| table | before | after | final (Δ vs before) |
|---|---|---|---|
| audio_tours | 500 | 501 | **500 (0)** |
| audio_tour_versions | 68 | 69 | **68 (0)** |
| communities | 3 | 4 | **3 (0)** |
| community_memberships | 3 | 4 | **3 (0)** |
| audio_tours (is_test) | 424 | 425 | **424 (0)** |

Cleanup deleted **exactly** the rows it created, guarded by `is_test = TRUE`
(D141); the ZIP copy and the extracted work/new dirs were removed. No
purchase-bearing row was touched (D690). No stray files remain in the tours dir.

**Cost: $0.00.** The edit sent the original stop texts unchanged with
`action='unchanged'`, so the preserve path copied the existing mp3s
("Copied audio 2→2, 3→3") and **no Polly TTS fired**.

---

## Deployment note (requested by the ticket)

`tour-editing-phase2` **is** present in `docker-compose.subscribed-local.yml`
(an override block at ~line 124), but that block only adds env/volumes — it has
**no `build:` or `command:`** — so it inherits the base `docker-compose.yml`
image (`build: .`, `command: python tour_editing_phase2.py`). The running
container `tour-editing-phase2-1` is a **2-day-old image** and will **not** pick
up this fix on its own. **LEAD must rebuild the shared `tour-editing-phase2`
image** for the fix to take effect in the live stack. (The override will not
rebuild it because it defines no build context for the service.)
