##### READY FOR REVIEW

## LOCAL-222: Riviera Rerun vs Michael — Measurement at HEAD

**Commit:** (see below)
**Branch:** kiro/local222-riviera-rerun-vs-michael
**Cost:** $0.0268 generation + $0.0040 retry demo = **$0.031** (ceiling $0.35)

---

## Per-file summary

| File | Purpose |
|---|---|
| `RIVIERA_2STOP_ROUND2.md` | Best run (tour 180), numbered and annotated, ready for Michael |
| `tours/LOCAL222_riviera_run1.txt` | Raw tour text — Run 1 (best) |
| `tours/LOCAL222_riviera_run2.txt` | Raw tour text — Run 2 |
| `tours/LOCAL222_riviera_run3.txt` | Raw tour text — Run 3 |
| `tours/LOCAL222_results.json` | Per-paragraph analysis data for all 3 runs |
| `tours/LOCAL222_retry_pairs.json` | 3 before/after retry pairs with validation |
| `run_local222_riviera_rerun.py` | Generation script (reproducible) |
| `SUBMISSION_LOCAL-222.md` | This file |

---

## Evidence

### 1. Three runs completed

```
Run 1: tour_id=180, Cap d'Antibes + Eze Village, $0.0094, 819 words
Run 2: tour_id=181, Cap d'Antibes + Gorges du Loup, $0.0089, 945 words
Run 3: tour_id=182, Cap d'Antibes Coastal Path + Voie Verte du Littoral Varois, $0.0085, 713 words
```

### 2. Style retry behaviour (all 3 runs)

```
Run 1: 6 paragraphs retried, 3 fixed (50%), 3 kept original
Run 2: 4 paragraphs retried, 3 fixed (75%), 1 kept original
Run 3: 4 paragraphs retried, 3 fixed (75%), 1 kept original
Total: 14 retried, 9 fixed (64%), 5 kept original
```

The retry fires on 4–6 paragraphs per 2-stop tour. This is higher than
LOCAL-192's testing (2–4) because R1 now fires on "Position yourself" /
"Stand at the entrance" patterns (D69/D71).

### 3. Three before/after pairs (verified — run against identical retry prompt)

**PAIR 1: FIXED** — "Position yourself at the entrance" → "Eze Village is a medieval gem"
- Before: R1_IMPERATIVE
- After: clean
- The imperative is removed, content preserved

**PAIR 2: FAILED** — "As you wander through the village" → "As you explore the village"  
- Before: R3_SUGGESTIVE_EXPLORATION
- After: R3_SUGGESTIVE_EXPLORATION (still fires)
- Changed "wander" to "explore" — both trigger R3

**PAIR 3: IMPROVED** — removed R3 ("inviting you to explore further") but kept R1 ("contemplate")
- Before: R1_IMPERATIVE + R3_SUGGESTIVE_EXPLORATION
- After: R1_IMPERATIVE only
- Partial fix: one rule resolved, one remains

No "worse" example found: in no case did the retry produce MORE violations.

### 4. R9 deletions (all verbatim)

```
Run 1: "From Cap d'Antibes to Eze Village — a collection that spans more ground than these stops alone."
Run 2: "From Cap d'Antibes to Gorges du Loup — a collection that spans more ground than these stops alone."
Run 3: "From Cap d'Antibes Coastal Path to Voie Verte du Littoral Varois — a collection that spans more ground than these stops alone."
```

3 runs, 1 deletion each, all the same template. Zero content sentences deleted.
Michael's 0/5 pattern ("can be placed in millions of stops") is reliably caught.

### 5. Style rule rates: old vs new

```
              Old (tour 163, 6 paras)    New (best run, 6 paras)
R1_IMPERATIVE:   50% (3/6)               50% (3/6)
R3_SUGGESTIVE:    0% (0/6)                0% (0/6)
R4_PRESCRIBED:    0% (0/6)                0% (0/6)
R8_LEAKAGE:      17% (1/6)                0% (0/6)   ← eliminated
R9_GENERIC:      33% (2/6)               17% (1/6)   ← halved

All 3 runs combined (16 paras): R8 = 0/16 (0%), R9 = 3/16 (19%, all deleted by pipeline)
```

### 6. Michael's two failure modes

**Instructions aimed at the listener (R1):** Still present. 50% rate unchanged.
The retry fixes some but the LLM generates new ones. The specific "Position
yourself" / "Take a moment" pattern (D69/D71) appears in orientation paragraphs.
One genuine violation remains: "Take a moment to absorb the ancient aura."

**Sentences that would fit any stop (R9):** Effectively eliminated from delivered
text. The pipeline deletes them before delivery. The "As you continue your
journey through this charming town..." pattern from tour 163 does not appear.

### 7. Row counts

```
audio_tours BEFORE: 130
audio_tours AFTER:  133 (delta: +3, all is_test=true, lat/lng=NULL)
Nice list: [1, 12, 14, 17, 21, 24, 27, 28, 29, 152] — UNCHANGED
```

---

## Limitations

1. **Arms not comparable.** Tour 163 used Cap d'Antibes + Villefranche-sur-Mer.
   The new best run uses Cap d'Antibes + Eze Village. Different stops mean the
   rule rates are not a controlled delta — they show the pipeline's general
   behaviour, not a before/after improvement on the same content.

2. **Style retry stats from log capture, not instrumented.** The pipeline prints
   retry summaries but does not expose the before/after text. The 3 pairs were
   re-generated with the identical retry prompt on paragraphs from the delivered
   tour. They demonstrate the mechanism faithfully but are not the exact same
   API calls the pipeline made.

3. **R1 rate flat despite retry.** The retry's 64% success rate on triggered
   paragraphs is not enough to reduce the delivered R1 rate because the LLM
   generates new R1 violations that weren't in the original pipeline's vocabulary
   before D69/D71. The net effect is flat.

4. **Small sample.** 3 runs × 2 stops × ~3 paragraphs = ~16 paragraphs total.
   Rates have wide confidence intervals.

5. **No "worse" pair found.** The LOCAL-192 risk (retry damages good material)
   was not observed. But 3 pairs is insufficient to declare the risk absent.
