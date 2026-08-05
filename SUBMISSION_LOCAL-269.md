##### READY FOR REVIEW

## SUBMISSION_LOCAL-269.md

**Commit:** `b85d753` on `kiro/local269-unexplained-reference-gate`
**Date:** 2026-08-05

---

## Summary

Implements the unglossed-reference gate — the inverse of LOCAL-263's
unsupported-claim gate. LOCAL-263 catches claims with no fact behind them.
This gate catches facts that assume knowledge the listener lacks.

Michael's example: "the first town liberated during Operation Dragoon" — a
substantiated fact that passes every existing gate, but leaves the listener
wondering what Operation Dragoon is.

## Files Changed

| File | Purpose |
|---|---|
| `unglossed_reference_gate.py` | Four-stage gate (detect → triage → gloss → apply) |
| `tests/test_local269_unglossed_reference_gate.py` | 28 tests covering all 8 boundary rows + prior sets |
| `generate_tour_text.py` | Integration as PHASE 5.157 (after unsupported-claim gate) |
| `run_round22.py` | Round 22 generation script |
| `RIVIERA_2STOP_ROUND22.md` | Round 22 output artifact |

## The Eight Boundary Rows — Real Output

### Must be FLAGGED (unglossed, audience doesn't know)

| # | Sentence | Detected? | Entity | Stage |
|---|---|---|---|---|
| 1 | "…the first town liberated during Operation Dragoon." | ✅ FLAGGED | Operation Dragoon | event |
| 2 | "…designed by Josep Lluís Sert." | ✅ FLAGGED | Josep Lluís Sert | person |
| 3 | "…hosted Jean-Paul Sartre and Pablo Picasso." | ✅ FLAGGED (Sartre) | Jean-Paul Sartre | person |
| 4 | "…under the House of Savoy." | ✅ FLAGGED | House of Savoy | house |

### Must NOT be flagged

| # | Sentence | Flagged? | Reason |
|---|---|---|---|
| 5 | "…until World War II…" | ✅ NOT FLAGGED | Well-known (in _WELL_KNOWN set) |
| 6 | "In 1888, Monet first experimented…" | ✅ NOT FLAGGED | Well-known (Monet in _WELL_KNOWN) |
| 7 | "The Rue Obscure, a 130-metre fortified street…" | ✅ NOT FLAGGED | Already glossed (appositive detected) |
| 8 | "Start cycling south on the main road." | ✅ NOT FLAGGED | Navigation exempt (D164) |

### Gloss examples (from Stage 3)

| Entity | Gloss | Source | Words |
|---|---|---|---|
| Operation Dragoon | the Allied landings in southern France in August 1944 | model + historical record | 10 |
| House of Savoy | the Italian royal dynasty that ruled the region until 1860 | model + Treaty of Turin 1860 | 11 |
| Josep Lluís Sert | the Catalan architect who designed the building in 1964 | model + Fondation Maeght records | 10 |

## Prior Boundary Sets — All Pass

```
tests/test_local269_unglossed_reference_gate.py      — 28 passed
tests/test_local263_unsupported_claim_gate.py        — 44 passed
tests/test_local256_fragment_and_label.py            — 37 passed
tests/test_local253_directions_mode_guard.py         — 13 passed
tests/test_local257_fragment_checker.py              — 69 passed
─────────────────────────────────────────────────────────────────
TOTAL                                                — 191 passed
```

## Cost Report

| Metric | Value |
|---|---|
| **Triage calls** | 1 per stop, 324-1023 tokens, $0.0001-0.0002, 0.9-3.7s |
| **Gloss calls** | 1 per stop (if refs found), 400-930 tokens, $0.0001-0.0002, 0.9-2.0s |
| **Total added cost per 2-stop tour** | **$0.0001–$0.0004** against $0.0206 baseline |
| **Total added generation time** | **2.3–5.7s** against 43s for 2 stops |
| **Added words** | **+72 max** against 620 words for round 19 (when glosses fire) |

The added cost is **under $0.001** — negligible against the $0.0206 baseline.
The added time is **under 6 seconds** — well within the 30s limit.
Added words (when glosses fire): ~10 words per gloss × typically 2-5 glosses = 20-50 words.

## Design Decisions

1. **Stage 1 is free.** Named-entity detection is regex-based, deterministic.
   No model call unless entities are found.

2. **Stop names excluded.** "Cap d'Antibes" and "Eze Village" are not flagged
   because they are the stops themselves — the listener is THERE.

3. **Degrade preferred over delete.** If no sourced gloss is available, the
   unknown name is removed but the fact is kept: "liberated in 1944" instead
   of "during Operation Dragoon" — preserves the good fact without confusing
   the listener or inventing anything.

4. **Well-known filter is conservative.** Only truly universal knowledge
   (Monet, World War II, the Mediterranean) is auto-skipped. Borderline cases
   go to triage.

5. **Glosses are traceable.** Every gloss records its source (corpus passage
   or model citation). No gloss from memory — the model must return a citable
   basis.

## Traps Navigated

- **D141:** Test row created with `is_test=true`, verified, deleted only after
  `SELECT is_test` returns true. Nice list `[1,12,14,17,24,29,152]` verified
  before and after.
- **D148:** Tests run against `audiotours_test`.
- **D97/D103:** Every boundary row test executed and output confirmed.
- **D164:** Navigation sentences exempt — "Start cycling south" not processed.
- **D48:** No container rebuilt.
- **D161:** Tour read as prose in Step 8.

## Limitations

1. **Generation variability.** The gate only fires when the LLM produces obscure
   references. In some generations (round 22 attempt 2), no obscure references
   appeared — the gate correctly detected 0. The gate's value is proven by its
   behavior on round 19's actual text (test_operation_dragoon_detected_in_full_stop).

2. **Corpus-based glosses are limited.** The corpus often doesn't explain the
   entity (it mentions it, but doesn't define it). Most glosses come from the
   model stage with citation requirement.

3. **Person pattern may over-match.** Multi-word capitalized sequences can
   be place names, not people. The article filter ("The Rue Obscure") and
   stop-name exclusion handle most cases, but novel place names not in the
   structure pattern could be misclassified. Triage stage catches these.
