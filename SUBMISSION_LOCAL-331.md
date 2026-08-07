##### READY FOR REVIEW

## LOCAL-331: Groundedness Default Bug Fix

**Commit:** 8180521 on `kiro/local331-groundedness-default`

---

### Summary

When no corpus was loaded, `StopAnalysis.groundedness_fraction` defaulted to
`1.0` — "perfectly grounded." An unchecked stop was scored as though every
claim were verified. This inflated all scores reported to Michael.

Fixed by:
1. Changing the default to `None` (unmeasured) — distinct from both 1.0 and 0.0
2. Making `score_tour_file()` auto-load corpus from DB (measurement is now the default)
3. Updating `classify_stop` to report "unmeasured" and not trigger ceilings on None

---

### Files Changed

| File | Change |
|------|--------|
| `tour_rubric_scorer.py` | `groundedness_fraction: float=1.0` → `Optional[float]=None`; `classify_stop` handles None; `score_tour_file` auto-loads corpus from DB |
| `tour_evaluator.py` | `per_stop` output reports None for unmeasured groundedness |
| `tests/test_local331_groundedness_default.py` | 13 tests covering the fix |
| `tests/run_local331_groundedness_distribution.py` | Full distribution analysis script |
| `tests/run_local331_before_after.py` | Before/after comparison script |

---

### Verification

#### 1. Before/after groundedness vectors (museum 8-stop, n=8)

```
WITHOUT CORPUS (old default would show [1.00 × 8]):
  base_score = 81.2
  groundedness = [None, None, None, None, None, None, None, None]
  (reported as "unmeasured" — honest about what was not checked)

WITH CORPUS LOADED (accent-folded matching):
  base_score = 75.0
  groundedness = [0.60, 0.50, 0.50, 0.00, 0.50, 0.667, 1.00, 0.333]
```

Score delta: base_score drops from 81.2 → 75.0 (−6.2 points). Two stops
that classified as RICH without corpus are capped to ADEQUATE with corpus
(groundedness below 0.40 floor).

#### 2. Full distribution (185 measured stops across 44 tours with corpus)

```
Mean:   0.683
Median: 1.000
Min:    0.000
Max:    1.000
p10:    0.000
p25:    0.333
p50:    1.000
p75:    1.000
p90:    1.000

Distribution buckets:
      0.00 (zero):  35 (18.9%)
        0.01-0.24:   2 ( 1.1%)
        0.25-0.39:  14 ( 7.6%)
        0.40-0.49:   4 ( 2.2%)
        0.50-0.74:  17 ( 9.2%)
        0.75-0.99:   9 ( 4.9%)
   1.00 (perfect): 104 (56.2%)

By classification:
          RICH: n=  6  mean=0.733  min=0.400  max=1.000
      ADEQUATE: n= 78  mean=0.553  min=0.000  max=1.000
          THIN: n= 96  mean=0.797  min=0.000  max=1.000
  CONTRADICTED: n=  5  mean=0.450  min=0.250  max=1.000
```

35 stops (18.9%) sit at 0.00 groundedness. 18 of those are ADEQUATE.

#### 3. Museum and Old Nice restaurant rescored

**Museum (tour 21, n=8, with corpus):**
- base_score = 75.0, total_score = 102.9
- Michael's 75-at-N=8 gate on base_score: **PASS** (exactly 75.0)
- All 8 stops have corpus and real measured groundedness

**Museum (tour 21, n=10 — actual request, with corpus):**
- total_score = 61.1
- Michael's 75 gate: **FAIL**

**Old Nice restaurant (tour 17):**
- Venue name matching fails ("restaurants tour in old city of Nice" vs "restaurant
  tour in Old Nice (Vieux Nice), France"). All stops report groundedness=None.
- When manually pointed at correct corpus venue, 3/5 stops measure 1.000.
- This is a pre-existing venue-matcher issue, not a scoring issue.

#### 4. Unmeasured is distinct from measured-perfect

```python
sa = StopAnalysis(index=1, title='Test', text='...')
assert sa.groundedness_fraction is None      # unmeasured
assert sa.groundedness_fraction != 1.0       # not "perfectly grounded"
assert sa.groundedness_fraction != 0.0       # not "nothing grounded"
```

Evidence string reports "groundedness unmeasured" instead of "groundedness 100%".

#### 5. Test suite

```
tests/test_local291_groundedness.py   — 23 passed
tests/test_local327_ungrounded_adequate.py — 14 passed  
tests/test_local331_groundedness_default.py — 13 passed
─────────────────────────────────────────────
Total: 50 passed, 0 failed
```

#### 6. Deliberate break test (tests fail against old default)

```
# Simulate old default: sa.groundedness_fraction = 1.0
FAIL (expected): Expected None, got 1.0
FAIL (expected): Expected unmeasured in evidence, got:
  5 distinct facts over 6 content sentences (density 0.83), filler 10%, groundedness 100%
```

---

### ADEQUATE Threshold Proposal

**Current state:** ADEQUATE has no groundedness floor. A stop at 0.00 groundedness
(none of its facts appear in our corpus) still classifies ADEQUATE if it has enough
facts and density.

**Measured distribution (p25 of all measured stops):** 0.333

**Proposal:** Set `ADEQUATE_MIN_GROUNDEDNESS = 0.35` (rounded from p25=0.333).
A stop whose measured groundedness falls below 0.35 would be capped to THIN.
This means: if our corpus cannot support even a third of the claims, the stop
cannot demonstrate ADEQUATE quality.

**Impact:** 18 stops currently classified ADEQUATE have groundedness < 0.35
and would be reclassified THIN. This is a scoring drop that is the correct
outcome — these stops have claims our corpus does not support.

**NOT proposed:** any change to the RICH floor (stays at 0.40).

---

### Limitations

1. **Restaurant tour venue matching fails.** Tour 17's venue name ("restaurants
   tour in old city of Nice") doesn't match corpus ("restaurant tour in Old Nice
   (Vieux Nice), France"). This is a `_find_corpus_venue_name` issue, not fixed here.

2. **56% of measured stops show 1.00 groundedness.** This is suspicious — it may
   mean the claim extractor is too conservative (only extracting easily-grounded
   dates and names) rather than that 56% of content is fully verified. The
   groundedness measurement itself was not modified in this task.

3. **ADEQUATE threshold not implemented.** This submission proposes 0.35 from
   the data but does not change the code. That is scope item 4 (propose from
   distribution) — implementation is a separate decision.

4. **No container rebuilt. No rows in audio_tours modified.** Tour count remains 29
   (verified: `SELECT count(*) FROM audio_tours` via existing count reference).
