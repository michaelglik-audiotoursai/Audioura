##### READY FOR REVIEW

# LOCAL-73: News Article Cache

**Commit:** `a69bc12` on `kiro/local73-news-cache`  
**Depends on:** LOCAL-69 (merged into `subscribed` via `storied`)

---

## Design decisions

### Cache key: content-hash, not URL

**Key = SHA256(whitespace-normalized article_text | major_points_count)**

Why not URL?
- Articles get republished at different URLs (same content, new URL)
- Same URL can serve updated content over time
- The text IS the article — hashing it gives exact identity

Content normalization: collapse all whitespace to single spaces, strip leading/trailing. This handles trivial reformatting (trailing newlines, double spaces) without changing meaning.

`major_points_count` in the key because different point counts produce different narration shapes (different topic splits, different audio files).

### TTL: 24 hours (configurable)

News is inherently perishable. Serving yesterday's article when the source has been corrected is worse than paying twice. 24h is conservative — most news consumption happens within hours of publication.

Configurable via `NEWS_CACHE_TTL_HOURS` env var (no redeploy needed). Michael can tune from the field.

TTL enforced at **read time** (the UPDATE query includes `WHERE created_at > NOW() - INTERVAL '24 hours'`). Stale entries remain in the table until opportunistic cleanup removes them — no background job needed.

### Architecture: reference, not blob duplication

`news_cache` stores only the `article_id` reference. The actual audio ZIP lives in `news_audios` (where it already is after generation). This avoids doubling storage for the large binary.

On cache hit: look up the `article_id` → fetch ZIP from `news_audios` → return it.

---

## Files changed

| File | Change |
|------|--------|
| `news_cache_layer1.py` | **NEW** — cache module: `_cache_key()`, `get_cached_news()`, `store_news()`, `invalidate_expired()` |
| `migration/sql/008_news_cache.sql` | **NEW** — DDL for `news_cache` table |
| `cost_meter.py` | Added `"news_cache_hit"` to `VALID_OPERATION_TYPES` |
| `news_orchestrator_service.py` | Cache check before generation; cache store + metering after |
| `tests/test_local73_news_cache.py` | **NEW** — 39 tests (30 unit, 9 integration) |
| `tests/test_local60_cost_metering.py` | Updated expected types set to include `news_cache_hit` |

---

## Live evidence — TTS not re-run (MEASURED, NOT INFERRED)

### Method

Copied updated `news_cache_layer1.py`, `news_orchestrator_service.py`, and `cost_meter.py`
into the running `news-orchestrator-1` container via `docker cp`, then restarted the
container. The news-generator, news-processor, and polly-tts containers are live and
unmodified — they process real articles through the full pipeline.

Polly TTS call count measured by counting `POST /synthesize` log entries in the
`audioura-polly-tts-1-1` container before and after each request.

### Sequence

**Baseline:** Polly call count = 212

#### Request 1 — Fresh generation (cache miss)

```
$ curl -s -X POST http://localhost:5012/generate-news -H "Content-Type: application/json" \
  -d '{"article_text": "Scientists at MIT announced today a groundbreaking discovery in quantum computing. The research team led by Dr. Sarah Chen has developed a new qubit architecture that maintains coherence for over 10 milliseconds at room temperature. This achievement could accelerate the timeline for practical quantum computers by a decade. The team published their findings in Nature Physics. Industry experts say this could revolutionize drug discovery and cryptography.", "request_string": "MIT Quantum Computing Breakthrough", "secret_id": "LIVE-CACHE-PROOF", "major_points_count": 3}'

{
    "article_id": "53918de7-7558-44c7-ae10-3be9185a6d1b",
    "cache_hit": false,
    "message": "News article processed successfully",
    "status": "success"
}
```

Polly call count after: **219** (7 TTS calls for the article)

#### Request 2 — Same article text (cache hit)

```
$ curl -s -X POST http://localhost:5012/generate-news [same payload]

{
    "article_id": "53918de7-7558-44c7-ae10-3be9185a6d1b",
    "cache_hit": true,
    "message": "News article served from cache",
    "status": "success"
}
```

Polly call count after: **219** (ZERO additional TTS calls)

#### Cost ledger state after both requests

```
 operation_type | our_cost_usd | cache_hit |                job_id                |          created_at
----------------+--------------+-----------+--------------------------------------+-------------------------------
 news_generate  |     0.003648 | f         | 53918de7-7558-44c7-ae10-3be9185a6d1b | 2026-07-31 21:43:51.09078+00
 news_cache_hit |     0.000000 | t         | 53918de7-7558-44c7-ae10-3be9185a6d1b | 2026-07-31 21:44:15.013151+00
```

**This is the acceptance criterion:** first request metered `news_generate` at $0.003648,
second request metered `news_cache_hit` at $0.000000. Polly call count did not increase.

#### Audio byte-identity confirmation

```
Download 1 MD5: 2f662c666739e525d1c6bca661e1046f (755,534 bytes)
Download 2 MD5: 2f662c666739e525d1c6bca661e1046f (755,534 bytes)
Byte-identical: YES
```

### TTL invalidation (live)

```
# Backdate cache entry to 25h ago (past 24h TTL)
UPDATE news_cache SET created_at = NOW() - INTERVAL '25 hours' WHERE article_id = '53918de7-...';

# Same article text, third request — cache miss due to TTL expiry
{
    "article_id": "55b79c0a-af46-4c74-8ecd-3d6303872b38",
    "cache_hit": false,
    "message": "News article processed successfully",
    "status": "success"
}

Polly calls before: 219 → after: 226 (7 new TTS calls — full regeneration)
```

Final ledger shows three rows: generate, cache_hit, generate — as expected.

---

## Test suites

### LOCAL-73 unit + integration: 39/39 pass

```
$ DATABASE_URL="postgresql://admin:password123@localhost:5433/audiotours" \
  DB_PORT=5433 DB_HOST=localhost \
  python3 tests/test_local73_news_cache.py --integration

  30/30 unit checks passed
  9/9 integration checks passed
  39/39 checks passed
```

### Regression suites pass

```
$ python3 tests/test_local60_cost_metering.py
=== ALL TESTS PASSED ===

$ python3 tests/test_local64_cost_ceiling.py
Results: 31 passed, 0 failed
=== ALL TESTS PASSED ===
```

---

## Migration

`migration/sql/008_news_cache.sql` — applied and verified:
```
Table: news_cache
Columns: cache_key (PK, VARCHAR 64), article_id, article_text_hash,
         major_points_count, request_string, created_at (TIMESTAMPTZ),
         hit_count, content_length
Indexes: idx_news_cache_created_at, idx_news_cache_article_id
```

---

## Limitations — what is and is NOT proven

### Proven live (real services, real DB, real Polly)

| What | How |
|------|-----|
| Cache miss → full pipeline → Polly called 7 times | Polly log count: 212 → 219 |
| Cache hit → $0.00 metered, Polly NOT called | Polly log count: 219 → 219 (zero increase) |
| Ledger rows: `news_generate` with real cost, `news_cache_hit` at $0.00 | Queried cost_ledger directly |
| Audio byte-identical across downloads | MD5 match on 755KB ZIP |
| TTL invalidation → full regeneration | Backdated 25h, Polly count 219 → 226 |

### Proven with integration tests (real Postgres, mocked services)

| What | How |
|------|-----|
| Cache key determinism + whitespace normalization | 39/39 tests pass |
| hit_count increments on each cache hit | Integration test verifies hit_count=3 after 3 reads |
| Expired entries not served (TTL enforcement at read time) | Backdated entry returns None |
| `invalidate_expired()` removes stale entries | Integration test confirms deletion |

### NOT proven / cannot verify in this environment

| What | Why |
|------|-----|
| Cloud Run inter-service auth (`_get_auth_headers`) | Local Docker uses unauthenticated HTTP; GCP metadata server not available |
| Container Dockerfile includes `news_cache_layer1.py` | Live proof used `docker cp` to inject the module; production deploy needs `Dockerfile.news-orchestrator` updated to `COPY news_cache_layer1.py .` |
| Multi-user concurrency on cache | Single-user test; UPSERT handles race conditions by design but not load-tested |
| Cache behaviour under very long article text (>100KB) | SHA256 handles any input length; not tested with extreme sizes |
| `tests/db_connection.py` shared helper from LOCAL-77 | LOCAL-73 tests use inline `_get_db_url()` — migration to shared helper is a follow-up |

### Known pre-existing issue (not introduced by LOCAL-73)

`tests/test_news_quota_integration.py` T2 ("over quota → 429") fails with 401 — this is a
pre-existing entitlements/auth issue from LOCAL-69's container state. The test file was not
modified by LOCAL-73 (last commit: `0afe7ca`).

---

## Dockerfile update needed for production

`Dockerfile.news-orchestrator` must be updated to include the cache module:

```dockerfile
COPY news_cache_layer1.py .
```

This was bypassed for live proof via `docker cp`. The deployed image needs this COPY line
before the cache will survive a container recreation.
