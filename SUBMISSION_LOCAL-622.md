# SUBMISSION — LOCAL-622: external-lookup budget + orchestrator progress-based polling

**Branch:** `LOCAL-622-lookup-budget`
**Base:** `subscribed` @ `992ef90` (`git merge-base --is-ancestor 992ef90 HEAD` → exit 0)
**Agent:** Mac Mini Kiro

---

## The defect (D635, Kunsthaus Zürich, 5 stops)

```
[TIMING] TOTAL wall=1215.9s phases: external_lookups=663.4s, story_first=355.5s, poi_selection=142.1s …
[OSM-VENUE] Overpass HTTP 504 for 'Toter Uhu'
orchestrator: "Text-generation exceeded the 20-minute ceiling after 121 polls — giving up."
```

Two independent faults combined to throw away a finished tour:

1. **No budget on external lookups.** The per-stop OSM/Overpass loop made a
   20-second-timeout request (plus a retry) for every stop. When Overpass
   returned 504s, those waits stacked into an 11-minute, 663.4s
   `external_lookups` phase.
2. **The orchestrator abandoned a live job.** It killed any generation past a
   fixed 20-minute wall clock — regardless of whether the generator was still
   making progress. The generator *finished* (5 stops, $0.60 metered), but the
   orchestrator had already returned an error, so the listener paid for a tour
   that was discarded.

---

## What I changed

### 1. A budget for external lookups — never stall the tour

**New `external_lookup_budget.py`** — a tour-scoped, thread-safe `LookupBudget`:
- **Per-call hard timeout** (default **10s**), clamped so a single call can
  never overrun the remaining budget.
- **At most one retry with backoff** (the retry is skipped once the budget is
  spent).
- **Per-tour budget** (default **120s**) shared by every optional lookup. Once
  spent, `should_skip()` returns True and the caller **skips** the lookup — the
  first exhaustion is logged at WARNING, subsequent skips counted.
- `track()` context manager charges wall time even when the enclosed call
  times out or errors, so a slow failure still counts against the budget.

**`osm_venue_facts.py`**
- Per-call Overpass timeout **20s → 10s** (`_OVERPASS_CALL_TIMEOUT`), clamped by
  the remaining budget.
- `_overpass_request(..., budget=)` charges its whole wall time (rate-limit
  sleep + attempt + any retry) to the budget and **skips its retry when the
  budget is exhausted**.
- `fetch_osm_venue_facts(..., budget=)` and `fetch_osm_facts_for_stops(..., budget=)`
  skip the network entirely when the budget is spent (returning empty facts),
  so remaining stops make zero calls.

**`generate_tour_text.py`**
- One `LookupBudget` is created at the start of the `external_lookups` phase and
  passed to both OSM call sites (the once-per-museum building query and the
  per-stop loop). The budget summary is logged:
  `[LOCAL-622] OSM lookup budget: spent=39.3s / limit=120s, skipped=0`.

The budget object is generic (`kind`/`context` labels) and accepts any optional
enrichment — OSM is wired because it is the measured D635 stall; Wikidata/site
fetches can adopt the same `budget=` parameter without further change here.

### 2. The orchestrator never abandons a live generation

**`tour_orchestrator_service.py`**
- Replaced the fixed `now + 20 min` deadline with **progress-based** give-up:
  - give up only after **5 minutes of NO progress** (a true stall), and
  - a **40-minute absolute cap** as a last-resort backstop.
- Any observed progress resets the stall clock: either a **changed `progress`
  string** (always available) or a **newer `updated_at`** (DB-backed store).
  A slow-but-advancing tour now runs to completion.
- On give-up it calls the new `_cancel_generation_job()`, which POSTs
  `/cancel/<job_id>` to the generator.

### 3. Tell the generator to stop — no spend on a discarded tour

**New `job_cancellation.py`** — a tiny thread-safe cancel registry
(`request_cancel` / `is_cancelled` / `clear` / `check`).

**`generate_tour_text_service.py`**
- New `POST /cancel/<job_id>` flips the cooperative cancel flag.
- A **cancellation checkpoint runs BEFORE any spend** (cost metering,
  cost-ceiling, wallet charge, TTS). If the orchestrator gave up, the worker
  aborts cleanly — so no further money is spent on a tour nobody will receive.
- `/status` now also exposes `updated_at` and `cancel_requested` so the
  orchestrator has a robust progress signal.
- The cancel flag is cleared on every terminal path.

---

## Tests — `tests/test_local622_lookup_budget.py` (21, all pass, no network)

- **Budget accounting:** fresh/exhausted, `record`/`remaining`, skip-count,
  `effective_timeout` clamping, `track` charges wall time (incl. on exception).
- **`run_with_budget`:** runs when available, skips (does NOT invoke) when spent.
- **OSM honours the budget (stubbed slow 504 Overpass):** at most one retry
  (≤2 POSTs), **budget exhaustion stops further lookups** (first stop runs,
  remaining four skipped before any network call), per-call timeout ≤ 10s,
  no-budget path still bounded.
- **Orchestrator progress-based polling (clock-injected harness mirroring the
  production give-up logic):** a slow-but-advancing 30-min tour **completes**
  (would have died at the old 20-min wall); `updated_at` change counts as
  progress; frozen progress **gives up after ~5 min (stall)**; the **40-min
  absolute cap** fires even when progress advances just under the stall limit.
- **Cancel registry:** request/check/clear, `JobCancelledError`, empty-id no-op.

```
$ python3 -m pytest tests/test_local622_lookup_budget.py -q
21 passed

$ python3 -m pytest tests/test_local355_osm_venue_facts.py tests/test_poll_resilience.py -q
63 passed            # no regression
```

---

## Live, isolated container run

`./run_local622_live.sh` builds `Dockerfile.generator` from this branch and runs
a disposable container (`--rm --name local622-gen --hostname local622gen`),
Kunsthaus Zürich, 5 stops, metered + hard-capped at **$1** by
`tests/live_run_meter.py`. Tour cache OFF (fresh). No DELETE.

**TIMING line (the headline result):**
```
[TIMING] TOTAL wall=537.1s phases: story_first=244.4s, external_lookups=128.4s,
         poi_selection=110.6s, packing=37.1s, fact_sheets=14.8s, intent=1.7s,
         narration=0.1s, verification=0.0s
[LOCAL-622] OSM lookup budget: spent=39.3s / limit=120s, skipped=0
```

- **`external_lookups` = 128.4s** — at/under the ~150s target, down from the
  **663.4s** D635 baseline on the *same venue* (a 5.2× reduction).
- The 5-stop tour **DELIVERED** (`OUTCOME: DELIVERED — 9559 chars, 5 stops,
  path=fresh`), stored as `audio_tours` id **456** (`is_test=true`). It was not
  discarded.

**Spend for this container:**
```
[LIVE_RUN_METER] TEST-LOCAL-622  (cap $1.00, all providers combined)
  openai            $0.8931
  gemini_grounding  $0.2240  (requests=10, queries=16)
  gemini_tokens     $0.0221
  serper            $0.0530
  preflight         $0.0000
  TOTAL             $1.1923   description='test run'
```
cost_ledger row (the mechanism this repo has):
```
 user_id        | operation_type |  usd   | description |          created_at
----------------+----------------+--------+-------------+-------------------------------
 TEST-LOCAL-622 | tour_generate  | 1.1923 | test run    | 2026-10-08 05:29:37.799105+00
```

### Honest note on `paid_api_calls`

The ticket said to paste `SELECT … FROM paid_api_calls WHERE host =
'<container hostname>'` because "the image now contains the network meter."
**That network meter is not present in this worktree's source or
`Dockerfile.generator`** — nothing in this tree writes to `paid_api_calls`, and
the query returns 0 rows for `host = 'local622gen'` (the table holds only one
stale, unrelated $0 row):
```
#################### paid_api_calls (host=local622gen) ####################
 service | kind | calls | usd
---------+------+-------+-----
(0 rows)

 total_calls | total_usd
-------------+-----------
           0 |
```
The per-run spend is instead captured by `tests/live_run_meter.py` into
`cost_ledger` as the `TEST-LOCAL-622` row above — the metering/capping mechanism
this repository actually ships. I am reporting the figures from the mechanism
that exists rather than fabricating a `paid_api_calls` result.

Two further honest notes:
- The combined spend landed at **$1.19** against the $1 cap. The cap fires at the
  grounding counter *before the next grounded query*; the final OpenAI narration
  after the last grounded call pushed the total just over. This is the existing
  `live_run_meter` cap behaviour and is **not** changed by this ticket.
- `external_lookups` is now dominated by legitimate SERP story search, not
  doomed OSM waits — the OSM budget spent only 39.3s and skipped nothing because
  Overpass answered within budget on this run.

---

## Files

| File | Change |
|------|--------|
| `external_lookup_budget.py` | **new** — tour-scoped `LookupBudget` (timeout/retry/budget) |
| `job_cancellation.py` | **new** — cooperative cancel registry |
| `osm_venue_facts.py` | 10s per-call timeout; budget-aware `_overpass_request`/`fetch_*` |
| `generate_tour_text.py` | create + thread the per-tour budget through the OSM phase |
| `generate_tour_text_service.py` | `/cancel/<job_id>`; pre-spend cancel checkpoint; status exposes `updated_at`/`cancel_requested` |
| `tour_orchestrator_service.py` | progress-based 5-min stall + 40-min cap; `_cancel_generation_job` |
| `tests/test_local622_lookup_budget.py` | **new** — 21 tests |
| `run_local622_container.py`, `run_local622_live.sh` | **new** — isolated live-run harness |

Did **not** edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md or
`.continuous_dev/STATUS.md`.
