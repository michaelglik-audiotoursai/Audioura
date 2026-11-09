##### READY FOR REVIEW

**Task:** LOCAL-876 — Tour 544 findings: the header-vs-narration contradiction, and the "★ 7.5 · New" badge that looks like a rating
**Branch:** `LOCAL-876-544-findings`
**Based on:** `subscribed` @ `0a64fc79` (`git merge-base --is-ancestor 0a64fc79 HEAD` → 0)
**Evidence:** tour 544 (ouVCyG8V), ClickUp wdvrdazdpz

---

## Summary

Two findings on tour 544, both unaddressed by 872C/873/874/875:

1. **Header vs narration contradiction.** Stop 1's `Specific Examples` line said
   "neo-Romanesque architecture" while the narration/evidence say neo-Gothic. The
   `Type/Specialty` and `Specific Examples` header lines were restored from the poi
   dict (LOCAL-866) and never checked against the body or the evidence.
2. **The "★ 7.5 · New" badge.** `map_delivery`'s `RANK_PRIOR_SCORE = 7.5` was shown
   as a rating for a tour with **no** ratings. Michael read it as an evaluation.

Both are fixed; a tour with no ratings now shows **"New"** with no number, the 7.5
prior is kept only for list ORDER, and a header style that contradicts the body or
the evidence is dropped (fact sheet wins when present).

---

## Changes

| File | Change |
|------|--------|
| `stop_header_consistency.py` | **New** pure module. Reconciles the `Type/Specialty` and `Specific Examples` header lines per stop. Fact sheet wins when it names a style; otherwise a header style contradicted by the body/evidence is dropped (the LOCAL-872 claim-gate idea, applied to the header lines). Mutually-exclusive architectural style families (gothic/neo-gothic/Gothic Revival, romanesque/neo-romanesque/Romanesque Revival, baroque, renaissance, neoclassical, art deco/nouveau, brutalist, modernist). Drops the whole line if nothing substantive remains. Deterministic, idempotent, no network/LLM/DB. |
| `generate_tour_text.py` | Finding 1 wiring: on the walking/landmark path, immediately **after** `_restore_stop_headers_866`, build per-stop evidence from each poi's `description`/`_thin_evidence`/`_lore` and call `reconcile_stop_headers`. Guarded, non-fatal. |
| `map_delivery/app.py` | Finding 2 server: `compute_rating` and `_rating_payload` now return `display_rating` = `None` when the tour has **no** ratings, else the shown score. `rank_score` (the sort key) is unchanged and keeps the 7.5 prior; `rating_score` is kept for backward compatibility. |
| `tour_rating_service.py` | Finding 2 server (orchestrator `/tour/<id>/rating`): `compute_score` now returns `display_rating` (None when unrated, else the score), so `get_rating`/`record_rating` carry it too. |
| `audio_tour_app/lib/services/tour_rating_service.dart` | `TourRating` gains a nullable `displayRating`; `fromJson` reads `display_rating` (legacy fallback to `rating_score` only when `count > 0`); `isUnrated` getter; `badgeText` shows just `"New"` when unrated, else `"<score> · <label>"`. |
| `audio_tour_app/lib/widgets/rate_tour_dialog.dart` | `TourRatingBadge` gains a nullable `displayRating`; `fromTour` reads `display_rating`; the badge shows just `"New"` (no number) when unrated, else `"<score> · <label>"`. |
| `audio_tour_app/lib/screens/home_screen.dart` | After a rating submission, also set `item['display_rating']` so the badge updates to the new number. |
| `tests/test_local876_544_findings.py` | **New** — 15 server tests for both findings (below). |
| `audio_tour_app/test/rating_badge_new_local876_test.dart` | **New** — 8 Flutter widget/unit tests for the badge. |
| `tests/test_local670_tour_ratings.py`, `tests/test_local685_editor_score.py` | Updated 3 existing exact-dict assertions to the new `display_rating` contract. |
| `run_local876_live.py` | **New** budget-gated live harness (one 3-stop tour, own container, own DB). |

---

## Evidence

### Finding 1 — header style reconciled against the body/evidence

The exact tour-544 Stop 1 block (header `neo-Romanesque`, narration `neo-Gothic`),
run through the new reconciler:

```
BEFORE:  Specific Examples: Stunning neo-Romanesque architecture, beautiful stained glass windows, and a peaceful garden.
         (body: "...its neo-Gothic design...")
AFTER :  Specific Examples: beautiful stained glass windows, and a peaceful garden.
reason:  "Specific Examples: style 'romanesque' contradicts the body/evidence ('gothic') — dropped"
```

The body's `neo-Gothic` is retained; the contradicted header style is gone; the
reconcile is idempotent (a second pass changes nothing). Fact-sheet precedence and
an evidence-only path are both covered by the unit tests. `python -m pytest`:

```
tests/test_local876_544_findings.py::TestFinding1HeaderConsistency
  test_neo_romanesque_header_dropped_when_body_says_neo_gothic PASSED
  test_idempotent                                              PASSED
  test_fact_sheet_style_wins_over_contradicting_header         PASSED
  test_evidence_path_via_reconcile_stop_headers                PASSED
  test_no_style_in_header_is_untouched                         PASSED
  test_agreeing_style_is_kept                                  PASSED
  test_whole_line_dropped_when_only_the_contradicted_style_remains PASSED
  test_full_tour_text_reconcile_runs_over_all_stops            PASSED
  test_style_token_helpers                                     PASSED
```

### Finding 2 — unrated tour shows "New", not 7.5

Server (pure, no DB):

```
tour_rating_service.compute_score([])  → {'score': 7.5, 'count': 0, 'display_rating': None, 'label': 'New'}
tour_rating_service.compute_score([9]) → {'score': 8.3, 'count': 1, 'display_rating': 8.3, 'label': '1 rating'}

map_delivery _rating_payload([],       ...) → display_rating=None, rating_count=0, rank_score=7.5   # 7.5 KEPT for sort
map_delivery _rating_payload([9,9,9,9],...) → display_rating=9.0,  rating_count=4
```

`rank_score` (the "top rated" sort key) still returns the 7.5 prior for an unrated
tour, so list ORDER is unchanged; only the SHOWN number is suppressed.

```
tests/test_local876_544_findings.py::TestFinding2RatingDisplay
  test_orchestrator_compute_score_unrated_display_is_none       PASSED
  test_orchestrator_compute_score_rated_display_is_the_score    PASSED
  test_orchestrator_evaluated_prior_unrated_still_new           PASSED
  test_map_delivery_payload_unrated                             PASSED
  test_map_delivery_payload_rated                               PASSED
  test_map_delivery_rank_score_independent_of_display           PASSED
```

App (Flutter widget test, package `audio_tour_app_dev`):

```
$ flutter test test/rating_badge_new_local876_test.dart
  [LOCAL-876] TourRating.badgeText unrated (display_rating null) → "New", no number  ✓
  [LOCAL-876] TourRating.badgeText count 0 with a prior score still reads "New"       ✓
  [LOCAL-876] TourRating.badgeText rated → "<score> · <label>"                        ✓
  [LOCAL-876] TourRating.badgeText unrated const shows "New"                          ✓
  [LOCAL-876] TourRatingBadge widget unrated tour map → shows "New", not 7.5          ✓
  [LOCAL-876] TourRatingBadge widget legacy server (no display_rating) unrated → "New"✓
  [LOCAL-876] TourRatingBadge widget rated → "8.3 · 2 ratings"                        ✓
  [LOCAL-876] TourRatingBadge widget default badge → "New", no number                 ✓
  All tests passed!  (8/8)
```

### Server unit/integration in an isolated container (D753)

Own postgres `local876-pg` on own network `local876_net`, seeded from
`local821-initdb/01_schema.sql`; pytest run inside the `audioura-tour-generator`
image with `map_delivery/` on the path and `DATABASE_URL` → the isolated DB. The
shared `audioura-*` containers and the live DB were never touched.

```
$ docker run --rm --network local876_net -e DATABASE_URL=...@local876-pg... \
    -v "$PWD":/app -w /app audioura-tour-generator \
    sh -c "pip install -q pytest; python -m pytest \
      tests/test_local876_544_findings.py tests/test_local670_tour_ratings.py \
      tests/test_local672_verified_reviews.py tests/test_local685_editor_score.py \
      tests/test_local866_stop_header.py test_local27_truthfulness.py \
      test_local743_stop_header_split.py test_local536_self_contradiction.py -q"
83 passed, 23 skipped in 1.40s
```

### One 3-stop live tour (header consistency)

```
$ TASK_BUDGET_ID=LOCAL-876 TASK_BUDGET_USD=0.15 python3 run_local876_live.py
request='Saigon centre landmarks, Ho Chi Minh City, Vietnam'  3 stops  cap $0.15
...
[LIVE_RUN_METER] TOTAL $0.0784  (openai $0.0734, serper $0.0050)

--- delivered header lines ---
  Type/Specialty: Market
  Specific Examples: Vibrant stalls selling local handicrafts, fresh produce, and street food delicacies.
  Type/Specialty: Historical Landmark
  Specific Examples: Stunning neo-Romanesque architecture, twin bell towers, and beautiful stained glass windows.
  Type/Specialty: Architectural Landmark
  Specific Examples: Beautiful colonial architecture, a large central hall with a vaulted ceiling, and historical maps on the walls.
------------------------------
   [PASS] delivered header lines are consistent (reconcile is a fixpoint): no change
   [PASS] no neo-Romanesque/neo-Gothic header-vs-body clash shipped: clean
=== LOCAL-876 PASS ===
```

The reconciler is wired into the real path and runs on every stop. In this run the
delivered Notre-Dame body did not state a contradicting style, so the reconcile was
a **fixpoint** (no change) — proving it does not corrupt a consistent tour. The
exact neo-Romanesque→drop behaviour is proven deterministically by the unit test
above with the exact strings.

Spend: **$0.0784** of the $0.15 cap.

---

## Limitations

1. **Live run did not reproduce the exact tour-544 contradiction.** Generation is
   non-deterministic; this run's Notre-Dame body did not mention neo-Gothic, so the
   reconciler was a no-op (fixpoint) on it. The deterministic DROP with the exact
   neo-Romanesque/neo-Gothic strings is covered by the unit test, not the live run.
2. **Style dimension only.** The reconciler treats architectural STYLE as the
   contradiction dimension (the tour-544 defect). Other header attributes
   (materials, dates) are not yet reconciled from the header line — the body-level
   LOCAL-872 claim gate already covers those in the narration.
3. **Fact sheet precedence is style-scoped.** When a stop carries a fact sheet,
   only its architectural style is treated as authoritative for the header lines;
   the fact sheet is not used to REWRITE the whole header line, only to drop a
   contradicting header style.
4. **Pre-existing local-only test failures.** `tests/test_local670` and
   `tests/test_local672` each have map_delivery-loading tests that fail OUTSIDE a
   container (`ModuleNotFoundError: personal_match`, because they load
   `map_delivery/app.py` by file path without `map_delivery/` on `sys.path`). These
   are present identically on the base `0a64fc79` (verified via `git stash`) and
   PASS in the container, where the Dockerfile's `COPY . .` puts the module on the
   path. Not introduced by this change.
5. **Build number not bumped** (per the ticket): the app change is covered by the
   widget test only; `pubspec.yaml` and `BUILD_NUMBERS.md` are untouched.
