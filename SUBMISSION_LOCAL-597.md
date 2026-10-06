# SUBMISSION — LOCAL-597: L2 "by reference" tours, zero grounding, zero SERP

**Branch:** `LOCAL-597-l2-by-reference` (from `subscribed` @ 99367cb)
**Design of record:** `SUBSCRIPTION_LEVELS.md` §"L2 by reference" (D613)

An L2 (free) tour now reuses already-researched stops only — the LOCAL-590 stop
pool and the stops of existing non-test tours of the same venue — re-sequenced
and re-narrated through the existing pool assembly. It issues **zero grounded
Gemini requests and zero Serper queries**, enforced in code by a guard that
RAISES if either is attempted. When a venue has no reusable material, the
listener gets an actionable refusal (`by_reference_no_material`) with up to three
nearby existing tours — never a fresh generation.

---

## What was built

### 1. The grounding / SERP guard (`l2_by_reference.py`, `story_leads.py`, `work_story_searcher.py`)
- `grounding_forbidden()` — a thread-safe, depth-counted context manager. While
  active, the two grounding choke points RAISE `GroundingForbiddenError`:
  - `story_leads._gemini(grounded=True)` and `gemini_with_sources(grounded=True)`
    (the guard sits **before** the API-key short-circuit and **outside** the
    broad `try/except` in `gemini_with_sources`, so a keyless build still fails
    hard and the raise is never swallowed into `out['error']`);
  - `work_story_searcher._serp_search` (before any key check or network).
- `check_zero_grounding()` reads the LOCAL-594 meter (`get_grounding_requests()`
  / `get_grounding_queries()`) so a build asserts `requests=0, queries=0`.
- Lazy imports keep `story_leads` / `work_story_searcher` free of a hard
  dependency on the guard: an import failure means "not forbidden" — the guard is
  a safety net, never a new way for ordinary generation to break.

### 2. The by-reference path (`l2_by_reference.build_by_reference_tour`)
Runs the whole build inside `grounding_forbidden()`:
- **Material** (`gather_material`, zero network): pooled stops from
  `stop_pool_store.get_pool_stops`, then stops parsed from existing **non-test**
  tours of the same venue identity (`audio_tours.tour_content` via
  `parse_delivered_stops`; translations and `is_test` rows excluded), deduped by
  title.
- **Assembly** via the existing `stop_pool_assembly`: building tours fold the
  D611 opening **from stored material only** (`_opening_from_material` — no venue
  web fetch); outdoor tours route-re-sequence and rewrite only adjacent
  transitions with deterministic templates (no LLM). Narration of reused stops is
  byte-identical to what was stored, so downstream audio reuse holds.
- Returns an allow (`mode='by_reference'`, `new_cost=0.0`,
  `grounding={requests:0,queries:0}`) or the refusal.

### 3. Nothing-to-reuse → actionable refusal
`error_code=by_reference_no_material`, message **"This place hasn't been
researched yet on the free level."**, suggestion **"Buy a $10 pack for a freshly
researched tour, or pick one of these nearby tours: …"** listing up to 3 existing
tours (id + name) from the tours-near query (haversine-ranked from the venue's
resolved coordinates; most-requested fallback when the venue cannot be geocoded).
If there are fewer than N reusable stops, it REFUSES — it never tops up with
fresh research.

### 4. Wiring
- `subscription_levels._check_generate`: an L2 (`by_reference_only`) request is
  now **allowed with `mode='by_reference'`** (the daily/monthly volume caps and
  stop ceiling still run first; only a DELIVERED tour counts, D613). The old
  `by_reference_unavailable` refusal is gone.
- Orchestrator reads `quota['mode']` and threads it through
  `orchestrate_tour_async → generate_data['mode'] →` the generator service
  `/generate → generate_tour_async → generate_tour_text(mode=...)`.
- `generate_tour_text`: `mode='by_reference'` routes to the terminal
  by-reference branch. Success returns the assembled text with
  `_LAST_GENERATION_COST` at $0; no material sets `_LAST_CLEAN_FAIL_EVIDENCE` to
  the refusal and returns `None`, which the generator service surfaces verbatim
  (skipping the `actionable_failure` remap) through `/status`.

---

## Tests

`tests/test_local597_guard.py` (pure, no DB) and
`tests/test_local597_by_reference.py` (DB-backed).

| suite | exit |
|---|---|
| `tests/test_local597_guard.py` + `tests/test_local597_by_reference.py` | **21 passed** |
| `tests/test_local595_enforcement.py` | **31 passed** |
| `tests/test_local596_*.py` | **32 passed** |
| `test_local590_orchestrator.py` + `test_local590_assembly.py` + `test_local590_pool_store.py` | **42 passed** |
| `tests/test_local594_grounding_cost.py` (story_leads guard move) | **10 passed** |

Guard tests prove: grounded Gemini (`_gemini`, `gemini_with_sources`) and Serper
(`_serp_search`) RAISE under the guard; ungrounded is never blocked; nested
guards compose; the guard is thread-aware; the LOCAL-594 meter stays 0; the
refusal copy is the exact D613 wording.

By-reference tests prove: pool hit (≥N) → assembled, `reused_stops` counted,
`new_cost=0`, grounding 0/0; existing non-test tour of the venue mined when the
pool is empty; partial material (<N) → `by_reference_no_material` refusal with
nearby tours (id+name), no tour text; empty pool → refusal; caps → L2 allowed
with `mode='by_reference'`, daily cap refuses after one delivered,
`stops_over_plan` at 6.

---

## Live run

Built `local597-tour-generator` from this branch's HEAD (`Dockerfile.generator`),
run with `docker run --rm --name local597-tour-generator` on the
`development_default` network against the **real** DB (`postgres-2`) with the real
Gemini / Serper / OpenAI keys (so grounding staying at 0 is the guard + path, not
a missing key). **No `audioura-*` container was touched, rebuilt, or renamed.**
Container and image removed afterwards.

**Pool counts (prod `audiotours`):** McMullen Museum of Art = **10** pooled stops,
Griffin Museum of Photography = **7**, MassArt Art Museum = **7**.
*Note:* MassArt **already has a pool** (7 stops, seeded by earlier LOCAL-59x live
runs), so it DELIVERS — contrary to the task's assumption that it has none. For
the refusal demonstration I used a genuinely unresearched venue.

### Delivered tour (McMullen Museum of Art, 5 stops, `mode=by_reference`)
```
[LOCAL-597] BY-REFERENCE DELIVERY: reused=5 rewritten_transitions=0 about_stops=1 grounding(requests=0, queries=0)
[LOCAL-60] Cost metered: tour_generate | $0.000000 (incl grounding $0.0000) | cache_hit=False
```
- **Tour total: $0.00** (target ≤ $0.10) · **Grounding: $0.00 (0 queries, 0 requests)**
- Delivered 5-stop tour: Dura-Europos: Crossroads of Antiquity, Grace Hoops,
  Ideal Portrait, Landscape with Woman in Red, Meal at the House of Simon the
  Pharisee — all reused narration, zero new generation.

### Refusal (unresearched venue, `mode=by_reference`) — `/status` JSON
```json
{
  "status": "error",
  "error_code": "by_reference_no_material",
  "message": "This place hasn't been researched yet on the free level.",
  "suggestion": "Buy a $10 pack for a freshly researched tour, or pick one of these nearby tours: French Riviera Biking Tour (#29); Palais Lascaris, Nice, France - museum Tour (#1); Camelback riding tour in Abu Dhabi desert, UAE - museum Tour (#5).",
  "nearby_tours": [
    {"id": 29, "name": "French Riviera Biking Tour", "lat": 43.5804, "lng": 7.1266, "popularity": 31, "distance_km": null},
    {"id": 1,  "name": "Palais Lascaris, Nice, France - museum Tour", "lat": 43.6972, "lng": 7.2769, "popularity": 16, "distance_km": null},
    {"id": 5,  "name": "Camelback riding tour in Abu Dhabi desert, UAE - museum Tour", "lat": 23.6604, "lng": 53.9915, "popularity": 3, "distance_km": null}
  ]
}
```
`distance_km` is `null` because the imaginary venue does not geocode, so the
nearby list falls back to the most-requested tours — the documented, actionable
fallback.

### Cost + cleanup
- Total live spend **≈ $0.00** (well under the $0.50 cap): the by-reference path
  makes no OpenAI / Gemini / Serper call; `venue_resolver` did only free Wikidata
  lookups.
- The by-reference path is **read-only**: it created no `device_entitlement`,
  `tour_requests`, or `audio_tours` rows (verified: 0 `LOCAL597-` rows, 0 rows for
  the test venue). Nothing to clean up.

---

## Files changed
- `l2_by_reference.py` (new) — guard + by-reference path + refusal + nearby tours
- `story_leads.py` — grounded guard in `_gemini` / `gemini_with_sources`
- `work_story_searcher.py` — SERP guard in `_serp_search`
- `subscription_levels.py` — L2 allow with `mode='by_reference'`
- `generate_tour_text.py` — `mode` param + terminal by-reference branch
- `generate_tour_text_service.py` — forward `mode`; surface structured refusal in `/status`
- `tour_orchestrator_service.py` — read `quota['mode']`, thread it to the generator
- `tests/test_local595_enforcement.py` — updated L2 expectations (allow + mode)
- `tests/test_local597_guard.py` (new), `tests/test_local597_by_reference.py` (new)

---

## r2

### Why it bounced
LEAD (2026-10-06): the path was fine ($0.00, zero grounding, actionable refusal),
but `tests/test_local597_by_reference.py` broke a binding CLAUDE.md rule (D141,
the tour-29 event):
1. It INSERTed `audio_tours` rows with `is_test = FALSE` and real Boston lat/lng
   ("LOCAL597 Nearby A/B" + a venue tour) into the shared DB. While the test ran,
   `tours-near` (which filters on lat/lng) could surface them in Michael's app.
2. It DELETEd them in tearDown with **no** `SELECT is_test` check immediately
   before the DELETE — the exact shape of the tour-29 loss.
3. It wrote ZZ597 `stop_pool` rows into the shared pool.

### Fix — zero shared/production writes via a throwaway schema
Every DB-touching test now runs against a **private throwaway schema** that is
dropped at the end; no row is ever added to any shared (`public.*`) table. One
mechanism, no production-code change:

```
PGOPTIONS = "-c search_path=<throwaway>,public"
```

libpq applies `PGOPTIONS` to **every** new connection in the process — both the
ones `l2_by_reference` opens from `db_url` and the env-var connections
`subscription_levels` / `entitlements` open. With the throwaway schema first on
the search_path, an unqualified `audio_tours` / `stop_pool` /
`device_entitlement` / `tour_requests` / `users` resolves to a schema-local copy
created `LIKE public.<t> INCLUDING ALL` (byte-compatible with the code's
INSERTs, incl. `device_entitlement`'s unique `user_id` for `ON CONFLICT`).
`public` is never touched.

- **No cleanup DELETE anywhere.** Rows die with `DROP SCHEMA ... CASCADE` in
  `tearDownModule`. The D141 "`SELECT is_test` before DELETE" rule governs
  cleanup DELETEs; there are none.
- `is_test = FALSE` rows (required because `_nearby_existing_tours` and
  `tours-near` only surface `is_test IS NOT TRUE`) are safe **only** because they
  live in the schema, invisible to `tours-near` which queries `public`. Each test
  asserts its seeded ids are absent from `public.audio_tours`.
- `tearDownModule` reads `public` row counts for `audio_tours`, `stop_pool`,
  `device_entitlement`, `tour_requests` before any test and again after the drop,
  prints both, and asserts they are identical.

Gotcha found and documented in the test: `conftest.py`'s guarded connection
wrapper does not delegate the `autocommit` **attribute**, so the schema DDL
commits explicitly (`conn.commit()`), otherwise `CREATE SCHEMA` silently rolls
back and writes leak to `public`.

Proof (pytest `-s`, re-runnable — identical on repeat):
```
[LOCAL-597 r2] public row counts before/after (must be identical):
  public.audio_tours          before=0        after=0
  public.stop_pool            before=0        after=0
  public.device_entitlement   before=7        after=7
  public.tour_requests        before=2        after=2
[LOCAL-597 r2] OK — zero shared/production writes.
9 passed
```

### Nearby-tours test updated for the c09eda6 rule
`_nearby_existing_tours` now means "within `NEARBY_MAX_KM` (50 km) of a
resolvable anchor; no anchor → no list". The tests were updated accordingly:
- `test_partial_material_refuses_with_nearby_tours` stubs
  `venue_resolver.resolve_venue` → a Boston anchor (lat/lng) and seeds two
  Boston-coordinate tours; it now asserts they are offered and that the
  suggestion contains "pick one of these".
- `test_no_anchor_offers_empty_list` (new) stubs the resolver → `None` and
  asserts `nearby_tours == []` and the suggestion drops the "pick one of these"
  clause (just "Buy a $10 pack for a freshly researched tour.") — a Boston
  listener is never again offered Nice/Abu Dhabi.

### r1 leftover scan + cleanup
Scanned both DBs for `audio_tours` named `LOCAL597%`/`ZZ597%` and `stop_pool`
keys/identities matching `%zz597%`/`%local597%`:
- **Production (`audiotours`): clean** — 0 rows in every table. r1's test routing
  kept production untouched.
- **Test (`audiotours_test`)**: `audio_tours` 0; `stop_pool` had 130 rows (98 from
  r1 + 32 that leaked from my own pre-fix runs before the autocommit gotcha was
  found), all 38 identities matching the exact provably-mine pattern
  `^loc:zz597_(pool|partial)_[0-9a-f]{8}$` (produced only by this test's
  `ZZ597_POOL_`/`ZZ597_PARTIAL_` + uuid seeds).

Deleted only the exact-pattern rows (regex match, no name-pattern/date-range/
"above id N"), with counts:
```
audiotours:       provably-mine BEFORE=0   (nothing to delete)
audiotours_test:  provably-mine BEFORE=130  DELETED=130  AFTER=0
```
Post-cleanup the suite still passes and `public.stop_pool` before/after is 0/0.

### Re-run of tests/test_local59[5-7]_*  (exits)
```
tests/test_local595_anniversary.py        exit=0  18 passed
tests/test_local595_api.py                exit=0  10 passed
tests/test_local595_edit_gate.py          exit=0   8 passed
tests/test_local595_enforcement.py        exit=0  31 passed
tests/test_local596_api.py                exit=0  11 passed
tests/test_local596_mirror_in_sync.py     exit=5  no tests ran (script-style check;
                                                   passes as `python3 <file>` → exit 0;
                                                   unchanged from base)
tests/test_local596_referral.py           exit=0   9 passed
tests/test_local596_seats.py              exit=0  12 passed
tests/test_local597_by_reference.py       exit=0   9 passed
tests/test_local597_guard.py              exit=0  13 passed
```

### Files changed (r2)
- `tests/test_local597_by_reference.py` — throwaway-schema isolation + public
  count proof; nearby test stubs a Boston anchor; new no-anchor empty-list test.
  No production code changed in r2.
