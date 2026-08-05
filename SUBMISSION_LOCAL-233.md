##### READY FOR REVIEW

**Commit:** `e35bc69b4d8f3646628f1e78d6b9187ebca60fe6`
**Branch:** `kiro/local233-mid-sentence-imperatives`
**Base:** `storied`

---

## Per-file summary

| file | change |
|---|---|
| `style_validator_detector.py` | +338 / −70 lines. Added mid-sentence imperative detection and clause-level navigation exemption. |

No other files modified. No container rebuilt (D48). `git status --short` clean after commit.

---

## What was done

### 1. Mid-sentence imperative detection

Added `_extract_clause_after_subordinate()` — identifies the main clause after a leading subordinate clause introduced by `As you`, `While`, `When`, `After`, `Before`, `Once`, `Upon`, `If`. Finds the clause-separating comma and returns the remainder.

Added `_check_clause_for_imperative()` — applies the same inverted-design gate logic (non-verb starters, morphology, third-person -s, noun subjects, navigation+directional) to the extracted main clause. Adapted for mid-sentence position where capitalization heuristics don't apply.

### 2. Clause-level navigation exemption

Added `_check_nav_sentence_suggestive_tail()` — for sentences classified as navigation, splits at the first comma and checks the tail for:
- R3/R4 patterns (suggestive exploration, prescribed feeling)
- Prescriptive gerund participials (`envisioning`, `immersing yourself`, `absorbing`, `imagining`, etc.) — these are imperative-equivalent when attached to a navigation clause
- Mid-sentence imperatives (base-form verb after the comma in a nav sentence)

**The split explained:** `_is_style_navigation_paragraph()` still classifies the paragraph as navigation, but now iterates through each sentence calling `_check_nav_sentence_suggestive_tail()`. The route-movement clause (before the comma) remains exempt. The tail (after the comma) is checked. Non-navigation sentences within a nav paragraph retain their paragraph-level exemption (no full R1 applied — only tail checks). This prevents "Take the second exit" from losing its exemption when nested inside a nav paragraph.

### 3. Modified `validate_paragraph`

Navigation paragraphs now call `_check_nav_sentence_suggestive_tail` on every sentence. Non-navigation paragraphs also check tails when a sentence passes the sentence-level nav heuristic.

---

## Evidence: acceptance table

```
MUST FIRE:
  FIRES  {'R1_IMPERATIVE'}              As you arrive at X, pause to take in the breathtaking view.
  FIRES  {'R1_IMPERATIVE'}              As you stand before Y, take in the sight of the lighthouse.
  FIRES  {'R4_PRESCRIBED_FEELING'}      Pedal along the coastline, envisioning the hidden coves and immersing yourself in the beauty.
  FIRES  {'R1_IMPERATIVE'}              Take a moment to absorb the ancient aura.

MUST STAY EXEMPT:
  CLEAN  set()                          Start cycling south on the main road toward the coast.
  CLEAN  set()                          Head south along the Promenade des Anglais.
  CLEAN  set()                          Turn left at the fountain and continue past the church.
  CLEAN  set()                          Continue straight until the roundabout.
```

---

## Evidence: corpus-wide R1 rate (before and after)

```
BEFORE (QUALITY_PROFILE.md, D119): 797/2854 groups = 27.9%
AFTER (LOCAL-233):                1076/2975 groups = 36.2%
Delta:                            +279 groups, +8.3 percentage points

By tour type:
  cycling   258/726  = 35.5%
  walking   474/1189 = 39.9%
  museum    344/1060 = 32.5%
```

The group count difference (2854 → 2975) is because `split_into_sentence_groups` counting varies slightly with the paragraph min-length filter (the 84 tours are the same). The rate increase is expected and correct — 279 additional mid-sentence imperatives are now visible.

---

## Evidence: calibration against Michael's 11 marks

```
BEFORE: 5 agree, 2 partial, 4 disagree
AFTER:  7 agree, 3 partial, 1 disagree

  ✓ M#0: Navigation 5/5          Machine=clean (nav)
  ✓ M#1: Listen/Look 1/5         Machine={'R1_IMPERATIVE'}
  ~ M#2: Prolog 3/5              Machine={'R1_IMPERATIVE'}
  ~ M#3: Monet facts 3/5         Machine={'R8_PROMPT_LEAKAGE'}
  ~ M#4: Take in / Pedal 2/5     Machine={'R1_IMPERATIVE', 'R4_PRESCRIBED_FEELING'}
  ✓ M#5: Pause to take in 1/5    Machine={'R1_IMPERATIVE'}
  ✓ M#6: Look for 1/5            Machine={'R1_IMPERATIVE'}
  ✓ M#7: Bay facts 5/5           Machine=clean
  ✗ M#8: Whispers tales 1/5      Machine=clean
  ✓ M#9: Generic 0/5             Machine={'R9_GENERIC', 'R1_IMPERATIVE'}
  ✓ M#10: Generic 0/5            Machine={'R9_GENERIC'}
```

**Remaining disagreement:** M#8 ("whispers tales of a bygone era") — machine says clean, Michael scored 1/5. This is a KNOWN gap (R4 does not catch conditional prescriptions via personification "whispers tales" or "adds depth to your understanding"). Explicitly stated as out of scope.

**M#3's R8 false positive** (fires on "One concrete sensory detail..." in a group Michael scored 3/5) is also known and out of scope — R8 fires correctly on the prompt leakage; Michael valued the facts around it.

---

## Evidence: existing test suites

```
test_r9_generic_deletion.py:   39/39 pass ✓
test_r8_prompt_leakage.py:     31/31 pass ✓
test_local227_falsification.py: 16/16 instruments notice breakage ✓
test_local228_glue_falsification.py: 0 new errors (4 pre-existing known) ✓
```

Verbatim output (summary lines):
- R9: `TOTAL: 39/39 pass  ✓ ALL PASS`
- R8: `TOTAL: 31/31 pass  ✓ ALL PASS`
- Falsification: `Instruments that NOTICE breakage: 16 / DO NOT notice: 0 / errors: 0`
- Glue: `Contract HOLDS: 11 / DO NOT NOTICE: 4 / errors: 0`

---

## Evidence: database unchanged

```
audio_tours count: 138
Nice list: [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
```

---

## Limitations

1. **M#8 unresolved.** "Whispers tales", "may evoke the scent", "adds depth to your understanding" — these are R4/R3 detection gaps involving personification-as-filler and conditional prescriptions. Not addressed because out of scope.

2. **Subordinate clause detection is syntactically bounded.** Only fires after known subordinating openers (`As you`, `While`, `When`, etc.). A mid-sentence imperative after a different construction (e.g., "The chapel is remarkable — pause here to absorb it") would not fire. This is deliberate: the task scoped to the pipeline's house style pattern.

3. **Prescriptive gerund detection fires only in navigation tails.** "Envisioning the hidden coves" in a non-navigation sentence would NOT trigger R4 through this mechanism. The detection is context-dependent (navigation clause + suggestive tail) to avoid false positives on legitimate gerund usage elsewhere.

4. **Group count methodology.** The before/after comparison uses `split_into_sentence_groups` which yields 2975 groups vs QUALITY_PROFILE.md's 2854. This is a counting difference (slightly different min-length filter), not a data difference. The 84 tours are unchanged.

5. **No container rebuilt.** D48 honored.
