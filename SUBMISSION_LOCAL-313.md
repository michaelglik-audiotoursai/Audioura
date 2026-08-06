##### READY FOR REVIEW

**Commit:** e7ce4b0
**Branch:** kiro/local313-dining-verification
**Base:** storied

---

## Per-file summary

| File | Change |
|------|--------|
| `stop_existence_gate.py` | +`_check_dining_nominatim()` as Check 5 after Wikipedia/Wikidata; fixed city signal extraction to strip parentheses and noise words (old, vieux, stop) |
| `generate_tour_text.py` | Pass `tour_type=tour_category` to both `run_existence_gate()` call sites (main gate + replenishment) so dining tours use the correct classification path |
| `tests/test_local313_dining_nominatim.py` | Parametrised test: 6 real restaurants verify, fabricated/wrong-city fail, full gate integration |
| `tests/run_local313_tour_generation.py` | End-to-end generation: 5-stop restaurant + 2-stop Riviera, cost ceiling, row-count guard |

---

## Verbatim evidence

### The six restaurants now verify

```
  [EXISTENCE-GATE] ENFORCE — 8/8 stops verified (100%), dropping 0 unverified
    [VERIFIED] 'La Rossettisserie' — nominatim_osm: 'La Rossettisserie' found in nice(8 Rue Mascoïnat, nice) [category=amenity/restaurant]
    [VERIFIED] "Le Bistrot d'Antoine" — nominatim_osm: 'Le Bistrot d'Antoine' found in nice(3 Rue Place Vieille, nice) [category=amenity/restaurant]
    [VERIFIED] 'Acchiardo' — nominatim_osm: 'Acchiardo' found in nice(38 Rue Droite, nice) [category=amenity/restaurant]
    [VERIFIED] 'Restaurant Lou Pistou' — nominatim_osm: 'Lou Pistou' found in nice (Rue Raoul Bosio, nice) [category=amenity/restaurant]
    [VERIFIED] 'Chez Palmyre' — nominatim_osm: 'Chez Palmyre' found in nice(5 Rue Droite, nice) [category=amenity/restaurant]
    [VERIFIED] 'Le Tire Bouchon' — wikidata: 'Le Tire Bouchon' (QID:Q81170106) is a restaurant
    [VERIFIED] 'Café de Turin' — nominatim_osm: 'Café de Turin' found in nice(5 Place Garibaldi, nice) [category=amenity/restaurant]
    [VERIFIED] 'La Petite Maison' — wikipedia_search: snippet in 'Didier Casnati' mentions stop+city
```

From the unit test (direct verification of the six from the bug report):
```
  ✓ La Rossettisserie: nominatim_osm: 'La Rossettisserie' found in nice(8 Rue Mascoïnat, nice) [category=amenity/restaurant]
  ✓ Le Safari: nominatim_osm: 'Le Safari' found in nice(5 Rue de la Poissonnerie, nice) [category=amenity/restaurant]
  ✓ Chez Palmyre: nominatim_osm: 'Chez Palmyre' found in nice(5 Rue Droite, nice) [category=amenity/restaurant]
  ✓ Le Tire Bouchon: wikidata: 'Le Tire Bouchon' (QID:Q81170106) is a restaurant
  ✓ Le Bistrot d'Antoine: nominatim_osm: 'Le Bistrot d'Antoine' found in nice(3 Rue Place Vieille, nice) [category=amenity/restaurant]
  ✓ Le Vieux Four: wikipedia_fr_search: snippet in 'Nice' mentions stop+city
```

### Fabricated and wrong-city still fail

```
tests/test_local313_dining_nominatim.py::TestSafetyConstraints::test_fabricated_name_fails PASSED
tests/test_local313_dining_nominatim.py::TestSafetyConstraints::test_wrong_city_fails PASSED
tests/test_local313_dining_nominatim.py::TestSafetyConstraints::test_another_fabricated_name PASSED
```

### 5-stop Old Nice restaurant tour generated

```
  TOUR 1 RESULT:
    Requested: 5 stops
    Delivered: 5 stops
    Words: 1090
    Time: 75.8s
    Output: /Users/micha/Audioura/tours/LOCAL313_5stop_old_nice_restaurant.txt
    ✓ SUCCESS — restaurant tour generated
```

Total API cost: $0.1155 (under $1.00 ceiling).

### 2-stop Riviera walking tour (unregression)

```
  TOUR 2 RESULT:
    Requested: 2 stops
    Delivered: 2 stops
    Words: 903
    Time: 0.0s (cache hit)
    ✓ SUCCESS — Riviera tour unregressed
```

### LOCAL-281 tests (14/14 pass — no regression)

```
======================== 14 passed, 1 warning in 13.39s ========================
```

### Production row count

```
  Production real rows: 29 (must be 29)
```

### git status --short: clean

```
(empty)
```

---

## Root cause

Three defects compounded:

1. **Missing `tour_type` in pipeline call.** `generate_tour_text.py` called
   `run_existence_gate(stop_names, venue, conn)` without passing `tour_type`.
   Without it, `_classify_venue_kind` returns `'unknown'` → strict institution
   path → restaurant never matches any canonical_title → fails.

2. **No restaurant-appropriate verification source.** Even with `tour_type='restaurant'`
   routed to the `'dining'` path, `_check_dining_existence` only queried Wikipedia
   and Wikidata. Restaurants don't have Wikipedia articles. The function returned
   `False` for every real restaurant in Nice.

3. **City signal extraction broken for complex venue_names.** The generation
   pipeline produces venue_names like `"restaurant tour in Old Nice (Vieux Nice),
   France"`. The signal extraction didn't strip parentheses and picked noise words
   (`old`, `nice)` with trailing paren) instead of the city name.

---

## Limitations

- **Nominatim availability.** The fix depends on the public Nominatim API
  (nominatim.openstreetmap.org). If Nominatim is down or rate-limited (429),
  the check fails closed (raises RuntimeError, per D220). This is correct
  behavior but means a Nominatim outage would block restaurant tour generation.

- **OSM coverage gaps.** Very new or very obscure restaurants may not yet be in
  OpenStreetMap. The tier-1 Wikipedia/Wikidata path runs first and catches some
  (Le Tire Bouchon has a Wikidata entry, La Petite Maison passes via Wikipedia
  search). But a restaurant absent from both OSM and Wikipedia will be dropped.
  This is acceptable per the gate's design: "genuinely cannot be verified".

- **Nominatim rate limit.** The OSM usage policy allows 1 req/s. For an 8-stop
  candidate list, the checks run sequentially (one per stop, but only stops that
  fail Wikipedia/Wikidata reach Nominatim). Current run took ~8 requests over ~10s.
  Under heavy concurrent generation this could hit limits.

- **No Michelin/Gault&Millau source.** The task mentioned culinary guide sources.
  Nominatim effectively covers the same ground (confirms existence + location)
  without needing authenticated APIs. A dedicated guide lookup could be added
  later but is not needed for the fix.
