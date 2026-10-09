# SUBMISSION — LOCAL-645

**Cost prototype 1: one grounded Gemini research pass per MUSEUM, not per stop.**
Flag `GEMINI_PER_VENUE`, default **OFF**.

- **Agent:** Mac Mini Kiro
- **Branch:** `LOCAL-645-gemini-per-venue` (from `subscribed` @ `17aa7a4b`)
- **Parallel with LOCAL-644.** Only `story_leads.py` and its callers were touched.
  No pool or assembly code was edited.
- **ZERO paid calls.** No live tour was generated; OpenAI / Gemini / Serper were
  never called. Everything below is proved offline with unit tests, injected
  fakes, and the stored `story_loop_candidates.jsonl`.

---

## 1. Measure first (offline)

The authoritative sources named in the ticket — the `paid_api_calls` table and
`.continuous_dev/bench/R*/generator.log` — are **not reachable from this
worktree**: the DB host `postgres-2` is a container-only name (confirmed
`OperationalError: could not translate host name "postgres-2"`), there is no
`DATABASE_URL` in the worktree environment, and no `bench/R*` logs or
`PRICE_CARD.md` are checked out here. So the measurement is built from the two
deterministic sources that ARE present. Reproduce with:

```
python3 measure_local645_overlap.py      # writes LOCAL645_overlap_measurement.json
```

### (A) The grounded-call map — which story_leads calls are search-enabled

Every grounded Gemini request in a fresh tour is issued at exactly three sites,
and the per-tour count is a function of the stop count `N`:

| site | file | grounded requests / tour |
|---|---|---|
| venue preflight | `venue_preflight.py` | 1 |
| D511 per-stop narrate (r1) | `story_production_loop.py` | `N` (LOCAL-594 cap = 1/stop) |
| step-4 lead fan-out | `generate_tour_text.py` | 0 (`STORY_LEADS_GROUNDED` default off) |

So the shipped (post-LOCAL-594) state issues **`N + 1`** search-enabled requests
per fresh tour: **4 at 3 stops, 6 at 5 stops**. Before the LOCAL-594 cap each
stop ran up to `MAX_CREDIT_LINES`(4) × 2 grounded calls, i.e. up to **28 / 46**
per 3-/5-stop tour — the "~7 search-enabled requests per 3-stop tour" the morning
report cites is in this pre-cap band. We report both so the figure is honest
either way.

### (B) How much the per-stop calls overlap

`story_loop_candidates.jsonl` records every grounded credit_line pass the D511
loop ran, grouped by work, with the story text each produced. Many passes ask
about the **same museum and the same works from slightly different angles**:

| work | grounded passes | distinct angles | mean overlap | max overlap |
|---|---:|---:|---:|---:|
| Le Lézard aux plumes d'or | 273 | 4 | 1.00 | 1.00 |
| Le Lézard … (The Lizard …) | 38 | 5 | 0.17 | 0.91 |
| Moses and Monotheism | 24 | 14 | 0.21 | 0.45 |
| Au Soleil du Plafond | 22 | 12 | 0.31 | 0.54 |
| Le Lézard … (The Lizard …) | 12 | 4 | 0.12 | 0.69 |
| The Great Good Man | 8 | 7 | 0.24 | 0.56 |
| That Red One | 8 | 6 | 0.24 | 0.57 |
| Autorretrato con espejo | 8 | 6 | 0.26 | 0.67 |

**393 grounded passes for only 8 works (~49 grounded searches per work.)** Le
Lézard alone was researched 273 times at overlap 1.0. A per-venue pass answers
the venue and its works **once** and is reused by every later stop and every
later tour of the same museum (cached 30 days). (Counts drift slightly as the
local log is appended to; the conclusion — massive per-work redundancy — does
not.)

---

## 2. Implementation — behind `GEMINI_PER_VENUE=1` (default OFF)

### `story_leads.py` (the module LOCAL-645 owns)

- **`venue_research(venue, city, works=…)`** — ONE grounded Gemini request for a
  whole venue, asking about the venue and the tour's works together. The single
  grounded call flows through the existing `gemini_with_sources(grounded=True)`,
  so the LOCAL-594 meter counts it exactly once.
- **`gemini_venue_research_cache`** — a new **additive** DB table, created exactly
  like `venue_preflight_cache` (`cache_key` PK, `venue`, `city`, `result_json`,
  `fetched_at TIMESTAMPTZ`). `_venue_research_cache_get/_put` are best-effort
  (never raise), key on `f"{fold(venue)}|{fold(city)}"`, and honour a **30-day**
  TTL (`GEMINI_VENUE_RESEARCH_TTL_DAYS`, default 30). A cache hit — a later stop
  of this tour, or a later tour of the same museum within 30 days — issues **no**
  grounded request. Nothing DROPs or DELETEs; a stale row is ignored by TTL and
  overwritten on refresh. `venue_research_cache_row_count()` reports the table
  size for ops.
- **`gemini_per_venue_enabled()`** — gates on `GEMINI_PER_VENUE=1`; **OFF** by
  default.
- **`_split_work_material(text, works)`** — attributes the grounded prose to each
  work by title; a work the pass could not research is written as the literal
  `NO MATERIAL FOUND` and mapped to `''`, which is the signal for the per-work
  fallback.

### `story_production_loop.py` (`run_for_stop`, a direct caller — in scope)

- New optional `venue` / `city` params (default `''`, `matrix['venue_name']`
  fallback), so existing callers are unaffected.
- When the flag is **ON**: the stop fetches/reuses the one venue pass. If the
  pass has material about this work, the per-stop narrate runs **UNGROUNDED**
  with that material injected as context (no per-stop Google search). If the pass
  returned nothing about the work, the stop makes **one** per-work grounded
  request as a fallback, within the per-stop budget.
- When the flag is **OFF**: `_pv_on` is `False`, the venue pass is never fetched,
  and the stop grounds exactly as the LOCAL-594 cut does — byte-for-byte
  unchanged.

### `generate_tour_text.py`

- The D511 call passes `venue=_museum_venue_name`, `city=location` to
  `run_for_stop` (harmless and unread when the flag is off). No pool/assembly code
  touched.

Requests that need no search (class knowledge) stay ungrounded exactly as before.

---

## 3. Projected saving (price card r4; NO quality claim)

Priced at the price-card rate read from `_meter/paid_api_meter.py`
(`GROUNDED_REQUEST_USD = $0.035`, `RATE_TAG 2026-10-08-r4` — Google list price
$35 / 1,000 grounded prompts). No rate is hardcoded in the measurement.

| tour | OFF req | ON req (fresh) | OFF $ | ON $ | **save $** | **save %** |
|---|---:|---:|---:|---:|---:|---:|
| 3-stop | 4 | 2 | 0.140 | 0.070 | **0.070** | **50%** |
| 5-stop | 6 | 2 | 0.210 | 0.070 | **0.140** | **67%** |

`ON (fresh)` = preflight (1) + one venue research pass (1); the per-stop grounded
searches are replaced by the single venue pass. On a **cache hit** (a repeat tour
of the same museum within 30 days) the venue pass is 0 and the 7-day preflight
cache is 0, so the grounded channel approaches **$0.00 — a 100% saving** on that
tour.

**No quality claim is made here.** LEAD measures quality with the morning
benchmark, the same venues with the flag OFF vs ON.

---

## 4. Tests (injected fakes, zero paid calls)

`tests/test_local645_gemini_per_venue.py` — 10 tests, fully offline (`requests`
faked at the `story_leads` boundary, Serper/fetch/enrich stubbed, the DB cache
replaced by an in-memory dict, the candidate log redirected to a temp file so the
tracked `story_loop_candidates.jsonl` is never touched):

1. **request count, flag ON** — exactly one grounded request (the venue pass); the
   per-stop narrate is ungrounded (`out['grounded_requests'] == 0`).
2. **cache hits** — a 2nd stop of the same venue keeps `venue_passes == 1`; a later
   tour of the same museum drops it to 0; `use_cache=False` forces a fresh pass.
3. **per-work fallback** — a `NO MATERIAL FOUND` work triggers exactly one per-work
   grounded request; none when the pass has material; `_split_work_material` maps
   `NO MATERIAL FOUND → ''`.
4. **no change, flag OFF** — the venue pass is never fetched; the grounded count
   equals the LOCAL-594 cut; the flag defaults OFF.

### Required suites — exit codes (re-run on this branch)

| suite | result | exit |
|---|---|---:|
| `tests/test_local60*` `61*` `62*` + root `test_local60*…62*` | 674 passed | **0** |
| `tests/test_local63*` + root `test_local63*` | 190 passed, 1 skipped | **0** |
| `tests/test_lead_*` | 8 passed | **0** |
| `test_local590_assembly/orchestrator/pool_store` | 42 passed | **0** |
| `python3 test_sq4_merge.py` | ALL TESTS PASSED | **0** |
| `tests/test_local645_gemini_per_venue` (new) | 10 passed | **0** |

(`test_lead_*` exist only under `tests/`; `test_local590_*` only at the repo root
— each glob was run against the directory that actually contains the files.)

---

## 5. Files changed

- `story_leads.py` — `venue_research`, `gemini_venue_research_cache`,
  `gemini_per_venue_enabled`, `_split_work_material`, `venue_research_cache_row_count`.
- `story_production_loop.py` — `run_for_stop` `venue`/`city` params + flag gate on r1.
- `generate_tour_text.py` — pass `venue`/`city` to the D511 `run_for_stop` call.
- `measure_local645_overlap.py`, `LOCAL645_overlap_measurement.json` — offline measurement + savings.
- `tests/test_local645_gemini_per_venue.py` — the four-property test suite.

No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md or
`.continuous_dev/STATUS.md`.
