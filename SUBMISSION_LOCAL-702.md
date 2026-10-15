# SUBMISSION — LOCAL-702: Organiser steps down — hand-over, closed to new members, archive after 30 days (D663 §1)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-702-organiser-steps-down` (from `subscribed`, base `6c8fa3e2`)
**App build:** bumped `2.4.21+58` → `2.4.22+59` (`audio_tour_app/pubspec.yaml`)

Base verified: `git merge-base --is-ancestor 6c8fa3e2 HEAD` exits 0 (branch created from
local `subscribed` HEAD, never from `origin/*`).

---

## The state machine (D663 §1)

A community's `status` moves:

```
active ──step-down──▶ handover ──accept──▶ active (reopened, new owner)
                         │
                         └──30 days, no new organiser──▶ archived (terminal)
```

- **active** — normal. New members may join / buy passes.
- **handover** — the owner tapped **Step down as organiser** (§1 a). The community stays
  readable/playable for existing members, **refuses new joins and pass sales**
  (`409 community_closed_to_new_members`), and shows **"Looking for a new organiser"**.
- **archived** — no new organiser within **30 days** of stepping down (§1 c). Members keep
  their downloads; nothing new is served or sold. Terminal.

---

## 1. Migration `migration/sql/036_organiser_step_down.sql` (next free number)

Purely **additive + idempotent**, one transaction, no DROP/DELETE/retype:

- `communities.status VARCHAR(16) NOT NULL DEFAULT 'active'` + guarded
  `chk_communities_status CHECK (status IN ('active','handover','archived'))`.
  Every existing row is `active` (the DEFAULT + a value-asserting `UPDATE`), so behaviour is
  unchanged until an owner steps down.
- `communities.stepped_down_at TIMESTAMP` — the 30-day archive clock origin.
- `communities.archived_at TIMESTAMP` — stamped by the daily job.
- Partial index `idx_communities_handover` on `stepped_down_at WHERE status='handover'`
  (the archive scan only touches the small handover set).
- `community_organiser_offers` — one row per `(community, member)` volunteer, with
  `status IN ('offered','picked','accepted','withdrawn')`, `picked_at`, `accepted_at`.
  `uq_organiser_offers UNIQUE (community_id, member_user_id)` and a partial unique index
  `uq_organiser_offers_one_picked` (at most one *picked* offer per community).

> **LEAD applies the migration to the shared dev DB.** Per PROCESS, I did **not** touch
> `-p audioura` or the shared dev DB. I applied `036` to the **test** DB (`audiotours_test`)
> only and confirmed it re-runs clean (idempotent). **LEAD: please run
> `migration/sql/036_organiser_step_down.sql` against the shared dev DB** — it is additive and
> idempotent (`ADD COLUMN IF NOT EXISTS` × 3, a guarded `CHECK`, `CREATE TABLE IF NOT EXISTS`,
> `CREATE INDEX IF NOT EXISTS`).

## 2. Backend — `user-tracking/communities_api.py`

Self-contained blueprint (unchanged convention). Added:

- **State helpers:** `STATUS_ACTIVE/HANDOVER/ARCHIVED`, `ARCHIVE_AFTER_DAYS=30`
  (env `COMMUNITY_ARCHIVE_AFTER_DAYS`), `_accepts_new_members(status)`,
  `_community_member_count(cur, id)`, `_record_organiser_terms_acceptance(cur, user_id)`
  (LOCAL-691 `document_acceptance`, document `organiser_terms`), and
  `archive_stale_handovers(cur, now, after_days)` — the pure archive job.
- `_community_row` now selects the three new columns; **`_community_page`** emits
  `status`, `looking_for_organiser`, `archived`, `accepts_new_members`, `stepped_down_at`,
  `archived_at`, the owner-only `organiser_offers` list and the caller's own `my_offer`
  (both only while in hand-over).
- **Endpoints:**
  - `POST /communities/<id>/step-down` — owner only; `active → handover`, sets
    `stepped_down_at`. Idempotent on an already-handover community (no clock reset); `409
    already_archived`.
  - `POST /communities/<id>/offer-organiser` — a member (or the owner) volunteers; `409
    not_in_handover` otherwise. Re-volunteering reuses the row.
  - `POST /communities/<id>/withdraw-offer` — a volunteer withdraws.
  - `POST /communities/<id>/pick-organiser` — owner picks a volunteer; any previous pick is
    superseded back to `offered` (one pick at a time).
  - `POST /communities/<id>/accept-organiser` — the **picked** member accepts → ownership
    transfers (`owner_user_id`), `handover → active`, clock cleared, every other offer closed,
    and the organiser-terms acceptance recorded. `403 not_picked` for anyone else.
  - `DELETE /communities/<id>` — owner deletes a **member-less** community (§1 d). `409
    has_members` once members exist (the D658 rule only forbids *closing* once members exist).
  - `POST /communities/archive/run` — the daily archive tick (see LEAD line below).
- **Closed-to-new-members gate:** `join_free_community` and `verify_community_pass` return
  `409 community_closed_to_new_members` when the community is in `handover`/`archived` — but
  an **existing member renewing** is still allowed (the gate blocks a *new* membership, not a
  renewal of one that pre-dates the step-down).

## 3. `>>> LEAD: wire the daily archive tick <<<`

The archive-at-30-days job is a daily tick, exactly like the existing community reminder tick
(`/communities/reminders/run`). I ship the endpoint + the pure function; **LEAD wires the one
daily line** on the scheduler that already drives the reminder tick.

**The tick line (daily):**

```bash
# Daily — archive communities whose organiser stepped down ≥ 30 days ago (D663 §1 c).
curl -fsS -X POST "$USER_API_BASE/communities/archive/run" -H "X-API-Key: $GATEWAY_API_KEY"
```

(or, in-process on the same daily cron that calls `run_reminders`:)

```python
from communities_api import archive_stale_handovers
archived_ids = archive_stale_handovers(cur)   # returns the ids archived this run
conn.commit()
```

Idempotent: it only matches `status='handover'`, so a second run the same day archives nothing
new. `COMMUNITY_ARCHIVE_AFTER_DAYS` overrides the 30-day window if ever needed.

## 4. App — `audio_tour_app/`

- **`lib/services/communities_models.dart`** — `Community` extended with `status`,
  `lookingForOrganiser`, `archived`, `acceptsNewMembers`, `steppedDownAt`, `archivedAt`,
  `organiserOffers`, `myOffer`; new `OrganiserOffer` + `MyOffer` models. Parsing stays
  defensive and **defaults to `active`** when the server omits the fields (older shape).
- **`lib/services/communities_service.dart`** — `stepDown`, `offerOrganiser`, `withdrawOffer`,
  `pickOrganiser`, `acceptOrganiser`, `deleteCommunity` (+ a shared `_postCommunity` helper).
- **`lib/config/endpoints.dart`** — added a `delete()` convenience (apiHeaders + optional body)
  for the member-less-delete call.
- **`lib/screens/community_page_screen.dart`** — a screen for **each step**:
  - member **"Looking for a new organiser"** banner with **Volunteer / Withdraw**, and, when
    the owner has picked them, **"You were picked — Accept & organise"** (a confirmation that
    agrees to the Organiser Terms);
  - the **archived** read-only banner ("downloads only");
  - owner controls: the **volunteer list to pick from** during hand-over, **Step down as
    organiser** (confirmation dialog spelling out the 30-day rule) while active, and **Delete
    community** for a member-less one;
  - the join / pass UI is hidden while the community is closed to new members.

## 5. Tests — every state transition

**`tests/test_local702_organiser_steps_down.py`** (23 tests, all green against
`audiotours_test`): step-down (owner-only, 404, idempotent, no clock reset); closed-to-new
free join + pass sale (`409 community_closed_to_new_members`); existing member still reads the
page + episodes in hand-over; the full **offer → pick → accept → reopen** path (ownership
transfers, clock clears, `organiser_terms` acceptance recorded, a new member can join again);
offer refused when not in hand-over; pick owner-only / unknown-volunteer 404; accept refused
when not picked; pick supersedes a previous pick (exactly one `picked`); withdraw; archive at
30 days (and *not* at 10); archive idempotent; archived refuses new members; cannot step down
an archived community; delete a member-less community; delete refused with members (`409
has_members`); delete owner-only / 404.

Existing community suites still green (no regressions):
`test_local690_communities.py`, `test_local700_communities_ux.py`,
`test_local701_community_tours.py`, `test_local691_document_acceptance.py` — **64 passed**.

**App:** `flutter analyze` clean on all four changed `lib` files + the test. 5 new Dart
model-parse tests added to `test/communities_service_test.dart` (**32 passed**).

> Pre-existing lints in `lib/config/endpoints.dart` (`_cloudPaths` unused-field;
> `prefer_const_declarations` at line 201) are **not** from this change — my only edit there is
> the new `delete()` method.

## PROCESS

- Own containers + `is_test` data only. Migration `036` applied to **`audiotours_test`** inside
  my own postgres container; never `-p audioura`, no `audioura-*` rename, shared dev DB left
  for LEAD.
- No edits to DECISIONS / CLAUDE / BACKLOG / WORK_QUEUE / `.continuous_dev`.
- App build number bumped (`+58 → +59`).

## Files

- `migration/sql/036_organiser_step_down.sql` (new)
- `user-tracking/communities_api.py`
- `audio_tour_app/lib/services/communities_models.dart`
- `audio_tour_app/lib/services/communities_service.dart`
- `audio_tour_app/lib/config/endpoints.dart`
- `audio_tour_app/lib/screens/community_page_screen.dart`
- `audio_tour_app/pubspec.yaml`
- `tests/test_local702_organiser_steps_down.py` (new)
- `audio_tour_app/test/communities_service_test.dart`
- `SUBMISSION_LOCAL-702.md` (this file)
