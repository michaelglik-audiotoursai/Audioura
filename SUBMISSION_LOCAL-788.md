# SUBMISSION — LOCAL-788

**Reused (pooled) stops must pass the LOCAL-786 scope check; an Overpass outage must not cost real places.**

Branch: `LOCAL-788-pool-scope`  ·  Base: `subscribed` (`f4a45431`, contains `2dde77dc`)
`git merge-base --is-ancestor f4a45431 HEAD` → 0 (correct base, verified before work).

---

## The two defects (wave-2 proof, Subscribed Preview, 2026-10-27)

**A.** "middle eastern restaurants near me, west Roxbury, MA" (tour 454 wording) → the stop pool
reused yesterday's Stardust (West Roxbury, correct) **+ Byblos (Norwood, ~10 km)** and overwrote tour 454.
LOCAL-786's `_bind_in_scope` (places_search.py) runs only on NEW place lookups; the `stop_pool_orchestrator`
reuse path (pooled rows + LOCAL-778 mining) never re-checked scope.

**B.** Rephrased request → tour 460 got 1 of 2 stops. Log: `scope_precision=CITY`, Overpass **502**.
Addendum: the D545 replenish (after D538 dropped a closed stop) asked the **LLM** for candidates — no
bbox / places_search / Serper query ever logged — and the closed stop (Kebab House) had been "verified"
by a Wikipedia snippet about **Bitterne Park (Southampton, UK)**.

---

## What changed (by ticket item)

### 1. Reuse re-validation (defect A) — `places_search.py`, `stop_pool_orchestrator.py`
Added `places_search.row_in_scope(coordinates, address, scope, scope_center, scope_bbox, near)` — the
**same** LOCAL-786 scope test applied to a NEW lookup, reused for a REUSED stop. It calls the existing
LOCAL-786 primitives verbatim (`_scope_precision`, `_radius_for_precision`, `_parse_bbox`, `_inside_bbox`,
`_scope_town`, `_address_town`, `_haversine_km`): town-name mismatch → bbox + 500 m → scope-precision radius
(NEIGHBOURHOOD ≈ 2.5 km / CITY ≈ 8–15 km) → near-me 3 km. A coordinate-less row is kept (cannot be proven out).

`stop_pool_orchestrator._revalidate_pooled_scope(rows, location, tour_type, contained)` runs every pooled/mined
**place** (coords-bearing) row through `row_in_scope` **before K is counted**, inside `maybe_generate_with_pool`.
Only OUTDOOR / place-type tours are re-validated; a CONTAINED museum/facility (whose stops are works inside one
building) is left untouched (LOCAL-591 one-scope-per-tour). Rejected rows are dropped **from this tour only**,
logged `[LOCAL-788] pool reject <title> <km> <reason>`. **No DELETE; the pool is never mutated.** When K falls
below N the existing N>K path researches the remainder.

### 2. Neighbourhood precision (defect B) — `generate_tour_text.py`
Root cause: `scope_precision == CITY` makes `_assert_one_scope_per_tour` DROP the stop-by-stop containment scope
("too wide"), so a West Roxbury tour accepted a place up to city-wide. The LLM returned CITY on GCloud (the Mac,
same code, returned DISTRICT — the LLM verdict is non-deterministic, and the Overpass 502 coincided).

`_correct_scope_precision(intent, user_request)` corrects this **deterministically, independent of the LLM and of
Overpass**: it reuses the LOCAL-786 classifier (`places_search._scope_precision`, which reads "West Roxbury, MA" /
"Jamaica Plain" / "North End" as NEIGHBOURHOOD) and a "near me" regex, and tightens a `CITY`/empty verdict to
`DISTRICT`. It only ever tightens CITY — a genuine whole-city request ("Newton, MA", "Brookline, MA") stays CITY;
BUILDING / CORRIDOR / DISTRICT are untouched. Applied at the return of `analyze_tour_intent`.

### 3. Overpass outage (defect B) — `osm_venue_facts.py`, `osm_dining_facts.py`, `overpass_fallback.py` (new)
`osm_venue_facts._overpass_request` now walks **primary → public mirrors** (`overpass.kumi.systems`,
`overpass.private.coffee`). On a 5xx / timeout / connection error it tries the next endpoint, logging
`[LOCAL-788] overpass fallback <endpoint> <status>`; a 429 gets one same-endpoint back-off then moves on. The
primary is env-overridable (`OVERPASS_URL`) and the mirror list via `OVERPASS_MIRRORS`, so a live test can force
the outage. `osm_dining_facts._overpass_request` now **delegates to the shared client** (no second Overpass client;
old body kept as `_overpass_request_local` fallback).

New `overpass_fallback.query_pois_with_fallback(...)`: tries Overpass (shared client, with its mirror ladder) and,
when every endpoint fails or returns empty, falls back to **Serper Places with `ll` at the scope centre**
(`places_search.places_search`, LOCAL-786-bound). It never silently shrinks the candidate list; it returns `[]`
only when BOTH providers yield nothing, logging `[LOCAL-788] overpass fallback serper count=N`.

### 4. D545 replenish is places-first (addendum) — `generate_tour_text.py`
The D545 restaurant replenish (after D538 drops a closed stop) now runs a **PLACES-FIRST** block *before* the LLM
`propose_replacements` loop: `stop_existence_gate.replenish_with_escalation('dining', poi_type, scope, need, …)` —
the LOCAL-784 ladder (Serper Places with `ll` + the LOCAL-786 bbox FIRST → tier b → grounded Gemini LAST), each
candidate **geo-verified on the map** and still passed through `fetch_practicals` (the D538 closure check). The LLM
loop runs only for any remainder the map could not fill. Logs `[LOCAL-788] D545 places-first replenish …` and
`[LOCAL-788] D545 ADDED (map) …`.

### 5. Existence matches the PLACE, not the NAME (addendum) — `stop_existence_gate.py`
`_text_contradicts_scope(text, city_signals)` returns True when evidence positively names a place that
contradicts the scope (foreign markers — bitterne / southampton / england / uk / hampshire / … — plus pycountry
states & countries via `restaurant_practicals._geo_vocab`), never flags when a scope signal IS present, never
flags neutral text. Applied at **every** accept branch of `_check_dining_existence`: the English and French
summary checks now require the scope's own location AND no contradiction (the old "title match alone" accept — the
Bitterne Park hole — is removed), and `_snippet_has_evidence` rejects on contradiction. A same-named "Kebab House"
in Southampton, UK no longer verifies a West Roxbury stop.

---

## Tests (new, all pass — 39 unit tests)

| File | Tests | Covers |
|---|---|---|
| `tests/test_local788_reuse_scope.py` | 11 | item 1 — `row_in_scope` + `_revalidate_pooled_scope`; Byblos Norwood rejected, Stardust kept; near-me 3 km uses device coords; contained museum untouched; pool never mutated |
| `tests/test_local788_precision.py` | 12 | item 2 — West Roxbury / Jamaica Plain / North End / near-me CITY→DISTRICT; Newton & Brookline stay CITY; BUILDING/CORRIDOR/DISTRICT untouched |
| `tests/test_local788_overpass_fallback.py` | 6 | item 3 — 502 primary → mirror tried; all-down → `None`; timeout → mirror; Overpass down → Serper fallback non-empty; Overpass hit skips Serper; both down → `[]` not partial |
| `tests/test_local788_d545_places_first.py` | 4 | item 4 — source-order invariant (ladder BEFORE `propose_replacements`); ladder returns real coords-bearing places; Byblos Norwood never returned |
| `tests/test_local788_existence_place.py` | 6 | item 5 — Bitterne Park UK summary + snippet do NOT verify a West Roxbury stop; a genuine West Roxbury snippet still verifies; the guard in isolation |

### Full suite vs baseline
`tests/` run on BOTH the clean base (`git stash -u` → `f4a45431`) and this branch:
**199 failing test node-ids on baseline == 199 on branch — ZERO new failures.** All 199 pre-existing failures are
environmental (no DB / services / network in the local env: wallet, entitlement, newsletter, tier_change,
news_orchestrator). The root `test_local480_facility_category.py::TestWiring` 6 failures were likewise confirmed
pre-existing on the clean base (they grep the `generate_tour_text` wrapper source for markers that live in the impl).

Regression suites green on branch: LOCAL-786 (17), LOCAL-784 (19 + ladder), LOCAL-622 (21), LOCAL-779B / 783 / 348 /
417 (99), LOCAL-572 (pools-in-scope).

**One test edited:** `tests/test_local622_lookup_budget.py` autouse fixture now pins `_OVERPASS_MIRRORS = []` so
those budget/timeout tests still describe the primary-endpoint behaviour (the mirror fallback has its own suite).
This is a deliberate update to the changed Overpass contract, not a silent regression.

---

## Live test (Overpass forced dead; real Serper; cap $1.50)

`run_local788_live.py` drives the changed paths in-process against the REAL metered Serper Places door with Overpass
forced to a dead URL (`OVERPASS_URL` + `OVERPASS_MIRRORS` at `http://127.0.0.1:1/dead…`). It never touches the shared
`audioura-*` containers. Result:

```
scope centre = (42.2792649, -71.1494972)  bbox = [42.2530027, 42.3038383, -71.1912442, -71.1281245]

[item 4] replenish_with_escalation(dining, "middle eastern restaurants", "West Roxbury, MA")
  ladder returned 2: ['Al Wadi', 'Bread Thyme']            ← real WR places, NONE in Norwood

[item 3] overpass_fallback.query_pois_with_fallback
  [LOCAL-788] overpass fallback http://127.0.0.1:1/dead-primary ConnectionError
  [LOCAL-788] overpass fallback http://127.0.0.1:1/dead-mirror  ConnectionError
  [LOCAL-788] overpass fallback serper count=10            ← candidate list NOT shrunk
  fallback returned 10 (West On Centre, Bread Thyme, Al Wadi, Rox Diner, Stardust …)

[item 1] row_in_scope on {Stardust (WR), Byblos (Norwood)} for West Roxbury
    Stardust           keep=True  0.9km
    Byblos Restaurant  keep=False 10.3km town-name mismatch (norwood)

ALL LIVE CHECKS PASSED
```

Spend: a handful of Serper Places lookups (~$0.002 each) — a few cents, far under the $1.50 cap. The ledger row
write failed only because the local env has no `postgres-2` (the meter degrades gracefully, as designed). No full
stack was built; the proof drives this worktree's code directly so it measures LOCAL-788, not a stale image.

---

## Tables written
**None.** No `INSERT` / `UPDATE` / `DELETE` / `DROP` of any kind. The reuse re-validation drops rejected rows from
the in-memory tour only; the pool is never mutated. Row counts before/after for every table: **unchanged.**

## Files
Changed: `places_search.py`, `stop_pool_orchestrator.py`, `generate_tour_text.py`, `stop_existence_gate.py`,
`osm_venue_facts.py`, `osm_dining_facts.py`, `tests/test_local622_lookup_budget.py`.
New: `overpass_fallback.py`, `run_local788_live.py`, and the five `tests/test_local788_*.py` suites.

Not touched (per process rules): DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE, `.continuous_dev/`,
SUBSCRIBED_COMMUNICATION_01.MD, `legal/`, GCLOUD_STORIED_START_HERE.md, TRAVEL_PROJECTS.md.
