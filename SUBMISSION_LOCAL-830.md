# SUBMISSION — LOCAL-830

**Branch:** `LOCAL-830-pool-category`
**Base:** subscribed (`7d65854a`) — `git merge-base --is-ancestor 7d65854a HEAD` → 0.

A restaurant (Sandals Restaurant) was served as a stop in a kite-school tour, and
the phone sent one Generate tap as two `/generate-complete-tour` requests 1 s
apart. Three independent fixes.

---

## 1. How Sandals Restaurant got in — pool reuse, not fresh selection

Evidence (GCloud_Storied 2026-10-30 03:12, tour 502): "Kitesurf schools … Mui Ne"
→ Jibe's Beach Club, Muine Kitesurf School, C2Sky KiteSurfing, Palm Kite Club,
**Sandals Restaurant**. The same wrong stop appeared the previous night → reused
from the **stop pool**.

The fresh path keeps a business/places tour on-category two ways:
* PHASE 4 `_verify_against_intent` (needs the LLM `intent['poi_type']`), and
* the LOCAL-791B `category_match_guard.filter_off_category` (fires only on a
  plural CATEGORY noun — "pagodas", "temples"; **empty** for "kitesurf schools").

Neither runs on a **pooled** stop at reuse time. The reuse path
(`stop_pool_orchestrator`) had scope re-validation (LOCAL-788), junk-title reject
(LOCAL-792) and a museum-source check (LOCAL-811, contained tours only) — but **no
on-category check for a business/places tour**. So the pool served the
off-category restaurant.

Confirmed before the fix:
`requested_categories("Kitesurfing schools in Mui Ne")` → `set()` (guard is a
no-op); `classify_place("Sandals Restaurant", "Restaurant")` → `"restaurant"`.

## 2. Category-scoped reuse — on-category check applied to POOLED stops

`category_match_guard.py` (new, deterministic + offline):
* `is_food_request(request)` — is the request SUBJECT about food/dining?
* `business_off_category_class(request)` — for a request whose SUBJECT is a
  business/activity provider that is **not** about food (kite school, dive shop,
  yoga studio, surfboard rental, gym), returns `"restaurant"` (food is
  off-category); a food request ("seafood restaurants") or a non-business request
  (museums, pagodas, a plain walking tour) returns `None` (no-op). Uses the SAME
  classifier the fresh places router uses
  (`stop_existence_gate.classify_business_vs_landmark`) on the request subject, so
  the reuse path and the fresh path agree on what "a business request" is.
* `filter_off_category_business(rows, request, …)` — **skips** (never deletes) a
  pooled row classified as food for a non-food business request. A row the user
  named is always kept; an unclassifiable row is kept. Returns `(kept, skipped)`.
* `_candidate_category_text` now also reads a pooled row's `type_specialty`
  (a reused stop carries no Serper record).

`stop_pool_orchestrator.py` — wired into the reuse fast path right after the
LOCAL-788 scope re-validation, gated on `not contained` (so museum/facility tours
are untouched). **Skip-only: the pool row is never deleted** — it stays reusable
for the categories it matches (category-scoped reuse, ticket item 2). If K then
falls below N the existing N>K path researches the remainder fresh, exactly as if
the off-category stop had never been pooled.

## 3. Flutter double request — in-flight guard + client request id

`audio_tour_app/lib/screens/tour_generator_screen.dart`. Root cause: `_isGenerating`
was set true only AFTER the pre-request awaits (`_checkDuplicateTour` +
`_showDuplicateDialog`), so a second tap in that ~1 s window slipped past the
`if (_isGenerating) return` guard and sent a second request.

Fix: a **synchronous** `_generateInFlight` flag flipped true before any await and
cleared in a `finally` (applied to both `_generateTour` and
`_generateTourBackground`), plus a per-attempt `client_request_id`
(`cli-<ts>-<64-bit secure-random hex>`) sent in the request body of both POST
paths.

## 4. Server idempotency — duplicate client request id within 60 s = same job

`tour_orchestrator_service.py`. `/generate-complete-tour` reads
`client_request_id` and atomically reserves a job id for it
(`_reserve_idempotent_job`, one lock = prune + lookup + insert, race-safe). A
duplicate submission within `_IDEMPOTENCY_WINDOW_SECONDS` (60 s) returns the SAME
`job_id` (`idempotent_reuse: true`) and starts **no** second generation. An absent
key turns idempotency off (unchanged behaviour).

---

## Tests

* `tests/test_local830_category_scoped_reuse.py` — 15 tests: business-class
  detection (kite/dive/yoga/surf/gym → restaurant off-category; seafood/cafes →
  no-op; museums/pagodas/walking → no-op); the tour-502 fixture (kite tour
  excludes Sandals, keeps the kite schools); a seafood request keeps restaurants;
  unclassifiable + named-anchor kept; input list never mutated; orchestrator
  wiring import; server idempotency (dup → same job, distinct ids → distinct,
  absent id not idempotent, expiry > 60 s → new job).
* `audio_tour_app/test/local830_double_request_guard_test.dart` — 5 tests: client
  id prefix + uniqueness (100 distinct); two near-simultaneous taps → ONE request;
  a tap in the pre-request window dropped; a later tap → a second, distinct
  request.

Result: **15 Python + 5 Dart pass.** Regression on the pool/category suite
(830 + 791b + 791c + 788 + 811): 49 passed, 3 skipped (the LOCAL-811 DB tests skip
with no Postgres URL). `dart analyze` on the screen: clean.

## Live — BUDGET LOCAL-830 $0.60 (meter contract, own containers)

`run_local830_live.sh` + `run_local830_container.py` +
`docker-compose.local830-proof.yml`: an OWN `-p local830` throwaway Postgres
(tmpfs, port 55830), the real generator in a disposable container with the
worktree mounted, **POOL ON**, budget `TASK_BUDGET_USD=0.60` /
`TEST_GEMINI_MAX_USD=COST_HARD_LIMIT_USD=0.60`, metered by `tests/live_run_meter.py`.
Seeded a pooled "Sandals Restaurant" + 6 kite schools for Mui Ne, requested
"Kitesurfing schools in Mui Ne, Vietnam" (5 stops).

`reports/local830_live_proof.txt`:
* `delivery_path = pool` (the reuse path);
* guard logged `off-category reuse skip 'Sandals Restaurant'` and
  `category-scoped reuse: skipped 1 off-category food stop(s)`;
* delivered 5 stops — all kite schools, **NO restaurant**;
* pool AFTER still holds Sandals Restaurant (**skip, not delete**);
* **TOTAL $0.0000** — N ≤ K served entirely from the pool, no new generation.

Exit 0, clean `down -v` teardown, shared `audioura-*` containers untouched, live
DB never written. (The double-request fix is client-side Dart and is covered by
the Dart test modelling the exact guard mechanism; no simulator spend needed.)

## Files

Modified: `category_match_guard.py`, `stop_pool_orchestrator.py`,
`tour_orchestrator_service.py`,
`audio_tour_app/lib/screens/tour_generator_screen.dart`.
New: `tests/test_local830_category_scoped_reuse.py`,
`audio_tour_app/test/local830_double_request_guard_test.dart`,
`run_local830_container.py`, `run_local830_live.sh`,
`docker-compose.local830-proof.yml`, `reports/local830_live_proof.txt`,
`SUBMISSION_LOCAL-830.md`.
