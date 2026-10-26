# SUBMISSION — LOCAL-774: Free-level refusal reaches the app as a structured refusal, not "Tour Generation Failed"

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-774-free-refusal-dialog` (from `subscribed` @ `572a4844`)
**Base verified:** `git merge-base --is-ancestor 572a4844 HEAD` → exit 0.

## What Michael saw (TestFlight 2.4.32 (79), Subscribed cloud, 2026-10-26 16:07)
A fresh Free install asked for "Gyms near me, West Roxbury, MA" (2 stops, priced $3) and got a
generic red **"Tour Generation Failed — Error in tour text generation: This place hasn't been
researched yet on the free level."** with only Dismiss / Try again. That is the LOCAL-597
by-reference refusal (`error_code=by_reference_no_material` + a `suggestion` string + up to 3
`nearby_tours`). The structured fields were lost between the generator, the orchestrator job
status, and the app, so only the prefixed `error` string survived and the app showed its generic
dialog.

## Root cause — the structured refusal survives the generator but is dropped downstream

The refusal is BORN complete and stays complete through the tour-generator. It is dropped THREE
times after that (orchestrator ×2, worker ×1) and then MIS-READ once by the app.

### End-to-end trace (each hop, file:line)

| # | Hop | File:line | State |
|---|-----|-----------|-------|
| 1 | Generator sets the refusal | `generate_tour_text.py:9526-9534` (and the two DATABASE_URL/except fallbacks `:9463`, `:9479`) | ✅ all 4 fields set on `_J._LAST_CLEAN_FAIL_EVIDENCE` |
| 2 | Generator-service reads evidence | `generate_tour_text_service.py:330-337` → stores via `ACTIVE_JOBS.update(..., **_error_extra)` at `:409` | ✅ `error_code`/`message`/`suggestion`/`nearby_tours` all carried |
| 3 | Generator-service `/status` | `generate_tour_text_service.py:1327-1331` | ✅ forwards all 4 |
| 4 | **Orchestrator text-gen poll loop** | **`tour_orchestrator_service.py:1606`** prefixes `error_msg = f"Error in tour text generation: {…}"`; **`:1611`** copied only `error_code`/`message`/`suggestion` into `ACTIVE_JOBS` — **`nearby_tours` dropped** | ❌ |
| 5 | **Orchestrator outer except** | **`tour_orchestrator_service.py:2483`** `ACTIVE_JOBS[job_id]["error"] = str(e)` stores the PREFIXED string | (legacy `error`) |
| 6 | **Orchestrator `/status` (memory)** | **`tour_orchestrator_service.py:2998`** emitted ONLY `response["error"]` | ❌ PRIMARY DROP |
| 7 | **Orchestrator `/status` (database / background)** | **`tour_orchestrator_service.py:3043`** emitted ONLY `response["error"]` | ❌ PRIMARY DROP (Generate in Background) |
| 8 | **Worker background poll** | **`tour_worker_service.py:320`** `raise Exception(f"Text generation error: {…}")` — structured fields dropped; `run_job` terminal write `:569` wrote only `error` | ❌ |
| 9 | **App resolver** | **`tour_error_resolver.dart`** message precedence put `error` (prefixed) BEFORE `message`; `kRefusalActions` had no `by_reference_no_material`; `suggestion` parsed only as a `{label,request,tour_type}` MAP (server sends a STRING); `nearby_tours` not parsed | ❌ |
| 10 | **App screen** | **`tour_generator_screen.dart:878`** status-poll error always called `_showTourErrorDialog` (the generic red "Tour Generation Failed") | ❌ |

"Generate Now" flows through the orchestrator thread path (hops 4-6); "Generate in Background"
flows through the Cloud Tasks worker + DB path (hops 7-8). Both end at the same app `/status`
reader (hops 9-10), so both showed the same generic dialog.

## The fix

### Server — `tour_orchestrator_service.py`
- Poll loop (hop 4): forwarded key set widened to `("error_code", "message", "suggestion", "nearby_tours")`, so `nearby_tours` survives. The prefixed string stays only in `error` (legacy); `message` stays the clean copy.
- `/status` memory error branch (hop 6): now loops those four keys from the job into the response.
- `/status` database error branch (hop 7): now loops those four keys from `db_job` (merged from `output_data`) into the response — covering Generate in Background.

### Server — `tour_worker_service.py`
- New `TextGenRefusal(Exception)` carrying a `.structured` dict.
- The text-gen poll loop (hop 8) raises `TextGenRefusal` with the four fields when the generator's `/status` is an error.
- `run_job`'s terminal `update_job_status('error', …)` passes `**getattr(e, "structured", {})`, so the fields land in `job_status.output_data` and `_read_job_from_db` → `/status` forwards them.

### App — `audio_tour_app/lib/utils/tour_error_resolver.dart`
- `kRefusalActions['by_reference_no_material'] = TourRefusalAction.buyPack`.
- Message precedence: when the server sent an `error_code` AND a non-empty `message`, prefer `message` over `error` — so the clean copy wins and the "Error in tour text generation:" prefix is NEVER shown for a structured refusal. (Pre-581 / no-`message` failures still fall back to `error`.)
- New `NearbyTour` model (`tryParse {id,name}`); `ResolvedTourError` gains `suggestionText` (the server `suggestion` when it is a plain String) and `nearbyTours`.

### App — `audio_tour_app/lib/screens/tour_generator_screen.dart`
- Status-poll error branch (hop 10): `error_code == 'by_reference_no_material'` routes to the new `_showByReferenceRefusalDialog`; every other failure keeps the existing error dialog.
- New dialog: title **"Not available on the Free level yet"** (indigo `info_outline`, no red error icon), body = clean `message` + `suggestionText`, each `nearby_tours` entry a tappable `ListTile` that opens that tour via the existing `_downloadBackgroundTour({'id','title'})` (orchestrator `/download/<id>`), and a **Buy a pack** button → `PlanScreen`.

## Part 3 answers

### Empty `nearby_tours` suggestion
Already correct and unchanged: `l2_by_reference._refusal` uses
`NO_MATERIAL_SUGGESTION_NONE = "Buy a $10 pack for a freshly researched tour."` when no nearby
tour is found (and the generator's two DATABASE_URL/except fallbacks hardcode the same string).
So a refusal with an empty list still tells the listener how to get a tour.

### Does `l2_by_reference` reuse consider Stable (beta/storied) originals? — REPORT ONLY (LEAD rules)
**No — but not because it filters them out; because of what the DB it reads contains.**
`l2_by_reference._existing_tour_stops` / `gather_material` (and the stop-pool it reads) select from
`audio_tours` with **only** `original_tour_id IS NULL AND is_test IS NOT TRUE` and a same-venue
identity match — there is **no `track` filter** in the reuse path. LOCAL-770's
`SUBSCRIBED_STABLE_MIN_SCORE` lives entirely in **map-delivery's listing** path
(`map_delivery/app.py:_track_filter_clause`, gated on `track IN ('beta','storied')` or NULL and
`editor_score >= threshold`); **generation reads none of it**. So on the Subscribed cloud the reuse
query would in principle pick up a Stable original — *if that original's row exists in the Subscribed
database*. The Subscribed deployment is its own track (`track='subscribed'`, LOCAL-737/D708) with its
own data; a beta/storied original scored by LOCAL-770 is only reusable by Free here if its row is
actually present in the Subscribed DB.

**What would let Free reuse the Stable originals LOCAL-770 lists (NOT implemented):** make the
by-reference reuse apply the *same* admission LOCAL-770 uses for listing — in `gather_material` /
`_existing_tour_stops`, when running on the Subscribed deployment (`DELIVERY_TRACK_FILTER=subscribed`),
widen the `audio_tours` select to ALSO admit `track IN ('beta','storied')` (or NULL) originals whose
`editor_score >= SUBSCRIBED_STABLE_MIN_SCORE`, in addition to `track='subscribed'`. That is a reuse-
admission change (one WHERE clause, env-gated, off by default), and it only helps if those Stable rows
are visible in the Subscribed DB. **Deferred to LEAD.**

## Tests (red → green)

New:
- `tests/test_local774_refusal_status_forwarding.py` — orchestrator `/status` emits all four fields on BOTH the memory and the database branches, and `message` is never the prefixed string. (4 tests)
- `tests/test_local774_worker_background_refusal.py` — the `/run-job` background route's terminal `update_job_status('error')` carries the four fields. (1 test)
- `audio_tour_app/test/by_reference_refusal_local774_test.dart` — the real `TourGeneratorScreen` shows the plan dialog ("Not available on the Free level yet", Buy a pack, tappable nearby tours) and NOT "Tour Generation Failed" / "Error in tour text generation:" for a by_reference refusal. (3 tests)

All green after the fix. Regression run (base vs branch):
- Flutter (touched): `tour_error_resolver_test` + `refusal_action_test` + `tour_error_actionable_test` + `by_reference_refusal_local774_test` = **29 passed**. `flutter analyze` on both touched Dart files: no error-severity issues.
- Python: new (5) + `test_local717_job_status_version` + `test_local597_guard` + `test_poll_resilience` = **32 passed**; `test_local597_by_reference` + `test_local770_subscribed_lists_best_stable` = **19 passed** (dev DB reachable).
- `test_local476_orchestrator_empty_type` shows 3 failures that are **pre-existing on the base** (`git stash` confirmed identical) — a `subscription_levels` `'level'` DB-seed issue, unrelated to LOCAL-774.

## Live test (own process, spare port, $0; no `audioura-*` container touched)
- `run_local774_status_proof.py` runs the FIXED orchestrator Flask app on spare port **15002**, seeds a by_reference error job, and curls `/status` over real HTTP. Output (`screenshots_LOCAL-774/orchestrator_status_poll.json.txt`) shows all four fields with the CLEAN `message` (no prefix).
- Android emulator **`local715_test`** (mine — never Michael's phones): `flutter drive` of `integration_test/local774_refusal_dialog_screenshot_test.dart` with a `MockClient` serving the refusal ($0, no live server). Screenshot `screenshots_LOCAL-774/android_by_reference_refusal_dialog.png`: the dialog titled "Not available on the Free level yet", the clean message, the suggestion line, "Nearby tours you can open now:" West Roxbury Walk + Roslindale Square, and the Buy a pack button — with both **Generate Now** and **Generate in Background** visible behind it (both route through the same status poll). Emulator shut down afterwards (`adb emu kill`).

## Files changed
- `tour_orchestrator_service.py` — poll-loop forwards `nearby_tours`; `/status` memory + DB error branches emit the four structured fields.
- `tour_worker_service.py` — `TextGenRefusal` carrier; background path forwards the four fields into `job_status.output_data`.
- `audio_tour_app/lib/utils/tour_error_resolver.dart` — `NearbyTour`, `suggestionText`, `nearbyTours`, clean-message precedence, `by_reference_no_material` → Buy a pack.
- `audio_tour_app/lib/screens/tour_generator_screen.dart` — `_showByReferenceRefusalDialog` + routing.
- Tests + live-proof script + screenshots as listed above.
