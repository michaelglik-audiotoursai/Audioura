##### READY FOR REVIEW

## LOCAL-25: Fix NameError in corpus filter (LOCAL-24 bounce fix)

### Bug Fixed

`generate_tour_text.py` UNIFIED-FILL and POST-R4-FILL paths called
`classify_corpus_entry(venue_name=venue_name)` — but `venue_name` is not
defined inside `generate_tour_text()`. The correct in-scope variable is
`_museum_venue_name`.

Two instances fixed (lines 2622 and 2672):
```python
# BEFORE (crashes)
_fill_class = classify_corpus_entry(title=_cand_name, venue_name=venue_name)

# AFTER (correct)
_fill_class = classify_corpus_entry(title=_cand_name, venue_name=_museum_venue_name)
```

### All enforcement points verified

| # | Location | Variable Used | In Scope? |
|---|----------|--------------|-----------|
| 1 | `_verify_works_v2()` → `filter_corpus_titles()` | `venue_name` | ✓ (function parameter) |
| 2 | `generate_tour_text()` → UNIFIED-FILL | `_museum_venue_name` | ✓ (fixed) |
| 3 | `generate_tour_text()` → POST-R4-FILL | `_museum_venue_name` | ✓ (fixed) |

### Regression test added

`tests/test_local25_unified_fill_filter.py` — 8 tests:
- AST-inspects `generate_tour_text()` to verify classify_corpus_entry calls
  use `_museum_venue_name` (not bare `venue_name`)
- Unit tests for classify_corpus_entry classifications
- Integration test for filter_corpus_titles on Asian Arts Museum corpus

### Acceptance Evidence

#### 1. Cache deletion confirmed

```
DELETE FROM tour_cache WHERE location ILIKE '%asian arts%';  → DELETE 1
DELETE FROM venue_corpus WHERE qid = 'Q3330160';            → DELETE 1
```

#### 2. CACHE MISS confirmed

```
CACHE MISS: Asian arts museum, nice, France / museum / 8
```

#### 3. corpus_version after re-scrape

```
 Q3330160 | Asian arts museum, nice, France | corpus_version = 4
```

#### 4. Live 8-stop generation COMPLETES (no NameError)

Job `99cb3083-3a79-4796-9f01-9b57e642fee6` — status: **completed**

Key log sequence:
```
[LOCAL-24] Classification: 8 works, 4 galleries, 10 excluded
[LOCAL-24] Cross-language dedup removed 1:
[D1v2-LOCAL24] After filter: 7 works, 4 galleries, 10 excluded
[UNIFIED-FILL] tier=medium: added 1 unverified fills (from 8 pre-D1v2 candidates, total now 8/8)
[LOCAL-16 GATE] D1v2-verified-only filter for museum tour
  Removed 1 stop(s):
    ✗ (unverified fill)
  After: 7 verified stop(s)
[LOCAL-16 GATE] Accepting honest shortfall: 7/8 stops
```

#### 5. Every rendered Stop heading

```
Stop 1: Hokusai – Voyage au pied du mont Fuji
Stop 2: Disque
Stop 3: Fauteuil
Stop 4: La geste de Bouddha
Stop 5: Les paysages de l'âme
Stop 6: L'art en exil - Hàm Nghi, Prince d'Annam (1871-1944)
Stop 7: Daim et Daine symbolisant le premier sermon de Bouddha
```

No programme, workshop, gallery-meta, or Wikipedia section heading appears.
No "Promenade des Anglais", no "Monstre(s)", no "Origin of the museum's
pieces", no "The museum's collections".

#### 6. No invented artist

- No "Hiroshi Yoshida" or other invented artist appears
- "Jacques Dubois" (Stop 3) is a real historical French ébéniste (1694-1763)

#### 7. Honest stop count

**7/8 stops** — honest shortfall. The corpus has exactly 7 genuine works;
the LOCAL-16 GATE correctly strips the 1 unverified fill and accepts the
shortfall rather than padding to 8.

#### 8. LOCAL-23 gains (fact sheets)

6/7 fact sheets generated (86%). Only "Les paysages de l'âme" had no RAG
context available.

#### 9. MFA Boston — filter does NOT over-prune

```
CACHE MISS: Museum of Fine Arts, Boston, Massachusetts / museum / 8
[LOCAL-24] Classification: 173 works, 0 galleries, 0 excluded
[LOCAL-24] Near-duplicate collapse removed 14:
[D1v2-LOCAL24] After filter: 159 works, 0 galleries, 0 excluded
[D1v2] 8/8 works verified — tier: rich
[LOCAL-16 GATE] All 8 stops are D1v2-verified ✓
```

8/8 stops, all genuine artworks (Adam and Eve, Ankhhaf, Appeal to the Great
Spirit, etc.). corpus_version updated to 4.

#### 10. Full regression — verbatim exits

```
test_g4_false_positives.py          ALL TESTS PASSED
test_venue_identity.py              11/11 PASS, 0 FAIL — ALL TESTS PASSED
test_spine_generator.py             18 PASS, 0 FAIL — ALL TESTS PASSED
test_w4_matcher.py                  All W4 tests completed.
test_w7_wiring.py                   ALL TESTS PASSED
test_w9_collection_anchor.py        ALL TESTS PASSED
test_tier_computation.py            ALL TESTS PASSED
test_sq2_fixtures.py                ALL TESTS PASSED
test_sq3_fixtures.py                ALL TESTS PASSED
test_sq4_merge.py                   ALL TESTS PASSED
tests/test_local25_unified_fill_filter.py   8 passed (pytest)
```

**11/11 suites green.**
