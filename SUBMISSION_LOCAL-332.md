##### READY FOR REVIEW

## LOCAL-332: Interpretive Enrichment

**Commit:** d03b434  
**Branch:** kiro/local332-interpretive-enrichment  
**Commits:** 2 (on top of storied)

---

## Per-file summary

| File | Change |
|------|--------|
| `interpretive_enrichment.py` | New module. Builds interpretive questions by venue kind, searches via Serper, filters atmospherics/reviews, detects attributed quotes, verifies against primary sources, stores in stop_corpus. |
| `stop_existence_gate.py` | Wires interpretive enrichment after LOCAL-314 dining harvest. Extracts city/country from venue_name. Behind `DISABLE_INTERPRETIVE_ENRICHMENT=1` kill switch. |
| `tests/test_local332_interpretive_enrichment.py` | 11 unit tests. Imports production code. Tests module existence (fails on unfixed), question generation, attribution detection, atmospheric rejection, fact detection, accent-folded matching, source tier, pipeline filtering, and gate wiring. |
| `run_local332_enrichment.py` | Live enrichment runner with before/after measurement. |
| `run_local332_generate_and_score.py` | Tour regeneration + rubric scoring. |

---

## Evidence

### 1. Questions generated (not name searches)

```
Le Safari:
  Q: What is interesting about Le Safari restaurant in Nice, France?
  Q: Who are notable people associated with Le Safari in Nice and what did they do there?
```

These yield narrative content. The old queries were `"Le Safari" Nice restaurant` (directory listings).

### 2. Interpretive enrichment yield

| Stop | web_search (before) | interpretive (added) | total (after) |
|------|--------------------:|---------------------:|--------------:|
| Le Safari | 2 | +3 | 5 |
| Acchiardo | 4 | +2 | 6 |
| Chez Palmyre | 5 | +2 | 7 |
| La Rossettisserie | 5 | 0 | 5 |
| La Voglia | 4 | 0 | 4 |

Le Safari new passages include:
- "Le Safari, restaurant niçois à Nice **depuis 1972**" (year)
- "**Maître Restaurateur**, un titre" (accreditation)
- "wood-fired pizzas, a regional menu and homemade pastries" (dishes)
- "**Colman Andrews** — A three-star chef introduced me to the pizza..." (named journalist)

### 3. Dropped attributions (D233 safety)

```
Passage: Gourmet Magazine praised it as a haven for a "stylish, raffish population"
Attribution: Gourmet Magazine
Verified: False
Reason: no_primary_source_found_for:Gourmet Magazine
>>> DROPPED

Passage: Jacques Chirac described Le Safari as "the most authentic restaurant..."
Attribution: Jacques Chirac
Verified: False
Reason: no_primary_source_found_for:Jacques Chirac
>>> DROPPED
```

One attribution that DID verify:
```
Passage: Gault&Millau officially declared the restaurant an "indestructible event"
Attribution: Gault&Millau
Verified: True
Reason: verified_via:fr.gaultmillau.com
```

### 4. Tour regenerated and scored

| Stop | Facts | Baseline |
|------|------:|:---------|
| La Merenda | 3 | (not in baseline) |
| Restaurant Acchiardo | 2 | ADEQ/4 |
| Chez Pipo | 2 | (not in baseline) |
| Le Safari | **3** | **THIN/0** |
| Le Bistrot d'Antoine | 6 | (not in baseline) |
| **TOTAL** | **16** | **12** |

Le Safari: 0 → 3 detected facts. Stop selection differs from baseline because LOCAL-329 changed selection to prefer documentedness.

### 5. Museum 8-stop not regressed

```
Musee Matisse, Nice, France: 6 stops, 12 passages
Musee National Marc Chagall, Nice, France: 4 stops, 17 passages
Musee des Arts Asiatiques, Nice, France: 8 stops, 41 passages
```

All unchanged. Interpretive enrichment does not touch museum stops in this run (it was invoked for dining only).

### 6. stop_corpus count

- Before: 112 rows
- After: 117 rows (+5 new stops gained corpus during generation)
- audio_tours: 29 real (unchanged)

### 7. Unit tests

```
11 passed in 0.07s
```

Tests import production code and would fail with ImportError on the unfixed codebase (no `interpretive_enrichment` module exists on `storied` branch).

### 8. Cost

- Enrichment: 10 queries × $0.001 = $0.010
- Tour generation: ~$0.07 (GPT-4o)
- Total within $0.60 ceiling

---

## Limitations

1. **Selection changed from baseline.** The baseline had stops (La Rossettisserie, Acchiardo, Chez Palmyre, Le Safari, La Voglia). The regenerated tour has different stops because LOCAL-329's documentedness-based selection now prefers stops with more corpus. Direct before/after comparison is only possible for Le Safari (present in both).

2. **Attribution verification requires Serper queries.** Each attributed quote costs $0.001 to verify. In the live run, no search results happened to contain attributions (the enrichment returned factual snippets without quotes). The drop demonstration was run separately with injected test passages from Michael's evidence file.

3. **La Rossettisserie and La Voglia yielded 0 interpretive passages.** Their Serper results did not contain fact-carrying snippets that passed the quality gate. This is the honest "THIN" outcome — the module does not fabricate fallback content.

4. **`SERP_API_KEY` must be set in environment.** Without it, the module logs a warning and returns empty (graceful degradation, no crash).
