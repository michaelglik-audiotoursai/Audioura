##### READY FOR REVIEW

## LOCAL-187: Style validator false negatives fixed + Task 7

**Commit:** `7024750` on branch `kiro/local187-validator-false-negatives`
**Base:** `storied`
**Files changed:** 1 (`tests/style_validator_detector.py`, +243 −39)

---

## Changes

### 1. Navigation exemption narrowed for style purposes

The style validator previously imported `is_navigation_paragraph()` from
`stop_anchor_detector_v2.py` as a blanket exemption. That function classifies
"Look for the sturdy stone walls" as navigation because `look for the` is
in its pattern list.

**Fix:** The style validator now has its own `_is_style_navigation_paragraph()`
that only exempts **route-movement** verbs (head, turn, walk, cross, follow,
proceed, continue, etc.) + directional context. Attention-directing verbs
(look for, notice, observe) are **not** exempt from style rules.

The anchor detector's `is_navigation_paragraph` is **unchanged** — constraint
"Do not modify the anchor rule" is respected.

### 2. R3 generalized from "as you explore" to movement/discovery verb class

R3 previously had `\bas you explore\b` as a literal pattern. The generator
writes "as you wander", "as you stroll", "as you traverse" — same
construction, same problem.

**Fix:** Generalized to `\bas you (?:explore|wander|stroll|meander|amble|
roam|walk|venture|journey|travel|discover|uncover|find|encounter|traverse|
navigate|drift|ramble)\b`. Also generalized the `if you [verb]` variant.

### 3. New rule R7: hallucinated sensory data (D62)

Catches assertions of sensory experience the listener cannot actually be
having — historical sounds, absent smells, impossible perceptions.

**Severity: WARNING** (not error). Rationale: regex cannot perfectly
distinguish absent from present sensation in all cases. An honest warning
beats a wrong error. Real present-tense sensory descriptions ("The market
smells of lavender") do NOT fire.

Patterns detected:
- `you can almost hear the echo of his brushstrokes`
- `let the faint sound of X fill your ears`
- `breathe in the faint scent of oil paint that still lingers`
- `whispers/echoes of history/the past/centuries/bygone`
- `passageways echo with the whispers of history`
- `almost taste/smell/hear/feel` (impossibility marker)

---

## Verbatim evidence: four required sentences

```
"Look for the sturdy stone walls of the Château Grimaldi…"
  BEFORE: nav=True, 0 findings
  AFTER:  [R1_IMPERATIVE] error ✓

"As you wander through the museum, let the faint sound of waves
 lapping against the shore fill your ears…"
  BEFORE: 0 findings
  AFTER:  [R3_SUGGESTIVE_EXPLORATION] error + [R7_HALLUCINATED_SENSORY] warning ✓

"you can almost hear the echo of his brushstrokes"
  BEFORE: 0 findings
  AFTER:  [R7_HALLUCINATED_SENSORY] warning ✓

"breathe in the faint scent of oil paint that still lingers in the air"
  BEFORE: 0 findings
  AFTER:  [R7_HALLUCINATED_SENSORY] warning ✓
```

---

## Regression verification

```
"Observers considered the design scandalous in 1887."    → 0 findings ✓
"Explorers landed here in 1388 and named the cape."      → 0 findings ✓
"Discoveries were made beneath the chapel floor in 1932." → 0 findings ✓
"Head south on Promenade de la Croisette"                → is_navigation=True ✓
"Turn left at the intersection and follow the signs."    → is_navigation=True ✓
"Cross the bridge and continue along the river path."    → is_navigation=True ✓
```

Real present-tense sensory (must NOT fire R7):
```
"The market smells of lavender and rotisserie chicken."  → clean ✓
"The sound of waves is audible from the terrace."        → clean ✓
"Salt air fills the promenade."                          → clean ✓
"The scent of fresh pastries drifts from the bakery."    → clean ✓
"breathe in the fragrance of blooming flowers…"          → clean ✓ (no absence marker)
```

---

## Per-rule counts: tours 152, 156, 162

### BEFORE (pre-LOCAL-187)

| Tour | Paras | Nav | Clean | R1 | R2q | R2w | R3 | R4 |
|------|-------|-----|-------|----|-----|-----|----|----|
| 152  | 32    | 0   | 22    | 6  | 0   | 0   | 4  | 3  |
| 156  | 32    | 0   | 20    | 1  | 0   | 0   | 9  | 6  |
| 162  | 3     | 0   | 2     | 0  | 0   | 1   | 0  | 0  |

### AFTER (LOCAL-187)

| Tour | Paras | Nav | Clean | R1 | R2q | R2w | R3  | R4 | R7 |
|------|-------|-----|-------|----|-----|-----|-----|----|-----|
| 152  | 32    | 0   | 13    | 10 | 0   | 0   | 7   | 3  | 8   |
| 156  | 32    | 0   | 18    | 1  | 0   | 0   | 14  | 6  | 3   |
| 162  | 3     | 0   | 0     | 1  | 0   | 1   | 1   | 0  | 1   |

**Deltas explained:**
- Tour 152 R1: +4 from "Look for" sentences no longer hidden by nav exemption
- Tour 152 R3: +3 from "As you wander", "As you explore" (generalized pattern)
- Tour 152 R7: +8 new rule detections (whispers of history, echo of brushstrokes, etc.)
- Tour 156 R3: +5 from generalized "as you [verb]" pattern
- Tour 156 R7: +3 new rule (echoes of history, echo with whispers)
- Tour 162 R1: +1 "Look for the sturdy stone walls" now fires
- Tour 162 R3: +1 "As you wander" now fires
- Tour 162 R7: +1 "faint sound of waves fill your ears" now fires

---

## Limitations

1. **R7 is a warning, not an error.** Regex cannot reliably distinguish
   "the faint scent of oil paint that still lingers" (hallucinated, inside
   museum) from a hypothetical "the faint scent of lavender drifts from the
   garden" (plausibly real). The absence markers (faint, lingering, almost,
   echo of) are strong signals but not perfect. Warning severity means it
   flags for human review without hard-failing.

2. **"Look for" is now always R1.** There is no sentence-level heuristic to
   distinguish "look for the entrance" (navigation) from "look for the
   walls" (observation). The style-specific navigation exemption requires
   route-movement verbs, so "look for" always fires R1. If a generator
   legitimately uses "look for" as a wayfinding instruction ("look for the
   blue sign on your left"), it would need to use a route verb instead
   ("you'll see a blue sign on your left"). This is acceptable because
   "look for" is listed as banned in the ClickUp task.

3. **R7 cannot detect context-dependent hallucination.** "The sound of waves"
   is real at a coastal stop but hallucinated inside an interior museum room.
   R7 only catches syntactic markers of impossibility (faint, almost, echo
   of, whispers of history). Context-aware validation would require knowing
   whether the stop is indoor/outdoor, which is not available to a regex rule.

---

## Constraints respected

- ✓ Detector only — no generation changes
- ✓ No container rebuilds (D48)
- ✓ $0.00 spend — deterministic regex, no LLM
- ✓ Anchor rule (`stop_anchor_detector_v2.py`) not modified
- ✓ No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, STATUS.md
- ✓ Read-only database access (verified in report output)
- ✓ `git status --short` clean after commit
