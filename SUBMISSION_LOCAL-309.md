##### READY FOR REVIEW

**Task:** LOCAL-309 — Verified-unavailable scoring with live shortfall search  
**Branch:** kiro/local309-verified-unavailable  
**Commit:** 7d1329a  
**Base:** storied (6d68e70)

---

## Per-file summary

| File | Change |
|------|--------|
| `shortfall_search.py` | **NEW.** Bounded Wikipedia/Wikidata search for missing-stop verification. Cache by (area, date), max 5 queries/tour, 10s timeout, fail closed. |
| `tour_rubric_scorer.py` | Updated weights: FABRICATED -3.0×, UNAVAILABLE 0.0× (search-confirmed only), PIPELINE_LOST -1.0× (unchanged). Integrated shortfall_search for tours with missing stops. Added `venue_name` param to `compute_score` and `score_tour_file`. |
| `tests/test_local309_verified_unavailable.py` | **NEW.** 29 unit tests: all four classifications, search-failure→PIPELINE_LOST, caching, bounds, evidence recording, gate-not-weakened, cost measurement. |
| `tests/test_local305_missing_stop_fairness.py` | Updated 8 tests to reflect LOCAL-309 weight changes (FABRICATED -1.5→-3.0, UNAVAILABLE -0.15→0.0, exhausted flag alone no longer grants UNAVAILABLE). |

---

## Verification evidence

### 1. All four classifications tested (unit tests)

```
29 passed — tests/test_local309_verified_unavailable.py
24 passed — tests/test_local305_missing_stop_fairness.py
53 total, 0 failed
```

### 2. Riviera shortfall (rich area) → search finds candidates → PIPELINE_LOST → penalised

```
=== Riviera Shortfall Test ===
Requested: 8, Delivered: 5, Missing: 3
Total queries: 1
  Slot 1: PIPELINE_LOST
    Candidates: ['Villa Riviera', 'Southern France', 'Buick Riviera', ...]
    Evidence: search found 10 additional candidates in area → shortfall is our failure
```

### 3. Genuinely thin area → search finds nothing → UNAVAILABLE → 0 cost

```
=== Very Thin Area Test (Bzhyzhkh hamlet, Kabardino-Balkaria) ===
Requested: 5, Delivered: 2, Missing: 3
Total queries: 2
  Slot 1: UNAVAILABLE
    Candidates: []
    Evidence: search confirmed no further candidates in area → genuine scarcity;
             searched: 'notable landmarks bzhyzhkh hamlet kabardino-balkaria', got 0 results;
             wikidata searched: 'bzhyzhkh hamlet landmark', got 0 results
```

### 4. Search failure → PIPELINE_LOST (tested via mock)

```
TestSearchFailureFailsClosed::test_timeout_is_pipeline_lost PASSED
TestSearchFailureFailsClosed::test_rate_limit_429_is_pipeline_lost PASSED
TestSearchFailureFailsClosed::test_connection_error_is_pipeline_lost PASSED
```

### 5. Cache hit rate on repeat run

```
Call 1: queries=2, cache_hits=0, time=0.445s
Call 2: queries=0, cache_hits=3, time=0.000s
Cache stats: {'entries': 1, 'keys': ['50ac490e82ca0415ea2082d950ac4fb5']}
```

### 6. 8/8 museum tour unaffected

```
tours/LOCAL262_asian_arts_8stop_restored.txt (8/8):
  Delivered: 8/8
  Coverage: 1.0
  Missing: []
  Total score: +103.12 (unchanged)
  No shortfall search triggered
```

### 7. Cost per tour

```
Cost: $0.00/tour (Wikipedia/Wikidata REST APIs are free, no API key required)
Average wall time: 0.4s per shortfall search (with network latency)
Full-delivery tours (N/N): $0.00, 0ms (no search triggered)
```

### 8. Production row count

```
SELECT COUNT(*) FROM audio_tours WHERE is_test = false;
 count: 29
```

---

## Limitations

1. **Wikipedia search quality varies by region.** The "notable landmarks" query pattern works well for documented areas but may find false positives (e.g. "Buick Riviera" for French Riviera). The classification errs on the side of penalising (finding *any* candidate → PIPELINE_LOST), which is the safe direction per Michael's ruling.

2. **Cache is in-memory only.** Two separate process invocations on the same day will both pay. A persistent cache (filesystem or DB) would fix this but adds complexity. The cost is $0 per query (free APIs), so the penalty is latency only (~0.4s).

3. **Wikidata rate-limits (D220).** HTTP 429 → PIPELINE_LOST (fail closed, per spec). Under burst load, multiple concurrent tours might all hit the limit and all classify as PIPELINE_LOST. This is conservative (never buys a free pass) but could over-penalise in a burst. The 10s timeout and max-5-queries cap bound the blast radius.

4. **"No data found" is weak evidence.** Per D162: a search returning nothing is weak evidence. The zero-cost UNAVAILABLE is only available when BOTH Wikipedia AND Wikidata return nothing for the area. A single false-negative (Wikipedia temporarily down for one query) triggers PIPELINE_LOST, not UNAVAILABLE.
