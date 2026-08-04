##### READY FOR REVIEW

# SUBMISSION_LOCAL-184.md — Style Validator Detector

**Task:** LOCAL-184 — Detect instructions, questions and prescribed feelings in tour text
**Branch:** `kiro/local184-style-validator`
**Base:** `storied`

---

## Summary

Implements the **form** half of Michael's validator (ClickUp `wdvrdaxaqj`):
R1–R4 detect stylistic faults in tour narration text. The **substance** half
(R5 — every abstract claim must be grounded) already exists as
`stop_anchor_detector_v2.py` (ANCHORED / UNLINKED_ENTITY classification).

**No generation changes. No rewriting. No container rebuilds (D48). $0.00 spend.**

---

## Files Changed

| File | Action | Purpose |
|------|--------|---------|
| `tests/style_validator_detector.py` | **Added** | R1–R4 detector + report runner |
| `SUBMISSION_LOCAL-184.md` | **Added** | This submission document |

No other files touched. `audio_tours` database unchanged (read-only).

---

## Rules Implemented

| Rule | What it detects | Severity |
|------|----------------|----------|
| R1 | Sentence-initial imperatives aimed at the listener (Feel…, Explore…, Discover…, Imagine…, etc.) | error |
| R2 | Questions — `?` present | error |
| R2 | Interrogative opener without `?` (How/What/Why…) | warning |
| R3 | Suggestive exploration language (as you explore, you will…; explore further…; you can uncover…) | error |
| R4 | Prescribed feeling (you feel, pressing down upon you, immerse yourself, etc.) | error |

---

## Acceptance Criteria — Evidence

### 1. Michael's Buddha paragraph: R1, R2, R4 all fire ✓

```
Text: "As you stand in the presence of the 'Statue de Bouddha', feel the weight
of centuries pressing down upon you… How does this serenity manifest itself in the
different representations of divinity and wisdom throughout the museum's diverse
exhibits? Explore further and uncover the interconnectedness of human spirituality
across time and space."

Rules violated: ['R1_IMPERATIVE', 'R2_QUESTION', 'R3_SUGGESTIVE_EXPLORATION', 'R4_PRESCRIBED_FEELING']

  [R4_PRESCRIBED_FEELING] "…feel the weight of centuries pressing down upon you…"
  [R2_QUESTION] "How does this serenity manifest itself…?"
  [R1_IMPERATIVE] "Explore further and uncover…"
  [R3_SUGGESTIVE_EXPLORATION] "Explore further and uncover…" (same sentence, both rules fire)
```

### 2. "Head south on Promenade de la Croisette" does NOT fire ✓

```
  Text: "Head south on Promenade de la Croisette"
  findings: 0
  Does NOT fire: ✓
```

Navigation sentence exemption catches this at the sentence level.

### 3. Declarative examples do NOT fire R2 as errors ✓

```
  "What began as a fishing village became the busiest yacht harbour in Europe."
  Errors: 0 ✓ (zero errors)  Warnings: 1 (interrogative opener — non-blocking)

  "When the museum opened in 1963, Chagall attended in person."
  Errors: 0 ✓ (zero errors)  Warnings: 1 (interrogative opener — non-blocking)

  "Where the two rivers meet, the ramparts still stand."
  Errors: 0 ✓ (zero errors)  Warnings: 1 (interrogative opener — non-blocking)
```

### 4. Per-rule counts across baseline + tours 152, 156

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

**A high failure rate is a finding, not a reason to soften the rules.**

Boston Common (tour 46) is 100% clean — it was written differently.
MAMAC (tour 44) is worst at 47.1% — heavy use of "explore" and "immerse yourself".
Tour 156 (LOCAL-183 test regeneration) is 38.7% — R3 dominates (9 sentences).

### 5. Output shape

Each finding returns:
```json
{
  "rule_id": "R1_IMPERATIVE",
  "severity": "error",
  "sentence": "Explore further and uncover the interconnectedness…",
  "suggestion": "Rewrite as declarative statement. Remove the imperative \"explore\" and state the fact directly."
}
```

### 6. Read-only verification

```
git status --short: only ?? tests/style_validator_detector.py
audio_tours row count: 112 (unchanged)
No INSERT, UPDATE, or DELETE executed
```

---

## Design Decisions

1. **Reuses `is_navigation_paragraph` from `stop_anchor_detector_v2.py`** — imported, not duplicated. Also adds sentence-level nav detection for mixed paragraphs (e.g., "Head south on Promenade de la Croisette" alone is too short for the paragraph-level detector but is correctly exempted at sentence level).

2. **R1 requires imperative form** — "Visitors notice the asymmetry" does NOT fire; only sentence-initial verbs without a subject fire. This is the spec requirement that prevents false positives on third-person usage.

3. **R2 has two severity levels** — `?` is always an error. Interrogative openers without `?` are warnings only, because many are legitimate declaratives ("What began as a fishing village…").

4. **R5 is explicitly NOT reimplemented** — it maps to the existing anchor detector. Noted in the code docstring and report output.

5. **No rewriting** — this is a detector only. The rules have safe mechanical fixes but mixing detection and rewriting invites fabrication (D50 forbids this).

---

## Limitations

1. **Sentence splitting is regex-based** — abbreviations like "St." or "Dr." could cause mis-splits. In practice this hasn't produced false positives in the test set.

2. **R2 warning (interrogative opener) fires on ALL declaratives starting with How/What/Why/etc.** — This is by design (the spec calls it a "weaker warning"), but it means every such sentence produces a low-severity flag. A human reviewing warnings would need to filter these.

3. **R1 verb list is finite** — new imperative patterns not in the list won't be caught. The list covers Michael's examples and common tour-writing patterns.

4. **Navigation exemption depends on `is_navigation_paragraph`** — which uses a 150-char threshold. A very long navigation paragraph without 2+ pattern matches could fail to be exempted. Sentence-level nav detection mitigates this for mixed paragraphs.

5. **No false positive found in Boston Common** — this suggests the rules are well-calibrated but the test surface is limited to 9 tours.

---

## Commit

See `git log --oneline storied..HEAD` for the commit hash.
