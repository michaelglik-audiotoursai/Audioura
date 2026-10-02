# SUBMISSION — LOCAL-3494: Take `total_stops` out of the cache key (D581, step one)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-3494-cache-key-buckets`
**Base:** `storied` (`e1341e6`) — verified with `git merge-base --is-ancestor e1341e6 HEAD` (exit 0)

---

## Summary

`tour_cache_layer1._cache_key` no longer includes the exact `total_stops`. It now
keys on `location | tour_type | stop BUCKET`. The cache stores the **largest** count
in the bucket and **trims on delivery**, repairing the seam, so several stop counts
share **one paid generation**. A trimmed delivery is logged and counted as a **cache
HIT**, not a generation.

Buckets (as suggested by the task): `1-3 → 3`, `4-6 → 6`, `7-10 → 10`, `11+ → exact`.
I kept the suggested edges. Rationale: trimming only ever **removes trailing stops**
and never fabricates, so a bucket must be a run of counts where "generate the ceiling,
trim down" reads as well as generating the exact count would. `1-3 / 4-6 / 7-10` are
the three bands Michael's requests cluster in; beyond 10 the tours are long and rare
enough that trimming (e.g. 20→11) would waste most of a paid generation, so `11+`
stays exact.

## What changed

All logic lives in `tour_cache_layer1.py`:

- **`_stop_bucket(n)`** — collapses a requested count onto its bucket ceiling
  (the count actually generated and cached).
- **`_cache_key(location, tour_type, n)`** — hashes `location | tour_type | bucket`
  instead of the exact count. (Location normalisation from LOCAL-500 is preserved.)
- **`trim_tour_to_stops(content, target)`** — keeps stops `1..target` in order and
  then repairs the seam:
  1. rewrites the new last stop's `Directions:` hand-off to the generator's own
     final-stop form — `Your final stop in {venue}: {last name}.` — so it never
     points at a trimmed stop;
  2. rewrites the closing recap `From {first} to {last}` endpoints, the `That's N
     stops` count, and drops any enumerated highlight clause that could name a
     trimmed stop;
  3. preserves the trailing `Sources:` block verbatim;
  4. returns the tour **unchanged** when it already has `<= target` stops
     (exact-match delivery is never altered — AC4).
- **`get_cached_tour(...)`** — on a bucket hit for a smaller count, trims and logs
  a `Cache HIT (trimmed C→N, bucket=B)`. Still a HIT (`hit_count += 1`), never a
  generation.
- **`store_tour(...)`** — `ON CONFLICT` keeps the generation with the **greater**
  `total_stops`, because delivery can only trim down; a smaller generation never
  overwrites a bigger one.

A `_legacy_cache_key` read-only fallback (exact-count key) lets pre-change rows still
resolve; they converge to the bucketed key on the next store.

## Tests

`tests/test_local494_cache_key_buckets.py` — 17 pure-function tests (no DB):

```
$ python3 -m pytest tests/test_local494_cache_key_buckets.py -v
...
17 passed in 0.14s
```

Includes the explicit AC2 trap test `test_seam_does_not_name_trimmed_stop` (the
6-stop fixture's stop 6 is "The Crypt"; the 4-stop trim must not hand off to it) and
the AC3 test that a 6→4 trim scores `stops_delivered == 4` with no `truncated` defect.

## Real before/after run (live Postgres round-trip)

`demo_local3494_roundtrip.py` runs against the live cache DB
(`development-postgres-2-1`, `db=audiotours`, port 5433). It writes ONE row under a
clearly-synthetic venue name and deletes it at the end, so the production cache is
untouched.

**BEFORE** — request #1 for the venue at **6 stops** is a MISS, so a generation
happens and is stored (`total_stops=6, hit_count=0`).

**AFTER** — request #2 for the **same venue at 4 stops** hits the **same cache key**
(`76c4a15e…`), is served from cache trimmed to 4 stops, and increments `hit_count` to
1. There is exactly **one** `cache_key` row for the venue — one generation, one hit.

```
========================================================================
SETUP — cache key is location|tour_type|BUCKET (total_stops removed)
========================================================================
  key for 6 stops : 76c4a15e7ec4bc0dd602d50498fe232e0c64d3c142c017997c94112ca59eb943
  key for 4 stops : 76c4a15e7ec4bc0dd602d50498fe232e0c64d3c142c017997c94112ca59eb943
  bucket(6) = 6   bucket(4) = 6
  SAME KEY for 4 and 6 stops? True

========================================================================
REQUEST #1 — venue at 6 stops (BEFORE: cache empty)
========================================================================
  get_cached_tour(6) -> MISS (None)
  ...generation happens here (the paid step)... storing result.
  stored row: total_stops=6, hit_count=0

========================================================================
REQUEST #2 — SAME venue at 4 stops (AFTER: served from cache)
========================================================================
  get_cached_tour(4) -> HIT, delivered 4 stops
  cache_key rows for this venue in DB: 1 (AC1: must be 1)
  hit_count now = 1 (incremented by the 4-stop HIT)
  AC1 — one generation, second request is a HIT: True

========================================================================
AC2 — trimmed 4-stop delivery seam
========================================================================
  delivered stops: ['The Steeple', 'The Bell Chamber', 'The Box Pews', 'The Organ']
  last Directions line: 'Directions: Your final stop in ZZZ Demo Church LOCAL-3494: The Organ.'
  names a trimmed stop (Chandeliers/Crypt)? False
  recap endpoint line : From The Steeple to The Organ, you have followed the thread
  recap count clause  : That's 4 stops
  AC2 — clean seam, no dangling hand-off: True

========================================================================
AC3 — tour_quality.score_tour on the trimmed tour
========================================================================
  stops_delivered = 4 (must be 4)
  defects         = {'no_story': 'no named people anywhere in the tour'}
  AC3 — stops_delivered==4 and no `truncated` defect: True

========================================================================
AC4 — exact-match request (6 stops) unchanged
========================================================================
  6-stop delivery byte-identical to stored tour: True
  delivered stops: 6 (expected 6; exact-match not trimmed)

========================================================================
RESULT
========================================================================
  ALL ACCEPTANCE CRITERIA MET: True
  (demo row removed — production cache untouched)
```

## Acceptance criteria — status

1. **One generation, one hit for 4 & 6 stops** — ✅ same key `76c4a15e…`; DB holds one
   `cache_key` row; the 4-stop request incremented `hit_count` (HIT, not a generation).
2. **4-stop delivery ends cleanly** — ✅ last hand-off is
   `Your final stop in {venue}: The Organ.`; neither "The Chandeliers" (stop 5) nor
   "The Crypt" (stop 6) appears anywhere; recap reads `From The Steeple to The Organ …
   That's 4 stops`. Verified in both the live run and the dedicated unit test.
3. **`score_tour` on the trimmed tour** — ✅ `stops_delivered == 4`, no `truncated`
   defect. (The `no_story` note is unrelated to this task: the synthetic fixture's
   only titled name — "Captain Samuel Nicholson" — sits on the trimmed stop 6; it does
   not bear on AC3, which asks only about `stops_delivered` and `truncated`.)
4. **Exact-match request unchanged** — ✅ the 6-stop delivery is byte-identical to the
   stored tour; `trim_tour_to_stops` returns early when `len(stops) <= target`.

## Note on the base

The bucketing implementation and its unit tests were already present at the `storied`
base (`e1341e6`) from a prior run of this task whose deliverable was lost before it was
committed (per the task warning). This submission verifies that implementation end to
end against the live database, adds the reproducible before/after harness
(`demo_local3494_roundtrip.py`), documents the result, and — most importantly —
**commits the deliverable on the branch** so it is not lost again.

## Scope

Step one only (collapse stop counts so one generation serves several requests). The
full stop-pool design is LOCAL-495 and is not attempted here. Per PROCESS, no edits
were made to DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md, or
`.continuous_dev/STATUS.md`, and nothing is merged.
