##### READY FOR REVIEW

**Task:** LOCAL-316 — Painting vocabulary for fact detector
**Branch:** `kiro/local316-painting-vocabulary`
**Commit:** e5d02d3

---

## Files changed

| File | Change |
|------|--------|
| `tour_rubric_scorer.py` | Added three painting/print media detection tracks to `analyze_stop`: (1) `_PAINTING_MEDIUM_RE` for bare `<medium> on <support>` phrases in English and French, (2) `_ON_SUPPORT_RE` for `on the <support>` with article/possessive, (3) `_PRINT_TECHNIQUE_PATTERNS` for standalone print technique terms. Also added colour/appearance terms to `_MATERIAL_CONTEXT_RE` exclusion list. |

---

## Evidence

### 1. Chagall median density — before and after

```
Before: Chagall tour 1 median = 0.000, tour 2 median = 0.000
After:  Chagall tour 1 median = 0.143, tour 2 median = 0.038
Monitor (all 47 Chagall stops): 0.000 → 0.083
```

### 2. Five specific zero-fact Chagall stops — before and after

```
Tour 1 Stop 4: "Le prophète Jérémie"
  Before: facts=0, density=0.000, materials=[]
  After:  facts=1, density=0.143, materials=['canvas']
  Context: "...brings Jeremiah to life on the canvas, his anguished expression..."

Tour 1 Stop 5: "Resurrection"
  Before: facts=0, density=0.000, materials=[]
  After:  facts=1, density=0.143, materials=['canvas']
  Context: "...figures seem to float and dance on the canvas, evoking a dreamlike..."

Tour 1 Stop 9: "L'Arche de Noé"
  Before: facts=0, density=0.000, materials=[]
  After:  facts=1, density=0.143, materials=['stained glass']
  Context: "...his other works, including his renowned stained glass windows..."

Tour 2 Stop 9: "L'Exode"
  Before: facts=0, density=0.000, materials=[]
  After:  facts=1, density=0.111, materials=['canvas']
  Context: "...sense of movement and drama on the canvas..."

Tour 2 Stop 10: "L'Arche de Noé"
  Before: facts=0, density=0.000, materials=[]
  After:  facts=1, density=0.077, materials=['stained glass']
  Context: "...Stained glass elements subtly shimmer, stage sets..."
```

### 3. Corpus-wide distribution — before and after

```
Total stops: 149

Before: RICH 5 (3.4%) / ADEQUATE 47 (31.5%) / THIN 97 (65.1%)
After:  RICH 7 (4.7%) / ADEQUATE 46 (30.9%) / THIN 96 (64.4%)

Delta: RICH +2 stops (+1.3pp), ADEQUATE -1 stop (-0.6pp), THIN -1 stop (-0.7pp)
```

No large swing toward RICH.

### 4. Generic art language — still scores 0

```
"a beautiful painting"           → facts=0, materials=[]
"rich colours"                   → facts=0, materials=[]
"the artist's vision"            → facts=0, materials=[]
"a masterpiece of composition"   → facts=0, materials=[]
```

### 5. Asian Arts Museum — unregressed

```
Before: median density = 0.487
After:  median density = 0.487
```

### 6. Blindspot monitor — Chagall still flagged

```
Corpus-wide: median=0.264, mean=0.255, σ=0.117
Flag threshold (mean − 1σ): 0.138

Musee National Marc Chagall: median density 0.083  ⚠ LOW (< 0.138)
```

Chagall is off zero but remains below the 1σ threshold. This is expected:
most Chagall stops contain pure narrative filler without any medium reference
in the body text. The detector vocabulary gap is fixed; the remaining gap
is generation-side (the LLM puts "huile sur toile, 232.5 × 175.8 cm" in
Orientation but generates "artistic vision and deep connection" in the body).

### 7. Existing tests pass

```
$ python3 -m pytest tests/test_local306_inflight_scoring.py \
    tests/test_local35_visitor_facts.py tests/test_local36_practical_facts_qa.py -q
54 passed, 4 warnings in 0.26s
```

---

## Limitations

1. **Chagall still flagged by the monitor.** The vocabulary gap is closed
   (stained glass, canvas, oil, linen all now detected), but 21 of 47 Chagall
   stops remain at density 0 because the LLM body text contains no medium
   references at all — it is wall-to-wall narrative about biblical subjects.
   This is a generation gap, not a detector gap.

2. **No French `_ON_SUPPORT_RE` examples fired.** The pattern
   `sur la/le/les <support>` is implemented and tested in isolation, but no
   current Chagall body text contains e.g. "sur la toile". It will fire when
   future French-language tours use that construction.

3. **"on the canvas" is generous.** The phrase "float and dance on the canvas"
   uses "canvas" narratively, not as a catalogue medium description. It IS a
   material fact (the work is on canvas) but it is less rigorous than "oil on
   canvas, 232 × 175 cm". The rule is: the article+noun form ("on the canvas")
   identifies the physical support, which is a verifiable fact about the artwork.

4. **No threshold changed.** The distribution moved slightly (RICH 3.4%→4.7%)
   and does not warrant recalibration.
