# SUBMISSION_LOCAL-463.md — Validate_Story

## Summary

`validate_story.py` — a deterministic, offline routine that validates every claim
in a story is traceable to its source corpus. No LLM, no API key, no network.

## The Gap This Closes

The existing gates see **ungrounded entities** (names and dates absent from the corpus).
They do NOT see **ungrounded relations** — grounded entities joined by a causal link no
source states. "Dalí met Freud" is grounded. "This meeting… culminated in the creation
of Moses and Monotheism" is not — the corpus never says the meeting caused the book.

## Design

```python
def validate_story(story: str, corpus: str, matrix: Dict = None) -> Dict
```

Per sentence, returns one of:
- `GROUNDED` — every entity and every asserted relation is supported
- `UNSUPPORTED_ENTITY` — a name/date/place/organization is absent from the corpus
- `UNSUPPORTED_RELATION` — entities present but the causal link between them is not

Story verdict: `TRUE_TO_SOURCES` only when every sentence is GROUNDED; otherwise `REJECTED`.

### Two-phase check per sentence

1. **Entity check** — reuses the logic from `story_writer.validate` (proper noun names,
   years) and adds organization detection (`The Hogarth Press`, `Torf Gallery`).

2. **Relation check** — detects causal/consequential connectives (`culminating in`,
   `leading to`, `would channel`, `leaving a lasting`, `resulting in`, etc.), then
   requires the corpus to contain the same causal assertion — not merely both endpoints.

### Relation verification strategy

When a causal connective is detected:
1. **Verbatim check first**: does the corpus contain the connective + its context?
   (handles the case where corpus literally states the same causal phrase)
2. **Structural check**: extract antecedent/consequent keys, find corpus windows with
   both, and require the window to contain causal/consequential language linking them.

This ensures:
- If the corpus says "culminating in the creation of Moses and Monotheism" and the story
  says the same → GROUNDED (verbatim match)
- If the corpus only says "Dalí illustrated Moses and Monotheism" but the story says
  "the meeting culminated in the creation" → UNSUPPORTED_RELATION (corpus doesn't state causation)
- Plain "and" conjunction between two supported facts → GROUNDED (not causal)

## Reuse

- `story_opportunity_scan._fold` — accent-folded lowercase (D243)
- `story_opportunity_scan.split_sentences` — sentence splitter
- `story_material_check._PERSON_WITH_INITIAL` — proper noun detection
- `story_material_check._NOT_A_PERSON` — organization name filter
- `story_material_check.passages_about` — corpus lookup
- `story_material_check._corpus_units` — corpus sentence splitting

## Acceptance Results

### Test 1: D434 stop-2 story against stop2_survivors.txt
```
STORY VERDICT: REJECTED

  [✓] Sentence 1: GROUNDED
      "In July of 1938, a 34-year-old Salvador Dalí…marking their first and only encounter."

  [✗] Sentence 2: UNSUPPORTED_RELATION
      "This meeting was as surreal as Dalí's art, leaving a lasting impression on both…"
      → corpus contains both endpoints but not the asserted link "leaving a lasting"

  [✗] Sentence 3: UNSUPPORTED_RELATION
      "Years later, Dalí would channel his fascination with Freud into his work, culminating in…"
      → corpus contains both endpoints but not the asserted link "would channel"

  [✓] Sentence 4: GROUNDED
      "The piece was printed by Arts Litho, Torrents, Wolfensberger…"
```

### Test 2: Original stop-2 prose (Hogarth Press)
```
STORY VERDICT: REJECTED

  [✗] S2: UNSUPPORTED_ENTITY
      "Commissioned by The Hogarth Press…"
      → organization: The Hogarth Press — not in source material
```

### Test 3: Control — corpus states the causal link
```
STORY VERDICT: TRUE_TO_SOURCES
  [✓] All 4 sentences GROUNDED
```
Proves the check can pass, not only fail.

### Test 4: Plain conjunction — no false positive
```
STORY VERDICT: TRUE_TO_SOURCES
  [✓] "Dalí met Freud in London and the pair never met again." → GROUNDED
```

### Neutralization proof (D418/D421 pattern)

Neutralized `validate_story` to return all-GROUNDED:
```
NEUTRALIZED RESULTS: 2 passed, 2 failed
  Test 1: FAIL — Expected REJECTED, got TRUE_TO_SOURCES
  Test 2: FAIL — Expected REJECTED, got TRUE_TO_SOURCES
  Test 3: PASS (expects TRUE_TO_SOURCES)
  Test 4: PASS (expects TRUE_TO_SOURCES)
```

Restored: 4 passed, 0 failed.

## Files Created

- `validate_story.py` — the routine (repo root)
- `test_validate_story.py` — test suite (repo root)
- `SUBMISSION_LOCAL-463.md` — this document
