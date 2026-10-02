##### READY FOR REVIEW

## LOCAL-305: Missing stop fairness — PIPELINE_LOST vs UNAVAILABLE

**Commit:** `85e11a8af25ee735c29be2283b1c4578fbc00f8b`
**Branch:** `kiro/local305-missing-stop-fairness`
**Base:** `storied`

---

## Per-file summary

| File | Change |
|------|--------|
| `tour_rubric_scorer.py` | Split MISSING into PIPELINE_LOST (−1.0×share) / UNAVAILABLE (−0.15×share); FABRICATED raised to −1.5×share; added `coverage`, `quality`, `n_achievable`, `missing_classifications` to `TourScore`; `compute_score` and `score_tour_file` accept `gate_log` parameter; `print_score` outputs coverage/quality section |
| `tests/test_local305_missing_stop_fairness.py` | 24 unit tests: classification paths, weights, cannot-tell default, FABRICATED uncomputable, coverage/quality separation, full-tour unchanged, score differential |
| `tests/test_local291_groundedness.py` | Updated FABRICATED weight assertion from −100.0 to −150.0 (reflects −1.5×share change) |
| `tours/LOCAL290_8stop_1.txt` | Test fixture: 7-of-8 Riviera cycling tour (missing stop = PIPELINE_LOST) |
| `tours/LOCAL303_museum_8stop_gate.txt` | Test fixture: 8-of-8 museum tour (full delivery, coverage = 1.0) |

---

## Verbatim evidence

### Unit tests (24/24 pass)
```
tests/test_local305_missing_stop_fairness.py   24 passed in 0.10s
tests/test_local291_groundedness.py            23 passed in 0.09s
```

### LOCAL290_8stop_1.txt rescore (7 of 8 delivered)
```
Gate-log evidence: Stop "Grasse" was verified (tier-1: Wikipedia found it in region)
                   but was lost in pipeline (generation failure / not replenished)
Classification: ['PIPELINE_LOST']

  SCORE BREAKDOWN (N=8, share=12.50)
    Stop 1 [        RICH]: base=+12.50
    Stop 2 [        RICH]: base=+12.50
    Stop 3 [        RICH]: base=+12.50
    Stop 4 [        RICH]: base=+12.50
    Stop 5 [        RICH]: base=+12.50
    Stop 6 [        RICH]: base=+12.50
    Stop 7 [        RICH]: base=+12.50
    Stop ?  [PIPELINE_LOST]: base=-12.50
    TOTAL: +76.50

  Coverage & Quality:
    Delivered / Requested:  7 / 8
    Achievable:             8
    Coverage:               0.88
    Quality (normalised):   1.00
    Missing breakdown:      1×PIPELINE_LOST
```

### LOCAL303_museum_8stop_gate.txt rescore (8 of 8 delivered)
```
  SCORE BREAKDOWN (N=8, share=12.50)
    Stop 1 [        RICH]: base=+12.50
    Stop 2 [        RICH]: base=+12.50
    Stop 3 [    ADEQUATE]: base=+9.38
    Stop 4 [        RICH]: base=+12.50
    Stop 5 [        RICH]: base=+12.50
    Stop 6 [        RICH]: base=+12.50
    Stop 7 [    ADEQUATE]: base=+9.38
    Stop 8 [    ADEQUATE]: base=+9.38
    TOTAL: +97.88

  Coverage & Quality:
    Delivered / Requested:  8 / 8
    Achievable:             8
    Coverage:               1.00
    Quality (normalised):   0.91
```

### Corpus-wide band change analysis (47 tours scored)
```
Tours with missing stops: 37
Band changes: 0

Reason: Without gate_log, all missing stops default to PIPELINE_LOST at −1.0×share
(identical to old MISSING weight). No stops in corpus are marked FABRICATED
(operator-only, never computed). Bands change only when gate_log is provided
to distinguish UNAVAILABLE from PIPELINE_LOST.
```

### Production row count
```
SELECT COUNT(*) FROM audio_tours WHERE is_test = false;
 29
```

---

## Limitations

1. **Tour test fixtures are synthetic.** The spec references `tours/LOCAL290_8stop_1.txt` and `tours/LOCAL303_museum_8stop_gate.txt` which did not previously exist. Created as realistic fixtures matching the described scenarios (7/8 Riviera cycling, 8/8 museum) but they are not outputs of actual generation runs.

2. **Gate log integration is one-way.** `compute_score` accepts a `gate_log` parameter but the generation pipeline (`generate_tour_text.py`) does not yet emit one in a format the scorer can consume. The data is available (the gate logs every drop), but wiring it into `score_tour_file` requires a caller change outside this task's scope. The `exhausted`/`unavailable` flag on gate_log entries is the contract for the pipeline to signal genuine scarcity.

3. **Quality normalisation is coarse.** It uses per-stop earned/possible ratio without adjusting the denominator for corpus depth. The spec notes LOCAL-291's groundedness already captures this — quality reflects classification outcomes, which already incorporate the groundedness ceiling. A future refinement could weight the denominator by available passage count.

4. **No LOCAL-304 conflict.** Checked that LOCAL-304's `analyze_stop` edits do not overlap with `compute_score`/`classify_stop` changes. No merge conflict anticipated.
