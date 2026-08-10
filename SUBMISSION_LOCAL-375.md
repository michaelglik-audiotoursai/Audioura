# SUBMISSION_LOCAL-375.md

## Task

Classify the residual `empty_sentence_count` hits before anyone gates on them.

## What was done

1. **Generated 5 live tours** (`DISABLE_TOUR_CACHE=1`, `DATABASE_URL` set) covering:
   - Palais Lascaris, Nice, France (museum, 4 stops) — 12 flagged
   - Museum of Fine Arts, Boston, MA (museum, 8 stops) — 19 flagged
   - French Riviera, France (biking, 2 stops) — 2 flagged
   - Musee Matisse, Nice, France (museum, 4 stops) — 9 flagged
   - Boston Common, Boston, MA (walking, 3 stops) — 7 flagged

2. **Classified all 49 flagged sentences** into:
   - Class 1 (genuinely empty): 30 (61.2%)
   - Class 2 (broken grammar): 3 (6.1%)
   - Class 3 (false positive): 11 (22.4%)
   - Class 4 (ambiguous): 5 (10.2%)

3. **Added `get_flagged_empty_sentences` helper** to `tour_rubric_scorer.py` — the
   canonical entry point for extracting flagged sentences from a stop body.

4. **Added test** `tests/test_local375_get_flagged_empty_sentences.py` — 5 tests
   that go red when the helper is reverted (ImportError blocks collection).

## Deliverable

- `EMPTY_SENTENCE_CLASSIFICATION.md` — full table of all 49 sentences, verbatim,
  with tour, stop, and classification. Includes counts per class per tour type,
  recommendation with threshold, and proposed heuristic narrowing for class-3.

## Recommendation (from the document)

Class 3 (false positives) is 22.4% — not dominant, but non-trivial. The false
positives share a single pattern: **visual descriptions of artwork** (technique,
composition, depicted content) that lack mid-sentence proper nouns or dates.

**Safe threshold: >5 per stop** (catches catastrophic stops; passes all
false-positive-heavy stops in sample).

**Better path:** implement visual-description vocabulary exemption first (reduces
FP from 22.4% to ~4%), then enforce at >3 per stop.

## What was NOT done

- The metric was not promoted to enforcing.
- No scoring, prompts, or generation logic was changed.
- The heuristic was not tuned.
- No entries deleted from audio_tours.

## Tests

```
GREEN (5 passed):
$ python3 -m pytest tests/test_local375_get_flagged_empty_sentences.py -v
tests/...::test_known_empty_all_flagged PASSED
tests/...::test_known_factual_none_flagged PASSED
tests/...::test_mixed_only_empty_flagged PASSED
tests/...::test_short_fragments_excluded PASSED
tests/...::test_empty_body_returns_empty_list PASSED

RED (helper reverted → ImportError, 5 tests fail to collect):
ERROR tests/test_local375_get_flagged_empty_sentences.py
ImportError: cannot import name 'get_flagged_empty_sentences'
Exit code: 2
```

Expected red count: **5** (all tests fail at collection due to ImportError).

## Files changed

- `tour_rubric_scorer.py` — added `get_flagged_empty_sentences()` helper
- `tests/test_local375_get_flagged_empty_sentences.py` — new test file
- `run_local375_classify_empty_sentences.py` — generation script (main)
- `run_local375_supplement.py` — generation script (supplement)
- `EMPTY_SENTENCE_CLASSIFICATION.md` — deliverable
- `SUBMISSION_LOCAL-375.md` — this file

## Reproduction

```
code_sha: 81170f9
Branch: kiro/local375-empty-sentence-classification (off storied)
```
