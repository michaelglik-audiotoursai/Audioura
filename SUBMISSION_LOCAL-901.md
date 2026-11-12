# SUBMISSION LOCAL-901 — durable job heartbeat, place-level pin reference, 791E structure dedupe, single-place filler

Branch `LOCAL-901-progress-and-place-pin`, base f66153bd (subscribed). **Budget: $0** — offline tests only, no live run,
no paid call, Wikidata/Nominatim mocked. No DB write, no shared container touched.

## A0. Root cause and fix (replaces A1/A3)
Cause as stated in the task: `heartbeat_at` was added to /status only when `JOB_THREADS[job_id]` was alive on the
answering instance; on a second instance the DB fallback carried none, and `updated_at` never moved.

* **Durable heartbeat** — new `job_heartbeat.py`. `HeartbeatTicker` is started at the top of `generate_tour_async`
  (stopped in its `finally`) and writes `heartbeat_at` (+ `heartbeat_note`) through the existing `ACTIVE_JOBS` store every
  30 s. The `generator_jobs` upsert already bumps `updated_at` and merges extra keys into the `result` JSONB, which
  `GeneratorJobsStore.get` flattens back out — so **no schema change, no new column, no `ADD COLUMN`**. The ticker never
  writes status/progress, so it cannot clobber a terminal state.
* **/status DB fallback** (`generate_tour_text_service.py`) returns the stored `heartbeat_at` for a non-terminal job when
  this instance does not own the thread (the owning instance still answers `now()` as before).
* **Orchestrator belt-and-braces** — the watchdog logic is extracted to `StallWatchdog` (`tour_orchestrator_service.py`),
  used by the poll loop. Old rule kept (changed `(progress, updated_at, heartbeat_at)` marker resets the clock); new:
  `status='processing'` with `heartbeat_at`/`updated_at` ≤ 90 s old is alive wherever it came from. Timestamps >5 s in the
  future (tz-skewed DB clock) are not trusted, so a skew cannot pin a dead job "alive" forever. Consequence: the last
  credit can run up to 90 s past the last real heartbeat, so a dead worker is given up ~5–6.5 min after its last beat.

## A1. Phase / stop / post-pass heartbeats (`_hb_beat(job_id, label)`, no-op without a registered job)
Start of PHASE 1, 3A, 4, after 3B, D556 replenish+lore (+ one per stop in the lore loop), PHASE 5 start, each Phase-5
stop at start (parallel worker) and done (as_completed), story gate (+ per stop), story verification (+ per stop), PHASE 6,
key-fact coverage / finalize_tour, 897/898 post pass, and the delivery guards (`_apply_delivery_hours_guard` now takes
`job_id`: route content / finalize_898 / single-place guards). The D556/427 page-fetch pool inside `story_first` has no
job id; the 30 s ticker covers it.

## A2. Timing
`finalize_898` + `drop_fragments` + `apply_single_place_guards` on the 551 fixtures: **6 ms / 2 ms** (limit 1 s). Adversarial
bodies (5 KB, 50 sentences, 45 long comma clauses, 6 KB no punctuation, 1500 commas): all < 40 ms. 900/900B added no slow step
and no backtracking. Tests assert < 1 s.

## A3. Why waves 46/47 survived (answer to item 3)
Luck of topology, not a progress call 900/900B moved. Progress text is set only at job start and end in every wave;
`git log` shows 900/900B did not touch `generate_tour_text_service.py` or `job_store.py` (last touches: LOCAL-896 preview-stops
code, LOCAL-833). In waves 46/47 one generator instance answered every poll, so `JOB_THREADS` was alive and `heartbeat_at`
was present; wave 48 had two instances and 30/32 polls hit the one without the thread. The same input ran 666 s / 760 s,
both > 5 min, so any multi-instance moment kills a long tour on any revision — now fixed.

## A4. NameError
`[LOCAL-355] … name 'venue_name' is not defined`: `_museum_venue_name or venue_name` → `_museum_venue_name or location`
(`venue_name` is bound nowhere in the impl).

## A5. Fetch log (no selection change)
`story_first.fetch_full_pages` logs `[LOCAL-901] page fetch: N url(s), K social/video host(s)` (facebook, youtube/youtu.be,
instagram, tiktok, twitter/x, pinterest). Off-topic pages cannot be detected by host; left for the later task.

## B. Place-level pin reference
`area_resolver.first_named_place_reference`: when the neighbourhood part of the request is not on Wikidata (or has no P625)
and the centre falls back to the city, try the first named place (split on " and ", "&", ",", " – ", " - ") via the existing
`_wikidata_name_lookup`. Accept only within 100 km of the coarse centre or inside the city's geocoder bbox; refused otherwise
(`REFUSED` logged). Stored on new `AreaResolution.place_ref_*` fields (precision `place`, source `first_named_place`); the
scope centre/radius are unchanged. The GEO-CHECK-skipped pin check in `generate_tour_text.py` prefers it over any
city/province centre, so 900B's check can use it. Logs `[LOCAL-901] place reference '<name>' → lat,lng (first_named_place)`.
Tests (lookup mocked): 552 shape → both model pins (29.5 km off) replaced to within 15 km; lookup abroad → refused and the
coarse centre still `skipped_coarse_ref`.

## C. 791E dedupe
New `distinct_sites_901.distinct_sites(a, b)` veto, consulted first by `walking_stop_title._same_place` (the 791E title
dedupe) and by `local802_relevance_gate.same_building` (located-in / ≤60 m coordinate signals). A structure word (statue,
pagoda, temple, station, museum, cable car, …) vs a container-only name (mountain, park, area, …) is always distinct; two
structures with disjoint proper-noun cores are distinct. Same QID, shared name/alias, and two structures at the same
*street* address (house number) still merge (existing LOCAL-791C bilingual-address test kept green).

## D. Single-place filler
`route_content_896.cap_single_place_filler` (called from `apply_single_place_guards` for ≤2 stops when no route is active):
a sentence with no digit that has ≥2 mood terms, or 1 mood term and is not `_supported` by the stop's title / Type /
Specific Examples (/evidence if given), is dropped — in stop bodies and in the closing paragraph (supported by all stops).
`That's N stops` and the restaurant offer are untouched; a body that would be emptied is left as it was; idempotent.
Generic fixture `tests/fixtures/local901_tour552_filler.txt` (all three listed fillers removed, facts kept).
Judgement call: this also drops purely atmospheric sentences like "…symbolizing peace and serenity" on ≤2-stop tours.

## Tests
`tests/test_local901_progress_and_place_pin.py` — 32 tests (two fake instances sharing one fake store + real `/status`
route; watchdog with a fake clock: silent while the heartbeat advances over 12 min, fires ≥5 min after it stops; phase/stop
beats; timing; B; C; D). Required set (`test_local89[6-9]*`, `test_local90*`, `894*`, `87*`, `88[0-9]*`, `89[0-3]*`,
deselecting `test_local88_tour_pollution.py`): **976 passed, 4 skipped**; plus 791/802/833/622/751/858/790/852 suites:
1190 passed, 6 skipped in the combined run. **Pre-existing, unrelated failure** (also fails on the base without my changes):
`tests/test_local775_generator_job_store.py::test_orchestrator_tolerates_transient_404_then_succeeds`.

## Not verified
No live/multi-instance cloud run (budget $0): the two-instance behaviour is proven with a fake shared store, not Cloud Run.
The real `GeneratorJobsStore` SQL path for the heartbeat write was not exercised against Postgres here (the upsert code is
unchanged; it merges unknown keys into `result`). The 552 pin replacement is shown at the `check_pins_against_scope` level
with the real `resolve_area`; the full `generate_tour_text` pipeline was not run.

## Files
`job_heartbeat.py` (new), `distinct_sites_901.py` (new), `generate_tour_text_service.py`, `generate_tour_text.py`,
`tour_orchestrator_service.py`, `area_resolver.py`, `walking_stop_title.py`, `local802_relevance_gate.py`,
`route_content_896.py`, `story_first.py`, `tests/test_local901_progress_and_place_pin.py`,
`tests/fixtures/local901_tour552_filler.txt`, `SUBMISSION_LOCAL-901.md`. No schema change.
