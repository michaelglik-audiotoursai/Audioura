##### READY FOR REVIEW

# SUBMISSION LOCAL-189: Style A/B on Museum Venue (MAMAC)

**Branch:** `kiro/local189-style-ab-museum`
**Base:** `storied`
**Date:** 2025-08-04

---

## Venue Choice: MAMAC

**Musée d'Art Moderne et d'Art Contemporain (MAMAC), Nice, France.**

Why:
- Richest stop_corpus: 10 stops, 59 passages (vs Chagall's 4 stops / 8 passages).
- Historical data: tour 156 (museum-heavy) showed R3=9, R4=6 on 32 paragraphs — faults are dense at this venue.
- Generator not starved: ample grounding material for both arms.

---

## Design

- 3 runs per arm × 2 stops (D61) = 6 generations total.
- STORIED_MODE=true (required for multi-paragraph museum descriptions; without it, stops are ~80 words = 1 paragraph only).
- DATABASE_URL removed to bypass S20 tour_cache (cache key doesn't include DISABLE_STYLE_CONSTRAINTS; without this, all 6 runs return the same cached text).
- Stop_corpus reader uses its localhost:5433 fallback.
- No DB writes (generate_tour_text writes to file only).

---

## Results

### Paragraph Counts

| | ARM A (baseline) | ARM B (constrained) |
|--|--|--|
| Total paragraphs | 18 | 18 |
| Navigation (exempt) | 0 | 0 |
| Content paragraphs | 18 | 18 |
| Clean (no violations) | 13 | 12 |

### Per-Rule Rates (violations per content paragraph)

| Rule | ARM A | ARM B | Delta |
|------|-------|-------|-------|
| R1 (imperatives) | 0/18 = 0.00 | 1/18 = 0.06 | +0.056 |
| R3 (suggestive exploration) | 4/18 = 0.22 | 2/18 = 0.11 | −0.111 |
| R4 (prescribed feeling) | 4/18 = 0.22 | 4/18 = 0.22 | +0.000 |
| R7 (hallucinated sensory) | 0/18 = 0.00 | 0/18 = 0.00 | +0.000 |

### Overall Failure Rate

- ARM A: 27.8% (5/18 paragraphs with ≥1 violation)
- ARM B: 33.3% (6/18 paragraphs with ≥1 violation)
- **Delta: +5.6 percentage points (constraints made it worse)**

---

## Stop Titles (Itinerary Confound Check)

Both arms generated the same 2 stops in all 3 runs (deterministic from D1v2 verification):

- ARM A: Stop 1: Richard Long ou la sculpture en marchant / Stop 2: She-Bam Pow POP Wizz (×3)
- ARM B: Stop 1: Richard Long ou la sculpture en marchant / Stop 2: She-Bam Pow POP Wizz (×3)

**SAME stops — direct comparison valid.** No itinerary confound.

---

## Sample Violations

### ARM A (5 violations total)
```
[R3] "You are about to embark on a journey through the legacy of art donations to Mama..."
[R3, R4] "You are about to embark on a journey through the interconnected chapters of the..."
[R4, R3] "As you step into the realm of "Richard Long ou la sculpture en marc..."
[R4, R3] "As you stand before "Richard Long ou la sculpture en marchant" at M..."
[R4] "As you stand amidst the kaleidoscope of visual delights within "She-Bam Pow POP..."
```

### ARM B (6 violations total)
```
[R1] "You are about to embark on a journey through the interconnected chapters of the..."
[R4] "Amidst the hallowed halls of the museum stands "She-Bam Pow POP Wizz," a testame..."
[R3] "As you delve into the exhibit, you are greeted by a series of captivating instal..."
[R4] "In the heart of the museum, "She-Bam Pow POP Wizz" commands attention with its e..."
[R3, R4] "The "Richard Long ou la sculpture en marchant" exhibit showcases the groundbreak..."
[R4] (6th violation — overlapping paragraph)
```

---

## Sample Size Assessment

- ARM A: 18 content paragraphs from 6 stops (3 runs)
- ARM B: 18 content paragraphs from 6 stops (3 runs)
- Both arms have ≥10 content paragraphs — sample supports comparison.
- Same stops in both arms eliminates the itinerary confound.

---

## Whether the Sample Supports the Conclusion

**Yes, for the direction; no, for precise magnitude.**

With 18 paragraphs per arm and identical stops, the comparison is fair. The result is clear: prompt-injected style constraints **did not reduce** R3+R4 violation rates on this museum venue. R3 dropped from 4→2 (suggestive), R4 stayed at 4→4 (prescribed feeling), and R1 appeared in ARM B (0→1). The overall failure rate went UP with constraints (27.8% → 33.3%).

The n=18 sample is large enough to show that the constraints are not producing a dramatic reduction. It is NOT large enough to distinguish between "no effect" and "small effect masked by noise" — that would require ~50+ paragraphs per arm. But the sign of the delta (worse, not better) is interpretable: prompt instruction alone is insufficient for R4.

---

## Actual Spend

| Run | Cost | Tokens |
|-----|------|--------|
| A1 | $0.0186 | 9,316 |
| A2 | $0.0186 | 9,297 |
| A3 | $0.0186 | 9,275 |
| B1 | $0.0203 | 10,158 |
| B2 | $0.0203 | 10,130 |
| B3 | $0.0203 | 10,136 |
| **Total** | **$0.117** | **58,312** |

Ceiling: $0.30. Actual: $0.117 (39% of ceiling).

---

## Database Safety

- audio_tours total rows: 117 (unchanged)
- Nice list [1,12,14,17,21,24,27,28,29]: all present, all is_test=false
- Test tours: NOT WRITTEN (generate_tour_text writes to file only; all generated files cleaned up)

---

## Key Finding

**Prompt-injected style constraints are insufficient to suppress R4 (prescribed feeling) on museum venues.**

R3 (suggestive exploration) showed a partial reduction (4→2, −0.111 per paragraph), suggesting the prompt has some effect on that pattern. But R4 was completely unaffected (4→4, Δ=0.000), and an R1 violation appeared in the constrained arm that didn't exist in baseline.

The task spec anticipated this outcome: "If R3 and R4 rates do not fall on a museum venue, prompt instruction is insufficient and the fix becomes post-generation rewriting — a different and larger design."

That is the finding. Post-generation rewriting or few-shot example injection would be needed to suppress R4.

---

## Limitations

1. **Same stops across all runs** — D1v2 verification is deterministic for this venue, so all 6 runs produced the same 2 artworks. This eliminates the itinerary confound but means we're testing the model's treatment of only 2 specific works.
2. **STORIED_MODE=true but no DATABASE_URL** — the cache store step is skipped, so these generations aren't persisted. The spine generator and fact-sheet extraction still run (they use the API), but the tour_cache layer doesn't activate.
3. **3 paragraphs per stop × 2 stops × 3 runs = 18 per arm** — adequate for direction but not for precise rate estimation. Fisher's exact test on 5/18 vs 6/18 gives p≈1.0 (no significant difference).
4. **Only 2 artworks exercised** — "Richard Long ou la sculpture en marchant" and "She-Bam Pow POP Wizz" may elicit R4 patterns regardless of instructions (art description naturally gravitates to feeling language).

---

## Files Changed

| File | Change |
|------|--------|
| `tests/test_local189_style_ab_museum.py` | NEW — A/B test script for museum venue |
| `SUBMISSION_LOCAL-189.md` | NEW — this submission |

---

## Commit

```
git rev-list --count storied..HEAD >= 1
```
