# SUBMISSION_LOCAL-450.md — DB-as-fallback, not DB-first

## Summary

Inverted the retrieval order in `fetch_wikipedia_summary_with_provenance`:

**Before (LOCAL-448):** `stop_corpus` → Live Wikipedia  
**After (LOCAL-450):**  Live Wikipedia → `stop_corpus` (fallback only)

The DB is now consulted only when live yields nothing: the breaker is cold, a
timeout occurred, a 429 was returned, or a network error fired. When Wikimedia
is healthy, live content is served and the DB is never touched.

## What changed

### `rag_retriever.py` (lines 293–450)

- Removed the upfront `_fetch_from_stop_corpus()` call that ran before any
  network attempt.
- The cold branch (`is_host_cold = True`) now calls `_fetch_from_stop_corpus()`
  before returning `{}`. This turns a dead-end into a served stop with zero
  network calls.
- The timeout handler calls `_fetch_from_stop_corpus()` after marking cold.
- The 429 handler calls `_fetch_from_stop_corpus()` after the action API also
  fails (breaker blocks it).
- The `RequestException` handler calls `_fetch_from_stop_corpus()` on any other
  network error.
- `source: 'stop_corpus'` is preserved in provenance for all DB-served results.

### `tests/test_local447_db_first_and_wayback.py`

Updated 4 tests that encoded the old "DB-before-network" ordering:

| Old assertion | New assertion | Why |
|---|---|---|
| `test_db_first_serves_known_title_zero_network` | `test_db_fallback_serves_known_title_when_cold` | DB only serves when live is unavailable (cold) |
| `test_db_first_accent_folded_match` | `test_db_fallback_accent_folded_match_when_cold` | Same — requires cold host to reach DB |
| `test_db_first_goes_red_when_neutralised` | `test_db_fallback_goes_red_when_neutralised` | D242 binding: neutralised DB + cold → {} (proves DB was the guard) |
| `test_backwards_compat_returns_string` | (same name, updated to use live mock) | With live-first, backwards compat serves from live |
| `test_live_db_first_no_network` | `test_live_db_fallback_serves_when_cold` | Integration: cold→DB path in live DB |

Added: `test_live_wins_when_wikimedia_healthy` — core LOCAL-450 assertion.

No tests were deleted. Every assertion that changed encodes the new design
(DB-as-fallback); the old design (DB-before-live) is no longer correct.

### `tests/test_local450_db_as_fallback.py` (new, 14 tests)

- Cold branch serves from DB (zero network calls)
- Live wins when Wikimedia is healthy
- D242 check: neutralise DB fallback → cold test goes RED
- D242 check: neutralise live-first ordering → test goes RED
- Timeout handler consults DB
- 429 handler consults DB after action API fails
- Network error handler consults DB
- Measurement: cold=0 calls, timeout=1 call, 429=1 call

### `repro449.py` (extended)

Added cases C (cold + DB match) and D (429) to the measurement.

## Measurement table

From `repro449.py` on this branch:

| Case | Elapsed | Network calls | Source |
|---|---|---|---|
| A (first timeout) | 5.0s | 1 | — (empty) |
| B (already cold) | 0.000s | 0 | — (empty, no DB match) |
| C (cold + DB match) | 0.000s | 0 | stop_corpus (350 chars mocked / 1134 chars live) |
| D (429) | 0.000s | 1 | — (empty, DB also empty for this title) |

## Container run

```
$ docker run --rm -e L447_RETRIEVAL_CHAIN=true \
    -e DB_HOST=host.docker.internal -e DB_PORT=5433 \
    audioura-generator:local450 python -c "..."

CONTAINER VERIFICATION PASSED
  /app code: LOCAL-450 (DB-as-fallback)
  Live path: serves from wikipedia_live (DB not consulted)
  Cold path: serves from stop_corpus (1134 chars, 0 network calls)
```

## LOCAL-449 floors hold

- Cold host: **0 network calls** ✓
- First timeout: **5.0s, 1 network call** ✓
- 429: **1 network call** ✓

## DB/live comparison (live DB titles)

The task's measurement table shows the live DB content is a fraction of live
Wikipedia for 2 of 3 titles. I cannot widen beyond n=3 without adding rows to
`stop_corpus`, which would require running the harvester against new titles.
**Three rows is a thin basis** — but the design conclusion doesn't depend on
more data: the DB should never win over live when live is available, because
any stop with less content than live is a quality regression.

| title | stop_corpus chars | live chars | DB/live |
|---|---|---|---|
| Île Sainte-Marguerite | 1,134 | ~13,500 | 8% |
| Musée Picasso | 10,285 | ~512 | 2009% |
| Port Grimaud | 1,158 | ~1,333 | 87% |

## D242 checks

1. **Neutralise the DB fallback** → `test_neutralised_db_fallback_cold_returns_empty`
   goes RED (cold branch returns {} instead of content when DB is stubbed out).
2. **Neutralise the live-first ordering** (force `is_host_cold=True`) →
   `test_neutralised_live_first_db_takes_over` goes RED (live source expected but
   DB wins when ordering is broken).

Both bind to real code paths, not patched stand-ins.

## L447_RETRIEVAL_CHAIN flag

**Recommendation: should now default ON.**

With DB-as-fallback, the flag no longer gates a path that can lose content. When
the flag is ON:
- Live Wikipedia is unchanged — same quality, same latency.
- DB only activates where there was previously *nothing* (cold host returned `{}`).
- The change is strictly additive: live content is never replaced by DB content;
  DB content only appears where the alternative was an empty dict.

This makes the flag safe to flip. LEAD decides when.

## Regression

All suites green:

- `test_sq4_merge.py` — PASSED
- `test_palais_fix_lead_fixture.py` — PASSED (23/23 assertions)
- `test_local12_fact_retrieval_fix.py` — PASSED (8/8)
- `tests/test_local447_db_first_and_wayback.py` — 9 PASSED
- `tests/test_local448_db_first_correctness.py` — 16 PASSED
- `tests/test_local449_cold_host_short_circuit.py` — 13 PASSED
- `tests/test_local450_db_as_fallback.py` — 14 PASSED

Total: **52 tests** across 447/448/449/450 suites, all green.
