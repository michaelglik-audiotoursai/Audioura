##### READY FOR REVIEW

## LOCAL-258: Venue resolver parenthetical fix

**Commit:** `5907183` on `kiro/local258-venue-resolver-parenthetical`  
**Branch point:** `9ecb037` (merge-base with `storied`)

---

### Per-file summary

| file | change |
|---|---|
| `venue_resolver.py` | +48 lines: `_normalise_venue_name()` function strips parentheticals and trailing qualifiers, producing ordered search variants. +15 lines: city extraction from trailing comma segments when no city arg provided. Refactor of search cascade to iterate over normalised variants. |
| `ASIAN_ARTS_8STOP_RESOLVED.md` | 218-line evidence file: generated tour content, before/after table, canonical title provenance, existence gate results, next-blocker analysis. |

---

### Verbatim evidence

**Resolution of the three required spellings:**
```
$ python3 -c "from venue_resolver import resolve_venue; ..."
  [PASS] Musee des Arts Asiatiques (Asian Art Museum)       city=Nice   → Q3330160
  [PASS] Musée des Arts Asiatiques                          city=Nice   → Q3330160
  [PASS] Musee des Arts Asiatiques                          city=Nice   → Q3330160
  [PASS] Musee des Arts Asiatiques (Asian Art Museum), Nice city=       → Q3330160
```

**Non-regression of four existing venues:**
```
  [PASS] Palais Lascaris                                    city=Nice   → Q34653010
  [PASS] Musée Matisse                                      city=Nice   → Q1563354
  [PASS] Musée National Marc Chagall                        city=Nice   → Q3329265
  [PASS] Musée d Art Moderne et d Art Contemporain          city=Nice   → Q936859
```

**Negative test (different city resolves correctly):**
```
  Musee des arts asiatiques + city=Toulon → Q3330161 (Musée des arts asiatiques de Toulon) ≠ Q3330160
```

**Existence gate (production database `audiotours`, table `venue_corpus`):**
```
Before: 0/8 pass
After:  8/8 pass (source: venue_corpus canonical_title match, accent-normalised)
```

**Canonical titles — 16 total, provenance:**
- 9 from museum's official "œuvres commentées" page (maa.departement06.fr), extracted by LOCAL-28 catalogue parser
- 6 from Wikidata SPARQL P195/P276 query for Q3330160
- 1 additional from site section-heading extraction (story_miner T0a)

No titles were hand-registered. None are fabricated.

**Tour generation (container, NOT rebuilt — per D48):**
- Job `8545a116-44a6-4d82-934c-1e78d2b7ba15`, cost $0.0572
- 8 stops attempted, 6 descriptions generated, 2 failed (no per-work context)
- D1v2 verified 15/15 candidate stops before trim to 8
- Container code resolved the venue because input lacked parenthetical (comma-split path)
- The LOCAL-258 fix ensures resolution works even when the parenthetical IS in the input string

**D141 cleanup check:**
```
audio_tours for Nice: protected IDs [1, 12, 14, 17, 24, 29, 152] all present
No new audio_tours rows created by this task (served from container cache)
```

---

### Limitations

1. **The container does NOT have the fix.** The running `audioura-tour-generator-1` was built on 2026-08-03. The fix lives only in this branch. Per D48, deployment requires LEAD to merge and rebuild. The tour generation succeeded only because the container's input path strips the parenthetical via comma-splitting before calling `resolve_venue`.

2. **2/8 stops failed description generation** ("La danse cosmique de Ganesh", "Robe de prêtre taoïste"). These objects exist (existence gate passes) but have no per-work narrative corpus — only the title and category metadata. The description generator correctly refuses rather than hallucinating.

3. **Stop 5 ("Ulysses Grant au Japon") carries the D127 factual error.** The LLM states "reception at the imperial palace" which D127 identified as false (it was Ueno Park). The object genuinely exists at the museum (confirmed via maa.departement06.fr), but the generated prose is factually contaminated.

4. **The `test_contained_regression.py` Chagall failure pre-exists** (L'Exode parenthetical mismatch with SPARQL). Confirmed by running before and after the change — identical failure.

5. **Score projection:** The existence gate now passes 8/8. However, the internal scoring rubric also requires factual density in the prose. With 2 stops generating 0 facts, the maximum achievable score from this tour configuration is capped below 100 regardless of the gate. Whether it reaches 75 at N=8 depends on the rubric's weighting of empty stops.

---

### Database interactions

| database | table | operation |
|---|---|---|
| `audiotours` (production) | `venue_corpus` | READ (cache check for Q3330160) — row was created by the container during generation |
| `audiotours` (production) | `stop_corpus` | READ (existence gate verification of 8 stops) |
| `audiotours` (production) | `audio_tours` | READ (D141 cleanup verification) |

No rows created, modified, or deleted by this task's code.
