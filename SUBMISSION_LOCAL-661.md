# SUBMISSION — LOCAL-661: a Wikimedia 429 flips a famous museum onto the exhibition path

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-661-429-path-flip`
**Base:** `subscribed` @ `646ff499` (`git merge-base --is-ancestor 646ff499 HEAD` → exit 0)

## Summary

A Wikidata/Wikipedia **429 rate limit** could make `resolve_venue()` return `None`
for a museum that had **already resolved** earlier in the same tour. The caller
read that `None` as *"this museum has no Wikidata entity"* (LOCAL-599) and flipped
the venue off the collection path onto the **exhibition site-first path**.

On Bench AB6 tour 639 (`run_ON-3.log`) this turned **The Frick Collection**
(resolved to **Q682827**, 211 works) into an exhibition tour (*Ruffles & Ribbons*;
*Gainsborough: The Fashion of Portraiture*), D1 dropped a stop → **2 of 3
delivered, Kiro 2.5**. The OFF arm of the same venue, never re-asked under load,
delivered *More / d'Haussonville / The Polish Rider* → **6.5**.

The fix makes a Wikimedia failure **UNKNOWN, never "absent"**: a resolved QID stays
known for the rest of the tour, and a 429 on a later lookup reuses it instead of
flipping the path.

## Root cause (from the real log)

```
line  74  [venue_resolver] Resolved: 'The Frick Collection' → Q682827      (clean)
line  81  [venue_resolver] SPARQL: 211 works found for Q682827             (clean)
line  88  [LOCAL-230] _get_coordinates failed: HTTP 429 for qid 'Q1384'    (429 storm)
line  92  Single candidate Q682827 … city validation UNKNOWN (network/429);
          keeping high-confidence candidate                                (kept)
line 102  [LOCAL-599] No Wikidata entity for 'The Frick Collection' —
          exhibition-museum site-first path ELIGIBLE                       ← THE FLIP
```

The deterministic-fill block (`generate_tour_text.py`) re-calls `resolve_venue()`
for the same venue. The second call kept the candidate through geo-validation
(line 92, already UNKNOWN-safe since LOCAL-637), but **step-4
`_fetch_entity_properties` is a raw `requests.get` with no backoff**: on the 429 it
returned `None`, so `resolve_venue()` returned `None`, and the block fell into the
LOCAL-599 *"no Wikidata entity"* `else`-branch. A rate limit was read as absence.

## Deliverable 1 — reuse the resolution already made in this tour

**`venue_resolver.py` — a per-tour venue resolution memo (contextvars-scoped,
exactly like `dead_host_breaker`'s per-tour cold set from LOCAL-572).**

- `resolve_venue()` is now a thin wrapper over `_resolve_venue_impl()`:
  - On success it **memoises** the entity under the exact `(venue, city)` key and
    a normalised **name-only** key (so the two call sites that parse the city hint
    differently — the D1v2 block vs the deterministic block — still share the hit).
  - When the impl returns `None`, it distinguishes **UNKNOWN from absent**:
    - a network failure was observed during the call (`get_network_failure_count()`
      delta > 0), **or** Wikidata is currently host-cold → **UNKNOWN** → return the
      memoised entity (`QID known → never "no entity"`).
    - no failure observed → **verified absence** → return `None` unchanged, so a
      real no-Wikidata-entity museum (MassArt) still gets its site-first path.
- `begin_resolution_scope()` is wired in `generate_tour_text()` right next to
  `dead_host_breaker.begin_tour_scope()` (one memo per top-level tour; concurrent
  tours never share QIDs; `copy_resolution_memo()`/`run_in_resolution_memo()` are
  provided for worker threads).

Backoff/retry for the 429 itself already exists (LOCAL-637 `_request_with_backoff`);
this change ensures that **after** retries are exhausted the resolved QID is still
not lost.

## Deliverable 2 — audit of Wikimedia-failure-read-as-negative-answer

| # | Site | Before | After |
|---|------|--------|-------|
| a | `resolve_venue()` returns `None` under a 429 after an earlier success | read as "no Wikidata entity" → LOCAL-599 exhibition flip | **FIXED** — per-tour memo reuses the QID (Deliverable 1) |
| b | `fetch_venue_works()` returns `[]` on 429/None-after-retries | indistinguishable from a verified empty catalogue → LOCAL-580 "0 documented works → site-first eligible" | **FIXED** — counts the failure (`_network_failure_count`); the deterministic block guards the `==0` eligibility on the counter delta and keeps the collection path when a 429 fired |
| c | `_fetch_works_count()` returns `(0,0)` on exception | a 429 made a famous museum look like it holds nothing (collection-ranking / high-confidence bars) | **FIXED** — counts the failure (UNKNOWN, not a verified 0-work collection) |
| d | `_fetch_entity_properties()` raw `requests.get`, returns `None` on 429 | the concrete mechanism of the Frick flip (step 4) | **COVERED** at the resolve boundary by the memo (a); the resolved entity is reused rather than lost |

Already UNKNOWN-safe (tri-state `None` = could-not-verify, from LOCAL-230/637) and
left unchanged: `_get_coordinates`, `_geocode_city`, `_is_located_in`,
`_validate_city_match` (P131/P625/coordinates and city membership).

## Deliverable 3 — tests

`test_local661_path_flip.py` — **10 tests, all pass, exit 0**, fully offline
(resolver impl + HTTP stubbed, no network):

- **A** memo holds the QID under a 429 (per-call failure delta **and** cold-host).
- **B** a genuine absence (no failures) still returns `None`; a no-QID entity is
  never memoised.
- **C** `fetch_venue_works` counts a failure on 429/None-after-retries, and does
  **not** count a verified empty (200 + 0 bindings).
- **D** the LOCAL-580 eligibility decision modelled on the counter delta:
  0 works + 429 → **not** eligible; 0 works + no failure → eligible.
- **E** end-to-end replay: resolve-ok → 429 storm → re-resolve → **collection path
  kept, 3 documented stops survive** (More / Comtesse d'Haussonville / The Polish
  Rider), never the 2-of-3 exhibition flip.

```
$ python3 -m pytest test_local661_path_flip.py -q
..........                                                               [100%]
10 passed, 1 warning in 0.18s                       (exit 0)
```

Usual related suites (offline resolver / dead-host / deterministic family):

```
$ python3 -m pytest test_local637_resolver_robustness.py test_local661_path_flip.py \
    tests/test_local572_cold_host_per_tour.py tests/test_local572_real_pool_cross_tour.py \
    tests/test_local30_deterministic_selection.py tests/test_local50_deterministic_resolution.py \
    tests/test_local449_cold_host_short_circuit.py tests/test_d559_geocode_shared.py \
    tests/test_dh_integration.py tests/test_dh_simple.py -q
82 passed, 1 skipped, 2 warnings in 1.25s           (exit 0)
```

**Pre-existing failures (NOT introduced here):** `tests/test_local599b_opening_section.py`
has 3 failures (hours-sentence / sourced-facts content tests for MassArt). These
fail **identically on the base** `646ff499` — verified in a throwaway worktree:

```
# worktree @ 646ff499 (pristine base)
$ python3 -m pytest tests/test_local599b_opening_section.py -q
3 failed, 9 passed                                  (exit 1)   ← same 3, on base
```

## Deliverable 4 — offline replay (no live run needed)

`replay_local661_ab6_639.py` parses the **real** log
`~/Audioura/.continuous_dev/bench/AB6/run_ON-3.log`, confirms the defect sequence
(`resolved` l74 → `http429` l88 → `city_unknown` l92 → `flip599` l102), then drives
the **patched** `resolve_venue` with the log's fault mechanism:

```
resolve #1 (log line 74):            → Q682827  [clean]
resolve #2 (log line ~96, under 429):→ Q682827  [collection path KEPT]
RESULT: PASS — resolve #2 kept the resolved QID Q682827 under the 429.         (exit 0)
```

Before/after proof: with the memo wiped (pre-fix behaviour) resolve #2 returns
`None` → the flip reproduces; with the memo intact it keeps Q682827.

No live run was performed (none required; cost $0).

## Commits (on `LOCAL-661-429-path-flip`, from `subscribed` @ 646ff499)

```
f252af98  #1 per-tour venue resolution memo (UNKNOWN ≠ absent)
dc9b4e70  #2 fetch_venue_works / _fetch_works_count UNKNOWN-safe + LOCAL-580 guard
68a7b21c  #3 offline tests (10, exit 0) + related suites green
b3442053  #4 offline log replay of AB6 tour-639 (exit 0)
```

`git rev-list --count origin/subscribed..HEAD` → **4**.

## Files changed

```
generate_tour_text.py       |  79 ++   wire begin_resolution_scope; works-UNKNOWN guard
venue_resolver.py           | 190 ++   resolution memo; fetch_venue_works/_fetch_works_count counting
test_local661_path_flip.py  | 303 ++   offline tests
replay_local661_ab6_639.py  | 145 ++   offline log replay
```

No DB writes, no DELETEs, no GCloud, no containers. Did not edit DECISIONS.md,
CLAUDE.md, BACKLOG.md, WORK_QUEUE.md or .continuous_dev/STATUS.md.
