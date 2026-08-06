##### READY FOR REVIEW

**Commit:** 9525ac7  
**Branch:** kiro/local290-stop-loss  
**Base:** storied  

---

## Per-file summary

| File | Change |
|------|--------|
| `stop_existence_gate.py` | +Tier-1 Wikipedia/Wikidata fallback for geographic areas; proper-noun extraction for compound names; region bounding-box validation |
| `area_resolver.py` | Rewrote `_match_stop_to_landmark` with accent folding, article stripping, elision handling; added `_normalize_landmark_name` |
| `generate_tour_text.py` | Phase 3A requests N+margin candidates; geographic replenishment block after existence gate drops |
| `run_local290_verification.py` | Verification script: generates 3×8 + 2×2 Riviera tours, reports metrics |

---

## Verbatim evidence

### Fault 1 — Selector now proposes at least N candidates

```
PHASE 3A: Fetching 8 candidate POI(s) for French Riviera walking tour along the coast, France...
  [LOCAL-290] Asking for 12 candidates (N=8 + margin for gate filtering)
OK PHASE 3A parsed 11 candidate POI(s):
```

Before: `_phase3a_count = total_stops` (exact N for non-museum tours).  
After: `_phase3a_count = total_stops + max(3, total_stops // 2)` = 12 for N=8.

### Fault 2 — Real places no longer dropped for lack of corpus

The exact scenario from the bug report, re-run:

```
[EXISTENCE-GATE] ENFORCE — 7/7 stops verified (100%), dropping 0 unverified
  [VERIFIED] 'Saint-Jean-Cap-Ferrat' — stop_corpus(geographic): 'Cap Ferrat'
  [VERIFIED] 'Old Town of Menton' — wikipedia_proper_noun: 'Menton' at 43.77,7.50 confirms 'Old Town of Menton' is in region
  [VERIFIED] "Corniche d'Or" — wikipedia_fr_summary: 'Corniche d'Or' exists and mentions region
  [VERIFIED] 'Promenade des Anglais' — stop_corpus(geographic)
  [VERIFIED] 'Eze Village' — stop_corpus(geographic)
  [VERIFIED] 'La Croisette' — stop_corpus(geographic)
  [VERIFIED] 'Port de Nice' — venue_corpus canonical_title(geo)
```

Both "Old Town of Menton" and "Corniche d'Or" now pass via tier-1.

Safety preserved — fabricated/wrong-region:
```
[UNVERIFIED] 'Château des Imaginations' — no evidence       ← fabricated, still fails
[UNVERIFIED] 'Palais de la Nonsense' — no evidence          ← fabricated, still fails
[UNVERIFIED] 'Lyon Central Square' — no evidence            ← coords 45.77° outside 43.0–44.0 bbox
[VERIFIED]   'Eze Village' — stop_corpus(geographic)        ← real, passes
```

### Fault 3 — Normalization matching

Accent folding and article stripping:
```
'Old Town of Menton'    → normalized: 'old town menton'      → matches 'Old Town Menton' ✓
'Île Sainte-Marguerite' → normalized: 'ile sainte marguerite' → matches 'Ile Sainte-Marguerite' ✓
"Corniche d'Or"         → normalized: 'corniche or'           → matches "Corniche d'Or" ✓
'Cap Ferrat'            → substring of 'Saint-Jean-Cap-Ferrat' ✓
```

Note: `verify_landmarks` match rate remained 0/28 because the cached landmark list contains Wikipedia **section headings** (e.g., "Canton of Sainte-Maxime", "Origin of term"), not actual POI names. This is a pre-existing data quality issue in the landmark cache, unrelated to the matching algorithm. The existence gate's tier-1 fallback compensates effectively.

### Fault 4 — Replenishment fires

```
[LOCAL-245] EXISTENCE-GATE: tour SHORT — 1/2 stops, triggering replenishment

[LOCAL-290] REPLENISHMENT: need 1 more stops (have 1/2)
[EXISTENCE-GATE] ENFORCE — 3/5 stops verified (60%), dropping 2 unverified
  [VERIFIED] 'Jardin Exotique de Monaco' — stop_corpus(geographic)
  [VERIFIED] "The Prince's Palace of Monaco" — wikipedia_proper_noun: 'Monaco' at 43.73,7.42
  [VERIFIED] 'Oceanographic Museum of Monaco' — wikipedia_en_summary
  [UNVERIFIED] 'Val Rahmeh-Menton Botanical Garden' — no evidence
  [UNVERIFIED] 'Parc du Pian' — no evidence
  [LOCAL-290] REPLENISHED: 'Jardin Exotique de Monaco'
  [LOCAL-290] Round 1: +1 verified, total now 2/2
[LOCAL-290] Replenishment SUCCESS: 2/2 stops
```

### Tour delivery results

| Tour | Requested | Proposed | Gate verified | Delivered | Status |
|------|-----------|----------|---------------|-----------|--------|
| 8-stop cycling #1 | 8 | — (cache hit) | — | 7 | CACHE (pre-fix) |
| 8-stop walking #2 | 8 | 11 | 8/11 (73%) | 8 | ✓ |
| 8-stop cycling #3 | 8 | 11 | 11/11 (100%) | 8 | ✓ |
| 2-stop cycling #1 | 2 | 5 | 4/5 (80%) | 2 | ✓ |
| 2-stop walking #2 | 2 | 5 | 1/5→replenish→2 | 2 | ✓ |

Tour #1 was a cache hit from a pre-fix generation; not a regression.

### LOCAL-281 regression test (14/14)

```
test_le_chantecler_verifies_in_nice PASSED
test_la_petite_maison_verifies_in_nice PASSED
test_fake_restaurant_rejected PASSED
test_wrong_city_rejected PASSED          ← Le Chantecler in Lyon still fails
test_fabricated_museum_stop_rejected PASSED
test_riviera_stops_verify PASSED
test_fabricated_geographic_stop_rejected PASSED
```

### D141 cleanup

```
New rows created: []
Deleted 0 test rows: []
Protected IDs verified intact: [1, 12, 14, 17, 24, 29, 152]
```

---

## Acceptance criteria

| Criterion | Status |
|-----------|--------|
| Real place absent from stop_corpus no longer dropped | ✓ (Old Town of Menton, Corniche d'Or pass via tier-1) |
| Fabricated place still fails | ✓ (Château des Imaginations, Palais de la Nonsense) |
| Lyon proximity case still fails | ✓ (coords 45.77° outside 43.0–44.0 bbox) |
| Selector proposes at least N | ✓ (asks for N + max(3, N//2); delivered 11 for N=8) |
| verify_landmarks match rate improved | Partial — algorithm fixed (accent/article normalization), but cached landmark list is section headings not POIs |
| Replenishment fires on short tour | ✓ (2-stop #2: 1→2 via replenishment) |
| 8-stop requests deliver 8 | ✓ (tours #2 and #3 both deliver 8/8) |
| git status clean | ✓ |
| No container rebuilt | ✓ |

---

## Limitations

1. **verify_landmarks 0/28 persists** — the cached landmark list for "French Riviera" contains Wikipedia section headings ("Canton of Sainte-Maxime", "Origin of term"), not actual POIs. The matching algorithm is now correct (accent folding, article stripping) but cannot match against non-landmark entries. The existence gate's tier-1 fallback compensates.

2. **Tour #1 cache hit** — the first 8-stop run returned a cached pre-fix result (7/8). The cache mechanism is by design and the non-cached tours (#2, #3) both delivered 8/8.

3. **Cost per tour** — each full tour generation costs ~$0.07–0.08 (Phase 3A + Phase 3B + narration). Replenishment adds ~$0.003 per round (one extra Phase 3A call). Total verification run well under the $1.50 ceiling.

4. **Tier-1 fallback latency** — each unverified stop requires 2–4 Wikipedia/Wikidata API calls (~1–3s per stop). For a tour with 3 unverified stops, this adds ~5–9s. Acceptable for a one-time generation pipeline.

5. **"Plage de la Garoupe" still fails** — this is a real beach on Cap d'Antibes. It fails because its Wikipedia article doesn't mention a Riviera region signal, and the proper-noun extraction doesn't help ("Garoupe" isn't a known city). A Wikidata coordinate check would catch it but requires a standalone Wikidata entity. This is an edge case where corpus scraping would be the correct fix.
