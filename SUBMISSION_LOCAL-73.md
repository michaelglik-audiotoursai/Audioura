##### READY FOR REVIEW

# LOCAL-73: News Article Cache — Rebased onto `subscribed`

**Branch:** `kiro/local73-news-cache`  
**Base:** `origin/subscribed` (includes LOCAL-69, LOCAL-77, LOCAL-68)  
**Depends on:** LOCAL-69 (news metering) — preserved in full during rebase

---

## Rebase summary

Rebased onto current `origin/subscribed` (commit `3411407`). The only conflict was
in `news_orchestrator_service.py` — LOCAL-69's metering block vs LOCAL-73's
cache-store + metering block. Resolution:

1. **LOCAL-73's cache check** stays (before the pipeline) — unchanged
2. **LOCAL-73's cache store** stays (after the pipeline) — stores article_id reference
3. **LOCAL-69's detailed metering** replaces LOCAL-73's simple metering — preserves
   `description` field, segmented TTS cost calculation, and LLM cost logic

Also updated `tests/test_local69_news_metering.py`: flipped `test_no_news_cache_hit_type()`
→ `test_news_cache_hit_type_exists()` since LOCAL-73 adds the type that LOCAL-69
documented as missing.

---

## Files changed (vs `origin/subscribed`)

| File | Change |
|------|--------|
| `news_cache_layer1.py` | **NEW** — cache module: `_cache_key()`, `get_cached_news()`, `store_news()`, `invalidate_expired()` |
| `migration/sql/008_news_cache.sql` | **NEW** — DDL for `news_cache` table |
| `cost_meter.py` | Added `"news_cache_hit"` to `VALID_OPERATION_TYPES` |
| `news_orchestrator_service.py` | Cache check before pipeline; cache store after; LOCAL-69 metering preserved |
| `tests/test_local73_news_cache.py` | **NEW** — 39 tests (30 unit, 9 integration) |
| `tests/test_local60_cost_metering.py` | Updated expected types set to include `news_cache_hit` |
| `tests/test_local69_news_metering.py` | Updated: `news_cache_hit` now exists (was "not yet") |
| `Dockerfile.news-orchestrator` | Added `COPY news_cache_layer1.py .` |
| `SUBMISSION_LOCAL-73.md` | This file |

---

## Live evidence — TTS not re-run (MEASURED on rebased code)

### Method

Injected rebased `news_orchestrator_service.py`, `news_cache_layer1.py`, and `cost_meter.py`
into the running `news-orchestrator-1` container via `docker cp` + restart. The
news-generator, news-processor, and `audioura-polly-tts-1` containers are live and
unmodified — they process real articles through the full pipeline.

Polly TTS call count measured by counting `POST /synthesize` log entries in
`audioura-polly-tts-1-1` before and after each request.

### Sequence

**Baseline:** Polly call count = **229**

#### Request 1 — Fresh generation (cache miss)

```
$ curl -s -X POST http://localhost:5012/generate-news -H "Content-Type: application/json" \
  -d '{"article_text": "Researchers at Stanford University published groundbreaking findings on Thursday regarding a new approach to carbon capture. The team led by Professor James Wu demonstrated a membrane technology that can extract CO2 from ambient air at 40 percent lower energy cost than existing direct air capture methods. The study, published in Science, shows the membrane operates at room temperature using only solar power. Industry analysts estimate this could reduce the cost of carbon removal from $600 per ton to under $350, making large-scale deployment economically viable for the first time.", "request_string": "Stanford Carbon Capture Breakthrough", "secret_id": "REBASE-PROOF-73", "major_points_count": 3}'

{
    "article_id": "a53c0ecf-4c9c-4130-ba14-4884ebf80c3d",
    "cache_hit": false,
    "message": "News article processed successfully",
    "status": "success"
}
```

Polly count after: **236** (7 TTS calls for the article)

#### Request 2 — Same article text (cache hit)

```
$ curl -s -X POST http://localhost:5012/generate-news [same payload]

{
    "article_id": "a53c0ecf-4c9c-4130-ba14-4884ebf80c3d",
    "cache_hit": true,
    "message": "News article served from cache",
    "status": "success"
}
```

Polly count after: **236** (ZERO additional TTS calls)

#### Cost ledger after both requests

```
 operation_type | our_cost_usd | cache_hit |                job_id                |                  description                  |          created_at
----------------+--------------+-----------+--------------------------------------+-----------------------------------------------+-------------------------------
 news_generate  |     0.011944 | f         | a53c0ecf-4c9c-4130-ba14-4884ebf80c3d | Article: Stanford Carbon Capture Breakthrough | 2026-07-31 22:41:19.918582+00
 news_cache_hit |     0.000000 | t         | a53c0ecf-4c9c-4130-ba14-4884ebf80c3d |                                               | 2026-07-31 22:41:30.758282+00
```

**Acceptance criterion met:** first request metered `news_generate` at $0.011944 with
LOCAL-69's description field, second request metered `news_cache_hit` at $0.000000.
Polly call count did not increase (236 → 236).

#### Audio byte-identity confirmation

```
Download 1 MD5: 62c82096fc74b76c18fb0ab8bcda0097 (937,405 bytes)
Download 2 MD5: 62c82096fc74b76c18fb0ab8bcda0097 (937,405 bytes)
Byte-identical: YES
```

### TTL invalidation (live)

```
# Backdate cache entry 25h (past 24h TTL)
UPDATE news_cache SET created_at = NOW() - INTERVAL '25 hours'
  WHERE article_id = 'a53c0ecf-4c9c-4130-ba14-4884ebf80c3d';

# Request 3 — same text, cache expired → full regeneration
{
    "article_id": "504b49cc-b5df-4ab4-ac96-9c7babd6277b",
    "cache_hit": false,
    "message": "News article processed successfully",
    "status": "success"
}

Polly count: 236 → 243 (7 new TTS calls — full regeneration on TTL expiry)
```

Final ledger (3 rows): `news_generate` → `news_cache_hit` → `news_generate` — as expected.

---

## Test suites (all pass on rebased code)

```
$ DATABASE_URL="postgresql://admin:password123@localhost:5433/audiotours" \
  DB_PORT=5433 DB_HOST=localhost python3 tests/test_local73_news_cache.py --integration
  39/39 checks passed

$ python3 tests/test_local60_cost_metering.py
  === ALL TESTS PASSED ===

$ python3 tests/test_local64_cost_ceiling.py
  Results: 31 passed, 0 failed === ALL TESTS PASSED ===

$ python3 tests/test_local69_news_metering.py
  === ALL LOCAL-69 TESTS PASSED ===

$ python3 tests/test_wallet_ledger.py
  RESULTS: 8 passed, 0 failed, 8 total

$ python3 tests/test_wallet_api.py
  Results: 53/53 passed, 0 failed ALL TESTS PASSED ✓

$ python3 tests/test_local67_entitlement_gate.py
  RESULTS: 23/23 passed, 0 failed
```

---

## Limitations — what is and is NOT proven

### Proven live (real services, real DB, real Polly, rebased code)

| What | How |
|------|-----|
| Cache miss → full pipeline → Polly called 7 times | Polly log count: 229 → 236 |
| Cache hit → $0.00 metered, Polly NOT called | Polly log count: 236 → 236 (zero increase) |
| Ledger: `news_generate` with real cost + LOCAL-69 `description` | Queried cost_ledger directly |
| Ledger: `news_cache_hit` at $0.00 with `cache_hit=true` | Queried cost_ledger directly |
| Audio byte-identical across downloads | MD5 match on 937KB ZIP |
| TTL invalidation → full regeneration | Backdated 25h, Polly count 236 → 243 |
| LOCAL-69's `description` field preserved through rebase | Ledger shows "Article: Stanford Carbon Capture Breakthrough" |

### Proven with integration tests (real Postgres, mocked services)

| What | How |
|------|-----|
| Cache key determinism + whitespace normalization | 39/39 tests pass |
| hit_count increments on each cache hit | Integration test verifies hit_count=3 after 3 reads |
| Expired entries not served (TTL enforcement at read time) | Backdated entry returns None |
| `invalidate_expired()` removes stale entries | Integration test confirms deletion |
| LOCAL-69 test suite passes (`news_cache_hit` now valid) | 12/12 tests pass |

### NOT proven / cannot verify in this environment

| What | Why |
|------|-----|
| Cloud Run inter-service auth (`_get_auth_headers`) | Local Docker uses unauthenticated HTTP; GCP metadata server not available |
| Container Dockerfile builds correctly with `news_cache_layer1.py` | Live proof used `docker cp` to inject module; Dockerfile updated but not rebuilt |
| Multi-user concurrency on cache | Single-user test; UPSERT handles race conditions by design but not load-tested |
| Cache behaviour under very long article text (>100KB) | SHA256 handles any input length; not tested with extreme sizes |

---

## Design decisions (unchanged from pre-rebase)

### Cache key: content-hash, not URL

**Key = SHA256(whitespace-normalized article_text | major_points_count)**

- Articles get republished at different URLs → URL not reliable
- Same URL can serve updated content → URL not fresh
- `major_points_count` in key because different counts produce different narration shapes

### TTL: 24 hours (configurable via `NEWS_CACHE_TTL_HOURS` env var)

News is perishable. 24h is conservative — most consumption happens within hours.
TTL enforced at read time (UPDATE WHERE created_at > NOW() - INTERVAL). No background job.

### Architecture: reference, not blob duplication

`news_cache` stores only `article_id` reference. Audio ZIP lives in `news_audios` (no duplication).

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
