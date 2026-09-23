# SUBMISSION — LOCAL-514: take `total_stops` out of the cache key (D581, step one)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-514-cache-key-buckets`
**Base:** `storied` = `4837e98` (verified: `git merge-base --is-ancestor 4837e98 HEAD` exits 0)

---

## TL;DR

`tour_cache_layer1` now keys on `location | tour_type | stop BUCKET` instead of the exact
`total_stops`. The cache stores the **largest** count in a bucket and **trims on delivery**
to the requested count, repairing the seam and the closing recap so no trimmed stop is
named. A trimmed delivery is logged and counted as a **cache HIT, not a generation**.

Two requests for the same venue at 4 and 6 stops now produce **one paid generation and one
cache hit** — verified end-to-end against the live Postgres (see the run below).

---

## Where the code lives / relationship to LOCAL-494

This ticket is D581 step one. The identical work was tracked as **LOCAL-494**, and its
implementation is already merged into my base:

```
4837e98 Merge branch 'LOCAL-494-cache-key-buckets' into storied   <-- my base HEAD
1788205 LOCAL-500: accent-fold + normalise tour_cache key (SAFE half)
861e43a LOCAL-494: bucket the cache key on stop count, trim on delivery (D581 step one)
```

The prior LOCAL-514 attempt was pruned because it **never committed its deliverable** (its
reasoning survives only in `kiro_session_logs/`). The bucketing *code* reached `storied`
via the LOCAL-494 branch; what was lost was the submission + a real before/after run
proving it. This submission supplies exactly that, plus an independent re-verification of
every acceptance criterion (I did not assume the merged code was correct — I ran it).

New files added on this branch (the deliverable):

- `SUBMISSION_LOCAL-514.md` — this file.
- `demo_local514_cache_hit.py` — runnable live-DB before/after demonstration.

The implementation under test (`tour_cache_layer1.py`) and its unit suite
(`tests/test_local494_cache_key_buckets.py`) are the storied versions, unchanged.

---

## Design: the buckets

Key on `location | tour_type | _stop_bucket(total_stops)`:

| requested stops | bucket ceiling (generated & cached) |
|-----------------|-------------------------------------|
| 1–3             | 3                                   |
| 4–6             | 6                                   |
| 7–10            | 10                                  |
| 11+             | exact (no bucketing)                |

I kept the suggested edges. Rationale: trimming only ever **removes trailing stops**, never
fabricates, so a bucket must be a run of counts where "generate the ceiling, trim down"
reads as well as generating the exact count would have. 1–3 / 4–6 / 7–10 are the bands
Michael's requests actually cluster in. Beyond 10, tours are rare and long enough that
trimming (e.g. 20→11) wastes most of a paid generation, so **11+ stays exact**. The cache
stores the ceiling; every smaller count in the band is served by trimming.

`store_tour` upserts and keeps the **larger** generation on conflict
(`WHERE EXCLUDED.total_stops > tour_cache.total_stops`), because delivery can only trim
down — a smaller generation must never overwrite a bigger cached one.

## Design: trim + seam repair

`trim_tour_to_stops(content, target)`:

1. Keeps stops `1..target` in order; drops every later `Stop N:` block.
2. **Trailing seam:** the new last stop's `Directions:` line (which pointed at the
   now-removed next stop) is rewritten to the generator's own final-stop template —
   `Directions: Your final stop in {venue}: {last name}.` — or dropped if the venue
   cannot be recovered. This is Michael's requirement: *"whatever stop we take out, the
   previous and next stop need to adjust the directions and orientation."*
3. **Closing recap:** `From {first} to {last}` endpoints and the `That's N stops` count are
   corrected to the delivered set, and the enumerated highlight clause (which may name a
   trimmed stop) is reduced to the bare count sentence.
4. `Sources:` block preserved verbatim.
5. If the tour already has `<= target` stops it is returned **unchanged** (exact-match
   delivery is never altered — AC4).

`get_cached_tour` trims when `total_stops < cached_stops` and still logs a **HIT** (with a
`trimmed C→R` note), so a trimmed delivery is never miscounted as a generation.

---

## BEFORE / AFTER — real run against the live cache DB

Run: `DB_URL=postgresql://admin:***@localhost:5433/audiotours python3 demo_local514_cache_hit.py`
(the docker-compose `postgres-2` container, host port 5433). The demo deletes only this
venue's bucket keys first so the before/after is unambiguous, and deletes its synthetic row
again afterwards so the live cache is left as it was found.

```
========================================================================
LOCAL-514 bucketed-cache demonstration (live Postgres)
DB_URL: postgresql://admin:***@localhost:5433/audiotours
========================================================================

[keys] 6-stop key = 058c77fff405ddbc…
[keys] 4-stop key = 058c77fff405ddbc…
[keys] SAME KEY (AC1 bucketing): True

------------------------------------------------------------------------
REQUEST A — Old North Church / museum / 6 stops
------------------------------------------------------------------------
get_cached_tour(6) -> MISS (None)          <-- BEFORE: cold, nothing cached
=> paying for ONE generation, storing it under the bucket key
store_tour(6) -> True
rows under THIS venue's bucket key: 1  (total_stops, hit_count) = [(6, 0)]

------------------------------------------------------------------------
REQUEST B — Old North Church / museum / 4 stops  (the SECOND request)
------------------------------------------------------------------------
get_cached_tour(4) -> HIT (served from cache, trimmed)   <-- AFTER: served from cache
rows under THIS venue's bucket key after request B: 1  (still ONE row = one generation)
hit_count on the row: 1  (incremented by the HIT)

[AC2] delivered stops: ['The Steeple', 'The Bell Chamber', 'The Box Pews', 'The Organ']
[AC2] last Directions line: Directions: Your final stop in Old North Church: The Organ.
[AC2] names 'The Chandeliers' (stop 5)?: False
[AC2] names 'The Crypt' (stop 6)?:       False

[AC3] score_tour(delivered, 4):
      stops_delivered = 4
      defects         = {'no_story': 'no named people anywhere in the tour'}

[AC4] exact 6-stop request returns stored content verbatim: True

========================================================================
ALL ACCEPTANCE CRITERIA PASSED
========================================================================
```

Full trimmed 4-stop delivery (note the clean terminal Directions line and the recap that
names only The Steeple → The Organ, "That's 4 stops."):

```
Stop 4: The Organ
...
Directions: Your final stop in Old North Church: The Organ.

From The Steeple to The Organ, you have followed the thread of Signals and Silence. The church was built in 1723. That's 4 stops.

Sources: This tour draws on information from oldnorth.com and the Wikipedia article on the church.
```

---

## Acceptance criteria — evidence

**AC1 — 4 and 6 stops → one generation + one hit.**
Live run: the 4-stop and 6-stop keys are identical (`058c77…`); request A was a MISS that
stored ONE row; request B was a HIT that left the row count at 1 and bumped `hit_count` to
1. No second generation. ✅

**AC2 — the 4-stop delivery ends cleanly (the trap).**
The trimmed tour names neither `The Chandeliers` (stop 5) nor `The Crypt` (stop 6). The
last `Directions:` line is `Your final stop in Old North Church: The Organ.` — not a
"just ahead, the Crypt awaits" hand-off at a trimmed stop. The recap reads
`From The Steeple to The Organ … That's 4 stops.` This is covered explicitly by
`test_seam_does_not_name_trimmed_stop` and `test_recap_names_only_delivered_stops`. ✅

**AC3 — `score_tour` on the trimmed tour: `stops_delivered == 4`, no `truncated`.**
Live run reports `stops_delivered = 4` and the defects dict contains **no `truncated`** (and
no `thin`). ✅
*Transparency note:* the defects dict does show `no_story`. That is an artefact of the
synthetic fixture, whose only named person (Captain Samuel Nicholson) lived in the trimmed
Crypt stop; `no_story` is **not** in `tour_quality.REQUIRED_CLEAN` and is **not** part of
AC3. AC3 asks specifically for `stops_delivered == 4` and the absence of `truncated`; both
hold. The real-corpus test `test_asian_arts_8_to_4` (a genuine generated tour) trims 8→4
and scores with no `truncated` and no `no_story`.

**AC4 — exact-match request unchanged.**
Live run: the exact 6-stop request returns the stored content **verbatim** (`== True`).
Unit test `test_exact_match_unchanged` asserts `trim_tour_to_stops(tour, 6) == tour`. ✅

---

## Unit suite

`python3 -m pytest tests/test_local494_cache_key_buckets.py -v` → **17 passed** (0.13s):

- bucket edges + 11+ exact (5 tests)
- key collision for 1–3 / 4–6 / 7–10, non-collision for 11+, different venue/type, and
  case/whitespace normalisation (6 tests)
- trim: keeps first N, drops trimmed, seam not naming trimmed stop, recap names only
  delivered, Sources preserved, exact unchanged, undersized unchanged (7 tests)
- `score_tour` trimmed-clean + real-corpus 8→4 (2 tests)

---

## Scope / non-goals

- Step one only: collapse stop counts so one generation serves several requests. The full
  stop-pool design is **LOCAL-495**.
- No coordinate/fuzzy venue matching (that would risk merging different venues — LEAD's
  call, separate from this).
- No edits to `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `WORK_QUEUE.md`, or
  `.continuous_dev/STATUS.md`. Committed on branch; not merged.
