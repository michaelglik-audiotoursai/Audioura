##### READY FOR REVIEW

## LOCAL-351: US Address Parsing Fails at First Step

**Commit:** `a70a453`  
**Branch:** `kiro/local351-us-address-parsing`  
**Base:** `storied`

---

### Files Changed

| File | Change |
|------|--------|
| `area_resolver.py` | Added US-format address detection in `_parse_location` (lines 380-414) |
| `tests/test_local351_us_address_parsing.py` | 26 tests — US parsing, structural signal, Nice regression, D242 compliance (new file) |

---

### Root Cause

`_parse_location("biking tour in Norwood, MA 02062, USA")` splits on comma into:
1. `"Norwood"` → assigned as **neighborhood**
2. `"MA 02062"` → assigned as **city**
3. `"USA"` → len ≤ 3, appended to city → `"MA 02062, USA"`

Result: `neighborhood='Norwood', city='MA 02062, USA'`

The parser assumes a 2-part comma split is `Neighborhood, City` (true for `Nice, France`). For US-format addresses, the first segment IS the city and subsequent segments are state/country qualifiers. "MA 02062" cannot be a city name — the ZIP code is a definitive structural signal.

The cascade failure:
```
area unresolved (Wikidata can't find "MA 02062, USA")
  → no landmark discovery (0 landmarks)
  → 0/3 stops verified
  → enrichment skips unverified stops (by design)
  → [EXISTENCE-GATE] LOG_ONLY: 0/3 verified, 3 would be dropped
```

---

### The Fix

Added structural US-format detection AFTER cleanup but BEFORE the standard comma-split assignment (lines 380-414 of `area_resolver.py`):

1. After splitting on comma and stripping filler words, scan segments from index 1 onward
2. Match against `^[A-Z]{2}(?:\s+\d{5}(?:-\d{4})?)?$` — a 2-letter uppercase code optionally followed by a 5-digit ZIP (or ZIP+4)
3. Fire only when the structural signal is **unambiguous**: segment has a ZIP code, OR there is a subsequent segment (country)
4. When triggered: everything before the state segment becomes the city; no neighborhood assigned

This is structure-based detection (D236) — no hardcoded country/state lists.

```
BEFORE: city='MA 02062, USA', neighborhood='Norwood'
AFTER:  city='Norwood', neighborhood=''
```

---

### Per-Stage Cascade (Fixed)

```
Stage 1 - Area Resolution:    PASS
  city='Norwood', qid=Q2415892
  center=(42.1944, -71.2000), radius=2.0km, lang=en, country=Q30 (USA)

Stage 2 - Landmark Discovery: 7 landmarks
  Norwood, Massachusetts (Q2415892)
  St. Peter Parish, Norwood (Q934731)
  Norwood Memorial Municipal Building (Q7061632)
  Fred Holland Day House (Q5495475)
  Norwood Hospital (Q7061628)
  Norwood High School (Q18705977)
  Oak View, Norwood (Q7073754)
  [excluded by LOCAL-294 P31 filter: Norwood Depot, Norwood Central station (transit)]

Stage 3 - Stop Verification:  0/3 (with OLD stops)
  Norwood Central Station  → excluded by P31 filter (transit infrastructure Q55488)
  Neponset River Trail     → not on Wikidata within 2km radius
  Blue Hills Reservation   → 12.04km from center, excluded by bounding box

Stage 4 - Enrichment:         REQUIRES REGENERATION
```

**Stage 3 shows 0/3 because the existing stops are wrong, not because the lookup is broken.** The fix unblocks Stages 1-2. With area context available during regeneration, GPT will propose stops from the 7 discovered landmarks.

---

### Blue Hills Reservation Distance

```
Blue Hills Reservation → 12.04km from Norwood center (42.1944, -71.2000)
Area bounding radius:    2.0km
EXCLUDED:                Yes, by coordinate bounding box in SPARQL query
```

The distance filter correctly prevents Blue Hills from appearing as a landmark candidate once the area resolves properly. This was not a separate defect — it was invisible because the area never resolved.

---

### Parse Verification

**US format (fixed):**
```
"biking tour in Norwood, MA 02062, USA" → city='Norwood', neighborhood=''
```

**Nice variants (unchanged):**
```
"Nice, France"                                              → neighborhood='Nice', city='France'
"Old Nice (Vieux Nice), France"                             → neighborhood='Old Nice (Vieux Nice)', city='France'
"Musee des Arts Asiatiques (Asian Art Museum), Nice, France" → neighborhood='Musee des Arts Asiatiques (Asian Art Museum)', city='Nice'
"walking tour in Nice, France"                              → neighborhood='Nice', city='France'
"restaurant tour in Old Nice (Vieux Nice), France"          → neighborhood='restaurant in Old Nice (Vieux Nice)', city='France'
```

All five Nice variants produce identical output to the unfixed code.

---

### Verification Evidence

```
$ python3 -m pytest tests/test_local351_us_address_parsing.py tests/test_local348_le_safari_zero_yield.py tests/test_local334_museum_object_questions.py tests/test_local346_bridge_vs_thin_row.py -v
61 passed in 0.50s
```

**Full suite (network-dependent tests included):**
```
$ python3 -m pytest tests/test_local351_us_address_parsing.py tests/test_local348_le_safari_zero_yield.py
  tests/test_local332_interpretive_enrichment.py tests/test_local341_harvest_relevance.py
  tests/test_local334_museum_object_questions.py tests/test_local346_bridge_vs_thin_row.py
  tests/test_local293_landmark_extraction.py tests/test_local294_sparql_quality.py
96 passed in 51.70s
```

**Museum bounds (D258):**
- 8-stop: 75.0 ✓ (test_museum_8stop_score_bound PASSED)
- 4-stop: 81.2 ✓ (test_museum_4stop_score_bound PASSED)

**LOCAL-46 transport tests (44/44):**
```
$ python3 test_local46_transport_scope.py
LOCAL-46 Transport/Region Tests: 44 PASS, 0 FAIL
```

**D242 compliance:** `test_unfixed_would_fail` asserts `city == "Norwood"` — the unfixed code produces `city='MA 02062, USA'` which fails this assertion.

**Git status clean:**
```
$ git status --short
(empty)
```

**audio_tours row count:** unchanged (no rows modified, 29 real tours intact).

---

### LEAD Must Regenerate

The fix corrects area resolution but does NOT regenerate the tour. `OPENAI_API_KEY` is not in my environment. LEAD must:

1. Set `DISABLE_TOUR_CACHE=1` and `DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours`
2. Regenerate: `biking tour in Norwood, MA 02062, USA` (3-stop)
3. Verify the cascade clears through all 4 stages with NEW stops
4. Expected: area resolves → landmarks guide stop selection → stops from the 7-landmark set verify → enrichment runs
5. Score and compare against baseline (58.3, 0/3 verified, 0 enrichment)

**Baseline:** `tours/NORWOOD_biking_3stop.txt`, base 58.3, 0/3 verified, 0 enrichment queries.

---

### Limitations

1. **Bare `City, ST` without ZIP and without country (e.g., "Norwood, MA") does NOT trigger US detection.** The structural signal requires either a ZIP code or a subsequent country segment. A bare 2-letter code is ambiguous — it could be `Neighborhood, City` (e.g., `Big Lake, AK` in LOCAL-46). This is a deliberate choice per D236: structure-based, not list-based.

2. **"Old Nice (Vieux Nice), France" does not resolve end-to-end via `resolve_area()`.** This is a pre-existing limitation (confirmed on base branch) — the parenthesized form doesn't resolve on Wikidata after the country-swap. Unrelated to US parsing; the `_parse_location` output is unchanged.

3. **Stage 3 verification shows 0/3 with the existing stops.** This is expected: the original tour was generated without area context and proposed stops that are either transit (Norwood Central), absent from Wikidata (Neponset River Trail), or 12km away (Blue Hills). Regeneration will produce stops from the 7 discovered landmarks.

4. **Norwood Central station is excluded by the LOCAL-294 P31 type filter (Q55488 = railway station).** If the regenerated tour proposes it as a stop, it will not verify via the landmark-matching path. It may still verify via the existence gate's Nominatim path.
