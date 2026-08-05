##### READY FOR REVIEW

## LOCAL-220: Sentence Group Scoring Pipeline

**Commit:** `a1af961`
**Branch:** `kiro/local220-sentence-scoring-pipeline`
**Base:** `storied`

---

### Summary

Implements sentence-group-level scoring as specified by Michael's Riviera
evaluation. Splits paragraphs into sentence groups (1–3 sentences on one idea),
classifies each group (NAVIGATION / CONTENT / CONNECTIVE), and emits per-group
records with style verdicts, claim verdicts, and a separate PUBLISHABLE / BLOCKED
flag.

**Does not** compute a combined quality score, wire into generation, rewrite
anything, or rebuild containers.

---

### Files

| File | Action | Purpose |
|------|--------|---------|
| `sentence_group_scorer.py` | NEW | Core pipeline: split → classify → score per group |
| `run_local220_sentence_scoring.py` | NEW | Calibration script: runs against Michael's 11 groups |
| `sentence_group_records_local220.json` | NEW | JSON output: per-group records for all 6 paragraphs |

**No existing files modified.** `claim_check.py`, `corpus_coverage.py`,
`style_validator_detector.py`, `DECISIONS.md`, `CLAUDE.md`, `.continuous_dev/*`
all untouched.

---

### Acceptance Criteria Evidence

#### 1. Grouping, classification, and per-group records for all six paragraphs

All 11 of Michael's groups have records in `sentence_group_records_local220.json`
with classification, style verdicts, claim verdicts, and publishable flag beside
his scores. See Part 2 output above.

#### 2. Group-boundary agreement rate: 54.5% (6/11)

```
GROUP BOUNDARY AGREEMENT: 6/11 = 54.5%
Michael's groups: 11, Our groups: 16
```

**Where we agree (6):** ¶1A, ¶4A, ¶4B, ¶5A, ¶5C, ¶6.
**Where we disagree (5):** ¶1B (we split at "Enjoy" creating 3 groups vs his 2),
¶2 (we split "Join us" off from the prolog), ¶3A (we split the 6-sentence group
at the topic shift between Monet and the Tire-Poil trail), ¶3B (we isolate
"As you stand..." from the Olivette+Pedal pair), ¶5B (we isolate "Walking
through..." from the Rue Obscure pair).

**Interpretation:** The algorithm over-splits — it produces 16 groups where
Michael drew 11. His larger groups span topic shifts that our heuristic treats
as boundaries. The 3-sentence cap forces splits on his 4- and 6-sentence groups.
This is a learnable boundary but requires either a larger calibration set or
Michael's direct input on whether sub-topic shifts should start new groups.

#### 3. Both known disagreements present and visibly two-axis

```
1. '320 feet' — quality 5/5 but BLOCKED (unsupported): ✓ PRESENT
2. Cycling directions — NAVIGATION, clean, publishable: ✓ PRESENT
```

**¶5A (320 feet):** Michael 5/5. Style: clean. Claims: `UNSUPPORTED` (320 feet,
"Free City on Sea"). Publishable: **False** (UNSUPPORTED_CLAIM). Two axes
visible: excellent quality AND blocked.

**¶1A (cycling):** Michael 5/5. Classification: NAVIGATION. Style: clean (exempt).
Claims: none. Publishable: **True**. Pure imperatives, no proper noun, no date —
correctly classified and not penalized.

#### 4. JSON record schema documented

```json
{
  "schema_version": "1.0",
  "task": "LOCAL-220",
  "group_boundary_agreement": "6/11 = 54.5%",
  "known_disagreements": {
    "320_feet_quality_vs_publishability": true,
    "cycling_navigation_clean": true
  },
  "records": [
    {
      "paragraph": 1,
      "group_label": "A",
      "michael_score": 5,
      "michael_reason": "...",
      "classification": "NAVIGATION | CONTENT | CONNECTIVE",
      "sentences": ["..."],
      "style_rules_violated": ["R1_IMPERATIVE", ...],
      "claim_verdict_counts": {
        "supported": 0,
        "supported_elsewhere": 0,
        "unsupported": 0,
        "contradicted": 0,
        "not_checkable": 0
      },
      "claims": [{"text": "...", "verdict": "...", "type": "..."}],
      "publishable": true,
      "block_reasons": []
    }
  ]
}
```

Nothing wired into generation.

#### 5. Existing validator regressions all pass

```
R9 vs Michael's 0/5 boundary:
  ✓ R9 agrees with Michael's 0/5 boundary on all 11 groups

Navigation group classification (LOCAL-220 classifier):
  ✓ Classified NAVIGATION: "Start biking southeast..."
  ✓ Classified NAVIGATION: "Take the second exit..."

validate_paragraph on ¶5A (Michael 5/5, should be style-clean):
  ✓ Clean (no style rules violated)
```

R9 corpus-wide regression (existing test):
```
✓ R9 agrees with Michael's boundary, deletion rate 1.3%
```

#### 6. `audio_tours` at 130, Nice list unchanged

```
audio_tours count: 130
✓ audio_tours at 130
Nice list: [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
✓ Nice list intact
```

#### 7. `git status --short` clean

```
$ git status --short
(empty — clean working tree)
```

---

### Limitations

1. **Group boundary agreement is 54.5%.** The algorithm over-splits because of the
   3-sentence cap and topic-shift heuristics. Michael's groups of 4 and 6 sentences
   span what the heuristic sees as sub-topic boundaries. Improving this requires
   either relaxing the cap (which changes semantics for the scoring pass) or a
   larger calibration set from Michael.

2. **Villefranche has no corpus.** All claims there are marked UNSUPPORTED by
   default. This is correct (D94: we can't verify them) but it means ¶5A is
   blocked for being unverifiable, not for being wrong. The two-axis shape makes
   this visible: quality is high, publishability requires sourcing.

3. **¶3B ("take in the sight... Pedal...") shows style: clean.** Michael scored
   it 2/5 for "too many imperatives without substance." "Take in" and "Pedal" are
   imperatives, but the style validator's R1 doesn't fire because "take in the
   sight" is a phrasal construction, and "Pedal along the coastline" is recognized
   as route-movement. This is a gap in the style validator's patterns, not in this
   pipeline. The task says not to modify the validator unless a rule is missing —
   the rule (R1) exists, its patterns need extension.

4. **¶4A ("pause to take in the breathtaking view") shows style: clean.** Michael
   scored it 1/5 for the instruction. R1 doesn't fire because "As you arrive" is
   not a sentence-initial imperative. The violation is in R3 (suggestive
   exploration) territory, but "arrive" doesn't match R3's movement-verb list.
   Again a pattern gap in the existing validator.

5. **No i-con score emitted.** Per task specification: Michael has not settled the
   thresholds. The pipeline emits inputs to a score (style verdicts, claim verdicts,
   publishable flag) but not a combined number.

---

### Cost

$0.00 — deterministic, no LLM calls, read-only database access.
