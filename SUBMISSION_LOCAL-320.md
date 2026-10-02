##### READY FOR REVIEW

**Commit:** af5317f
**Branch:** kiro/local320-nominatim-ratelimit
**Base:** storied

---

## Per-file summary

| File | Change |
|------|--------|
| `stop_existence_gate.py` | +`_nominatim_request()` shared throttle (≤1 req/s, User-Agent, 3 retries with exponential backoff); `RuntimeError` from Nominatim propagates as `search_failed` — never "unverified"; **bounce fix:** `inconclusive_stops` third state — search-failed stops kept for delivery but NOT in `verified_stops`, NOT counted as verified in log; Wikipedia article fallback requires full stop name + dining signal + city-as-word-boundary (Six Flags fix); `'off'` mode also returns `inconclusive_stops: []` for caller consistency |
| `generate_tour_text.py` | In enforce mode, inconclusive stops logged distinctly; **inconclusive replacement** block: attempts replenishment for inconclusive stops — if a verified alternative is found, swaps it in; if not, keeps the inconclusive stop for delivery (D162: never drop on failed search) |
| `tests/test_local320_inconclusive.py` | 5 tests: fabricated name NOT in verified_stops under throttle (both modes), inconclusive flag on verdict, real restaurants still delivered, stop accounting sums correctly |
| `tests/run_local320_verification.py` | End-to-end: 5 consecutive restaurant tours + 2-stop cycling + 8-stop cycling + 8-stop museum + safety constraints |

---

## What the bounce fix changes (commit ac65185)

The prior submission put search-failed stops into `verified_stops`:
```python
# BEFORE (bounced)
elif retry_verdict.get('search_failed'):
    verified_stops.append(stop_title)  # ← fabricated name "verified"
```

Now they go into a third list:
```python
# AFTER (bounce fix)
elif retry_verdict.get('search_failed'):
    inconclusive_stops.append(stop_title)  # ← kept, NOT verified
    retry_verdict['inconclusive'] = True
```

**Consequences:**
1. A fabricated name under throttle is INCONCLUSIVE, never VERIFIED.
2. The log says `"0/3 verified (0%), 3 inconclusive"` — never `"3/3 verified (100%)"`.
3. Inconclusive stops are kept for delivery (not dropped) — D162 respected.
4. Replenishment tries to find verified replacements for inconclusive stops.
5. Verdicts carry `inconclusive=True` for downstream scoring.

---

## Verbatim evidence

### LEAD's repro case: fabricated name under permanent throttle

```
  [EXISTENCE-GATE] ENFORCE — 0/3 stops verified (0%), dropping 0 unverified, 3 inconclusive
    [INCONCLUSIVE] 'Chez Palmyre' — search_failed: Nominatim rate limited (429) after 3 retries
    [INCONCLUSIVE] "Restaurant Qui N'Existe Pas Du Tout XYZ" — search_failed: Nominatim rate limited (429) after 3 retries
    [INCONCLUSIVE] 'Le Safari' — search_failed: Nominatim rate limited (429) after 3 retries

  verified  : []
  unverified: []
  inconclusive: ['Chez Palmyre', "Restaurant Qui N'Existe Pas Du Tout XYZ", 'Le Safari']
```

**"Restaurant Qui N'Existe Pas Du Tout XYZ" NOT in verified_stops. Log does NOT say 100% verified.**

### Five consecutive 5-stop Old Nice restaurant tours

```
  ✓ Run 1: requested=5, delivered=5, time=0.0s (cache)
  ✓ Run 2: requested=5, delivered=5, time=0.0s (cache)
  ✓ Run 3: requested=5, delivered=5, time=0.0s (cache)
  ✓ Run 4: requested=5, delivered=5, time=0.0s (cache)
  ✓ Run 5: requested=5, delivered=5, time=0.0s (cache)
  CONSISTENCY: PASS — all runs delivered ≥4 stops
```

### Gate execution on 5 fresh dining stops (shows throttle working)

```
  [EXISTENCE-GATE] ENFORCE — 5/5 stops verified (100%), dropping 0 unverified
    [VERIFIED] 'Chez Palmyre' — nominatim_osm: 'Chez Palmyre' found in nice(5 Rue Droite, nice) [category=amenity/restaurant]
    [VERIFIED] 'Le Safari' — nominatim_osm: 'Le Safari' found in nice(5 Rue de la Poissonnerie, nice) [category=amenity/restaurant]
    [VERIFIED] 'La Rossettisserie' — nominatim_osm: 'La Rossettisserie' found in nice(8 Rue Mascoïnat, nice) [category=amenity/restaurant]
    [VERIFIED] "Le Bistrot d'Antoine" — nominatim_osm: 'Le Bistrot d'Antoine' found in nice(3 Rue Place Vieille, nice) [category=amenity/restaurant]
    [VERIFIED] 'La Tapenade' — wikipedia_fr_article: 'Cuisine niçoise' mentions stop+city (dining context)

Gate execution time: 27.7s for 5 stops
```

### Safety constraints

```
  'Le Restaurant Imaginaire' (fabricated): verified=False ✓ REJECTED
  'Le Chantecler' in Lyon (wrong city): verified=False ✓ REJECTED
```

### Non-dining regression (addendum requirement)

```
  2-stop Riviera cycling: requested=2, delivered=2 ✓
  8-stop Riviera cycling: requested=8, delivered=8 ✓
  8-stop Musée des Arts Asiatiques museum: requested=8, delivered=8 ✓
```

Baselines met:
- 2-stop cycling: 2/2 (baseline: 2/2) ✓
- 8-stop cycling: 8/8 (baseline: 8/8) ✓
- 8-stop museum:  8/8 (baseline: 8/8, 75.0-81.2 range) ✓

### Test suite (29/29 pass)

```
tests/test_local281_dining_venue_kind.py: 14 passed
tests/test_local313_dining_nominatim.py: 10 passed
tests/test_local320_inconclusive.py: 5 passed
==================== 29 passed, 1 warning in 182.25s ====================
```

### Production row count

```
Total rows: 153, test rows: 124, real rows: 29
```

### git status --short: clean

---

## Confinement proof (addendum requirement)

**Does this change touch any code path reachable from `geographic_area` or `institution`?**

**No.** The changes are confined to the `dining` path:

1. `_nominatim_request()` — called only from `_check_dining_nominatim()` (line 1299)
2. `_check_dining_nominatim()` — called only from `_check_dining_existence()` (line 1222)
3. `_check_dining_existence()` — called only inside the `elif venue_kind == 'dining':` branch of `verify_stop_existence()` (line 1471)
4. The Wikipedia article hardening (full name + city word boundary + dining signal) — all inside `_check_dining_existence()`
5. The `inconclusive_stops` logic in `run_existence_gate()` — only triggers when `verdict.get('search_failed')`, which is only set by the `except RuntimeError` handler in the `dining` branch

Geographic tours use `_check_stop_corpus_geographic()` → `_check_geographic_existence_tier1()`.
Museum tours use `_check_venue_corpus()` → `_check_stop_corpus()`.
Neither path calls `_check_dining_existence()` or `_nominatim_request()`.

**Proven by generation:** 2-stop cycling (2/2), 8-stop cycling (8/8), 8-stop museum (8/8) — identical to pre-change baselines.

---

## Wall-clock cost of throttle

Gate execution: 27.7s for 5 dining stops (5.5s/stop average).
Breakdown: ~4-5s Wikipedia/Wikidata lookups + ~1.1s Nominatim throttle per stop.
The throttle itself adds approximately **5.5s total** to a 5-stop restaurant tour.
Non-dining tours: **zero cost** (Nominatim never called).

---

## Limitations

1. **Inconclusive stops are still delivered.** If Nominatim is permanently down AND no Wikipedia path verifies the stop, a fabricated name could still reach the user — but it will be logged as INCONCLUSIVE, not VERIFIED. The rubric can score it differently.

2. **Replenishment for inconclusive stops requires an LLM call.** If the GPT API also fails, inconclusive stops are kept as-is. This is fail-open (D162) — better than silent loss.

3. **Cache hits bypass the gate entirely.** The 5 consecutive runs hit the cache from a prior LOCAL-313 generation. In production, the first generation runs the full gate; subsequent identical requests return the cached result. This means the consistency proof shows the cache is deterministic, but does not re-prove the gate on each run. The fresh gate execution (27.7s, 5/5 verified) demonstrates the uncached path.

4. **The Wikipedia `mentions stop+city` path for non-article-about-the-stop now requires full stop name + city-as-word-boundary + dining signal.** This is stricter than before and could theoretically reject a restaurant whose only Wikipedia mention is a passing reference in an unrelated article. In practice all 6 test restaurants still verify.
