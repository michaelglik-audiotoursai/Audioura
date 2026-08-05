##### READY FOR REVIEW

**Task:** LOCAL-231 — Corpus Quality Profile  
**Branch:** `kiro/local231-corpus-quality-profile`  
**Commit:** `0381da7`  
**Base:** `storied`

---

## Files

| file | purpose |
|---|---|
| `QUALITY_PROFILE.md` | Report for Michael — distribution, worst/best 10, by-type split, calibration |
| `quality_profile_data.json` | Per-tour raw data (84 tours, all measurements at every level) |
| `run_quality_profile.py` | Profiling script — read-only, uses existing instruments unmodified |

---

## Evidence

### Row count guard
```
audio_tours: 138 rows (before and after)
Nice list: [1, 12, 14, 17, 21, 24, 27, 28, 29, 152] — all present, unchanged
```

### git status clean
```
$ git status --short
(empty)
```

### No containers rebuilt
No `docker` commands executed. Script connects to existing postgres-2 on port 5433.

### No detectors modified
`style_validator_detector.py`, `claim_check.py`, `sentence_group_scorer.py`,
`corpus_coverage.py` — imported but not edited. No writes to `DECISIONS.md`,
`CLAUDE.md`, `.continuous_dev/*`.

### Scoring coverage
- 84 tours with `tour_content` scored
- 29 real tours, 55 test tours
- 2,854 sentence groups processed across all tours
- All four levels computed: sentence group → paragraph → stop → tour

### Calibration against Michael's marks
Tour 163, 11 groups: machine agrees on 4 of 11 (36%). Disagreements called out
with specific gap identification in QUALITY_PROFILE.md §5.

### No i-con score invented
Rule rates, claim verdicts, group counts, coverage verdicts reported — inputs
to a score, not a score (D102).

---

## Limitations

1. **Row count 138, not 133.** 5 test tours created between task specification
   and execution. No real tours affected.

2. **Unsupported claim measurement unreliable for 83% of real tours.** 24 of 29
   real tours have ALL stops EMPTY — `claim_check` has nothing to measure against.
   Reported as "unchecked" rather than "clean" per task instruction.

3. **Calibration limited by group boundary mismatch.** Machine produces 18 groups
   for Michael's 11. Alignment is approximate for groups beyond the first few.

4. **Tour type classifier falls back to "other" for non-English.** This inflates
   the "other" category and makes the by-type split less precise for Russian tours.

5. **Cost: $0.00.** No LLM calls. All instruments are deterministic.
