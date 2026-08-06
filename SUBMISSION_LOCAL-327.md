##### READY FOR REVIEW

## LOCAL-327: Ungrounded ADEQUATE Ceiling

**Commit:** ceda4cc  
**Branch:** kiro/local327-ungrounded-adequate  
**Files changed:**

| File | Change |
|------|--------|
| `tour_rubric_scorer.py` | Added `corpus_available` and `corpus_lookup_attempted` fields to `StopAnalysis`; `classify_stop` caps to THIN when no corpus; `_compute_groundedness_for_stop` sets the new fields |
| `tests/test_local327_ungrounded_adequate.py` | 12 new tests covering the ceiling behavior |
| `run_local327_groundedness_audit.py` | Measurement script for the corpus audit |
| `run_local327_rescore.py` | Before/after rescore script |

---

## 1. Measured Distribution

**54 of 56 ADEQUATE+ stops (96%) reach their band on ZERO corpus passages.**

```
DISTRIBUTION: ADEQUATE-or-better stops
  Total ADEQUATE+ stops:       56
  With corpus passages > 0:    2
  With corpus passages = 0:    54  ← UNVERIFIED
  Fraction unverified:         96.4%

ALL STOPS BY CLASSIFICATION:
  RICH           :    8 total,    7 zero-corpus (88%)
  ADEQUATE       :   48 total,   47 zero-corpus (98%)
  THIN           :  103 total,   80 zero-corpus (78%)

FACT COUNT DISTRIBUTION — zero-corpus ADEQUATE+ stops:
  n = 54
  min = 3, max = 9
  mean = 5.0, median = 5.0
```

Only 2 stops in the entire 159-stop corpus have corpus AND reach ADEQUATE.
The rest is unverified parametric memory counted as demonstrated quality.

---

## 2. Threshold Choice

**Threshold: corpus passages ≥ 1 required for ADEQUATE or RICH.**

Picked from the data: the distribution is binary. There is no "partial corpus"
gradient to calibrate a fraction threshold against — stops either have passages
(n=2) or they don't (n=54). The threshold is therefore the simplest possible:
at least one corpus passage must exist for the stop to demonstrate quality.

When `corpus_lookup_attempted=True` and `corpus_available=False`:
- RICH-qualifying → capped to THIN
- ADEQUATE-qualifying → capped to THIN
- THIN → unchanged (no penalty for being unverified)

When no corpus lookup was attempted (`corpus_data=None` passed to scorer):
- No ceiling applied (backward compatible with existing calls)

---

## 3. Before/After Scores (9 tours)

```
File                                                    N   Before   After    Delta
LOCAL262_asian_arts_8stop_restored.txt                  8   78.1     71.9     -6.2
LOCAL317_5stop_old_nice_restaurant.txt                  5   55.0     55.0     +0.0
LOCAL318_5stop_old_nice_restaurant.txt                  5   65.0     60.0     -5.0
matisse_nice.txt                                        8   68.8     65.6     -3.1
pilot_chagall_resubmit.txt                              5   60.0     50.0     -10.0
Palais_Lascaris__Nice_museum_tour_20260727_174018.txt   5   70.0     60.0     -10.0
LOCAL208_riviera_2stop_for_michael.txt                  2   75.0     75.0     +0.0
LOCAL222_riviera_run1.txt                               2   62.5     62.5     +0.0
LOCAL250_riviera_2stop_round7.txt                       2   62.5     62.5     +0.0
```

**5 tours dropped (avg -6.9 points). 0 tours rose. 4 unchanged.**

Stop-level changes:
```
LOCAL262_asian_arts_8stop_restored.txt:
  La geste de Bouddha: RICH → ADEQUATE  (corpus=yes, LOW groundedness - LOCAL-291 cap)
  L'art en exil - Hàm Nghi: ADEQUATE → THIN  (corpus=NO - LOCAL-327 cap)

LOCAL318_5stop_old_nice_restaurant.txt:
  La Voglia: RICH → ADEQUATE  (corpus=yes, LOW groundedness - LOCAL-291 cap)

matisse_nice.txt:
  Nature morte aux grenades: ADEQUATE → THIN  (corpus=NO - LOCAL-327 cap)

pilot_chagall_resubmit.txt:
  The Prophet Elijah: ADEQUATE → THIN  (corpus=NO - LOCAL-327 cap)
  The Song of Songs: ADEQUATE → THIN  (corpus=NO - LOCAL-327 cap)

Palais_Lascaris__Nice_museum_tour_20260727_174018.txt:
  Venus and Cupid: ADEQUATE → THIN  (corpus=NO - LOCAL-327 cap)
  The Penitent Magdalene: ADEQUATE → THIN  (corpus=NO - LOCAL-327 cap)
```

---

## 4. Verification Evidence

### Zero-corpus stop with 5 facts no longer reaches ADEQUATE

```python
# Stop with ADEQUATE-level metrics, corpus lookup attempted, no corpus:
sa = StopAnalysis(...)
sa.distinct_fact_count = 5
sa.fact_density = 0.50
sa.corpus_available = False
sa.corpus_lookup_attempted = True

cls, evidence = classify_stop(sa)
# Result: cls='THIN', evidence contains "ADEQUATE capped: no corpus passages — facts unverified"
```

Demonstrated live:
```
Post-fix behavior (lookup, no corpus): THIN
```

### Well-grounded ADEQUATE stop is unaffected

```
LOCAL-318 WITH corpus (post-fix):
  Acchiardo    ADEQUATE   corpus_avail=True  ← unchanged, 4 corpus passages
  La Voglia    ADEQUATE   corpus_avail=True  ← was RICH, LOCAL-291 groundedness floor caps it
```

### Deliberate break → test goes red

```
With fix REMOVED (corpus_lookup_attempted=False):
  classification = ADEQUATE  ← test expects THIN, would FAIL
```

`test_adequate_metrics_zero_corpus_capped_to_thin` asserts `cls == 'THIN'`.
Without the fix (corpus_lookup_attempted stays False), it gets ADEQUATE → test fails.

### Existing tests pass

```
tests/test_local291_groundedness.py: 23 passed
tests/test_local327_ungrounded_adequate.py: 12 passed
tests/test_local309_verified_unavailable.py: 53 passed
tests/test_local305_missing_stop_fairness.py: 12 passed (subset shown)
Total: 88 passed, 0 failed
```

---

## 5. Limitations

1. **The "Before" score uses no corpus at all.** The pre-fix behavior is simulated
   by passing `corpus_data=None`. In production, if no code ever passes corpus_data
   to score_tour_file, the ceiling never activates. The fix only fires when a caller
   provides corpus_data — which is what the LEAD scorer does.

2. **No container rebuilt.** The fix is purely in the scoring logic (Python), not in
   any service container.

3. **The riviera outdoor tours have NO stop_corpus at all** (0 passages for every stop).
   Their scores are unchanged because they had no ADEQUATE stops to cap (already THIN
   by low density). This means the fix has no measurable effect on walking/cycling tours
   until corpus harvesting extends to those venues.

4. **The task mentions `LOCAL320_museum_8stop.txt` which does not exist in this worktree.**
   The Asian Arts equivalent is `LOCAL262_asian_arts_8stop_restored.txt`. The stops
   "Robe de prêtre taoïste" and "Masque du vieillard kojô" are not in LOCAL262's 8 stops —
   they may be in a different 8-stop variant that was generated but not committed.
   The closest equivalent demonstrated here is "L'art en exil - Hàm Nghi" (ADEQUATE → THIN,
   corpus=NO, 3 facts).

5. **RICH → ADEQUATE transitions for corpus-backed stops** (La geste de Bouddha, La Voglia)
   are caused by LOCAL-291's pre-existing groundedness floor (measured groundedness < 0.40),
   NOT by LOCAL-327. These were always present but not visible when scoring without corpus.
