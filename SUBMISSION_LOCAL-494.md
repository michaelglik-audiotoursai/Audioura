# SUBMISSION — LOCAL-494: take `total_stops` out of the cache key (D581, step one)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-494-cache-key-buckets`
**Base:** `storied` @ `5b269de` (`git merge-base --is-ancestor 5b269de HEAD` → exit 0)

## Summary

`tour_cache_layer1._cache_key` was `SHA256(location | tour_type | total_stops)`, so
the same venue at 4 stops and at 5 stops were two unrelated paid generations. This
change keys the cache on a stop **bucket** instead of the exact count, caches the
**largest** count generated in the bucket, and **trims on delivery** — with seam
repair — to the number the caller asked for. One generation now serves every request
whose count falls in the same bucket, and a trimmed delivery is logged as a cache
**HIT**, not a generation.

This is **step one only** (collapse stop counts onto one generation). The full
stop-pool design is LOCAL-495.

## What changed

Only `tour_cache_layer1.py` is touched on the production path; the call sites in
`generate_tour_text.py` already pass `total_stops` into `get_cached_tour` /
`store_tour`, so no wiring change was needed.

### 1. Bucketing (`_stop_bucket`, `_cache_key`)

```
1-3  -> 3
4-6  -> 6
7-10 -> 10
11+  -> exact (no bucketing)
```

`_cache_key` now hashes `location | tour_type | bucket`.

**Why these edges.** Trimming can only ever *remove trailing stops* — it never
fabricates a stop. So a bucket has to be a run of counts where generating the
ceiling and trimming down reads as well as generating the exact count would have.
`1-3 / 4-6 / 7-10` are the three bands the requests actually cluster in. Beyond 10
tours are rare and long enough that trimming a 20-stop generation down to 11 would
waste most of a paid generation, so **11+ stays exact**. The ceiling of each band
(3 / 6 / 10) is what gets generated and cached; every smaller count in the band is
served by trimming that one entry.

### 2. Trim on delivery with seam repair (`trim_tour_to_stops`)

A pure text function (no DB) so it is fully unit-testable. Given a cached tour and a
smaller target count it:

1. **Keeps stops 1..N in order**, dropping every later `Stop N:` block.
2. **Repairs the trailing seam.** The new last stop's `Directions:` line pointed at
   the next — now removed — stop. It is rewritten to the generator's own final-stop
   template, `Your final stop in {venue}: {last name}.`, recovering the venue string
   from the tour's own wording (an existing `Your final stop in …` / `Continue
   through … — next is` line, or the title). This is Michael's requirement: *"whatever
   stop we take out, the previous and next stop need to adjust the directions and
   orientation."*
3. **Rewrites the closing recap to name only delivered stops** — the
   `From {first} to {last}` endpoints and the `That's N stops` count are corrected,
   and the LLM-composed highlight enumeration (`— clause, clause, and clause.`) is
   dropped, because it can name a stop that was trimmed.
4. **Preserves the `Sources:` block** verbatim.
5. **Leaves an exact / undersized request untouched** (acceptance criterion 4).

### 3. Bucket-max storage (`store_tour`, `get_cached_tour`)

`store_tour` upserts on the bucketed key and keeps whichever generation has the
**greater** `total_stops` (`ON CONFLICT … WHERE EXCLUDED.total_stops >
tour_cache.total_stops`) — because delivery can only trim down, the entry must hold
the largest count in the bucket. `get_cached_tour` trims the cached tour to the
requested count on the way out and logs the hit as
`Cache HIT (trimmed 6→4, bucket=6)`.

## Acceptance criteria — evidence

| # | Criterion | Evidence |
|---|-----------|----------|
| 1 | Same venue at 4 and 6 stops → ONE generation, one hit | `_cache_key(…,4) == _cache_key(…,6)` (`ec03e66ae82b…`); before/after run below shows MISS(6) → STORE(6) → HIT(4). DB ends with **one row**, `hit_count = 1`. |
| 2 | 4-stop delivery ends cleanly — no hand-off to a trimmed stop | Last line: `Directions: Your final stop in Musee Des Arts Asiatiques (Asian Art Museum): Statue de Bouddha.` Recap: `From La geste de Bouddha to Statue de Bouddha …`. No navigation/recap line names a trimmed stop. Explicit test `test_seam_does_not_name_trimmed_stop`. |
| 3 | `score_tour` on the trimmed tour: `stops_delivered == 4`, no `truncated` | Run below: `stops_delivered : 4`, `truncated defect: False`. |
| 4 | Exact-match request unchanged | `trim_tour_to_stops(tour, 6) == tour` and `(tour, 8) == tour`; tests `test_exact_match_unchanged`, `test_undersized_request_unchanged`. |

## Before / after — real run served from cache

Run with the **real** cache functions against a throwaway Postgres database
(`local494_demo`, dropped afterwards). A real 8-stop corpus tour, trimmed to 6 by
the production trimmer, stands in for the "generated" 6-stop content — no paid
generation is invoked. Full log: `LOCAL494_BEFORE_AFTER.log` (reproduce with
`python3 local494_before_after_demo.py`).

```
LOG INFO: Cache MISS (bucket=6): Musee des Arts Asiatiques, Nice, France / museum / 6
LOG INFO: Cache STORE (bucket=6): Musee des Arts Asiatiques, Nice, France / museum / 6 (key=ec03e66ae82b…)
LOG INFO: Cache HIT (trimmed 6→4, bucket=6): Musee des Arts Asiatiques, Nice, France / museum / 4

KEY EQUALITY — 4-stop and 6-stop requests resolve to ONE cache key
  bucket(4) = 6   bucket(6) = 6
  key(4 stops) = ec03e66ae82bf3b0…
  key(6 stops) = ec03e66ae82bf3b0…
  SAME KEY: True

REQUEST A — 6 stops (cold cache): expect MISS, then generate + store
  get_cached_tour(6) -> MISS (None)
  [generate 6-stop tour once — this is the ONE paid generation]

REQUEST B — 4 stops, same venue: expect HIT (trimmed), NO generation
  get_cached_tour(4) -> HIT

4-STOP DELIVERY — seam + recap check
  stops delivered: 4 -> ['La geste de Bouddha', 'Daim et Daine symbolisant le premier sermon de Bouddha', 'Masque du vieillard kojô', 'Statue de Bouddha']
  last Directions line: Directions: Your final stop in Musee Des Arts Asiatiques (Asian Art Museum): Statue de Bouddha.
  closing recap: From La geste de Bouddha to Statue de Bouddha, you have followed the thread of The Vision of Pierre-Yves Trémois. Le musée a été inauguré le 16 octobre 1998.

SCORE — tour_quality.score_tour on the trimmed 4-stop delivery
  stops_delivered : 4
  truncated defect: False
  thin defect     : False
  defects         : {'no_story': 'no named people anywhere in the tour'}

VERIFY DB — one row (one generation) served both requests
  cached total_stops = 6 (bucket max)   hit_count = 1

RESULT: 1 generation, 1 stored row, 1 cache hit serving the 4-stop request.
```

(The `no_story` defect is inherent to this corpus tour — the Asian-art object
descriptions name no people — and is not in `score_tour`'s `REQUIRED_CLEAN` set, so
the tour scores `clean`. It is unrelated to trimming: the untrimmed 6- and 8-stop
versions carry it too.)

### Bucket-max storage, verified on the same DB

```
after 5 then 4: (5, 'FIVE')   # a smaller 4-stop generation does NOT overwrite the 5
after 6:        (6, 'SIX')    # a larger 6-stop generation DOES replace it
```

## Tests

`tests/test_local494_cache_key_buckets.py` — **17 tests, all pass**, no DB required
(pure functions):

```
$ python3 -m pytest tests/test_local494_cache_key_buckets.py -q
17 passed in 0.11s
```

Coverage: bucket edges and 11+ exact; key collision for 4&6, 1-3, 7-10; 11+ not
colliding with the bucket; different venue / tour_type never collide; case &
whitespace normalisation; trim keeps stops 1..N in order; trimmed stops dropped;
**seam never names a trimmed stop** (AC2); recap names only delivered stops and count
fixed; Sources preserved; exact-match and oversized requests unchanged; `score_tour`
`stops_delivered == 4` with no `truncated` (AC3); and the trimmer exercised on a real
corpus tour (Asian Arts 8→4).

## Scope note / known limitation

Deterministic seam repair covers the parts the generator emits from fixed templates:
the trailing `Directions:` hand-off and the closing recap. The **opening intro and
per-stop body prose are LLM-generated** and can still mention a trimmed stop by name
(e.g. Stop 1's "the route spans from … to …", or an object description that
references a later piece). Rewriting free prose is out of scope for step one and is
what the LOCAL-495 stop-pool design addresses; the acceptance criteria here target the
navigation seam and the recap, which are fully repaired.

## Files

- `tour_cache_layer1.py` — bucketing, `trim_tour_to_stops`, bucket-max store, trim-on-delivery hit.
- `tests/test_local494_cache_key_buckets.py` — new unit tests.
- `local494_before_after_demo.py` — reproducible before/after driver.
- `LOCAL494_BEFORE_AFTER.log` — captured run.
