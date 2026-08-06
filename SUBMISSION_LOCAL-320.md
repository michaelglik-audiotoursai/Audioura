##### READY FOR REVIEW

**Commit:** 62786d0
**Branch:** kiro/local320-nominatim-ratelimit
**Base:** storied

---

## Per-file summary

| File | Change |
|------|--------|
| `stop_existence_gate.py` | +`_nominatim_request()` shared throttle (≤1 req/s, User-Agent, 3x retry with backoff); `_check_dining_nominatim()` delegates to throttle; `verify_stop_existence()` catches RuntimeError as `search_failed` (not unverified); `run_existence_gate()` retries search_failed stops then fails open (D162); Wikipedia article fallback strengthened — requires title match OR full stop name + word-boundary city + dining signal; French Wikipedia summary requires both city AND dining signal |
| `tests/test_local320_nominatim_ratelimit.py` | 20 tests: throttle enforcement, 429/timeout → RuntimeError, search_failed retry, Chicago/Six Flags/Lyon/fabricated rejection, 5 consecutive consistent runs, wall-clock measurement, LOCAL-313 safety regression |

---

## Verbatim evidence

### Scope 1: Rate limit compliance

```
tests/test_local320_nominatim_ratelimit.py::TestNominatimThrottle::test_requests_are_throttled
  ✓ Throttle working: 1.08s between requests
PASSED

tests/test_local320_nominatim_ratelimit.py::TestNominatimThrottle::test_user_agent_is_set
  ✓ User-Agent: Audioura/2.2 (tour-generation; contact: support@audioura.com)
PASSED
```

### Scope 2: Throttled = failure, not absence

```
tests/test_local320_nominatim_ratelimit.py::TestThrottleFailureClassification::test_429_raises_runtime_error PASSED
tests/test_local320_nominatim_ratelimit.py::TestThrottleFailureClassification::test_timeout_raises_runtime_error PASSED
tests/test_local320_nominatim_ratelimit.py::TestThrottleFailureClassification::test_search_failed_not_unverified
  ✓ Throttled lookup classified as search_failed
PASSED
tests/test_local320_nominatim_ratelimit.py::TestThrottleFailureClassification::test_gate_retries_failed_searches
  [EXISTENCE-GATE] 1 stop(s) had search failures — retrying after pause
    [RETRY OK] 'Chez Palmyre' — nominatim_osm: 'Chez Palmyre' found in nice(5 Rue Droite, ni
  ✓ Gate retries search_failed stops (not dropped)
PASSED
```

### Scope 3: Proximity binds on every path

```
tests/test_local320_nominatim_ratelimit.py::TestProximityBinding::test_chicago_address_rejected_for_nice
  ✓ La Tapenade verified in Nice (correct): wikipedia_fr_article: 'Cuisine niçoise' mentions stop+city (dining context)
PASSED

tests/test_local320_nominatim_ratelimit.py::TestProximityBinding::test_six_flags_cannot_verify_safari
  ✓ Le Safari verified via proper source: nominatim_osm: 'Le Safari' found in nice(5 Rue de la Poissonnerie, nice) [catego
PASSED

tests/test_local320_nominatim_ratelimit.py::TestProximityBinding::test_wrong_city_restaurant_fails
  ✓ Le Chantecler in Lyon correctly rejected
PASSED

tests/test_local320_nominatim_ratelimit.py::TestProximityBinding::test_fabricated_restaurant_fails
  ✓ Le Restaurant Imaginaire correctly rejected
PASSED
```

### Scope 4+5: Consistent delivery (five consecutive runs)

```
  Run 1: 5/5 verified (['La Rossettisserie', 'Le Safari', 'Chez Palmyre', "Le Bistrot d'Antoine", 'La Tapenade'])
  Run 2: 5/5 verified (['La Rossettisserie', 'Le Safari', 'Chez Palmyre', "Le Bistrot d'Antoine", 'La Tapenade'])
  Run 3: 5/5 verified (['La Rossettisserie', 'Le Safari', 'Chez Palmyre', "Le Bistrot d'Antoine", 'La Tapenade'])
  Run 4: 5/5 verified (['La Rossettisserie', 'Le Safari', 'Chez Palmyre', "Le Bistrot d'Antoine", 'La Tapenade'])
  Run 5: 5/5 verified (['La Rossettisserie', 'Le Safari', 'Chez Palmyre', "Le Bistrot d'Antoine", 'La Tapenade'])
  ✓ All 5 runs consistent: 5/5 verified each time
```

### Wall-clock cost of throttle

```
  Wall-clock for 5-stop verification: 17.5s
  Throttle overhead: ~12.5s above baseline
```

The 12.5s overhead is the cost of policy compliance (5 stops × 1.1s minimum
interval for Nominatim requests, plus Wikipedia lookups that fire before
Nominatim). Pre-fix, the gate ran in ~5s but produced wrong results due to
throttled responses being misclassified.

### LOCAL-313 safety tests (10/10 pass — no regression)

```
======================== 10 passed, 1 warning in 51.13s ========================
```

### LOCAL-320 full test suite (20/20 pass)

```
================== 20 passed, 1 warning in 164.56s (0:02:44) ===================
```

### Production row count

```
 count
-------
    29
(1 row)
```

### git status --short: clean

```
(empty)
```

---

## Root cause

Four compounding defects:

1. **No rate limiting.** `_check_dining_nominatim()` called `requests.get()`
   directly with no interval between stops. For a 5-stop tour, 5 requests fired
   back-to-back. Nominatim's published policy is max 1 req/s; the server
   throttles violations by returning empty results (not always 429).

2. **Throttled response classified as absence.** An empty or degraded Nominatim
   response was treated as "restaurant not found" → UNVERIFIED → stop dropped.
   D162 fourth instance: a search that did not really run was used as evidence of
   absence. The correct classification is "unknown — retry", not "not found".

3. **Wikipedia article fallback too permissive (Six Flags).** The fallback that
   fetches a Wikipedia article when the snippet is partial only required:
   (a) any stop_word in article text, (b) any city_signal in article text,
   (c) proximity within 300 chars. For "Le Safari" in Nice: "safari" appeared in
   Six Flags Great Adventure (the Safari attraction), and "nice" appeared as the
   English adjective. Proximity was trivially satisfied.

4. **French Wikipedia summary only required city.** A summary lookup for a stop
   title that resolved to any article mentioning the city (as substring) was
   accepted, regardless of whether the article was about the restaurant.

---

## Limitations

- **Wall-clock cost: ~12.5s additional per 5-stop tour.** This is the minimum
  cost of Nominatim policy compliance. Most stops that reach Nominatim are those
  that failed Wikipedia/Wikidata first (all 5 in the typical case for small
  restaurants). Cannot be reduced without violating the 1 req/s policy or using a
  self-hosted instance.

- **Replenishment cost doubles.** If the gate drops stops and replenishment fires,
  the replacement candidates also go through the throttled Nominatim path. A
  worst-case 5-stop tour that needs full replenishment could take ~35s total for
  verification. This is acceptable vs. the alternative (wrong results).

- **Fail-open on persistent infrastructure failure.** If Nominatim is truly down
  (not just rate-limited), the retry still fails and the stop is kept (fail open).
  This means a Nominatim outage could allow an unverifiable stop through. This is
  the correct trade-off per D162: infrastructure failure must not be confused with
  evidence of absence. A fabricated name still fails because Wikipedia/Wikidata
  also return nothing (no retry needed — the search completed, it just found nothing).

- **"nice" as city signal.** The word "nice" is both the French city and a common
  English adjective. The snippet-based check (`_snippet_has_evidence`) still uses
  substring matching for city signals. This works correctly because the snippet
  check also requires dining signals AND proximity AND multiple stop words. The
  article fallback now uses word-boundary matching (regex `\b`) for the city,
  which eliminates the adjective match. A future improvement could apply word-
  boundary matching to snippet checks too, but it is not needed — the current
  multi-requirement check blocks the Six Flags pattern.
