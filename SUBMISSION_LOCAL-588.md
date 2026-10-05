# SUBMISSION — LOCAL-588: add a cache version to the tour-cache key

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-588-tour-cache-version`  (base: `storied` = af19b18)

## Defect
`tour_cache_layer1` keyed on `(normalised location, tour_type, stop bucket)` with
**no code version**. A repeated request therefore forever got the tour made by the
code of the day it was first stored. The 16:40 Griffin row held Michael's junk tour
391 (website menu items as stops) and would have been served to his next 4–6-stop
Griffin request with none of LOCAL-580/583/584 applied. 198 of 200 local rows
pre-date today; the oldest is 2026-07-30.

## Change (`tour_cache_layer1.py`)
1. **`TOUR_CACHE_VERSION = 2`** — folded into the key hash exactly like
   `venue_resolver.CORPUS_VERSION`. The key is now
   `SHA256("v{VERSION}|{normalised location}|{tour_type}|{stop bucket}")`.
   A bump changes the key, so every row written at an older version becomes a
   **cache MISS** and is regenerated under current code. **Old rows are never
   deleted** — they just stop being found and age out.
   - A comment states when to bump: *any change to stop selection, gates, or
     narration that changes what a listener would hear.*
   - The legacy migration-fallback key (`_legacy_cache_key`) is version-prefixed
     too, so no tour made by old code can be served through the fallback path.
2. **Lookup log line** on every lookup:
   `[S20] cache v<N> HIT|MISS key=<first 12>` (emitted on both the HIT and MISS
   branches of `get_cached_tour`).

## Tests
`tests/test_local588_cache_version.py` (new, 13 tests, pure functions — no DB):
- `TOUR_CACHE_VERSION == 2`; the constant actually participates in the hash.
- **same request, same version → same key (HIT)**; **same request after a bump →
  different key (MISS)**; a v1 row is unreachable at v2+; the legacy fallback key
  is version-gated too.
- **LOCAL-494 bucket + collision behaviour re-asserted unchanged** at the current
  version: 4↔6 collide, 1-3 collide, 7-10 collide, 11+ exact, different
  venue/type never collide (the version shifts all keys together, it does not
  reshape buckets).
- The `[S20]` HIT and MISS log lines are asserted against a mocked connection.

```
$ python3 -m pytest tests/test_local588_cache_version.py tests/test_local494_cache_key_buckets.py -q
..............................                                           [100%]
30 passed in 0.18s
```
(13 LOCAL-588 + 17 LOCAL-494 — the existing LOCAL-494 bucket/trim suite stays green.)

## Live, ISOLATED (CLAUDE.md 2026-10-05: never touch `audioura-*` containers)
My **own** throwaway Postgres container `local588-pg` on port **5544**
(`docker run --rm --name local588-pg … postgres:15-alpine`). No `audioura-*`
container was touched. `DATABASE_URL` pointed at it; `STORIED_MODE=true`;
cache ON; `TOUR_LLM_MODEL=gpt-4o-mini`; `COST_HARD_LIMIT_USD=0.50`.

One cheap 3-stop walking request (`Boston Common, Boston, MA`), run twice via the
real `generate_tour_text` path (`run_local588_cache_version.py`):

- **Run 1 — MISS, generates + stores** (`key=50423762df1d…`):
  ```
  CACHE MISS: Boston Common, Boston, MA / walking / 3
  Total API cost: $0.1244 (23699 tokens)      # OpenAI < $0.50 cap
  Cache STORE (bucket=3): Boston Common, Boston, MA / walking / 3 (key=50423762df1d…)
  ```
- **Run 2 — HIT, $0.00 OpenAI**:
  ```
  [S20] cache v2 HIT key=50423762df1d
  CACHE HIT: Boston Common, Boston, MA / walking / 3
  Total API cost: $0.0000 (0 tokens)
  ```

Then a lookup-only probe against the same stored row, showing the version MISS
line and that a bump invalidates the old row (which stays in the DB):
```
-- lookup at current version (v2): expect HIT on stored row --
[S20] cache v2 HIT key=50423762df1d
-- same request after a version bump (v3): expect MISS (old row unreachable) --
[S20] cache v3 MISS key=34a09549d2e4
```

Both acceptance log lines captured live:
```
[S20] cache v2 HIT key=50423762df1d
[S20] cache v3 MISS key=34a09549d2e4
```

Nothing was DELETEd — the row count stayed at 1 after the bump probe
(`SELECT count(*) FROM tour_cache` → `1`); the v3 request simply could not reach
the v2 row. Container stopped afterward (auto-removed via `--rm`).

## Files
- `tour_cache_layer1.py` — `TOUR_CACHE_VERSION`, versioned key + legacy key, `[S20]` log.
- `tests/test_local588_cache_version.py` — new suite.
- `run_local588_cache_version.py` — isolated live driver.
- `SUBMISSION_LOCAL-588.md` — this file.
