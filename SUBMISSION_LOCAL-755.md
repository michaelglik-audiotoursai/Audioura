# SUBMISSION — LOCAL-755: organiser-audio tours are never edited through our voice pipeline; members re-download by choice

**Branch:** `LOCAL-755-organiser-audio-updates`
**Base:** `subscribed` @ 1942ea37 (contains LOCAL-752 + LOCAL-754B)
**Decision:** D709 (LEAD agrees with Michael). No AI; budget **$0.00**.

`git merge-base --is-ancestor 1942ea37 HEAD` → exit 0 (verified on the correct base).

---

## Why

Michael (2026-10-23): an organiser-audio tour (`source_kind='organiser_audio'`, LOCAL-754B) is
edited on the **organiser's own site** (new MP3 at the same URL, or a new feed episode), never
through Audioura's voice pipeline. RSS/own-hosted audio must never reach our TTS/translation/OpenAI.
Instead, a **checkbox** in the builder marks a change, and members **re-download by choice** — never
pushed, even with auto-download on.

## What changed

### Server

| File | Change |
|---|---|
| `community_tours_service.py` | `has_source_kind_column()` + `tour_source_kind(cur, tour_id)` — reads `audio_tours.source_kind` (COALESCE original/own, migration 049), cached schema probe, fails OFF (None) on an older schema. |
| `tour_editing_phase2.py` | **Rule 1.** `_organiser_audio_edit_block(cur, tour_id)` resolves the edited id (numeric, or a UUID via `tour_edit_blobs`) and returns `(409, organiser_audio_not_editable)` for an organiser-audio tour, else `None`. Wired into `_bulk_save_core` right after the LOCAL-745 community gate — **before** language resolution, metering or any build — so `/tour/<id>/bulk-save`, `/update-multiple-stops` and `/update-stop` all refuse it and **no organiser audio/text ever reaches TTS**. Never raises (ordinary editing is untouched). |
| `user-tracking/communities_api.py` | **Rule 2.** `build_audio_tour` EDIT path now gates the archive + version bump on a new `notify_members` flag. `notify_members=true` ("I changed this tour — tell my members") → archive the old content to `audio_tour_versions`, version rises. Absent/false → a **silent save** (typo fix): the row is replaced in place with **no archive** and the **version unchanged**. Response carries `notify_members` + `version`. |
| `map_delivery/app.py` | `/tour-info/<id>` returns `source_kind` via a **guarded separate SELECT** (does not disturb the positional unpack), so the app can classify a held tour as organiser-audio even if its saved record predates source_kind stamping. |

### Flutter

| File | Change |
|---|---|
| `services/community_downloads.dart` | `HeldCommunityTour.isOrganiserAudio`; **`RefreshPlanner` SKIPS organiser-audio tours** (Rule 3 — never auto-re-downloaded); generated community tours still auto-refresh (Rule 4). New pure `OrganiserAudioUpdatePlanner` (opt-in offers, no download), `organiserAudioUpdateLabel()` ("Updated by the organiser — Re-download"), `organiserAudioUpdateMessage()`, `kOfferedOrganiserAudioKey`. |
| `services/community_tour_service.dart` | `serverTourVersion` now returns `({version, updatedAt, isOrganiserAudio})`, reading `source_kind` from `/tour-info`. |
| `services/community_tours_sync.dart` | Held records read `source_kind`; `HeldCommunityTour` built with `isOrganiserAudio` (record \|\| server). New `onOrganiserAudioUpdate` + `reDownloadOrganiserAudio` seams. `_offerOrganiserAudioUpdates` stamps `pending_organiser_version` on the saved record and emits **one** in-app message per (tour, server version). |
| `services/foreground_community_messages.dart` | `buildOrganiserAudioUpdateSnackBar` / `showOrganiserAudioUpdateInApp` — the LOCAL-750 in-app message with a **Re-download** action. |
| `main.dart` | Wires `onOrganiserAudioUpdate` → in-app SnackBar with Re-download (foreground) or a quiet system notification (background). |
| `screens/my_tours_screen.dart` | **Rule 1** — `canEditTour` returns false for organiser-audio (Edit hidden even for the owner). Listen-row **"Updated by the organiser — Re-download"** affordance (`organiserAudioReDownloadLabel`) + `_reDownloadOrganiserAudio` (in-place replace via `TourDownloadService.reDownloadAndReplace`). |
| `screens/community_page_screen.dart` | The community-page row shows the same Re-download affordance for an organiser-audio tour with a pending update + `_reDownloadOrganiserAudioTour`. |
| `screens/organiser_audio_tour_screen.dart` | `editTourId` param; the **"I changed this tour — tell my members"** checkbox (edit only); sends `tour_id` + `notify_members`. |

**Re-download safety (Rule 3):** `reDownloadAndReplace` downloads the new package, decodes it in
memory, fetches each remote MP3 from the organiser host, and replaces the old copy **only after** the
new one is complete — a failed re-download keeps the old copy (member never left with nothing).

## Tests (red first, then green)

- `tests/test_local755_organiser_audio_updates.py` (**6**): `_organiser_audio_edit_block` 409 /
  allow-generated / allow-unknown; end-to-end `_bulk_save_core` 409; builder **no-checkbox keeps
  version + no archive**; builder **checkbox bumps version**.
- `audio_tour_app/test/community_organiser_audio_updates_local755_test.dart` (**17**): RefreshPlanner
  skip (and generated still planned); `canEditTour` false for organiser-audio; labels;
  `OrganiserAudioUpdatePlanner`; Listen-row label.
- `audio_tour_app/test/community_organiser_audio_sync_local755_test.dart` (**3**): the sync OFFERS
  once, **never auto-downloads** an organiser-audio update, and a **generated tour still
  auto-refreshes**.
- Updated `tests/test_local754b_organiser_audio.py` `test_edit_bumps_version` to pass
  `notify_members=True` (the ticket changes its premise: the bump is now opt-in).

## Verification

- **Flutter full suite:** 993 passed, **7 failed** — the known baseline failures
  (`local109_swipe_e2e_test.dart` ×6 + `storied_compat_screens_404_test.dart` ×1), all
  `SocketException: Connection refused` (server-backed e2e with no live server in the test host).
  **Zero new failures** from LOCAL-755.
- **flutter analyze:** no errors in any touched file (pre-existing errors only in untouched
  `audio_handler.dart` + `subscription_management_screen.dart`).
- **Python:** `test_local755_*` 6/6; `test_local754b_*` + tour-editing guards 26/26; DB-backed
  `test_local745_*` 4/4 against the live test DB; `test_local701` 14/14.
- **Live (`live_local755.py` vs `audiotours_test` @ localhost:5433):** 13/13 checks PASS —
  build organiser-audio → 201 (`source_kind`, v1); edit guard → 409 `organiser_audio_not_editable`
  (and allows a generated tour); silent edit keeps v1 with **no** archive row; checkbox edit → v2 with
  `audio_tour_versions.version_no = 1` archived. **Row counts clean** before/after
  (`audio_tours` 0→2→0, `audio_tour_versions` 0→1→0), **is_test rows only**, D141 cleanup,
  no purchase-bearing rows touched (D690), **$0.00** (no AI).

## Not done / honest note

**Simulator screenshots of the Re-download row and message were not captured.** Running the full
Flutter app on a simulator against the live container stack is a heavyweight operation; instead the
**server behaviour is proven live** end-to-end (`live_local755.py`, 13/13) and the **Flutter UI logic
is proven by widget/unit tests** (the pure planners/labels, the sync glue that offers-once and never
auto-downloads, and the in-app message snackbar builder). The row/message widgets wire those tested
pure functions to the already-tested `reDownloadAndReplace` path.

## Guardrails honoured

Branched from `subscribed` @ 1942ea37 (not origin). No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md,
WORK_QUEUE, `.continuous_dev/`, SUBSCRIBED_COMMUNICATION_01.MD, `legal/`. `tour_html_map.py` (root and
`user-tracking/`) untouched — the identical-copies guard is unaffected. Commit is file-scoped (no
`git add -A`).
