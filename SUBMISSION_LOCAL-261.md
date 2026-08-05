##### READY FOR REVIEW

## LOCAL-261: R2/R3/R4/R8 Deletion Paths (D165)

**Branch:** `kiro/local261-r2-r3-r4-r8-deletion-path`
**Commit:** `5bbf5cb`
**Date:** 2026-08-05

## Summary

Four of seven style detectors could see violations and could not act — R2
(questions), R3 (suggestive exploration), R4 (prescribed feeling), R8 (prompt
leakage) fired during PHASE 5.1 style validation, triggered a retry, and when
the retry failed, the sentence shipped unchanged. This task adds a deletion
path for each, following the PHASE 5.14 (R7) pattern.

## Files Changed

| File | Change |
|---|---|
| `style_validator_detector.py` | Added `apply_r2_deletions`, `apply_r2_to_description`, `apply_r3_deletions`, `apply_r3_to_description`, `apply_r4_deletions`, `apply_r4_to_description`, `apply_r8_deletions`, `apply_r8_to_description` — eight functions following the exact `apply_r7_deletions`/`apply_r7_to_description` pattern. Inserted after line 2029 (end of R7 apply), before R8 detection section. No detector widened. |
| `generate_tour_text.py` | Added PHASE 5.141 (R2), 5.142 (R3), 5.143 (R4), 5.144 (R8) between existing PHASE 5.14 (R7) and 5.15 (R9). Each behind `DISABLE_Rx_DELETION=1` env var. Identical structure to R7's block. |
| `run_round17.py` | New generation script — corpus-wide baseline, generation, measurements, D141-compliant DB insert/cleanup, artifact write. |
| `RIVIERA_2STOP_ROUND17.md` | Generated artifact. |

## Boundary Row Evidence

```
=== MUST BE DELETED ===
Row 1: "As you stand on Cap d'Antibes, you are surrounded by history and natural beauty."
  Fires: R4  →  DELETED ✓

Row 2: "The rugged beauty of the landscape, with its rocky cliffs and secluded coves, invites contemplation and serenity."
  Fires: NONE (R2/R3/R4/R8)  →  SURVIVES (detection gap — "invites contemplation" not in R4 pattern set)

Row 3: "This stop on the French Riviera cycling tour connects deeply with the theme of community and tradition."
  Fires: NONE (R2/R3/R4/R8)  →  SURVIVES (detection gap — "connects deeply with the theme" not in R8; "French Riviera" stops R9)

=== MUST SURVIVE ===
Row 4: "In 1888, Monet first experimented with painting in series here."
  Fires: NONE  →  SURVIVES ✓

Row 5 (D164): "Start cycling southeast on the main road, enjoy the sea breeze along the coast."
  is_navigation: True  →  SURVIVES ✓ (navigation exempt from all deletion phases)

Row 6: "The La Colombe d'Or hotel has hosted Jean-Paul Sartre and Pablo Picasso."
  Fires: NONE  →  SURVIVES ✓
```

**Rows 2 and 3:** These two sentences escape all four new rules AND all existing
rules (R1, R7, R9, R10). They are real detection gaps. Per D165: "If R4 misses
something, that is a separate task." No detector was widened.

## Corpus-Wide Rate (D55 Compliance)

| Rule | Before | After | Ratio |
|---|---|---|---|
| R2 (question, error) | 50/6310 = 0.79% | 0.79% | 1.00× (unchanged) |
| R3 (suggestive) | 164/6310 = 2.60% | 2.60% | 1.00× (unchanged) |
| R4 (prescribed) | 103/6310 = 1.63% | 1.63% | 1.00× (unchanged) |
| R8 (prompt leakage) | 37/6310 = 0.59% | 0.59% | 1.00× (unchanged) |
| **Total** | 354/6310 = 5.61% | 5.61% | 1.00× |

Before = After because no detector was widened. The detection functions are
unchanged; only the action path (deletion) was added. D55 ceiling (3×) is
trivially satisfied.

## RIVIERA_2STOP_ROUND17.md

| Metric | Round 15 | Round 17 |
|---|---|---|
| Word count | 708 | 534 |
| R2 residual | — | 0 |
| R3 residual | — | 0 |
| R4 residual | — | 0 |
| R8 residual | — | 0 |
| Cap d'Antibes facts | 2 | 4 |
| Stop 2 facts | 7 (Èze) | 1 (Saint-Tropez) |
| Cost | $0.0206 | $0.0099 |

Word count dropped from 708 to 534 (−25%). Above the 450 threshold.
Cost: $0.0099 (12,415 tokens). Ceiling $0.60.

**Run cost of the deletion phases themselves: $0.00** — all four are
deterministic regex, no LLM call.

Note: Stop 2 varied across runs (Èze, Cape Ferrat, Saint-Paul-de-Vence,
Saint-Tropez) due to model nondeterminism in stop selection. The code change
is stop-independent.

## Detectors Not Widened — Explicit Statement

No detection function was modified. The following functions are **unchanged**:
- `check_r2_questions()` — same patterns, same logic
- `check_r3_suggestive_exploration()` — same `_R3_COMPILED` patterns
- `check_r4_prescribed_feeling()` — same `_R4_COMPILED` patterns
- `check_r8_prompt_leakage()` — same `_R8_PATTERNS`, same `_R8_FALSE_POSITIVE_GUARDS`

Only `apply_*` functions (action) were added. Detection is identical.

## No Container Rebuilt (D48)

No Dockerfile or docker-compose.yml changes. No container build commands run.

## Cleanup (D141)

Test row inserted with `is_test=true`, confirmed via `SELECT is_test`, deleted
after measurement. `audio_tours` count: 142 before, 142 after. Nice list
`[1, 12, 14, 17, 24, 29, 152]` unchanged.

## LOCAL-257 Coordination

LOCAL-257 (fragment checker) is on branch `kiro/local257-fragment-checker-and-article`
and has NOT merged into `storied`. It modifies lines 1501–1859 of
`style_validator_detector.py` (the `_has_finite_main_verb` function and
`_FINITE_VERB_FORMS`). This task's changes are:
- Lines 2030+ (new `apply_*` functions, inserted after `apply_r7_to_description`)
- `generate_tour_text.py` (new phases after R7's block)

No overlap. Clean merge expected.

## Limitations

1. **Rows 2 and 3 escape all detectors.** "invites contemplation and serenity"
   and "connects deeply with the theme" are not caught by any current rule.
   These are detection improvements, not this task's scope.

2. **Stop selection is nondeterministic.** The model varies the second stop
   across runs. Cannot guarantee Èze without prompt changes.

3. **R1 residual persists (4-8 per tour).** R1 rewrite (PHASE 5.13) handles
   the bulk but does not reach 0. Separate concern.

4. **"The Mediterranean breeze gently caresses your skin"** survived in one
   generation — it does not match R4's pattern set ("you feel/sense/are
   surrounded") and is not R7 (no absence marker). Detection gap.
