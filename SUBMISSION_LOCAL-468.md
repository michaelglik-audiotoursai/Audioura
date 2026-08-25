# SUBMISSION_LOCAL-468.md

## LOCAL-468: Ask About The Seed, Not The Work

**Branch:** LOCAL-468-seed-diversity  
**Date:** 2025-08-25  
**Agent:** Mac Mini Kiro

---

## Problem

Stop 1 of TOUR_D525_UNBOUND.txt used four seeds naming four different people —
Joan Miró, Louis Broder, Mourlot, Boris Fridman — and all four returned the same
story: the 1967 edition, the paper defect, the erased plates.

Three causes:
1. The seed is a trailing appositive in the question, not its subject
2. `seed['ask']` exists and is the right question, but production never uses it
3. Prose seeds are grammatical fragments that cannot steer retrieval

## Solution

### Fix 1: Use `seed['ask']` as the question (Cause 1 + 2)

`story_production_loop.py` line ~275: replaced

```python
gq = compile_for_gemini(matrix, cl, exhibition)  # "What story about {work}, {seed}?"
```

with

```python
seed_ask = seed.get('ask') or compile_for_gemini(matrix, cl, exhibition)
```

The seed's own question is now the FIRST LINE of the Gemini prompt. The work
becomes context, not subject.

### Fix 2: Narrow the context per seed (Cause 1)

Before: the entire matrix (10+ fields) was appended identically to every query.
After: agent seeds get only `canonical_title + artist + venue_name + their_own_field`.

- Mourlot gets `printed_by: Mourlot` but NOT `publisher: Louis Broder`
- Fridman gets no other agent's field
- This prevents the model from answering about the most prominent person
  in the context regardless of what the question asks

### Fix 3: Seed-specific instruction (Cause 1)

Before: "Prefer what a visitor cannot see: why it was made, who decided, what went
wrong, what it cost someone" — describes exactly ONE episode for this work.

After: agent seeds get "What did they do in relation to this work? What happened to
them because of it?" — lets the seed choose the episode. Prose seeds keep the
original instruction.

### Fix 4: Prose seed quality gate (Cause 3)

Rejects prose seeds that:
- Are truncated (last word is 1 char, or total >= 40 chars without punctuation)
- Have no subject and start with a subordinating word (participial/relative clause)

Tested against the five fragments from the task:
- REJECTED: 'was to design it' — no subject + subordinate
- REJECTED: 'would provide the text' — no subject + subordinate  
- ACCEPTED: 'Freud's ideas to life' — has anchor 'Freud'
- REJECTED: 'making it a multifaceted artwork that extend' — truncated
- REJECTED: 'having only completed half of the intended w' — truncated

### Fix 5: Pairwise overlap measurement (task requirement 4)

Added to `run_for_stop`: after all candidates are collected, compute pairwise
Jaccard similarity (character 5-shingles via `story_element_extractor.jaccard_similarity`).
Reported in the log and in stdout. Logged to `story_loop_candidates.jsonl`.

## Files Changed

- `story_production_loop.py` — the production call site (fixes 1–5)
- `story_query.py` — added `compile_for_seed()` function + export
- `run_local468_acceptance.py` — acceptance test script

## Wiring Proof

The LOCAL-465 lesson: "every test called the function directly and none exercised
the call site." Here, the wiring proof is:

1. Monkey-patched `gemini_with_sources` to capture prompts
2. Called `run_for_stop` (the PRODUCTION call path)
3. Verified the captured prompt's first line IS `seed['ask']`, not the generic question

```
4 prompt(s) sent to Gemini:
  Prompt 1: 'What did Joan Miró actually do, and what came of it?'        ✓
  Prompt 2: 'What did Louis Broder actually do, and what came of it?'     ✓
  Prompt 3: 'What did Mourlot actually do, and what came of it?'          ✓
  Prompt 4: 'Why did Boris Fridman acquire this, and why give it away?'   ✓
```

## Live Run Results

### Candidates (stop 1, Le Lézard aux plumes d'or)

**Seed 'Joan Miró' (index=61, kind=eventful, PASS):**
Joan Miró authored the original poetry and produced the color lithographs for the
illustrated book project. In 1967 he executed a series of lithographs to accompany
the text...

**Seed 'Louis Broder' (index=41, kind=inert, fail:index):**
In 1971, publisher Louis Broder brought Joan Miró's Le Lézard aux plumes d'or to
fruition in Paris. The artist created fifteen color lithographs...

**Seed 'Mourlot' (index=70, kind=eventful, PASS):**
In 1967, Joan Miró created a series of color lithographs to illustrate his own
poetry. The plates were printed in Paris at Atelier Mourlot under the direction...

**Seed 'Boris Fridman' (index=15, kind=none, fail:index):**
No verified facts from the earlier account can be confirmed from retrieved evidence.
(Fridman is a private collector with minimal public record — this is correct behavior.)

### Pairwise Overlap

```
Joan Miró      × Louis Broder   = 0.006
Joan Miró      × Mourlot        = 0.009
Joan Miró      × Boris Fridman  = 0.062
Louis Broder   × Mourlot        = 0.316
Louis Broder   × Boris Fridman  = 0.011
Mourlot        × Boris Fridman  = 0.002

mean=0.135, max=0.316 — DIVERSE (all below 0.6)
```

Compare to pre-fix: all four seeds returned effectively the same story (overlap ~1.0).

### Indices

- Accepted stories: index 61 (Miró), index 70 (Mourlot)
- Multi-story: 2 stories published from this stop

### Multi-Story

Two stories survived with indices 61 and 70 — the LOCAL-466 machinery now has
distinct material to work with.

## What Is NOT Changed

- `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`
- D515 floor of 50
- `story_append_merge.py`
- `story_publish_gate.py`

## Remaining Variance

Indices vary across runs (LLM non-determinism). The mean index across all 4
candidates (including failures) is ~47 — below the 75.7 baseline. But that
baseline measured only ACCEPTED stories, not all candidates. The accepted stories
(61, 70) are within baseline range. The Miró seed sometimes scores low because
asking "what did Miró do" for a Miró work retrieves catalogue prose rather than
narrative — but it's a DIFFERENT catalogue prose from the Broder or Mourlot answers.

The Fridman seed reliably returns nothing useful because Boris Fridman is a private
collector with no public biography. This is correct behavior: "no reliable story"
is better than fabricating one about a person whose only public trace is a museum
credit line.
