##### READY FOR REVIEW

# SUBMISSION_LOCAL-124.md — Noise Floors for Every Metric

**Branch:** `kiro/local124-noise-floor-everywhere`  
**Base:** `storied` @ `80ec866`

## Per-file changes

| File | Change | Description |
|------|--------|-------------|
| `FEATURE_PLAYBOOK.md` | +67 lines (§5e inserted) | Noise floor table, per-metric data, cost distribution breakdown, usage guidance |
| `SUBMISSION_LOCAL-124.md` | +this file | Evidence, methodology, limitations |

---

## The table (acceptance criterion 1)

| Metric | Source | Samples | Mean | Stdev | Min believable Δ (n=3) | Min believable Δ (n=5) |
|--------|--------|---------|------|-------|------------------------|------------------------|
| **Rubric score** | LOCAL-100 (5 runs) | 5 | 98.8 | 9.2 | 10.6 | 8.2 |
| **Museum fact count** (rule present) | LOCAL-72 ARM B | 3 | 39.7 | 2.1 | 2.4 | — |
| **Museum fact count** (rule removed) | LOCAL-72 ARM A | 3 | 32.7 | 7.0 | 8.1 | — |
| **Cost per tour** (museum N=8) | cost_ledger + submissions | 9 | $0.068 | $0.002 | $0.003 | $0.002 |
| **Cost per tour** (all sizes, instrumented) | cost_ledger | 40 | $0.050 | $0.023 | — | — |
| **Fact coverage** (stops w/ catalogue facts /8) | LOCAL-98 + LEAD | 4 | 5.75 | 0.50 | TOO FEW SAMPLES | — |
| **Callback count** | LOCAL-95 | — | — | — | INVALID (D25) | — |

**Formula:** Min believable Δ = 2σ/√n (two-sided, ~95% confidence that a shift is real).

---

## Cost distribution from `cost_ledger` (acceptance criterion 2)

**Query:** `SELECT operation_type, our_cost_usd, breakdown FROM cost_ledger WHERE operation_type = 'tour_generate'`  
**Row count:** 85 total; 40 instrumented (non-empty breakdown); 43 flat-rate ($0.0700 exact, NULL breakdown, all 2026-07-31); 2 with empty breakdown `{}`.

### Instrumented entries (n=40) — three distinct populations

| Population | n | Mean | Stdev | Range |
|-----------|---|------|-------|-------|
| Small tours (< $0.03) | 12 | $0.0176 | $0.0012 | $0.0160–$0.0191 |
| Mid tours ($0.03–$0.055) | 4 | $0.0427 | $0.0033 | $0.0383–$0.0464 |
| Full museum tours (> $0.055) | 24 | $0.0673 | $0.0043 | $0.0573–$0.0803 |

### Museum N=8 specifically (9 confirmed measurements)

Sources: LOCAL-96 ($0.065, $0.066, $0.066), LOCAL-100 ($0.0669, $0.0700, $0.0673, $0.0672, $0.0698), LOCAL-72 ($0.0720).

- Mean: $0.0678
- Stdev: $0.0023
- Range: $0.0650–$0.0720
- **A cost change < $0.005 for museum N=8 is noise.**

### The flat-rate entries

43 entries at exactly $0.0700, all from 2026-07-31, all with `breakdown = NULL`. These are pre-instrumentation placeholder estimates. They should not be cited as measurements.

---

## FEATURE_PLAYBOOK.md §5e added (acceptance criterion 4)

Section inserted between §5d ("The host is part of the system") and §6 ("Protect production data"). Contains:
- The full noise-floor table
- Usage template for task acceptance criteria
- Explicit callout of metrics with insufficient data
- Cost distribution detail with guidance on which entries to cite

---

## Verbatim evidence

### Rubric score data (from SUBMISSION_LOCAL-100.md)

```
LOCAL-100 runs: [108.1, 92.8, 97.1, 108.3, 87.8]
  Mean: 98.8, Stdev: 9.2, Spread: 20.5
  
LOCAL-96 runs: [78.1, 70.9, 67.8]
  Mean: 72.3, Stdev: 5.3, Spread: 10.3
```

### Museum fact count data (from SUBMISSION_LOCAL-72.md lines 16–17)

```
ARM A (rule REMOVED): [40, 26, 32]  mean 32.7, stdev 7.0
ARM B (rule PRESENT): [38, 39, 42]  mean 39.7, stdev 2.1
```

### Cost data (from cost_ledger query, 85 rows)

```sql
SELECT COUNT(*), AVG(our_cost_usd), STDDEV(our_cost_usd), MIN(our_cost_usd), MAX(our_cost_usd)
FROM cost_ledger WHERE operation_type = 'tour_generate';
-- Result: 85, 0.0608, 0.0188, 0.0160, 0.0900
```

### Fact coverage (from D27 + SUBMISSION_LOCAL-98.md)

```
LOCAL-98 three runs: 6/6, 6/6, 6/6 (self-measured, same task)
LEAD independent: 5/8
D27 position: "5–6 of 8, improving. Not target met."
```

### Callback count (from CLAIM_AUDIT.md flag #5 + D25)

```
LOCAL-95 reported: mean=8.0, spread=0 (3 runs)
D25 independent audit: 2, 0, 1 real callbacks (human reading)
Root cause: substring matching counted title-word co-occurrence as callbacks
```

---

## Methodology

1. **No new tour generations.** All data extracted from existing submissions (LOCAL-72, LOCAL-96, LOCAL-98, LOCAL-100) and the live `cost_ledger` table.
2. **Minimum believable delta** computed as 2σ/√n — the smallest mean shift that would be statistically distinguishable from zero with ~95% confidence at the given sample size.
3. **Cost populations** separated by visual inspection of the sorted distribution (clear gaps at $0.03 and $0.055), not by a clustering algorithm.
4. **Database read-only.** Row count before: 88. Row count after: 88. No writes.

---

## Limitations

1. **Rubric score stdev may be understated.** LOCAL-100's 5 runs used the same venue, same stop count, same prompt version. Variance across venues or after prompt changes is unknown and likely higher.
2. **Fact coverage has only 4 observations.** Three are from the same task/author (LOCAL-98), so they are not independent. A real floor needs ≥3 independent generations with independent scoring.
3. **Callback count has no valid floor.** The measurement instrument itself is broken (D25). A floor cannot be set until the counter is replaced.
4. **Cost clusters are labeled by inferred stop count**, not confirmed. The ledger has no stop-count column; the populations were identified from submission cross-reference and magnitude.
5. **Cannot verify without Docker.** The cost_ledger query ran against the live Postgres (host port 5433). No new tours were generated. The scorer, generator, and pricing code were not executed — only their documented outputs were used.
6. **The 43 flat-rate entries remain unexplained.** They may be from a batch import, a test harness, or a pricing simulation. Without the code that wrote them, they are flagged but not deleted.

---

## Constraints respected

- ✓ No Docker builds attempted
- ✓ No `DELETE FROM audio_tours` (row count 88 → 88)
- ✓ No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, STATUS.md, CLAIM_AUDIT.md
- ✓ No changes to scorer, pricing, or generation code
- ✓ Cost: $0.00 (no LLM calls, no tour generations)
