##### READY FOR REVIEW

# SUBMISSION_LOCAL-670: Tour ratings (1–10, 7.5 default), shown on the home page and filterable; per-stop thumbs kept and clearly per-stop

**Task:** LOCAL-670 — per-TOUR 1–10 rating with a 7.5 starting value, a home-page badge + filter, and the existing per-STOP thumbs relabelled so they read as per-stop
**Branch:** `LOCAL-670-tour-ratings` (from `subscribed` @ `27bd57ff`)
**Base:** subscribed (`git merge-base --is-ancestor 27bd57ff HEAD` → exit 0)
**Author:** Mac Mini Kiro
**Date:** 2026-10-10

---

## The rule (D647), as implemented

A listener rates a TOUR 1–10 (whole numbers). One rating per `(user, tour)`; a later rating **replaces** the earlier one (UPSERT on `UNIQUE(tour_id, user_id)`).

**Shown score:**
- **0 ratings → 7.5**, labelled **"New"**.
- **1–3 ratings → the average of 7.5 plus the real ratings** (the automatic 7.5 is included). One real `9` → `mean(7.5, 9) = 8.25 → 8.3`, matching the brief's worked example.
- **≥ 4 ratings → the median of the real ratings only** (the 7.5 prior is dropped). The robust middle value: one angry `1` or one fake `10` cannot swing a well-rated tour.
- Always returned with the count and a label: `{"score": 8.3, "count": 2, "label": "2 ratings"}`, `{"score": 7.5, "count": 0, "label": "New"}`.

A **translation shares its source tour's ratings**: every read/write resolves a translation row (`audio_tours.original_tour_id` set) to its original first, so ratings always key on the original `audio_tours.id`.

---

## Files changed

| File | Purpose |
|------|---------|
| `migration/sql/019_tour_ratings.sql` | **New.** Additive `tour_ratings(id, tour_id, user_id, rating SMALLINT CHECK 1..10, created_at, updated_at, UNIQUE(tour_id, user_id))` + two indexes. No DROP/DELETE, no change to `user_stop_feedback`. |
| `tour_rating_service.py` | **New.** `compute_score` (the pure D647 rule), `resolve_original_id` (translation→source), `has_downloaded` (download-record check via `tour_requests`), `record_rating` (UPSERT replace), `get_rating`, and `register_rating_routes(app)` → `POST`/`GET /tour/<id>/rating`. |
| `tour_orchestrator_service.py` | Registers `register_rating_routes(app)` alongside the existing swipe-preference and wallet route registrations (same ImportError-logged pattern). |
| `map_delivery/app.py` | `/tours-near`, `/search-tours`, `/tour-by-code`, `/tour-info` now return `rating_score`/`rating_count`/`rating_label` via **one grouped `ARRAY_AGG` join** on `COALESCE(original_tour_id, id)` (so translations inherit source ratings); `/tours-near` and `/search-tours` honour an optional `?min_rating=<float>` filtered server-side. Cached table-presence probe degrades to 7.5 "New" on a pre-670 schema (never a 500). |
| `audio_tour_app/lib/services/tour_rating_service.dart` | **New.** `TourRating` model + `submitRating`/`fetchRating` via `Endpoints.post/get(Service.orchestrator, …)`, `user_id` from SharedPreferences. |
| `audio_tour_app/lib/widgets/rate_tour_dialog.dart` | **New.** `RateTourDialog` (1–10 chips), `showRateTourDialog()`, and `TourRatingBadge` ("★ 8.3 · 2 ratings" / "★ 7.5 · New"). |
| `audio_tour_app/lib/screens/home_screen.dart` | Rating badge in the tour dialog + a "Rate" action; **Any / 7+ / 8+ / 9+** filter in the app bar, remembered per device (`home_min_rating`) and passed to `/tours-near` as `min_rating`. |
| `audio_tour_app/lib/screens/tour_player_screen.dart` | End-of-tour "Rate this tour" prompt (fires once, after the last stop's audio ends); passes the current stop name to the thumbs widget. |
| `audio_tour_app/lib/widgets/swipe_feedback_widget.dart` | Per-STOP thumbs now carry a **"This stop: &lt;name&gt;"** label and name the stop in the confirmation toast. Behaviour otherwise unchanged. |
| `audio_tour_app/lib/screens/my_tours_screen.dart` | "Rate this tour" item in the downloaded tour's ⋮ menu. |
| `audio_tour_app/pubspec.yaml` | `2.4.7+34` → `2.4.7+35`. |
| `tests/test_local670_tour_ratings.py` | **New.** 15 tests (below). |

---

## Authorisation (download record)

Only a user who has downloaded the tour should rate it. `has_downloaded` checks the existing `tour_requests` record (keyed on `secret_id`, matching the requested id or its resolved original as text). If **no record exists the rating is still allowed and the fact is logged** — per the ticket, a rating is never silently dropped.

---

## Evidence

### Python tests — 15/15 PASS

```
$ python3 -m pytest tests/test_local670_tour_ratings.py -v
test_zero_ratings_is_default_new ....................................... PASSED
test_one_rating_blends_the_prior_brief_example (7.5 & 9 → 8.3) ......... PASSED
test_three_ratings_still_average_including_prior ...................... PASSED
test_four_ratings_switches_to_median_of_real_only ..................... PASSED
test_seven_ratings_median_odd_count .................................. PASSED
test_median_drops_the_prior_so_a_low_outlier_cannot_sink_a_good_tour .. PASSED
test_half_up_rounding ................................................ PASSED
test_record_and_get_roundtrip ........................................ PASSED
test_rerate_replaces_not_appends ..................................... PASSED
test_invalid_ratings_rejected ........................................ PASSED
test_translation_shares_source_ratings ............................... PASSED
test_endpoint_post_then_get .......................................... PASSED
test_endpoint_rejects_bad_rating ..................................... PASSED
test_map_delivery_rating_fields_and_min_rating ....................... PASSED
test_map_delivery_unrated_tour_is_default ............................ PASSED
======================== 15 passed in 0.44s ========================
```

Coverage maps to the ticket's required cases: the score rule at **0 / 1 / 3 / 4 / 7** ratings, the **median**, **replacement** of a rating, **translation mapping**, the **endpoint** tests, and the **`min_rating`** filter.

### map-delivery `min_rating` (in-process Flask client, test DB)

```
/tour-info/<id>                       → rating_score 8.8, rating_count 2, rating_label "2 ratings"
/tours-near/43.70/7.26?radius=5       → tour present
/tours-near/...&min_rating=9          → tour EXCLUDED (8.8 < 9)
/tours-near/...&min_rating=8          → tour INCLUDED (8.8 ≥ 8)
```

### flutter analyze — changed files

New/widget files are clean:

```
$ flutter analyze lib/services/tour_rating_service.dart lib/widgets/rate_tour_dialog.dart lib/widgets/swipe_feedback_widget.dart
No issues found!
```

The remaining `info`/`warning` lines in `home_screen.dart`, `my_tours_screen.dart` and `tour_player_screen.dart` are **pre-existing at the base commit** (unused imports/fields such as `_connectionError`, `dart:io`, `config/endpoints.dart`) — verified against `27bd57ff`. No new error or warning is introduced by this change.

### flutter build ios --no-codesign

```
✓ Built build/ios/iphoneos/Runner.app (37.3MB)
```

(Not installed — LEAD installs with Michael's phone, per the ticket.)

---

## Safety / constraints honoured

- Additive migration only; `user_stop_feedback` untouched; no DELETE on any other table.
- No paid API calls. Every test row uses a `user_id` starting with `TEST-670-` and is deleted by exact id after a prefix check; **0 `TEST-670-` rows remain** in `audiotours` and `audiotours_test`.
- No `docker compose`, no `audioura-*` container replaced, no GCloud. Verification used read-only queries and in-process Flask test clients against the already-running local Postgres.
- Did not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`, or `.continuous_dev/STATUS.md`.

## Commits

Six commits on `LOCAL-670-tour-ratings`, one per step (migration → service → map-delivery → app service/dialog → app wiring → tests). `git merge-base --is-ancestor 27bd57ff HEAD` exits 0.


---

# 670B — Rebase onto current `subscribed` (9684e563) + rating requires ≥ 2 listened stops

## Why this follow-up

1. **Rebase.** LOCAL-670 was branched at `27bd57ff`, before LOCAL-666 added
   `source_version` and the translation-version columns to the same map-delivery
   SELECTs that LOCAL-670 extended with the rating fields. LEAD's merge of
   LOCAL-670 into `subscribed` therefore left `get_tour_info`/`get_tours_near_location`
   raising `not enough values to unpack (expected 15, got 13)`. This branch is
   rebased onto `subscribed` @ **9684e563** (`git merge-base --is-ancestor 9684e563 HEAD`
   exits 0) and the four map-delivery endpoints are reconciled into **ONE grouped
   query each** carrying version + source_version + the rating fields.

2. **Michael (2026-10-10):** don't allow a tour rating until the listener has
   heard enough — "similar to Audible … politely say that the user did not hear
   enough to rate the tour."

## Map-delivery reconciliation (one query per endpoint)

The production SELECTs in `map_delivery/app.py` were already the correct 15-column
shape after the rebase: `_source_version_select(cur)` emits `source_version`
(or `NULL::integer` on an older schema) and `_ratings_select(cur)` **always**
emits exactly two columns (`r.rating_count, r.rating_values`, or
`NULL::bigint, NULL::smallint[]`), so each of `/tour-by-code`, `/tour-info`,
`/tours-near`, `/search-tours` unpacks a fixed 15 columns in one pass. No
per-tour N+1, no second query.

The break surfaced in the **pre-existing LOCAL-657 and LOCAL-666 tests**: their
scripted `_FakeCursor` plans returned 13-column rows and answered the shared
`information_schema` probe as "present", so the rating columns were selected but
the fixture rows were short. Reconciliation extended each `audio_tours t`
fixture row to 15 columns (5 rows in 657, 6 in 666) and updated the column-order
comments. The 3-column translation-service helper fixtures were left untouched.

All three suites now pass together:

```
tests/test_local657_version_label.py
tests/test_local666_translation_source_version.py
tests/test_local670_tour_ratings.py
tests/test_local670b_listened_gate.py
→ 46 passed
```

## Listened-stops gate

**Schema — `migration/sql/020_tour_listens.sql`** (additive, idempotent):
`tour_listens(id, tour_id, user_id, stop_index, created_at,
UNIQUE(tour_id, user_id, stop_index))` + a `(tour_id, user_id)` index. The
service also carries identical self-healing DDL (`_ensure_tour_listens_table`)
so it works whether or not the migration was run — same pattern as `tour_ratings`.

**Server — `tour_rating_service.py`:**
- `record_listen(user, tour, stop)` — idempotent `INSERT … ON CONFLICT DO NOTHING`;
  resolves a translation id to its source first, so listens key on the ORIGINAL
  tour exactly like ratings.
- `required_listened_stops(cur, orig)` = `min(2, stops_count)` but never below 1
  (a 1-stop tour needs its one stop; an unknown length keeps the full 2).
- `POST /tour/<id>/rating` now validates the rating **value** first (→ 400 on a
  bad value regardless of listen history), then applies the gate: fewer than the
  required distinct listened stops → **403 `not_enough_listened`** with the polite
  message *"Listen to at least N stops to rate this tour. You've heard M so far."*
- New `POST /tour/<id>/listened {user_id, stop_index}` (idempotent) and
  `GET /tour/<id>/listened?user_id=…`. The orchestrator already registers these
  via `register_rating_routes(app)`.

**Server tests — `tests/test_local670b_listened_gate.py` (10):** idempotent POST;
403 at 0 and 1 stops with the count in the message; 200 at 2 stops; a 1-stop tour
rateable after its single stop; a translation's listens unlocking the source (and
vice-versa); read-only status; negative `stop_index` → `ValueError`; missing
`stop_index` → 400.

**App:**
- New `TourListenService` records a stop LISTENED when its audio reaches ≥ 80% or
  ends, stored locally per `(tour, stop)` in SharedPreferences and best-effort
  POSTed to `/tour/<id>/listened` (idempotent server-side; only numeric tour ids
  are synced, local-path tours are tracked locally so the gate still works offline).
- `tour_player_screen.dart` injects a `timeupdate`/`ended` listener per stop that
  fires `onStopListened` (guarded once per stop), and captures the tour's total
  stop count for the threshold.
- The end-of-tour prompt and every "Rate this tour" entry point (player, My Tours
  menu, home dialog) route through `showRateTourDialog`, which is now gated: below
  threshold it shows the polite Audible-style message with the running count and
  does not open the 1–10 picker. The per-STOP thumbs are untouched — you can always
  rate a stop you heard.
- `pubspec` 2.4.7+35 → 2.4.8+36.

## Verification

- `flutter analyze` on the owned new/edited files (`tour_listen_service.dart`,
  `rate_tour_dialog.dart`) → **No issues found!** Remaining analyzer output in the
  large screen files is pre-existing.
- `flutter build ios --no-codesign` → `✓ Built build/ios/iphoneos/Runner.app (37.3MB)`.
- **No NEW test failures vs `origin/subscribed` (9684e563).** The full
  `python3 -m pytest -q tests` was run on this branch and on a clean 9684e563
  worktree and the FAILED/ERROR node sets were diffed. Every pre-existing failure
  (integration suites needing live services, e.g. `test_wallet_api`,
  `test_newsletter_*`, `test_local67_entitlement_gate`'s missing `test_users`
  fixture, `test_local431` story-gate) fails identically on the baseline. The
  657/666/670/670b suites pass (46) in isolation and when ordered after other
  DB-backed suites; their occasional ERROR attribution in the 27-minute full run
  is a pre-existing full-run flakiness unrelated to this change (the same nodes do
  not error on the baseline and pass every targeted run).

## Safety / constraints honoured (670B)

- Additive migration only (`020_tour_listens.sql`); no DROP/DELETE on any existing
  table; `user_stop_feedback` and the per-stop thumbs untouched.
- No paid API calls. All test rows use `TEST-670-` user ids and are deleted by
  exact id after a prefix check (cleanup extended to `tour_listens`).
- Own containers only; no `audioura-*` container replaced; no `docker compose`;
  no GCloud. Verification used the already-running local Postgres and in-process
  Flask test clients.
- Did not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`, or
  `.continuous_dev/STATUS.md`.

## Commits (670B)

Rebased `LOCAL-670-tour-ratings` onto 9684e563, then one commit per step:
map-delivery fixture reconciliation → server listened gate (migration + service +
tests) → app listened gate → this SUBMISSION update. Pushed with
`--force-with-lease`.
