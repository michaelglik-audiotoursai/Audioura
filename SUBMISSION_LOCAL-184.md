##### READY FOR REVIEW

# LOCAL-184 — Style Validator Detector (Round 2)

## Commit

```
f4cd629 LOCAL-184 round 2: Fix R1 prefix-match → word-boundary match
5cee2d8 LOCAL-184: Style validator detector (R1-R4) — instructions, questions, prescribed feelings
```

Branch: `kiro/local184-style-validator` (2 commits ahead of `storied`)

## Per-file changes

| File | Status | Purpose |
|------|--------|---------|
| `tests/style_validator_detector.py` | **Modified** | R1 word-boundary fix + 3 regression cases |
| `tests/style_validator_report.txt` | **Added** | Full baseline report output |

## The Defect (Round 1 → Round 2)

Line 122 used `lower.startswith(verb)` — no word boundary. Sentences opening
with nouns derived from banned verbs were flagged as imperatives at **error**
severity:

```
OLD (broken):
  "Observers considered the design scandalous in 1887."   → R1_IMPERATIVE ✗
  "Discoveries were made beneath the chapel floor in 1932." → R1_IMPERATIVE ✗
  "Explorers landed here in 1388 and named the cape."     → R1_IMPERATIVE ✗
```

## The Fix

```python
# Before (line 122):
if lower.startswith(verb):

# After:
if re.match(rf'{re.escape(verb)}\b', lower):
```

`\b` enforces a word boundary at the end of the verb phrase. `re.escape`
handles multi-word verbs like "pay attention to" safely. No additional
heuristic needed — the word boundary alone prevents all identified false
positives while still matching true imperatives.

## Evidence: Regression cases pass

```
=== SHOULD FIRE (true imperatives) ===
  ✓ FIRES: Consider how this journey continues in his other works.
  ✓ FIRES: Explore the intricate details of the Annunciation.
  ✓ FIRES: Discover the strength of Raquel.
  ✓ FIRES: Observe the asymmetry in the facade.
  ✓ FIRES: Feel the weight of centuries pressing down upon you.
  ✓ FIRES: Notice the worn cobblestones beneath your feet.

=== SHOULD NOT FIRE (nouns/third-person) ===
  ✓ SILENT: Observers considered the design scandalous in 1887.
  ✓ SILENT: Discoveries were made beneath the chapel floor in 1932.
  ✓ SILENT: Explorers landed here in 1388 and named the cape.
  ✓ SILENT: Considerations of cost delayed construction until 1920.
  ✓ SILENT: Feelings of awe are common among visitors.
  ✓ SILENT: Noticed only in 1965, the painting had been overlooked.
```

## Evidence: All acceptance criteria pass

### 1. Michael's Buddha paragraph: R1, R2, R4 all fire ✓

```
Rules violated: ['R1_IMPERATIVE', 'R2_QUESTION', 'R3_SUGGESTIVE_EXPLORATION', 'R4_PRESCRIBED_FEELING']

  [R4_PRESCRIBED_FEELING] "As you stand in the presence of the 'Statue de Bouddha', feel the weight of centuries pressing down upon you…"
  [R2_QUESTION] "How does this serenity manifest itself in the different representations…?"
  [R1_IMPERATIVE] "Explore further and uncover the interconnectedness…"
  [R3_SUGGESTIVE_EXPLORATION] "Explore further and uncover the interconnectedness…"
```

### 2. Navigation exemption: "Head south…" does NOT fire ✓

```
  Text: "Head south on Promenade de la Croisette"
  findings: 0   Does NOT fire: ✓

  Text: "Turn left at the fountain and look at the tower ahead."
  nav=True  errors=0   ✓
```

### 3. Declarative exemptions: zero errors ✓

```
  "What began as a fishing village became the busiest yacht harbour in Europe."
    Errors: 0 ✓   Warnings: 1 (R2_INTERROGATIVE_OPENER — non-blocking)

  "When the museum opened in 1963, Chagall attended in person."
    Errors: 0 ✓   Warnings: 1 (R2_INTERROGATIVE_OPENER — non-blocking)

  "Where the two rivers meet, the ramparts still stand."
    Errors: 0 ✓   Warnings: 1 (R2_INTERROGATIVE_OPENER — non-blocking)
```

### 4. R1 word-boundary regression: ALL PASS ✓

```
  "Observers considered the design scandalous in 1887."   R1 fires: 0 ✓
  "Discoveries were made beneath the chapel floor in 1932." R1 fires: 0 ✓
  "Explorers landed here in 1388 and named the cape."     R1 fires: 0 ✓
```

## Per-rule counts across baseline (9 tours)

| Tour | Paragraphs | Nav | Content | Failing | Rate | R1 | R2(err) | R3 | R4 |
|------|-----------|-----|---------|---------|------|----|---------|----|-----|
| 1 (Palais Lascaris) | 18 | 1 | 17 | 2 | 11.8% | 3 | 1 | 0 | 2 |
| 29 (Riviera Biking) | 32 | 1 | 31 | 8 | 25.8% | 6 | 0 | 2 | 3 |
| 12 (Walking Nice) | 61 | 1 | 60 | 12 | 20.0% | 4 | 0 | 4 | 6 |
| 24 (Chagall) | 30 | 0 | 30 | 2 | 6.7% | 1 | 1 | 0 | 1 |
| 14 (Naïve Art) | 48 | 3 | 45 | 7 | 15.6% | 1 | 2 | 1 | 3 |
| 46 (Boston Common) | 12 | 0 | 12 | 0 | 0.0% | 0 | 0 | 0 | 0 |
| 44 (MAMAC) | 17 | 0 | 17 | 8 | 47.1% | 2 | 2 | 2 | 2 |
| 152 (Riviera Cycling) | 32 | 1 | 31 | 9 | 29.0% | 6 | 0 | 4 | 2 |
| 156 (Riviera LOCAL-183) | 32 | 1 | 31 | 12 | 38.7% | 1 | 0 | 9 | 6 |
| **TOTAL** | **282** | **8** | **274** | **60** | **21.9%** | **24** | **6** | **22** | **25** |

## Did R1 counts change?

**No.** R1 grand total remains 24, identical to round 1. The prefix-matching
defect did not inflate counts *on this specific baseline corpus* because none
of these tours happen to have sentences starting with "Observers",
"Discoveries", "Explorers", etc. The bug was a *class* of false positive that
would have struck new tours featuring good declarative prose (dated, specific,
exactly what R1 exists to promote). The fix is preventive.

## Why no additional heuristic

LEAD suggested considering whether "a true imperative is followed by an
object or preposition, not by a finite verb" as a secondary condition. After
testing:

- "Observers **considered**…" — `\b` alone blocks it (word boundary after "observe" fails)
- "Discoveries **were**…" — same
- "Explorers **landed**…" — same
- "Considerations **of**…" — same (not in verb list, but demonstrates `\b` sufficiency)

No case was found where `\b` misses a false positive that a finite-verb check
would catch. Adding complexity speculatively would violate the principle of
minimal change.

## Output shape (unchanged from round 1)

```json
{
  "rule_id": "R1_IMPERATIVE",
  "severity": "error",
  "sentence": "Explore further and uncover the interconnectedness…",
  "suggestion": "Rewrite as declarative statement. Remove the imperative \"explore\" and state the fact directly."
}
```

## R5 note

R5 (every abstract claim must be grounded with because + specific POI
attribute) maps to the existing `stop_anchor_detector_v2.py`
(`ANCHORED` / `UNLINKED_ENTITY` classification). Not reimplemented here.

## Constraints verified

- ✓ Detector only — no generation changes, no rewriting
- ✓ No container rebuilds (D48)
- ✓ $0.00 spend — deterministic rules, no LLM calls
- ✓ `audio_tours` unchanged (read-only)
- ✓ `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `STATUS.md` unchanged
- ✓ `git status --short` clean after commit

## Limitations

1. **R1 verb list is finite** — new imperative patterns not in the list won't
   be caught. The list covers Michael's examples and common tour-writing patterns.
2. **R2 interrogative-opener warnings are noisy** — every "What/When/Where" sentence
   triggers a warning even when declarative. By design (spec says warning-only), but
   in production these should likely be filtered from human-facing reports.
3. **R3/R4 patterns are regex-based** — complex paraphrases that avoid exact phrases
   but convey the same meaning (e.g., "the atmosphere envelops the visitor") may
   escape detection. Acceptable for a $0.00 deterministic detector.
4. **Sentence splitting is heuristic** — abbreviations (Dr., St., etc.) can cause
   mis-splits. Not observed in the baseline corpus but possible in edge cases.
