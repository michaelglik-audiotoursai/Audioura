# SUBMISSION_LOCAL-795.md

## Reviews page: a visible "Write a review" link, and a per-stop "Tell us about this place" note

**Branch:** `LOCAL-795-write-review`  ·  **Base:** subscribed (`79cd51bf`)
**Found by:** Michael, iPhone, 2026-10-27 20:1x — *"I like the review page, but no
link to leave a note: some people would love to; and some would describe their
experience we can potentially use afterwards."*

---

## What shipped

### 1. A "Write a review" link on the reviews section
`lib/widgets/reviews_section.dart` already listed reviews but offered no way to
write one — `showAddReviewDialog` was only reachable right after a star rating
(`rate_tour_dialog`); a listener who skipped it had no second chance.

`ReviewsSection` now renders, at the top of the expanded section:

- **"Write a review"** (becomes **"Edit your review"** once the user has
  submitted one this session) for a user who **has the tour downloaded** — it
  reuses the existing `showAddReviewDialog` (≤ 500 chars, `POST /tour/<id>/review`,
  server auto-check, curator reply). The server already replaces an existing
  review, so "edit" is the same call.
- **"Download the tour to review it"** for a user who does not have it.

The downloaded check reads the local `saved_tours` list (the same one My Tours
uses), matching the tour id against each record's `server_tour_id`/`tour_id`. It
is injected via `ReviewsSection.downloadedResolver` so it is unit-testable with
no `SharedPreferences`. `home_screen.dart` now passes `tourTitle` so the dialog
names the tour.

### 2. "Tell us about this place" — a per-stop note in the player
`lib/screens/tour_player_screen.dart` gains an `edit_note` icon in the player
AppBar (tooltip *"Tell us about this place"*). It opens a dialog for the stop
currently playing — the note (≤ 500 chars) is `POST`ed to the orchestrator with
the tour id, the stop's index + title, the user, and the playback language. A
note is free-form and needs **no prior rating**. When the tour has no numeric id
the control explains it rather than failing silently.

### 3. Copy line under both boxes
Both the reviews box and the stop-note dialog carry:

> **Notes may be used to improve Audioura tours.**

(The rules page carries the full wording; D727-style, no per-note consent
checkbox.)

---

## Server

### Additive migration — `migration/sql/057_stop_notes.sql`
A new `stop_notes` table: `id, tour_id, stop_index, stop_title, user_id,
note_text (≤ 500), language, note_status (pending|approved|rejected),
status_reason, created_at`, with indexes on `(tour_id, stop_index)` and
`(user_id, created_at)`. **Purely additive** — `CREATE TABLE/INDEX IF NOT EXISTS`
+ guarded `ALTER ADD COLUMN`, no `DROP`/`DELETE`, no column retype; applying it
twice is a no-op. (057 is the next free number after `056_stop_pool_rejected.sql`.)

### Endpoint — `POST /tour/<id>/stop/<n>/note`
Added to `tour_reviews_service.py` (the module that **owns reviews**, registered
on the **orchestrator** — same auth/attestation as reviews: `user_id` required,
X-API-Key + X-App-Attestation on the orchestrator in cloud mode). `submit_stop_note`:

- resolves the tour id to its **original** (a translation shares its source
  tour; the listener's own `language` is kept);
- **rejects an unknown tour** (`400 {"error":"unknown tour"}`);
- enforces a **rate limit of 10 notes / user / rolling 24 h** (the 11th is `400`);
- runs the **same auto-check** as reviews (profanity / url / contact → held
  `pending`, else `approved`);
- has self-healing DDL identical to the migration, so it works whether or not
  057 was applied.

The note is **not shown publicly** in this task — it is a write-only endpoint
from the app, raw material we "can potentially use afterwards".

Flutter client: `TourReviewsService.submitStopNote` + the pure helpers
`isTourDownloaded` / `savedToursContainTour`.

---

## Files changed

```
migration/sql/057_stop_notes.sql                               (new, additive)
tour_reviews_service.py                                        (stop-note service + route)
audio_tour_app/lib/services/tour_reviews_service.dart          (submitStopNote + downloaded helpers)
audio_tour_app/lib/widgets/reviews_section.dart                (Write/Edit review button + copy line)
audio_tour_app/lib/screens/tour_player_screen.dart             (per-stop note icon + dialog)
audio_tour_app/lib/screens/home_screen.dart                    (pass tourTitle)
audio_tour_app/test/reviews_section_write_review_local795_test.dart  (new)
tests/test_local795_stop_notes.py                              (new)
docker-compose.local795-proof.yml                              (new, live-test stack)
```

---

## Tests

**Widget** — `reviews_section_write_review_local795_test.dart` (4, all pass):
downloaded → "Write a review" shown and opens the add-review dialog;
not-downloaded → "Download the tour to review it", no button; the copy line in
both; plus the pure `savedToursContainTour` matcher.

**Server unit** — `tests/test_local795_stop_notes.py` (9, all pass): text/index
validation; clean → `approved`; flagged → `pending` + reason; **unknown tour
rejected**; **rate limit — 10 succeed, the 11th is refused**; a translation note
keys on the original tour but keeps its own language; the endpoint success + the
`user_id`-required / empty-text / no-body `400`s.

### Baseline (only NEW failures count)
- `flutter test` full suite: **1195 passed, 8 failed** — exactly the known
  baseline (6 in `local109_swipe_e2e_test.dart`, which need a live server, plus
  `storied_compat_guard_test.dart` and `storied_compat_screens_404_test.dart`).
  None touch the files in this change → **no new failures**.
- Server: `test_local795_stop_notes.py` 9/9. `test_local672_verified_reviews.py`
  24/26 — the 2 failures are pre-existing (they load `map_delivery/app.py`, which
  imports `personal_match`, present only in the Docker image, not the repo root);
  unrelated to this change.
- `flutter analyze` on the changed Dart files: only info-level
  `prefer_const_constructors` hints, all in pre-existing code shifted by the
  inserts; no errors/warnings in the new code.

---

## Live test — own containers, `-p local795`

`docker compose -p local795 -f docker-compose.local795-proof.yml up -d --build`
(a dedicated Postgres + the orchestrator **built from this worktree**, on
non-conflicting host ports, so the run measures the new code and never touches
the dev stack). The `python:3.9` orchestrator image has libpq < 10, so the
Postgres was configured for md5 auth. Seeded a minimal schema + tour id 1, an
owner (creator), and a reviewer with a rating.

Exercised the real HTTP endpoints directly (a stronger, lighter proof of the
server contract than a simulator tap; the Flutter side is covered by the widget
tests):

| Action | Request | Result |
|---|---|---|
| Write a review | `POST /tour/1/review` | **HTTP 200**, `review_status=approved` |
| Leave a stop note | `POST /tour/1/stop/2/note` | **HTTP 200**, `note_status=approved`, stored `stop_index=2`, `stop_title="Third-Floor Balcony"`, `language="en"` |
| Unknown-tour guard | `POST /tour/999999/stop/0/note` | **HTTP 400** `{"error":"unknown tour"}` |
| Rate-limit guard | 11 notes by one user | first 10 → 200, 11th → **400**; count capped at **10** |

Row counts (before → after): `tour_reviews` **0 → 1**, `stop_notes` **0 → 1**
(then 10 after the rate-limit check). **Paid-API cap $0** — every endpoint is
DB-only, no model calls. Stack torn down with `down -v`.
