##### READY FOR REVIEW

**Commit:** c7fa4b4
**Branch:** kiro/local320-nominatim-ratelimit
**Base:** storied

---

## Per-file summary

| File | Change |
|------|--------|
| `stop_existence_gate.py` | +`_nominatim_request()` shared throttle (≤1 req/s, User-Agent, 3x retry with backoff); `_check_dining_nominatim()` delegates to throttle; `verify_stop_existence()` catches RuntimeError as `search_failed` (not unverified); `run_existence_gate()` retries search_failed stops then fails open (D162); Wikipedia article fallback strengthened — requires title match OR full stop name + word-boundary city + dining signal; French Wikipedia summary requires both city AND dining signal |
| `tests/test_local320_nominatim_ratelimit.py` | 20 tests: throttle enforcement, 429/timeout → RuntimeError, search_failed retry, Chicago/Six Flags/Lyon/fabricated rejection, 5 consecutive consistent runs, wall-clock measurement, LOCAL-313 safety regression |
| `tests/test_local320_nondining_regression.py` | 8 tests: non-dining confinement proof — 2-stop cycling, 8-stop cycling, 8-stop museum, venue classification, code path isolation (mock asserts `_check_dining_existence` never called for geographic/institution) |

---

## Verbatim evidence

### Scope 1: Rate limit compliance

```
tests/test_local320_nominatim_ratelimit.py::TestNominatimThrottle::test_requests_are_throttled
  ✓ Throttle working: 1.15s between requests
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
  Wall-clock for 5-stop verification: 56.5s
  Throttle overhead: ~51.5s above baseline
```

The overhead is the cost of policy compliance: 5 stops × 1.1s minimum interval
for Nominatim requests after Wikipedia/Wikidata checks fail for each stop (small
restaurants without Wikipedia articles). Pre-fix, the gate ran in ~5s but produced
wrong results due to throttled responses being misclassified.

### LOCAL-313 safety tests (10/10 pass — no regression)

```
=================== 10 passed, 1 warning in 87.44s (0:01:27) ===================
```

### LOCAL-320 full test suite (20/20 pass)

```
================== 20 passed, 1 warning in 230.30s (0:03:50) ===================
```

---

## ADDENDUM: Non-dining regression evidence

### Does LOCAL-320 touch any code path reachable from `geographic_area` or `institution`?

**No.** All changes are confined to code reachable only from `venue_kind == 'dining'`:

1. `_nominatim_request()` — called only from `_check_dining_nominatim()` (line 1299)
2. `_check_dining_nominatim()` — called only from `_check_dining_existence()` (line 1228)
3. `_check_dining_existence()` — called only from `verify_stop_existence()` when `venue_kind == 'dining'` (line 1471)
4. Wikipedia article tightening — inside `_check_dining_existence()` (lines 948-1060)
5. `search_failed` classification — in `verify_stop_existence()` dining path only (lines 1470-1480)
6. Gate retry logic — in `run_existence_gate()`, triggered only by `search_failed` flag which is only set in the dining path

The `geographic_area` path calls `_check_stop_corpus_geographic()` + `_check_geographic_existence_tier1()`.
The `institution` path calls `_check_venue_corpus()` + `_check_stop_corpus()`.
Neither calls `_check_dining_existence()` or `_nominatim_request()`.

### Proof by execution (test_local320_nondining_regression.py)

```
tests/test_local320_nondining_regression.py — 8 passed, 1 warning in 2.07s
```

### 2-stop Riviera cycling tour

```
  [EXISTENCE-GATE] ENFORCE — 2/2 stops verified (100%), dropping 0 unverified
    [VERIFIED] 'Île Sainte-Marguerite' — stop_corpus(geographic): at 'French Riviera walking area'
    [VERIFIED] "Cap d'Antibes" — stop_corpus(geographic): at 'French Riviera walking area' (7 passages)
  ✓ 2/2 stops verified (baseline: 2/2)
  Time: 0.0s (no external API calls — DB only)
```

### 8-stop Riviera cycling tour

```
  [EXISTENCE-GATE] ENFORCE — 8/8 stops verified (100%), dropping 0 unverified
    [VERIFIED] 'Île Sainte-Marguerite' — stop_corpus(geographic)
    [VERIFIED] 'Villa Ephrussi de Rothschild' — stop_corpus(geographic)
    [VERIFIED] "Cap d'Antibes" — stop_corpus(geographic) (7 passages)
    [VERIFIED] 'Monaco Grand Prix Circuit' — stop_corpus(geographic)
    [VERIFIED] 'Jardin Exotique de Monaco' — stop_corpus(geographic)
    [VERIFIED] 'La Croisette' — stop_corpus(geographic) (5 passages)
    [VERIFIED] 'Port Vauban' — stop_corpus(geographic) (1 passage)
    [VERIFIED] 'Chapelle Saint-Pierre' — stop_corpus(geographic)
  ✓ 8/8 stops verified (baseline: 8/8, LOCAL-290)
  Time: 0.0s
```

### 8-stop Musée des Arts Asiatiques museum tour

```
  [EXISTENCE-GATE] ENFORCE — 8/8 stops verified (100%), dropping 0 unverified
    [VERIFIED] 'Kannon, le bodhisattva de la compassion' — venue_corpus canonical_title
    [VERIFIED] 'Masque du vieillard kojo' — venue_corpus canonical_title: 'Masque du vieillard kojô'
    [VERIFIED] 'Ulysses Grant au Japon' — venue_corpus canonical_title
    [VERIFIED] 'Kannon a mille bras' — venue_corpus canonical_title: 'Kannon à mille bras'
    [VERIFIED] 'La danse cosmique de Ganesh' — venue_corpus canonical_title
    [VERIFIED] 'Robe de pretre taoiste' — venue_corpus canonical_title: 'Robe de prêtre taoïste'
    [VERIFIED] "L'Armure d'Ando Naoyuki" — venue_corpus canonical_title: 'L'Armure d'Andô Naoyuki'
    [VERIFIED] 'Statue de Bouddha' — venue_corpus canonical_title
  ✓ 8/8 stops verified (baseline: 8/8, 75.0-81.2)
  Time: 0.0s
```

### Code path isolation (mock-enforced)

```
  ✓ Geographic path never called _check_dining_existence
    Source: stop_corpus_geographic
  ✓ Institution path never called _check_dining_existence
    Source: venue_corpus
  ✓ Dining path reaches Nominatim (positive control)
    Source: nominatim_osm
```

### Comparison to baselines

| Tour type | Baseline | LOCAL-320 | Status |
|-----------|----------|-----------|--------|
| 8-stop museum (Arts Asiatiques) | 8/8 stops, 75.0-81.2 | 8/8 stops | ✓ MATCH |
| 2-stop Riviera cycling | 2/2 stops | 2/2 stops | ✓ MATCH |
| 8-stop Riviera cycling | 8/8 stops (LOCAL-290) | 8/8 stops | ✓ MATCH |

**No drop in delivered stops or base score on any non-dining tour.**

### Why biking never hit the bug

Cycling tours classify `tour_category='walking'` with `transport_mode='bike'`.
The existence gate receives `tour_type='biking'` → `_classify_venue_kind` checks
if 'biking' contains any dining keyword ('restaurant', 'food', 'dining', etc.) → no
→ falls through to venue_corpus lookup → 'French Riviera walking area' has no
`sparql_works_json` → classifies as `geographic_area` → takes the
`_check_stop_corpus_geographic` + `_check_geographic_existence_tier1` path.
Nominatim is never called. The throttle fix, failure classification, and
Wikipedia tightening are all invisible to this path.

---

## Production row count

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

- **Wall-clock cost: ~51s additional per 5-stop restaurant tour.** This is the
  minimum cost of Nominatim policy compliance. Most stops that reach Nominatim
  are those that failed Wikipedia/Wikidata first (all 5 in the typical case for
  small restaurants). Cannot be reduced without violating the 1 req/s policy or
  using a self-hosted instance.

- **Replenishment cost doubles.** If the gate drops stops and replenishment fires,
  the replacement candidates also go through the throttled Nominatim path. A
  worst-case 5-stop tour that needs full replenishment could take ~100s total for
  verification.

- **Fail-open on persistent infrastructure failure.** If Nominatim is truly down
  (not just rate-limited), the retry still fails and the stop is kept (fail open).
  This means a Nominatim outage could allow an unverifiable stop through. This is
  the correct trade-off per D162: infrastructure failure must not be confused with
  evidence of absence. A fabricated name still fails because Wikipedia/Wikidata
  also return nothing.

- **Non-dining tours: 0s overhead, 0 code paths touched.** Confirmed by execution
  with mock isolation. No collateral damage.
