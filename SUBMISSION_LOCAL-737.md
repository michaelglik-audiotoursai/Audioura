# SUBMISSION — LOCAL-737: Subscribed has its own track value ('subscribed')

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-737-track-subscribed`
**Base:** `subscribed` @ `58782f8f` (verified: `git merge-base --is-ancestor 58782f8f HEAD` → 0)
**code_sha (base):** `58782f8f4f47b1766d7fc30c259b8ad2fa7b9183`
**code_sha (this commit):** see `git rev-parse HEAD` on `LOCAL-737-track-subscribed` (the single commit on top of the base; use the pushed tip sha).

## Summary

`track` now accepts a third first-class value `subscribed` everywhere it is read,
written, defaulted or filtered, so a Subscribed deployment can share ONE GCloud
Postgres with Beta and Storied without the same-name collision class (bug 432,
wdvrdaz108) returning between Subscribed and Beta. Missing/unknown still means
`beta`. **Beta and Storied behaviour is unchanged** (proved: LOCAL-727 and the
store/version tests stay green; the track filter is opt-in and no-op without an
explicit `?track=`).

Ruling implemented (D708): a Subscribed app lists / generates / translates /
downloads only `track='subscribed'` tours, exactly as Beta and Storied are
separated today.

---

## Files changed (code) and helpers

Each backend service got ONE shared helper instead of scattered literals:
`VALID_TRACKS = ('beta', 'storied', 'subscribed')` + `normalize_track(value)`
(None/empty/unknown → `beta`, case- and whitespace-insensitive).

### `tour_orchestrator_service.py`
- Added module-level `VALID_TRACKS` + `normalize_track()`.
- Replaced the three two-value normalisation sites with `normalize_track(...)`:
  1. the pre-lookup track resolve in `store_audio_tour` (`_track`),
  2. the serving-path `_store_track`,
  3. the post-store re-read `_track_lookup`.
- Updated `store_audio_tour` docstring to name `subscribed`.
- Write/lookup key already `(lower(tour_name), creator_user_id, track)` from
  LOCAL-727/043 — now spans three tracks automatically.

### `translation-service/translation_service.py`
- Added `VALID_TRACKS` + `normalize_track()`.
- Replaced both `_env_track` two-value checks with `normalize_track(...)`. A
  translation still INHERITS its source tour's track; the env fallback (then
  `beta`) now also accepts `subscribed`.

### `map_delivery_service.py` (ROOT — legacy, used by `docker-compose.yml`)
- Added `VALID_TRACKS`, `normalize_track()`, `_requested_track(req)`.
- `/tours-near` and `/search-tours` accept an optional `?track=` filter
  (parameterised, column-guarded). No param ⇒ historic behaviour (all tracks).

### `map_delivery/app.py` (DEPLOYED — `docker-compose-master.yml` +
`docker-compose.subscribed-local.yml` build `./map_delivery`; running container
`audioura-map-delivery-1`)
- Added `VALID_TRACKS`, `_HAS_TRACK_COLUMN` + `_has_track_column(cur)`,
  `normalize_track()`, `_requested_track(req)`, `_track_filter_clause(cur, req)`.
- `/tours-near` and `/search-tours` apply the optional `?track=` filter
  (parameterised, column-guarded, appended to the existing WHERE). No param ⇒
  byte-for-byte unchanged query → Beta/Storied unaffected.
- NOT changed: the fixed-column `_row_with_rating` SELECT/unpacking (adding a
  `track` payload column there is fragile and risks the sibling 666/606 tests).
  Listing-only-your-track is achieved by the filter; the app saves a tour's
  provenance track from `/status` at generation time, not from these lists.

> Note: both map-delivery files were updated so either deployment path carries
> the same `?track=` contract. The live/canonical one is `map_delivery/app.py`.

### App (Flutter) — single source of truth in `lib/config.dart`
- `Config.validTracks = ['beta','storied','subscribed']` — the ONE list.
- `Config.appTrack` — baked in at build via `--dart-define=APP_TRACK=subscribed`
  for the Subscribed build; defaults `beta` so Beta/Storied builds are unchanged.
- `Config.isSubscribedBuild`, `Config.normalizeTrack(track)`.
- `lib/config/endpoints.dart`:
  - `cloudTrack()` returns `'subscribed'` for the Subscribed build; otherwise the
    existing Stable/Preview (`beta`/`storied`) tester selector, now normalised.
  - `setCloudTrack` assert widened to `Config.validTracks.contains(track)`.
  - `trackLabel` shows **Subscribed** for `subscribed` (Stable/Preview unchanged).
- `lib/screens/tour_generator_screen.dart`: the read-back provenance parser
  (`statusData['track']`) now accepts any `Config.validTracks` value (was
  `storied|beta` only); imports `../config.dart`. The translation-track save at
  ~864 already uses `Endpoints.cloudTrack()` → `subscribed` for that build.
- `lib/screens/my_tours_screen.dart`: unchanged — it passes `tour['track']`
  through verbatim to `Endpoints.trackLabel`, which now knows `subscribed`.

App does NOT send `track` in request bodies; the server sets it from the
per-deployment `TOUR_TRACK` env. The Subscribed stack sets `TOUR_TRACK=subscribed`.

---

## Local-only migration (declared, NOT applied by me)

`local737_track_subscribed_migration.sql` (repo ROOT — deliberately NOT in
`migration/sql/`, which is the GCloud path via `apply_to_cloud.sh`). Numbered 048
(the next free GCloud number) for traceability, but it is a LOCAL DATA fix only.

- `UPDATE audio_tours SET track='subscribed' WHERE track='storied'` for the Mac
  Mini's local DB (every local non-beta row was written as `storied` while the
  Subscribed code ran against it pre-737).
- Wrapped in `BEGIN … COMMIT`; BEFORE/AFTER `RAISE NOTICE` per-track counts; a
  guard that aborts if any `storied` row remains; reversible (mirror UPDATE).
- No DELETE, no schema change, no purchase-bearing rows touched (D690).
- **LEAD applies it.** Validated syntactically in a disposable throwaway schema
  (created + dropped, real rows untouched): BEFORE storied=2/subscribed=0/beta=1
  → `UPDATE 2` → AFTER storied=0/subscribed=2/beta=1, guard OK, COMMIT.

---

## GCloud migrations Subscribed needs (L5 package)

On GCloud, Subscribed shares ONE Postgres (`audiotours`) with Beta and Storied —
OR runs the `audiotours_subscribed` schema created by migration **010**. Either
way, **track needs NO new GCloud schema migration**: the `track` column already
exists via migration **007** (storied schema parity) and migration **043** adds
the `(lower(tour_name), creator_user_id, track)` index — both three-track-ready.
Subscribed's own rows are born `track='subscribed'` from the code in this ticket;
there is nothing to relabel on GCloud (the local relabel migration is LOCAL-only).

The migrations that bring a Subscribed DB to full parity with Storied's GCloud DB
(i.e. 022 onward that Storied's DB may not have yet), with what each changes:

| Migration | Changes |
|---|---|
| 010_create_subscribed_database.sql | Creates the EMPTY `audiotours_subscribed` schema (base, billing, entitlement, subscription, cost/wallet, news, swipe tables) |
| 022_tour_price_tiers.sql | Tour price tiers (LOCAL-677, D624/D652) |
| 023_tour_downloads.sql | Tour downloads table (LOCAL-677C, D654) |
| 024_price_tiers_6_7.sql | Two more price tiers ($19.99, $49.99) |
| 025_editor_score.sql | Evaluated starting score per tour (LOCAL-685) |
| 026_price_ladder.sql | Price ladder (LOCAL-686) |
| 027_content_rating.sql | Content rating per tour (LOCAL-687 / D656) |
| 028_rescore_requested_version.sql | One free re-score after an edit (LOCAL-688) |
| 029_communities.sql | Communities (LOCAL-690, D657/D658) |
| 030_document_acceptance.sql | Legal-page acceptance (LOCAL-691) |
| 031_tour_unlock_consumption.sql | Tour unlock consumption (LOCAL-693, D660) |
| 032_tour_unlock_restore.sql | Unlock restore (LOCAL-693B, D660) |
| 033_recovery_code_portability.sql | Recovery-code portability (LOCAL-695, D660) |
| 034_recovery_code_lookup_selector.sql | Recovery-code lookup selector (LOCAL-695B) |
| 035_community_tours.sql | Community tours (LOCAL-701, D663) |
| 036_organiser_step_down.sql | Organiser step-down (LOCAL-702, D663 §1) |
| 037_community_launch_window.sql | Community launch window (LOCAL-703, D664) |
| 038_community_dollar_minimum_and_member_count.sql | Community $ minimum + member count (LOCAL-704) |
| 039_article_char_limit.sql | Article char limit |
| 040_short_title.sql | Server-written short tour title (LOCAL-711 / D673) |
| 041_tour_creator.sql | A tour belongs to its creator (LOCAL-718 / D678) |
| 042_tour_reports.sql | In-app content reports (LOCAL-724 item 5) |
| **043_tour_track.sql** | **(name, creator, track) index — the LOCAL-727 protection this ticket relies on; already three-track-safe** |
| 044_community_blocks.sql | Community blocks (LOCAL-726, Apple Guideline 1.2) |
| 045_community_reports_triage.sql | Community reports triage (LOCAL-728, D691) |
| 046_admin_moderation.sql | Admin moderation (LOCAL-728, D691/D690/D658) |
| 047_reimbursement.sql | Reimbursement (LOCAL-729) |

**New GCloud migration from this ticket: none.** (The local 048 is LOCAL-only.)

---

## Tests

`tests/test_local737_track_subscribed.py` — 11 tests, all green. Same
throwaway-schema harness as LOCAL-727 (`_isolated_db.IsolatedSchema`, PGOPTIONS
search_path; teardown asserts zero writes to public and DROPs the schema). No
DELETE anywhere.

- **RED test** `test_subscribed_stored_as_subscribed`: a tour stored with
  `track='subscribed'` is persisted as `subscribed`, not normalised to `beta`.
  **Proven red:** temporarily reverting `VALID_TRACKS` to the two-value set made
  this test FAIL (`subscribed` coerced to `beta`); restoring made it pass.
- `test_subscribed_and_beta_same_name_two_rows`: same name + creator, tracks
  `beta` and `subscribed` → TWO rows; the Beta row is unchanged.
- `test_same_subscribed_track_versions_one_row`: same track re-generation still
  versions the one row (legitimate regeneration unaffected).
- `normalize_track` unit tests for all three services + the deployed
  `map_delivery/app.py` helper, incl. the `?track=` "no param ⇒ None" contract
  that preserves Beta/Storied behaviour.
- `tours-near` filter via the real `map_delivery_service` Flask test client:
  no `?track=` lists all three tracks; `?track=subscribed` → only subscribed;
  `?track=beta` / `?track=storied` symmetric (proves the filter is not
  subscribed-specific and isolates each track).

### Baseline / pre-existing failures (listed, not caused by me)
- LOCAL-727 (`test_local727_track_name_key.py`): 4 tests GREEN with my changes.
- Regression set run with changes, then with changes STASHED (baseline):
  `test_local606_replace_on_change.py` (4) and
  `test_local666_translation_source_version.py` (6) = **10 PRE-EXISTING
  failures, identical with and without my changes.** They fail in
  `map_delivery/app.py` line 116 (`ValueError: expected 24, got 22`), a
  fixed-column unpack against the test's cloned schema — a file/area unrelated
  to this ticket. NOT caused by and NOT fixed by LOCAL-737.
- `test_local718/717/156` (touch `store_audio_tour`): GREEN.

### Flutter
`flutter analyze` on the four changed Dart files: no error-level issues (only
pre-existing info/warning lints elsewhere in the files).

---

## Live test

Prepared and ready (NOT yet run — awaiting go/no-go because it spends real money
and builds a parallel stack):
- `docker-compose.local737.yml` — project `local737`, spare ports (547xx), own
  throwaway `postgres-737` (tmpfs), `TOUR_TRACK=subscribed`, built from THIS
  worktree. Never `-p audioura`, never touches `audioura-*`. `docker compose
  config` validates.
- `scripts/local737_live_rowcounts.sh before|after` — per-track counts on
  `postgres-737` only.

Plan: one short generation through the isolated stack, row counts before/after,
budget ≤ $0.30. (The write-path proof — a subscribed row written as
`track='subscribed'` — is already proven in-process by the RED test above.)

> Known isolation note: `map_delivery/app.py` `get_db_connection()` hardcodes
> `host="postgres-2"`, so map-delivery in the isolated stack needs a
> `postgres-2` network alias (or is simply omitted) — it is not required for the
> generation write-path proof, which goes through the orchestrator/generator
> (both honour `DB_HOST`).

---

## Process compliance
- Branched from `subscribed` @ `58782f8f`; never from `origin/*`.
- Did NOT edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
  SUBSCRIBED_COMMUNICATION_01.MD, `legal/`. Did not change ClickUp status.
- Commit lists specific files (no `git add -A`).
