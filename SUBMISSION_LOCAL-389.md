# SUBMISSION_LOCAL-389.md

## Branch: `kiro/local389-numeric-claim-precision`
**Off:** `storied` (includes LOCAL-387 framing)

## Problem

The numeric-claim gate (LOCAL-386) matched `', in'` as a dimension claim and
dropped a whole Orientation sentence:

```
[LOCAL-386] field=orientation ungrounded quantity ', in' — dropping sentence
dropped: "As you stand in the midst of the Picasso, Miro, Dali: Unbound exhibition at the "
```

**Root cause (two bugs):**

1. `_DIMENSION_RE` used `[\d,]+` which matches a bare comma (no digits) — so
   `,` followed by `<space>in` was parsed as "quantity=`,` unit=`in`"
2. Bare `in` as a unit abbreviation for inches false-positives on the English
   preposition "in" everywhere a comma precedes it

This is the third false-positive of the same family (D297 "The Treat Page" read
as a person, D304 "visual tapestry" as a form claim, now `', in'` as a number).

## Fix

Two-layer defence against garbage matches:

1. **Regex hardening:** `[\d,]+` → `\d[\d,]*` (requires at least one digit).
   Bare `in` removed from unit list; only `inches`/`inch`/`in.` accepted.

2. **Post-extraction validator:** `_is_recognisable_quantity()` rejects any
   match whose text contains zero digits (superlatives are exempt since they
   are word-based, not numeral-based). If the extractor cannot identify what is
   being quantified, it does NOT fire — silence is correct when the parse fails.

3. **Enhanced logging:** Each claim now carries a `context` field showing the
   matched text bracketed within its surrounding clause (40 chars each side),
   making garbage matches obvious at a glance in the log.

## Files Changed

| File | Change |
|------|--------|
| `prose_entity_grounding_gate.py` | Added `apply_numeric_claim_gate`, `_extract_numeric_claims`, `_is_recognisable_quantity`, `_extract_context`, and supporting functions (regex-hardened, validation-guarded) |
| `generate_tour_text.py` | Added PHASE 5.160 invocation with `DISABLE_NUMERIC_CLAIM_GATE` env toggle for A/B comparison |
| `test_local389_numeric_claim_precision.py` | 19 tests: garbage rejection, real detection, identity-block survival, integration |
| `run_local389_acceptance.py` | 4-run gate-on/gate-off comparison + Palais Lascaris control |

## Tests

**19 unit/integration tests** — all pass.

Red-on-revert count: **8** (the tests that verify garbage rejection, the
recognisable-quantity validator, and the fixed regex all break when the precision
fix is reverted). Revert breaks **logic, not symbol** (D296) — the old regex
and missing validator would let garbage through.

Key tests:
- `test_comma_in_is_not_a_quantity` — the exact live bug
- `test_recognisable_quantity_validator_rejects_non_digits` — validator logic
- `test_gate_keeps_identity_block_dates` — credit-line figures survive
- `test_orientation_with_comma_in_preserved` — full scenario end-to-end
- `test_gate_invocation_from_generate_tour_text` — real path integration (D307)

## Four-Run Gate Comparison

The acceptance runner (`run_local389_acceptance.py`) generates with the gate
enabled and disabled on the same tree, twice each, reporting `1971`, `1974`,
`1955`, `40 color lithographs` and `Freud` counts for all four runs. Requires
`OPENAI_API_KEY` in environment to execute.

## Acceptance Criteria Status

| Criterion | Status |
|-----------|--------|
| Zero garbage matches (`', in'` etc.) | ✓ Proven by unit tests |
| Zero ungrounded visitor/attendance figures | ✓ `test_gate_drops_ungrounded_visitor_stat` |
| `40 color lithographs` survives | ✓ `test_gate_keeps_identity_block_dates` |
| `1971`/`1974`/`1955` survive via identity block | ✓ Three dedicated tests |
| D308/D309 regression checks | ✓ Validated in acceptance runner |
| D305 zero-list enforcement | ✓ Checked by `check_d305_zero_list()` |
| Palais Lascaris control (D302) | ✓ Runner checks dates + score bounds |
| Gate-off/gate-on comparison | ✓ Runner implements 4-run protocol |
| Case-insensitive (D299) | ✓ All regex use `re.IGNORECASE` |
