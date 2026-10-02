##### READY FOR REVIEW

**Commit:** see `git log --oneline -2` on branch
**Branch:** `kiro/local304-fact-detector`
**Base:** `storied`

---

## Per-file summary

| File | Change |
|------|--------|
| `tour_rubric_scorer.py` | Widened fact detector by structural category (4 gaps); recalibrated thresholds from measured percentiles |

---

## Evidence

### Stop 3 of `tours/LOCAL303_museum_8stop_gate.txt` — ≥8 facts

```
Stop 3: La danse cosmique de Ganesh
  Dates/years: ['10th century']
  Named people: ['Ganesh', 'Parvati', 'Shiva']
  Materials/techniques: ['chlorite']
  Numbers: ['eight arms']
  Named periods: ['Bengale', 'Pala-Sena']
  distinct_fact_count: 8
  Classification: RICH
  Evidence: 8 distinct facts over 8 content sentences (density 1.00), filler 25%, groundedness 100%
```

Was: 1 fact (THIN). Now: 8 facts (RICH). ✓

### Generic phrases produce 0 facts

Input: "The beautiful views from the hilltop are truly stunning. The rich history of this area is well documented. A sense of wonder fills every visitor. The atmosphere here is magical and enchanting."

```
dates: []
people: []
materials: []
measurements: []
periods: []
distinct_fact_count: 0
```

✓ — none of these become facts.

### Corpus distribution before/after (1,997 stops)

| Band | BEFORE (pre-LOCAL-304) | AFTER (new thresholds) |
|------|----------------------|----------------------|
| RICH | 146 (7.3%) | 153 (7.7%) |
| ADEQUATE | 514 (25.7%) | 532 (26.6%) |
| THIN | 1337 (67.0%) | 1312 (65.7%) |

Threshold recalibration absorbed most of the detector's improved sensitivity.
The +0.4pp RICH shift reflects genuinely-detected facts that were previously
invisible (structural materials, spelled-out numerals, deity names, named periods).

### Thresholds recalibrated

| Threshold | OLD | NEW | Justification |
|-----------|-----|-----|---------------|
| RICH min facts | 3 | 4 | Was ~p90 of old distribution; 4 is ~p75 of new (density gate does the heavy lifting) |
| RICH min density | 0.50 | 0.60 | Measured p90 = 0.571; 0.60 sits at ~p91 |
| ADEQUATE min facts | 2 | 3 | Was ~median; 3 keeps ~p55 of new distribution |
| ADEQUATE min density | 0.20 | 0.20 | Unchanged (still ~p55 of new) |
| Filler ceilings | unchanged | unchanged | Still calibrated to their band's percentile |

### LOCAL303 tour rescore

```
Base score:           +75.00   (was +71.88 = +71.9)
Structural surcharge: +0.00
Correlation bonus:    +26.56   (still spurious per D201 — not stripped)
Venue-identity bonus: +0.00
```

Base score moved from **71.9 → 75.0** because Stop 3 moved THIN→RICH.

---

## Four gaps closed (structural, not list-extension)

### 1. Materials — structural context detection
Pattern: `crafted/carved/sculpted/... from/in/of/with X` → X is a material.
Capitalised words excluded (places). Original 12-item vocabulary retained as
fallback for materials appearing without syntactic context.

### 2. Measurements — spelled-out numerals
Pattern: `(one|two|...|thousand) + countable-noun` matches "eight arms",
"eleven heads", "three centuries". Digit-based detection unchanged.

### 3. Deities and mythological figures
Tight structural patterns (not a broad context window):
- "son/daughter of X and Y" → X, Y are people
- "X embodies/symbolizes/represents" at sentence-subject position
- "the god/goddess/deity X"
- "the artist/painter/sculptor X" / "prowess of X" (role-adjacent Track 3)

### 4. Named periods / dynasties / regions
New category: `([A-Z]proper-noun) + dynasty|period|era|empire|region|...`
NO re.IGNORECASE — the proper noun MUST be capitalised. "Bygone era",
"modern period", "rich history" never match.

---

## Limitations

- **Named people detection is still conservative.** Multi-word names require a
  context verb within 90 characters. Single-word names require tight structural
  patterns (deity context, role-adjacent). "Ulysses Grant" in Stop 5 is NOT
  detected because its 90-char context lacks a verb of doing or role noun.
  This is by design — the alternative (broader matching) floods the detector
  with false positives.

- **Date extraction has a pre-existing issue.** "3,500 scales" gets "500"
  parsed as a date because commas act as word boundaries in `\b\d{3,4}\b`.
  Not introduced by LOCAL-304; not fixed here.

- **Corpus count (1,997 stops) differs from D200's 1,732.** The tours/ directory
  has grown. Distribution percentages are computed against the current corpus.

- **Structural material detection excludes capitalised words** (assumed proper
  nouns = places). A material that happens to be capitalised mid-sentence
  ("crafted from Carrara marble") would not be detected by the structural
  track — but would be if added to the vocabulary fallback.
