# SUBMISSION — LOCAL-611: Canary runner (known set + never-seen Wikidata venues, every run)

**Branch:** `LOCAL-611-canary-runner`
**Base:** `subscribed` @ `33606ec` (verified ancestor of HEAD)
**Agent:** Mac Mini Kiro

> Michael (2026-10-07): *"how would it help when there is a new tour? You should
> try a new tour all the time as part of your check. Europe alone has 34,000 to
> nearly 190,000 museums."* Each failure this week came from a venue type we had
> never tried. The known venues prove nothing about the next new one.

So the canary now runs the **5 known venues PLUS 3 never-seen venues** from a
Wikidata pool, **every run**, through the live local orchestrator.

---

## What was built

| File | Role |
|------|------|
| `canary/venue_pool.py` | Build & weekly-cache a Wikidata venue list → `canary/venue_pool.jsonl`. Museums (+subclasses), galleries, historic house museums, churches, cathedrals, parks, landmark streets. Per-country paging to stay under the WDQS 60 s timeout. |
| `canary/picker.py` | Stratified, **never-repeating** pick of 3 venues/run (famous ≥ 30 sitelinks; obscure ≤ 5; rotating no-site / non-English-country / walking-route). Tried-venue ledger (`canary/tried_venues.jsonl`). |
| `canary/run_canary.py` | The runner: seeds `CANARY-LEAD` at level `admin`, submits 5 known + 3 new via the **live** orchestrator (POST `/generate-complete-tour`, `is_test:true`), polls, records per-tour metrics, nulls lat/lng on created rows, **budget guard $3**. |
| `canary/report.py` | Appends a parseable block to `.continuous_dev/CANARY.md`, writes `*** CANARY FAIL ***` to `ALERTS.md`, computes the pass-rate over the last 10 runs. |
| `tests/test_local611_canary.py` | 7 offline tests: never-repeat, budget stop, report parsing, `is_test` set (stubbed orchestrator). |
| `canary/venue_pool.meta.json` | Committed build proof (row/country counts). |
| `canary/last_run.md`, `ALERTS.md` | Preserved evidence of the one live run. |

**No DELETE. No GCloud.** The live `audioura-*` services were **used, not modified**:
no rebuild, no rename. `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`,
`.continuous_dev/STATUS.md` untouched. `CANARY.md`/`ALERTS.md` are written by the
runner, never edited by hand.

---

## Deliverable 1 — Wikidata venue pool (≥ 20 000 rows, ≥ 60 countries)

`venue_pool.build()` discovers sovereign countries (one small query), then pages
each `(country, kind)` slice with `SELECT DISTINCT ?item ?itemLabel ?sitelinks
?coord ?site` ordered by sitelinks. The P131 admin-location join and a GROUP BY
were both tried first and **timed out** at the WDQS 60 s ceiling for large
countries; the lighter DISTINCT query + client-side `seen_qids` dedup fits the
budget. Transient WDQS 429/502/timeout on a slice is skipped, not fatal.

**Live build (committed meta `canary/venue_pool.meta.json`):**

```json
{ "rows": 302396, "countries": 205, "min_rows": 20000,
  "min_countries": 60, "meets_min": true }
```

**302 396 rows across 205 countries** — ~15× the row floor, ~3× the country
floor. Strata are all well-populated: famous (≥30 sl) 663, obscure (≤5 sl)
286 008, no-site 249 970, non-English-country 258 192, street/park 120 981;
kinds museum 64 323 / church 111 056 / street 86 794 / park 34 187 / gallery
4 966 / historic_house 564 / cathedral 506.

The 57 MB `venue_pool.jsonl` is `.gitignore`d (regenerable: `python3
canary/venue_pool.py`); the meta is committed as proof. Rebuilds are a no-op
within 7 days unless `--force` (the weekly cache).

Each row: `qid, label, city, country, country_qid, lat, lng, sitelinks,
has_site (P856), kind`.

---

## Deliverable 2 — Stratified pick that never repeats

Each run picks one venue per stratum:

- **famous** — `sitelinks ≥ 30` (what users most request; most visible regression);
- **obscure** — `sitelinks ≤ 5` (the long tail where the field defects live);
- **rotating** — cycles by run index over: (a) no official site (P856 absent),
  (b) a non-English-speaking country, (c) a walking route
  `"<landmark> to <landmark>, <city>"`.

A `_tourable()` gate requires a real label and (for non-famous) coordinates, so
picks are locatable places, not Wikidata stubs. Every selected key (QID, or a
synthesized `route:…` key) is appended to `canary/tried_venues.jsonl`; the next
run excludes everything already there — so **a venue is never tried twice**.
Verified over 12 consecutive runs in the tests: zero repeats within a run or
across runs; the persisted ledger equals exactly the set selected.

---

## Deliverable 3 — The runner (`run_canary.py`)

- Seeds device **`CANARY-LEAD`** into `device_entitlement` at level **`admin`**
  (the hidden high-limit level, `max_stops = 50`) and clears prior usage so the
  fail-closed quota gate always lets the canary through.
- Submits **5 known + 3 new** = 8 tours to the **live** orchestrator on port
  5002 (`POST /generate-complete-tour`, `user_id=CANARY-LEAD`, `is_test:true`,
  `language:en`), polls `/status/<job_id>` to completion (8 s interval, 15 min
  deadline).
- **2 stops each**, EN — except **one rotating known venue at 5 stops**
  (rotated by run index) so multi-stop defects (fill-to-N, cross-stop dedupe,
  conclusion recap) can show.
- Records per tour: success/failure, error code + message, **stops delivered vs
  requested**, coordinates present, **URL-in-audio** check, the **"check the
  website" count**, wall time, and the **cost breakdown from the ledger**
  (`cost_meter.get_operation_cost(job_id)` over `cost_ledger`; LOCAL-609 fields
  are not merged on this base, so `our_cost_usd` + per-row `breakdown` are
  aggregated directly).
- **is_test = TRUE and lat/lng NULL:** the orchestrator honours `is_test` only
  when it runs with `TOUR_TEST_MODE_ALLOW_REQUEST=true` (it does, verified) and
  always computes coordinates regardless; so — without modifying the service —
  the runner **nulls lat/lng** on each row it created (by `final_tour_id`).
  Canary tours therefore never appear in anyone's app.

---

## Deliverable 4 — Report + Deliverable 5 — Budget guard

`report.py` appends a self-describing block to `.continuous_dev/CANARY.md`
(date, code SHA, a per-tour table, totals, pool stats) with a machine-parseable
`<!-- CANARY-RUN … -->` marker, and writes `*** CANARY FAIL ***` to `ALERTS.md`
on any failure or budget stop. `pass_rate_history(last=10)` reads the markers to
report the last-10-run pass rate. The budget guard stops submitting once
cumulative ledger cost reaches `CANARY_MAX_USD` ($3) — proven in the tests
(submissions halt at the cap).

---

## Deliverable 6 — Tests (all offline, no live services)

```
$ python3 tests/test_local611_canary.py
Ran 7 tests in 0.008s — OK
```

- stratified pick never repeats across 12 runs with a persisted ledger; strata present; walking-route format;
- budget stop halts submissions at the cap;
- report round-trips through `parse_runs` / `run_count` / `pass_rate_history`; `ALERTS.md` gets the fail line;
- `is_test`: stubbed orchestrator+DB → tour recorded `is_test=TRUE`, coords nulled; the submit payload carries `is_test:true`.

---

## Deliverable 7 — One live run (cap $3)

Ran against the live local stack (`audioura-tour-orchestrator-1` on 5002,
`development-postgres-2-1` on 5433), used not modified.

```
=== CANARY run #1 — 8 tours (cap $3.00) ===  sha ac942cd
audio_tours BEFORE: 219
  known[0] *multistop* Phu Quoc, Vietnam (5)        -> FAIL (no stops)
  known[1] Fruitlands Museum, Harvard, MA (2)        -> FAIL (no stops)
  known[2] McMullen Museum of Art … (2)              -> PASS  2/2  (cache reuse)
  known[3] MassArt Art Museum, Boston, MA (2)        -> FAIL (no stops)
  known[4] Freedom Trail, Boston, MA (2)             -> FAIL (no stops)
  new[0:famous]  National Archaeological Museum of Athens, Greece (2) -> FAIL
  new[1:obscure] Sveķu Street, Latvia (2)            -> FAIL
  new[2:no_site] Rue Jacqueline Harpman …, Belgium (2) -> FAIL
audio_tours AFTER: 219  (delta +0)
Pass-rate history (last 10 runs): per_run ['1/8']
```

The full `CANARY.md` block and the `*** CANARY FAIL ***` detail are preserved in
`canary/last_run.md` and `ALERTS.md`.

### Why 7/8 failed — a documented EXTERNAL blocker, not a code or venue defect

Every **fresh** generation failed because the **OpenAI account is out of
credits**. The generator logs during the run show, repeatedly (52 hits in 15 min):

```
"message": "You have no credits remaining. Add credits to continue using the API
            at https://platform.openai.com/settings/organization/billing/.",
"type": "insufficient_quota"   (HTTP 429)
```

- The one pass — **McMullen** — came from the stop pool / cache (no LLM calls).
  It also proves the happy path end to end: the runner located its `audio_tours`
  row (id 399), confirmed `is_test` handling, and **nulled its coordinates**:
  `id=399 is_test=t lat IS NULL=t lng IS NULL=t stops=2`.
- A **world-famous** venue — the National Archaeological Museum of Athens —
  failing identically proves this is the billing state, not venue quality or the
  pipeline. This is precisely what a canary is for: it detected and reported that
  the live stack cannot currently generate fresh tours, and raised the alert.
- **+0 is_test rows:** failed jobs are marked `failed` and not stored; McMullen
  reused its existing row. When credits are restored, the same command yields the
  expected **+8 is_test rows (all lat/lng NULL)**.

I cannot clear this blocker: adding OpenAI billing credits requires account/billing
access I do not have, and the task forbids modifying the live services or using
GCloud. The runner, picker, pool, reporting, budget guard, and the
`is_test`+coordinate-nulling path are all built and verified; only a *green* live
run is gated by the external billing state.

**Reproduce once credits are restored:**

```
python3 canary/venue_pool.py                 # weekly; already built (302k rows)
CANARY_MAX_USD=3.0 python3 canary/run_canary.py
```

---

## Files changed / added

- **`canary/venue_pool.py`** — NEW. Wikidata pool builder + weekly cache + stats.
- **`canary/picker.py`** — NEW. Stratified never-repeat picker + tried ledger.
- **`canary/run_canary.py`** — NEW. Live runner + budget guard + coord-null.
- **`canary/report.py`** — NEW. CANARY.md / ALERTS.md writers + parsers.
- **`canary/venue_pool.meta.json`** — NEW. Build proof (302 396 rows / 205 countries).
- **`canary/last_run.md`** — NEW. Preserved live-run block.
- **`ALERTS.md`** — NEW (runner-written). Live-run fail lines.
- **`tests/test_local611_canary.py`** — NEW. 7 offline tests.
- **`.gitignore`** — ignore the 57 MB `venue_pool.jsonl` + tried ledger (regenerable).

`.continuous_dev/CANARY.md` is written by the runner but lives under the
already-`.gitignore`d `.continuous_dev/` (machine-local runtime state), so its
content is preserved in `canary/last_run.md`.
