# SUBMISSION_LOCAL-433.md

## LOCAL-433 — measure the variance before anyone argues about the threshold

### Distribution Table — Palais Lascaris (5 live runs)

| stop | run 1 | run 2 | run 3 | run 4 | run 5 | mean | min | max | stdev | pass_rate |
|---|---|---|---|---|---|---|---|---|---|---|
| Harpe (1780) | 0 | 2 | 1 | 1 | 0 | 0.8 | 0 | 2 | 0.84 | 0% |
| Sacqueboute (1581) | 0 | 2 | 1 | 1 | 2 | 1.2 | 0 | 2 | 0.84 | 0% |
| Violes gambe (1652) | 3 | 3 | 1 | 1 | 0 | 1.6 | 0 | 3 | 1.34 | 40% |
| Basse de violon (1696) | 0 | 0 | 2 | 3 | 2 | 1.4 | 0 | 3 | 1.34 | 20% |
| **total** | **3** | **7** | **5** | **6** | **4** | — | — | — | — | — |
| **gate (all ≥3)** | **1/4** | **1/4** | **0/4** | **1/4** | **0/4** | — | — | — | — | — |

**All-stops-pass frequency: 0/5 (0%)**

No single run cleared the gate. The best run (run 2, total=7) had two stops at 3 but the other two at 0 and 2.

### Per-stop analysis

- **Variance is uniform across stops.** Stdev ranges 0.84–1.34 (same order of magnitude). No stop is reliably good or reliably bad.
- **No stop ever exceeds 3.** The maximum story_count observed is 3, which is exactly the threshold. The classifier is not "nearly passing" — it is at the boundary.
- **Two stops (Harpe, Sacqueboute) never reach 3.** Their maximum across 5 runs is 2. These stops cannot pass the gate under current conditions.
- **Two stops (Violes, Basse) reach 3 in some runs but not others.** Violes passes in 2/5 runs, Basse in 1/5. This is the swing D385 identified.

### How often each stop clears 3

| stop | clears 3 | rate |
|---|---|---|
| Harpe (1780) | 0/5 | 0% |
| Sacqueboute (1581) | 0/5 | 0% |
| Violes gambe (1652) | 2/5 | 40% |
| Basse de violon (1696) | 1/5 | 20% |

### How often ALL stops clear 3 in the same run

**0/5 = 0%.** The gate as currently designed would reject 100% of Palais Lascaris tours.

### MFA Unbound — unproven, handing to LEAD

MFA Unbound cannot produce live variance data:
1. `mfa.org` returns HTTP 429 to all requests (persistent since LOCAL-425).
2. Even with the page-fetch pin from `run_mfa_unbound_pinned.py`, BLOCKER4b rejects the GPT-generated Phase 3A stops as address-scattered (6 distinct addresses for 6 stops).
3. The exhibition checklist integration path that `run_mfa_unbound_pinned.py` depends on is not reached before BLOCKER4b fires.

This is an infrastructure problem (mfa.org down + blocker ordering), not a measurement refusal. The venue literally cannot be generated.

---

### Control (D302/D326): Palais 4/4, dates intact

From run 2 (the highest-total run):
- **Stops: 4/4** (Harpe by Naderman, Sacqueboute ténor, Violes gambe, Basse de violon)
- **Dates: 4/4** (1780, 1652, 1581, 1696 — all in stop titles and text)
- **Coordinates: 4/4** (43.6984, 7.276 — museum single-coordinate mode)
- framing=venue_purpose detected

---

### Recommendation: gate on a tour-level aggregate, not every stop

**`L421_GATE_BLOCKS` cannot be flipped as currently designed.** The data is unambiguous: a per-stop threshold of ≥3 with an all-must-pass conjunction produces a 0% pass rate across 5 runs. Flipping the gate would make Palais Lascaris permanently undeliverable.

**Options considered:**

1. **Retry until the gate passes** (fixed attempt cap).
   Against: The retry already fires 3 attempts per stop and lands at 0–2. The gap is not "one more try" — the model generates ~1.2 story sentences per stop on average when the threshold is 3. Triple-retrying to hit 3× your baseline is not convergent. Cost: ~$0.60/tour with 3×4 stop retries already. Verdict: **impractical**.

2. **Gate on tour-level aggregate rather than every stop.**
   For: The total story count across the tour is 3–7 (mean ~5). A tour-level threshold of "≥8 total story sentences" or "≥2 mean per stop" is reachable in some runs and would distinguish truly thin tours from noise. The per-stop gate punishes the variance of individual stops; a sum smooths it.
   Against: A tour where one stop has 7 stories and three have 0 would pass. But that is a quality-weighting concern, not a blocking concern.
   Verdict: **viable, with a threshold chosen to match the ~50th percentile of current production**.

3. **Record the gate as a quality signal per tour, not a delivery block.**
   For: The underlying metric is valuable for monitoring and triggering alerts. The problem is using it as a blocking gate when n=1 variance exceeds the threshold. A recorded signal can be aggregated over time to detect regressions without refusing individual tours.
   Against: Does not prevent delivery of genuinely thin tours — a future task would need a threshold that is reliably reachable.
   Verdict: **safe, but defers the quality enforcement question**.

**My recommendation: option 2 (tour-level aggregate gate).**

Reasoning:
- It preserves the intent of the gate (ensure the tour has substantive story content).
- It is robust to per-stop variance (a sum of 4 random variables has lower coefficient of variation than each individually).
- A threshold set at the 20th percentile of current production (e.g., ≥4 total story sentences) would pass 4/5 of these Palais runs while still rejecting genuinely empty tours.
- The per-stop version is fundamentally incompatible with the observed noise: stdev ≈ 1.1 on a threshold of 3 with a mean of 1.25 means the threshold is ~1.6σ above the mean. That's a 5% expected pass rate per stop and ~0.0006% for all-4-pass. The math does not support it.

**Do not implement in this task** — this is the measurement that establishes the numbers for the threshold discussion.

---

### Red output (neutralisation evidence)

**Neutralising `compute_statistics` → 7 tests red:**
```
FAILED tests/test_local433_variance_statistics.py::TestComputeStatistics::test_single_value
FAILED tests/test_local433_variance_statistics.py::TestComputeStatistics::test_two_values
FAILED tests/test_local433_variance_statistics.py::TestComputeStatistics::test_three_values_from_task
FAILED tests/test_local433_variance_statistics.py::TestComputeStatistics::test_five_identical_values
FAILED tests/test_local433_variance_statistics.py::TestComputeStatistics::test_five_values_known
FAILED tests/test_local433_variance_statistics.py::TestComputeStatistics::test_empty_raises
FAILED tests/test_local433_variance_statistics.py::TestComputeStatistics::test_zeros
```

**Neutralising `compute_gate_verdicts` → 3 tests red:**
```
FAILED tests/test_local433_variance_statistics.py::TestComputeGateVerdicts::test_d385_table_data
FAILED tests/test_local433_variance_statistics.py::TestComputeGateVerdicts::test_empty_raises
FAILED tests/test_local433_variance_statistics.py::TestComputeGateVerdicts::test_mixed_stop_counts
```

### Targeted suites

```
tests/test_local433_variance_statistics.py: 12 passed in 0.11s
```
