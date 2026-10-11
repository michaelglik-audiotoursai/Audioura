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
