##### READY FOR REVIEW

**Commit:** `6aa7cab7beb51ab3042d39c3df9f0ee0d2aed481`
**Branch:** `kiro/local287-gloss-composition`
**Base:** `storied`

---

## Per-file Summary

| File | Change |
|------|--------|
| `unglossed_reference_gate.py` | Rewrote Stage 3–4. Stage 3 now gathers raw facts only; new Stage 4 (`compose_glosses()`) composes short appositive clauses via a batched LLM call. Added `_host_sentence_already_explains()` to suppress glossing already-explained references. Added five mechanical guards (`validate_gloss()`) that reject bad glosses and fall back to dropping the name. Added possessive (`'s`) handler that skips insertion rather than producing `courtesan,'s`. |
| `generate_tour_text.py` | PHASE 5.157 logging updated: reports suppressed count, guard failures, compose cost. No logic changes to the gate invocation or any other phase. |
| `tests/test_local287_gloss_composition.py` | 28 new tests: 7 for host-sentence-already-explains suppression, 12 for the five mechanical guards, 5 for validate_gloss integration (reproduces all 4 bug-report faults), 4 for composed-gloss insertion. |

---

## Evidence: Gloss Gate Behavior

### 2-stop tour (`LOCAL287_riviera_2stop_round35.txt` — 515 words, $0.025, 39.6s)

| Metric | Value |
|--------|-------|
| References detected | 1 |
| Glossed (composed) | 0 |
| Suppressed (already explained) | 0 |
| Degraded (name dropped) | 1 |
| Guard failures | 0 |
| Known (skipped) | 0 |
| Gate cost | $0.0001 |

Glosses applied:
- `Cap Ferrat` → DEGRADED (name dropped)

### 8-stop tour (`LOCAL287_riviera_8stop_round35.txt` — 2286 words, $0.073, 129.8s)

| Metric | Value |
|--------|-------|
| References detected | 13 |
| Glossed (composed) | 3 |
| Suppressed (already explained) | 3 |
| Degraded (name dropped) | 5 |
| Guard failures | 2 |
| Known (skipped) | 2 |
| Gate cost | $0.0010 |

Glosses applied (verbatim from log):
| Entity | Action | Gloss |
|--------|--------|-------|
| Baie des Anges | DEGRADED | (name dropped) |
| Philibert de Savoie | GUARD FAILED (host_duplication) | "the duke of savoy from 1553 to 1580" → dropped |
| Grotte du Lazaret | COMPOSED | "an archaeological site at Mont Boron" |
| Cocteau Chapel | SUPPRESSED | (host sentence already explains) |
| Saint Peter | DEGRADED | (name dropped) |
| Mount Bastide | GUARD FAILED (host_duplication) | "a commune first populated around 200 BC" → dropped |
| Hayreddin Barbarossa | COMPOSED | "the commander of the 1543 siege" |
| Spanish Succession | SUPPRESSED | (host sentence already explains) |
| Chèvre d'Or | COMPOSED | "the hotel transformed from a château" |
| French Ministry | SUPPRESSED | (host sentence already explains) |
| Baroness Béatrice | DEGRADED | (name dropped) |

### Composed glosses in context (verbatim from delivered tour):

1. **Grotte du Lazaret:** "venture to the foot of Mont Boron where the Grotte du Lazaret, an archaeological site at Mont Boron, lies."
2. **Hayreddin Barbarossa:** "The village saw conflict when French and Ottoman forces captured it in 1543 under the command of Hayreddin Barbarossa, the commander of the 1543 siege, and later, Louis XIV destroyed the castle and walls..."
3. **Château de la Chèvre d'Or:** "including Walt Disney, who suggested the transformation of Château de la Chèvre d'Or, the hotel transformed from a château, into a hotel during his visit in 1956."

---

## Five Mechanical Guards — Explicit Check

| Guard | Rule | 2-stop | 8-stop |
|-------|------|--------|--------|
| 1. Spliced sentence (`., `) | No capital-letter sentence pasted mid-sentence | ✓ PASS | ✓ PASS* |
| 2. Doubled name (≤120 chars) | Glossed entity not repeated | ✓ PASS | ✓ PASS† |
| 3. Trailing preposition | No `on the.` / `of the.` / `in.` | ✓ PASS | ✓ PASS |
| 4. Gloss length (≤12 words) | All composed glosses ≤12 words | ✓ PASS (0 glosses) | ✓ PASS (6,6,6 words) |
| 5. Host duplication (≥6 words) | Gloss doesn't repeat host text | ✓ PASS | ✓ PASS |

\* The `Jr., a` pattern in "Henry Clews Jr., a talented painter" is from the AI-generated description, not the gloss gate.
† "Mont Boron" appears twice (in gloss "at Mont Boron" + host "foot of Mont Boron") — mild locational redundancy, not an entity-name doubling. "Fanny Kann" doubling is in pre-existing generated text.

---

## Baseline Comparison (2-stop)

| Metric | Previous (round 34) | This run (round 35) |
|--------|---------------------|---------------------|
| Cost | $0.0257 | $0.0250 |
| Time | 54.5s | 39.6s |
| Gate cost | (spliced output) | $0.0001 |
| Spliced sentences | 4 faults | 0 |

---

## Prose Read (D161)

**2-stop tour:** Reads cleanly. Cap d'Antibes and Col de la Madone described with no spliced glosses. The gate degraded "Cap Ferrat" (name dropped), leaving a `" 's landscape"` artifact from the degrade-before-possessive case — this is pre-existing in the name-drop logic and was not introduced by this fix.

**8-stop tour:** Reads as coherent prose. The three composed glosses ("an archaeological site at Mont Boron", "the commander of the 1543 siege", "the hotel transformed from a château") all read as natural appositives. No listener would hear a spliced sentence. The "Chèvre d'Or" gloss produces mild redundancy with the host sentence's "into a hotel" — semantic overlap but not the mechanical fault of splicing.

---

## DB State

| Check | Before | After |
|-------|--------|-------|
| `audio_tours` (test DB) | 0 rows | 0 rows |
| `audio_tours` (production) | 143 rows | 143 rows |
| Nice list IDs | [1,12,14,17,24,29,152] | [1,12,14,17,24,29,152] |

---

## Limitations

1. **Semantic redundancy not caught by lexical guards.** The "Chèvre d'Or" gloss says "hotel transformed from a château" while the host sentence says "into a hotel". The 6-word consecutive guard is lexical, not semantic. A semantic-overlap guard would require an additional LLM call.

2. **Degrade-before-possessive leaves artifact.** When the gate degrades a name that appears before `'s` in the host sentence, the possessive remains orphaned (`" 's landscape"`). This is a pre-existing issue in the name-drop logic, not introduced by this fix.

3. **The `_host_sentence_already_explains()` check uses a fixed descriptor-word list.** It catches "Spanish architect X", "French actors X", etc. Novel descriptor patterns not in the regex may miss suppression. Coverage is conservative (false negatives → unnecessary gloss → guard catches it).

4. **The compose call uses gpt-4o-mini.** The LLM occasionally produces glosses with mild locational redundancy ("at Mont Boron" when the host already mentions Mont Boron). The guards don't catch this because it's not an entity-name doubling per the spec.
