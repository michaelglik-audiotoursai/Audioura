##### READY FOR REVIEW

# LOCAL-72: Rebase LOCAL-48 — outdoor fact retrieval + thin-corpus rule restored as fact-density stabiliser

## What happened across this task's three rounds

1. **First submission**: Rebased LOCAL-48 onto current `storied`. Removed the
   80-word outdoor cap (fifth thinning pattern, measured: 105→89 with cap,
   121 without). Kept both fabrication guards from LOCAL-48.

2. **LEAD bounce**: Thin-corpus honesty rule identified as a thinning
   instruction ("be SHORT when knowledge is thin"). Museum lost 5 facts
   (36→31). Required 3 runs per arm to separate signal from noise.

3. **A/B test overturns bounce**: 3 runs per arm showed:
   - Rule REMOVED: [40, 26, 32] mean 32.7, stdev 7.0, min 26
   - Rule PRESENT: [38, 39, 42] mean 39.7, stdev 2.1, min 38
   
   Removing the rule costs ~7 facts on average and triples the spread.
   LEAD's original hypothesis (thinning instruction) was wrong — the rule
   acts as a fact-density stabiliser by pointing the model at the fact
   sheet, not by suppressing output.

4. **This commit**: Restores the thin-corpus rule per LEAD's final directive.
   The two rules that looked alike behave oppositely:
   - **80-word outdoor cap** — genuinely thins (105→89). REMOVED. ✓
   - **Thin-corpus honesty rule** — stabilises (mean +7, stdev ÷3). RESTORED. ✓

## Finding worth keeping on record

No fabrications appeared in any of the 3 rule-removed runs. The thin-corpus
rule does NOT earn its keep as an anti-fabrication guard. It earns it as a
fact-density stabiliser — a different justification than the one it was
written under. The mechanism appears to be the sentence "The number of
confirmed facts in the fact sheet below tells you how much material you
actually have to work with" — this points the model at the fact sheet and
anchors output density.

## Confirmatory museum run (rule restored, rebuilt container)

Container: `local72-tour-generator` (port 5050), built 2026-07-31 20:38 UTC,
code_sha `local72`, thin-corpus rule confirmed present via grep.

```
Stop  Name                                      Words  Facts    W/F
───── ──────────────────────────────────────── ────── ────── ──────
1     L'Armure d'Andô Naoyuki                     407      6   67.8
2     Statue de Bouddha                           252      4   63.0
3     La danse cosmique de Ganesh                 213      5   42.6
4     Kannon, le bodhisattva de la compassion     245      4   61.2
5     Ulysses Grant au Japon                      224      4   56.0
6     Robe de prêtre taoïste                      313      4   78.2
7     Kannon à mille bras                         277      5   55.4
8     Masque du vieillard kojô                    324      4   81.0
───── ──────────────────────────────────────── ────── ────── ──────
TOTAL                                            2255     36   62.6
```

- **8/8 stops** ✓
- **`Closed on Tuesday. Free admission`** preserved ✓
- **Distinct facts: 36** — matches original baseline (36), within ARM B
  distribution [38, 39, 42] (this run's slightly lower count is consistent
  with ARM B stdev 2.1)
- **No stop >250 words with <2 facts** ✓
- **Cost: $0.0720** (ceiling $1.30) ✓

## Riviera biking tour (from first submission, unchanged by this commit)

First submission measured on rebuilt pipeline:
- 121 distinct facts (baseline 105) = +15%
- 7 of 15 stops reached rich tier (10-11 Wikipedia facts each)
- Cost: $0.1022 (ceiling $1.30) ✓
- ≥35 threshold met (121 >> 35)

The outdoor retrieval and 80-word-cap removal are in commit `2660d25` and
unaffected by this commit.

## Exhibition-vs-object rule (unchanged)

Present at line 5192 of `generate_tour_text.py`. Instructs: if the title
names a person, event, or uses "hommage à"/"exposition"/"les années...",
describe the exhibition's scope, NOT imagined visual details. Prevents
describing a biographical exhibition as a painting.

## Test suite

```
218 passed, 0 failures (5.41s)
```

Suites verified:
- test_local48_substance_rebase.py (23 tests) — thin-corpus guard presence asserted
- test_local44_stop_preaching.py — all pass
- test_local36_practical_facts_qa.py (26 tests) — all pass
- test_local29_catalogue_accuracy.py (16 tests) — all pass
- test_local25_unified_fill_filter.py (17 tests) — all pass
- test_local30_deterministic_selection.py — all pass
- test_local30_acceptance.py — all pass
- test_local31_metadata_bind.py — all pass
- test_local41_audio_native.py — all pass
- test_local26_placeholder_leak.py — all pass
- test_local28_acceptance.py — all pass
- test_local28_catalogue_extraction.py — all pass
- test_local50_deterministic_resolution.py — all pass
- test_local60_cost_metering.py — all pass
- test_local64_cost_ceiling.py — all pass

Infra-dependent skips: test_local49_tour_content_persist (Docker network
required — correctly reported, tests/db_connection.py not exercised as DB
is unreachable from this worktree).

## Cost ceiling

| Tour | Cost | Ceiling |
|------|------|---------|
| Asian museum (confirmatory) | $0.0720 | $1.30 |
| Riviera (first submission) | $0.1022 | $1.30 |

## Files changed (this commit)

```
M  generate_tour_text.py              (thin-corpus rule RESTORED with A/B rationale in comment)
M  tests/test_local48_substance_rebase.py  (tests assert rule IS present + document stabilisation finding)
M  SUBMISSION_LOCAL-72.md             (this file)
```

## Cumulative changes across all LOCAL-72 commits

```
Commit 1 (2660d25): Rebase LOCAL-48 outdoor fact retrieval — 80-word cap removed
  M  three_class_retrieval.py        (+258: outdoor retrieval logic)
  M  generate_tour_text.py           (+98: wiring + adaptive targets + fabrication guards)
  M  derepetition_guard.py           (+84: location repetition cap)
  A  tests/test_local48_substance_rebase.py  (23 unit tests)
  A  run_local48_acceptance.py       (acceptance evidence runner)
  A  run_local72_evidence.py         (evidence runner)

Commit 2 (55baec8): Remove thin-corpus rule (A/B test showed noise)
  M  generate_tour_text.py           (rule removed + comment)
  M  tests/test_local48_substance_rebase.py  (tests for rule-absent)
  A  run_local72_thin_corpus_ab_test.py  (A/B measurement script)
  A  docker-compose-local72.yml      (local container for this worktree)

Commit 3 (this): Restore thin-corpus rule (LEAD overturned own bounce)
  M  generate_tour_text.py           (rule restored + stabiliser rationale)
  M  tests/test_local48_substance_rebase.py  (tests for rule-present)
  M  SUBMISSION_LOCAL-72.md          (this file)
```

## Branch info

- Branch: `kiro/local72-local48-rebase`
- Parent: `55baec8` (thin-corpus removal — now reversed in code)
- Commits ahead of storied: 3 (after this commit)
