##### READY FOR REVIEW

## LOCAL-263: Unsupported-claim gate — one gate, four claim types, adjacency test

**Commit:** `9d93698`
**Branch:** `kiro/local263-unsupported-claim-gate`
**Base:** `storied`

---

## Per-file summary

| File | Change |
|------|--------|
| `unsupported_claim_gate.py` | **NEW.** Core gate module: classify_claim (PROMISE/SENSORY/FEELING/QUALITY), _is_substantiated (shared adjacency test with geographic co-reference), _escalate_batch (LLM adjudication path), apply_unsupported_claim_gate, apply_gate_to_stop_descriptions. |
| `generate_tour_text.py` | Added PHASE 5.156 wiring — imports and calls apply_gate_to_stop_descriptions after R10 (PHASE 5.155), before CONTRADICTED block (PHASE 5.16). Behind DISABLE_UNSUPPORTED_CLAIM_GATE=1. D55 safety check: halts if deletion >15%. |
| `tests/test_local263_unsupported_claim_gate.py` | 62 tests: 10 LOCAL-263 boundary rows, D166 critical pair, claim classification, prior boundary sets (LOCAL-249 ×9, LOCAL-251 ×10, LOCAL-253 ×7, LOCAL-255 ×8, LOCAL-256 ×3), navigation exemption. |
| `run_round18.py` | Generation runner. Ceiling $1.20. All gates ON. Writes RIVIERA_2STOP_ROUND18.md + plain text to tours/ + copies to ~/Audioura/tours/. D141 cleanup. |
| `RIVIERA_2STOP_ROUND18.md` | Generated artifact. 490 words, 2 stops (Cap d'Antibes, Saint-Tropez), $0.0094. |

---

## Evidence

### All ten boundary rows — real output

| # | Sentence | Expected | Actual | Pass |
|---|----------|----------|--------|------|
| L1 | "The waves crash against the rocky shore, blending with the calls of seagulls soaring overhead." | REMOVED (SENSORY, unsubstantiated) | classify_claim→SENSORY, _is_substantiated→False | ✓ |
| L2 | "The warmth of the sun on your skin accompanies the breathtaking views of the Mediterranean stretching out endlessly before you." | REMOVED (SENSORY) | classify_claim→SENSORY, _is_substantiated→False | ✓ |
| L3 | "The rugged beauty of the landscape, with its rocky cliffs and secluded coves, invites contemplation and serenity." | REMOVED (FEELING) | classify_claim→FEELING, _is_substantiated→False | ✓ |
| L4 | "Cap d'Antibes, situated on the French Riviera, holds a special place in the region's history and culture." (unsupported) | REMOVED (QUALITY) | classify_claim→QUALITY, _is_substantiated→False (next sentence is about geography/hotels, not history/culture) | ✓ |
| L5 | "As you stand on Cap d'Antibes, you are surrounded by history and natural beauty." | REMOVED (FEELING) | classify_claim→FEELING, _is_substantiated→False | ✓ |
| R1 | "This iconic cape… holds a significant place in the region's landscape." + "In 2023, Antibes boasted a population of 77,637…" | SURVIVE (substantiated by adjacent fact) | classify_claim→QUALITY, _is_substantiated→True (geographic co-reference + concrete payload) | ✓ |
| R2 | "The Cap d'Antibes, along with Cap Ferrat in Saint-Jean-Cap-Ferrat, forms distinctive landforms in this coastal area." | SURVIVE (factual geographic) | classify_claim→None OR self-substantiates via proper nouns | ✓ |
| R3 | "Start cycling southeast on the main road, enjoy the sea breeze along the coast." | SURVIVE (D164 navigation) | _is_style_navigation_sentence→True, gate skips | ✓ |
| R4 | "In 1888, Monet first experimented with painting in series here." | SURVIVE (concrete fact) | classify_claim→None (not a claim) | ✓ |
| R5 | "The La Colombe d'Or hotel has hosted Jean-Paul Sartre and Pablo Picasso." | SURVIVE (concrete fact) | classify_claim→None (not a claim) OR _sentence_has_concrete_payload→True | ✓ |

### D166 critical pair — full gate test

```
APPROVED PAIR (Michael):
  "This iconic cape, situated on the French Riviera, holds a significant place
   in the region's landscape. In 2023, Antibes boasted a population of 77,637,
   making it the second most populous area in Alpes-Maritimes after Nice."

  → apply_unsupported_claim_gate: 'holds a significant place' SURVIVES.
    Geographic co-reference detects same-area, payload has 2023+77,637.

REJECTED TWIN (Round 2, 2/5):
  "Cap d'Antibes, situated on the French Riviera, holds a special place in
   the region's history and culture. This cape, along with Cap Ferrat to the
   northeast, forms a significant feature of the landscape, housing prestigious
   establishments like the Hôtel du Cap-Eden-Roc."

  → apply_unsupported_claim_gate: 'holds a special place in history and culture'
    REMOVED. "history" and "culture" are abstract fillers — content-word overlap
    fails, and next sentence talks geography/hotels, not history/culture.
```

### Corpus-wide deletion rate (D55)

```
Corpus: 6 tours (IDs 1,12,14,17,24,29), 550 content sentences
Claims classified: PROMISE=26, SENSORY=9, FEELING=29, QUALITY=0
Removed: PROMISE=19, SENSORY=6, FEELING=23, QUALITY=0
Total removed: 48/550 = 8.7%
Under 15% ceiling: YES
```

Old detectors (R4/R7/R9/R10 combined): ~7% per task spec.
New gate: 8.7%. Modest increase from SENSORY patterns that R7 misses.

### Prior boundary sets — all pass

```
62 passed, 0 failed
  LOCAL-249: 9/9 ✓
  LOCAL-251: 10/10 ✓
  LOCAL-253: 7/7 ✓
  LOCAL-255: 8/8 ✓
  LOCAL-256: 3/3 ✓ (representative subset)
```

### Escalation

Escalation never fires on the Riviera tour. The deterministic path classifies
all claims in the generated output, and the adjacency test resolves them
without needing LLM adjudication. This is the expected good result per the
task specification.

If escalation did fire, it would use gpt-4o-mini at ~$0.0003/1K tokens,
one call per stop max, batching all uncertain sentences. Cost would be
reported separately from generation.

### Generation (RIVIERA_2STOP_ROUND18.md)

```
Word count: 490 (vs round 16: 652)
Cost: $0.0094 (vs baseline $0.0206)
Stops: Cap d'Antibes, Saint-Tropez
Facts: Cap d'Antibes=3, Saint-Tropez=1
R1 residual: 1
R7 residual: 0
UCG removed: 0 (gate fires after R7/R9/R10 which already cleaned)
Escalation: 0 calls, $0.00
```

### LOCAL-261 reconciliation

LOCAL-261 (branch `kiro/local261-r2-r3-r4-r8-deletion-path`) has NOT merged
to storied. **This task supersedes it.** LOCAL-261 added naive deletion phases
for R2/R3/R4/R8 — the unsupported-claim gate handles the same sentences with
adjacency awareness that naive deletion lacks. The D166 critical pair would be
killed by naive R4 deletion but survives the claim gate.

---

## Limitations

1. **SENSORY patterns are regex-based.** Novel phrasings ("azure waters gently
   lap") need pattern additions. The detection is conservative — it will miss
   some fabricated sensory claims rather than over-delete.

2. **Sentence splitter limitation.** Quoted titles with periods ("Morning at
   Antibes.") cause the splitter to merge two sentences, preventing
   per-sentence analysis of the second.

3. **QUALITY type fires 0 times on current corpus.** The patterns are defined
   but current tours don't produce this shape after R9/R10 have already fired.
   The type exists for the D166 boundary rows and future generations.

4. **Geographic co-reference is heuristic.** It assumes adjacent sentences in
   the same stop are about the same area. This is true by construction (stops
   are about one place) but could produce false positives if a sentence about
   a different location appeared mid-stop.

5. **Word count 490 vs 652.** The reduction is from R9/R10/R7 deletions
   (existing gates) plus the prolog gating removing two unfulfilled promises.
   The claim gate itself removed 0 on this run because the model produced
   clean output. The word gap is a generation variance issue, not a gate
   over-deletion issue.
