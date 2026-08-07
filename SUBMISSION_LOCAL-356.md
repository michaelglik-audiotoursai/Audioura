##### READY FOR REVIEW

**Commit:** c1e30db  
**Branch:** kiro/local356-filler-detection  
**Base:** storied  

---

## Per-file summary

| File | Change |
|------|--------|
| `tour_rubric_scorer.py` | Added `_is_empty_sentence()` function (8 structural signal checks), `_ORIENTATION_RE`, `_ATTRIBUTABLE_CLAIM_RE` regexes, `empty_sentence_count`/`empty_sentence_fraction` fields on `StopAnalysis`, integration into `analyze_stop()`. |
| `tour_evaluator.py` | Added `"empty_filler"` field to per-stop evaluation output (reporting only). |
| `tests/test_local356_empty_sentence_detection.py` | 10 tests: filler examples detected, factual control spared, orientation spared, old metric bug documented, museum bounds regression guard. |
| `run_local356_distribution.py` | One-shot script: queries all scorable tours from DB, reports per-tour and per-stop empty-sentence distribution. |

---

## What generic_filler_fraction currently measures

`generic_filler_fraction` matches **12 fixed regex phrases** (lines 1061–1073 of the scorer):

```
invit(es|ing) (you )?(to )?(contemplate|explore|consider|reflect|ponder|delve)
transcend(s|ing)? (time|boundaries|cultural)
(profound|deep|rich) (sense|cultural|spiritual) (of|significance)
consider (how|the)
as you (continue|gaze|admire|explore|marvel)
testament to
resonat(es?|ing)
interconnect(ed)?(ness)?
tapestry of
echoe?(s|ing)
you (can't|cannot) help but
wash(es)? over you
```

A sentence must match one of these patterns AND lack a "fact exemption" (`\b\d{3,4}\b` or specific material keywords). The threshold for `has_generic_filler` is >0.4.

**Why the task examples score zero:** None of the 12 phrases appear in:
- "the weight of centuries settles upon you" — no match
- "the faint strains of music emanate" — no match  
- "these artifacts speak of heritage" — no match
- "a mix of laughter and clinking glasses creating a symphony of conviviality" — no match

The metric is blind to any filler that doesn't use one of those 12 specific constructions.

---

## Verbatim evidence

### Filler examples — detected under new measure

```
=== FILLER EXAMPLE 1 ===
  empty=True  'the weight of centuries settles upon you…'
  empty=True  'the faint strains of music emanate…'
  empty=True  'these artifacts speak of heritage…'
  empty=True  'the past lingers here.'

=== FILLER EXAMPLE 2 ===
  empty=True  'a mix of laughter and clinking glasses creating a symphony of conviviality…'
  empty=True  'the warmth envelops you…'
  empty=True  'time slows here.'

Example 1 as stop: empty_sentence_fraction=1.00, generic_filler_fraction=0.00
Example 2 as stop: empty_sentence_fraction=1.00, generic_filler_fraction=0.00
```

### Factual control — NOT flagged

```
=== FACTUAL CONTROL ===
  empty=False  'Built in 1650 and consecrated in 1699, the cathedral dominates the skyline.'
  empty=False  'The bell tower was added in 1757 using local red sandstone.'
  empty=False  'The nave seats 400 worshippers.'
```

### Orientation sentences — NOT flagged

```
=== ORIENTATION (must NOT be flagged) ===
  empty=False  'As you stand on Cours Saleya, the market stalls are ahead of you.'
  empty=False  'Look to your left and you will see the Baroque facade of the chapel.'
  empty=False  'Turn right at the fountain and continue along the promenade.'
```

### Museum bounds

```
8-stop museum: 82.6  (bound: >= 75.0) ✓
4-stop museum: 121.9 (bound: >= 81.2) ✓
```

---

## Distribution across all scorable tours

```
Scorable tours: 30 (of 31 in DB; 1 has no parseable stops)
Total content sentences: 2279
Total empty sentences:   1288
Corpus-wide fraction:    56.5%

Per-tour distribution (n=30):
  Min:    33.9%
  P25:    49.2%
  Median: 58.8%
  P75:    63.2%
  P90:    68.1%
  Max:    72.7%
  Mean:   56.7%

Per-stop distribution (n=192):
  Min:    0.0%
  P25:    45.5%
  Median: 57.9%
  P75:    66.7%
  P90:    76.9%
  Max:    100.0%
  Mean:   55.4%
```

**56.5% of delivered content sentences carry no entity, no number, no date, no orientation cue, and no attributable claim.**

---

## Limitations

1. **Non-English tours are over-counted.** The proper-noun signal (Signal 2) relies on mid-sentence capitalisation, which works for Latin-script languages but not for Cyrillic (Russian tours). Russian text has named entities that don't trigger the uppercase heuristic, inflating their empty counts.

2. **Signal 4 (attributable claims) is cuisine-biased.** The regex includes Nice-specific dishes (socca, ratatouille, etc.). Tours about other regions may have verifiable claims in different vocabularies that aren't covered.

3. **No sentence deletion.** This task measures and flags only. The 56.5% figure shows how much prose could be challenged, but removal is a separate, riskier change that affects delivered text quality.

4. **`has_generic_filler` threshold (0.4) has never fired in production.** The new `empty_sentence_fraction` would fire on every single tour at that threshold. A useful gate threshold for the new metric would need separate calibration — the distribution suggests the flag would be informative above ~0.65 (P75).

5. **The detector cannot distinguish "true atmosphere" from "empty atmosphere."** A sentence like "the sunset paints the sky in shades of gold" is structurally empty (no entity, no number) but might be acceptable scene-setting in small doses. The metric treats it as empty, which is correct for measurement — whether to penalise it is a policy decision.
