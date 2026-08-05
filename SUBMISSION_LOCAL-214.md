##### READY FOR REVIEW

## Commit

`b398da2` on branch `kiro/local214-resolver-host-connection`

## File changed

| File | Summary |
|------|---------|
| `venue_resolver.py` | Added `_is_inside_container()` (checks `/.dockerenv`). Rewrote `_get_db_connection()` to gate localhost→postgres-2 and admin:admin→admin:password123 rewrites behind container detection. Distinguished misconfiguration (loud ERROR) from absence (quiet skip). Container default unchanged. |

## Evidence

### 1. Host-side connection (the bug)

Before (reproduced):
```
$ DATABASE_URL='postgresql://admin:password123@localhost:5433/audiotours' \
  python3 -c "import venue_resolver as vr; print(vr._get_db_connection())"
  [venue_cache] DB connection failed: could not translate host name "postgres-2"
None
```

After:
```
$ DATABASE_URL='postgresql://admin:password123@localhost:5433/audiotours' \
  python3 -c "import venue_resolver as vr; conn = vr._get_db_connection(); print(conn)"
<connection object ...; dsn: 'user=admin password=xxx connect_timeout=5 dbname=audiotours host=localhost port=5433', closed: 0>
```

Row read through it:
```
Rows in venue_corpus: 16
```

### 2. Host without DATABASE_URL (graceful skip)

```
$ python3 -c "import os; os.environ.pop('DATABASE_URL',None); import venue_resolver as vr; print(vr._get_db_connection())"
  [venue_cache] No DATABASE_URL set (host mode) — venue cache skipped
None
```

### 3. Container — default (no DATABASE_URL)

```
$ docker exec audioura-tour-generator-1 python3 -c "..."
Inside container: True
Container default connection: <connection ...; host=postgres-2 port=5432>
Rows: 16
TEST 1 PASS: container default works
```

### 4. Container — localhost URL (rewrite fires)

```
$ docker exec -e DATABASE_URL='postgresql://admin:password123@localhost:5432/audiotours' \
  audioura-tour-generator-1 python3 -c "..."
Inside container: True
Localhost URL (rewritten in container): <connection ...; host=postgres-2 port=5432>
Rows: 16
TEST 2 PASS: localhost rewritten to postgres-2 inside container
```

### 5. End-to-end MAMAC generation from host

```
VENUE_CACHE_DB_URL='postgresql://admin:password123@localhost:5433/audiotours'
STORIED_MODE=true  TOUR_LLM_MODEL=gpt-4o-mini

  [venue_cache] HIT for Q936859 (tier=exhibit_museum, expires=2026-08-30 18:12:43.158897)
  [D1v2] Venue resolved: Q936859 → URL=http://www.mamac-nice.org/, lang=fr
  [D1v2] Cache HIT: 14 canonical titles (tier=exhibit_museum), 0 catalogue works, combined_text=315185 chars
  [D1v2] 4/4 works verified — tier: exhibit_museum
  [D1] Tier: exhibit_museum (4 verified works)
  [LOCAL-16 GATE] All 4 stops are D1v2-verified ✓

Output file: Musee_d_Art_Moderne_..._museum_tour_20260804_114108.txt
Text length: 6222 chars
```

This is the exact failure LOCAL-212 hit: `[D1] Tier:` resolving rather than `unresolvable`.

### 6. audio_tours table integrity

| Check | Before | After |
|-------|--------|-------|
| Count | 130 | 130 |
| Nice list | `[1,12,14,17,21,24,27,28,29,152]` | `[1,12,14,17,21,24,27,28,29,152]` |

No rows inserted or deleted.

## Finding: DATABASE_URL-deletion "cache bypass" in LOCAL-189/194/195/198

**The `DATABASE_URL` deletion was intended to bypass the S20 tour cache, and it did. But it ALSO disabled the venue cache as a side effect — on the host.**

Mechanism with the OLD code:
1. Test deletes `DATABASE_URL` from `os.environ`
2. S20 cache (`generate_tour_text.py` line 2520): sees no `DATABASE_URL` → skips → **intended**
3. Venue cache (`venue_resolver._get_db_connection()`): falls back to hardcoded default `postgresql://admin:password123@postgres-2:5432/audiotours` → `postgres-2` doesn't resolve on host → returns `None` silently → **unintended side effect**

**Impact:** Those experiments ran with fresh SPARQL/web mining every time (no cache reads or writes). The venue _resolution_ still worked (it doesn't depend on the cache — the cache is a performance optimization). The configuration differed from production in that production uses the cache and never re-mines a venue within the 30-day TTL.

**LOCAL-205 is different:** it ran `docker exec` inside the container where `postgres-2` resolves, so its `DATABASE_URL=` deletion left the venue cache using the container default successfully.

**Conclusion:** LOCAL-189, 194, 195, 198 ran in a slightly degraded configuration (no venue cache, always re-mining), but their results are still valid because the resolution path itself is identical — only the latency and cost differ. No measured outcome (style violations, anchor rates, model comparisons) depends on whether the corpus came from cache or fresh mining.

## Cost

$0.00 (MAMAC generation was a cache hit on the S20 layer; the non-cached generation used `VENUE_CACHE_DB_URL` which only read from cache, no LLM calls for venue resolution). The only LLM spend was the second generation: ~$0.01 for 2-stop gpt-4o-mini.

Total: **≤ $0.01** (well within $0.20 ceiling).

## Limitations

1. **Container test used `docker cp` to `/tmp` with a path hack** — not a rebuild, not a modification of the running `/app/venue_resolver.py`. The container's live code is unchanged. Full verification requires LEAD deploying the fix.
2. **The "loud ERROR" on misconfiguration still returns `None`** — it does not raise. Callers (`cache_get`, `cache_put`) still degrade gracefully. The improvement is observability, not behavior change. A future task could make it raise if the caller wants to fail-fast.
3. **No test for `VENUE_CACHE_DB_URL` override inside the container** (only tested `DATABASE_URL` and default). This path is straightforward (env var takes priority, no rewrite needed).
