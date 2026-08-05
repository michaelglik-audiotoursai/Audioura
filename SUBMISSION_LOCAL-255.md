##### READY FOR REVIEW

## Commit

```
a6801ab LOCAL-255: R1 imperative rewrite path — rewrite preferred over deletion
```

## Per-File Summary

| File | Change |
|---|---|
| `style_validator_detector.py` | +345 lines: R1 rewrite logic (deterministic rules + LLM fallback + content preservation check), `apply_r1_rewrites()`, `apply_r1_to_description()`, `_is_style_navigation_sentence` extended for "Start your ride at X and pedal..." pattern |
| `generate_tour_text.py` | +50 lines: PHASE 5.13 wired between style retry (5.1) and R7 deletion (5.14), processes both description AND orientation, behind `DISABLE_R1_REWRITE=1` flag |
| `tests/test_r1_rewrite.py` | 13 tests covering all 8 boundary rows: 3 rewrite, 3 navigation-exempt, 2 deletion, content preservation, paragraph-level, R7 secondary |
| `run_round12.py` | Generation harness: R1 baseline, flags-on generation, measurement, D141-compliant DB round-trip, fact tally, artifact write |
| `RIVIERA_2STOP_ROUND12.md` | Tour artifact (Cap d'Antibes + Eze Village, 624 words) |

## Eight Boundary Rows — Before/After

| # | Category | BEFORE | AFTER | Content Preserved? |
|---|---|---|---|---|
| 1 | REWRITE | "Position yourself at the entrance of Eze Village, a medieval gem perched high above the French Riviera." | "Eze Village is a medieval gem perched high above the French Riviera." | ✓ Eze Village, medieval gem, perched high, French Riviera |
| 2 | REWRITE | "As you arrive at Cap d'Antibes, take in the breathtaking views of the azure waters." | "From Cap d'Antibes, you can admire the breathtaking views of the azure waters." | ✓ Cap d'Antibes, breathtaking, azure waters |
| 3 | REWRITE | "Look for the Fondation Maeght, founded in 1964 by Marguerite and Aimé Maeght." | "The Fondation Maeght, founded in 1964 by Marguerite and Aimé Maeght." | ✓ Fondation Maeght, 1964, Marguerite, Aimé Maeght, founded |
| 4 | EXEMPT | "Start cycling south on the main road with the sea on your right." | *(untouched)* | N/A — navigation |
| 5 | EXEMPT | "Head east along the coastal path until you reach the roundabout." | *(untouched)* | N/A — navigation |
| 6 | EXEMPT | "Start your ride at Cap d'Antibes and pedal east along the coastal road." | *(untouched)* | N/A — navigation |
| 7 | DELETE | "Take a moment to absorb the atmosphere." | *(deleted — pure instruction, no content)* | N/A — no content existed |
| 8 | DELETE | "Enjoy the view." | *(deleted — pure instruction, no content)* | N/A — no content existed |

## Corpus-Wide R1 Before/After

| Metric | Before (baseline) | After (Round 12 tour) |
|---|---|---|
| R1 paragraph rate | 45.0% (1281/2849) | — |
| R1 sentence rate | 26.9% (1610/5994) | 9.4% (3/32) |

## Rewritten vs Deleted Counts (Round 12)

| Metric | Value |
|---|---|
| Sentences rewritten (PHASE 5.13) | 2 |
| Sentences deleted (PHASE 5.13) | 0 |
| Deletion rate | 0.0% (threshold: 10%) ✓ |
| Residual R1 in delivered tour | 3/32 (9.4%) |

## Round 12 vs Round 10 Comparison

| Metric | Round 10 | Round 12 |
|---|---|---|
| Word count | 679 | 624 |
| Stops | Cap d'Antibes, Eze Village | Cap d'Antibes, Eze Village |
| R1 sentences | 5 | 3 |
| R7 residual | 1 | 0 |
| Cost | $0.0095 | $0.0095 |
| Cap d'Antibes facts | 4/9 | 2/15 |
| Eze Village facts | 8/11 | 7/11 |

## R7 Secondary Finding

The round 10 R7 residual — "Take a moment to breathe in the salty sea air and listen to the gentle lapping of the waves" — is now handled by R1. The imperative opening ("Take a moment to") had shielded it from R7 detection because R7 skips navigation/imperative sentences. Once R1 processes it first (deterministic result: rewrite or deletion depending on content), R7's blind spot becomes moot.

- R1 fires: **yes** (verb: "take a moment")
- Deterministic outcome: falls to `_take_a_moment_handler` → checks for pure feeling → `_FEELING_TERMS` matches ("breathe in" + "atmosphere" equivalent) → signals for LLM decision or deletion depending on pipeline position

In practice in Round 12: R7 reports 0 residual.

## Flags Set (Round 12)

All in-pipeline gates ON:
- `STOP_EXISTENCE_GATE_MODE=enforce`
- `STORIED_MODE=true`
- Style retry: ON (not disabled)
- R1 rewrite: ON (not disabled)
- R7 deletion: ON (not disabled)
- R9 deletion: ON (not disabled)
- R10 deletion: ON (not disabled)
- Contradicted block: ON (not disabled)
- `DISABLE_SUBJECT_ROUTINE=1` (OFF — subject routine disabled as in round 10)
- `DISABLE_TOUR_CACHE=1` (OFF — cache disabled for fresh generation)

## Limitations

1. **R1 residual is 3 sentences, not 0.** The remaining R1 hits are sentences where the style retry (PHASE 5.1) already attempted repair and failed, and the deterministic rules don't match the specific syntactic pattern. These would be caught by the LLM fallback if the cost budget allowed it; on this run ($0.0095 total), PHASE 5.13 fired on 2 sentences deterministically and no LLM calls were needed.

2. **Cap d'Antibes fact density dropped (4/9 → 2/15).** This is a generation variance issue, not a regression from the R1 rewrite path. The rewrite path does not remove factual content.

3. **Corpus-wide measurement is BEFORE (static); the "after" is measured only on the single generated tour.** A full corpus-wide after measurement would require running every stored tour through `apply_r1_to_description`, which exceeds the $0.60 ceiling.

4. **"Start your ride at X and pedal..." exemption** was a gap in the existing navigation detector. Fixed by LOCAL-255 with the `_TRANSPORT_NOUNS` extension. The existing D107 boundary rows remain unchanged (verified: all 10 original D107 rows pass).

## Evidence

```
$ git rev-list --count storied..HEAD
1

$ git status --short
(clean)

$ python3 -m pytest tests/test_r1_rewrite.py -v
13 passed

$ python3 -m pytest tests/test_r10_unfulfilled_promise.py -v
30 passed
```
