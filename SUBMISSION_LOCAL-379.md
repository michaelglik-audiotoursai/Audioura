# SUBMISSION_LOCAL-379.md

## Status: Unproven, handing to LEAD

The structural logic is correct and all 78 tests pass (38 LOCAL-378 + 20 LOCAL-369
+ 20 LOCAL-379). A live generation run has not been completed — the acceptance
criteria require a full `Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA`
generation, which requires the full service stack.

## Summary of Changes

### Defect 1 — WORK IDENTITY block emitted whenever ANY field is available

**Problem:** `build_provenance_block` only emitted when `credit_line` was non-empty.
The MEDIUM CONSTRAINT only emitted when `medium` was non-empty. Stops 2 and 3
had `medium='Illustrations'`/`''` with no credit line and got **0 chars** of
grounding material — so the model hallucinated freely (ceiling, installation, etc.).

**Fix:** New function `build_work_identity_block(matched_work)` emits whenever
ANY of artist, date, medium, publisher, or credit_line is available. When medium
is empty, it explicitly states: "Medium: UNKNOWN — do NOT describe physical form,
placement, or spatial relationship." This prevents the ceiling/installation
fabrication even when we don't know what the work IS.

The block includes ALL available fields so the model has truthful material to
draw from. It explicitly instructs: "You MUST name the artist in your description."

### Defect 2 — Correct artist now named in prose

**Problem:** `Miró`, `Dalí`, `Freud`, `Gris`, `Reverdy` — 0 hits each in delivered
stop prose. LOCAL-378 removed wrong names but never supplied right ones.

**Fix:** The WORK IDENTITY block carries `Artist: Joan Miró` (stop 1),
`Artist: Salvador Dalí` (stop 2), `Artist: Juan Gris` (stop 3) directly into the
description prompt, with an instruction to name them. The artist is sourced from
`match_work_for_stop()` → the exhibition checklist's own work data. This is the
positive half of grounding — telling the truth, not just preventing lies.

### Defect 3 — Closing recap stop count matches headings

**Problem:** `_build_closing_recap` counted "delivered" stops as those with
`len(desc.split()) >= 30`. After the grounding gate shortened a stop, it fell
below 30 words → excluded from count → "That's 2 stops" when 3 headings exist.

**Fix:** Separated the concepts:
- `delivered`: all stops with a non-empty, non-failed, non-placeholder description
  (used for the "That's N stops" count — matches `Stop N:` headings)
- `content_rich`: stops with ≥ 30 words (used for recap highlight extraction)

The stated count now equals the actual number of delivered `Stop N:` headings.

### Defect 4 — Stops no longer collapse to near-empty

**Problem:** Stop 1 was 73 words, stop 2 was 67 words. The `_specificity_short`
gate was triggering ("Write EXACTLY 120 words") because `confirmed_facts < 2`
and no corpus context — it didn't recognise the WORK IDENTITY block as substance.

**Fix:** Added `_has_work_identity = bool(_work_identity_block)` to the gate
condition. A stop with a matched work (artist, date, medium, etc.) is NOT
"short on substance" — it has real material. The model now gets the 280-word
target instead of the 120-word short mode, and has the grounded facts (artist,
date, medium) to fill it with.

## Files Changed

| File | Change |
|------|--------|
| `generate_tour_text.py` | `build_work_identity_block()` (new), replaces MEDIUM CONSTRAINT with full WORK IDENTITY block; recap count fix separates delivered/content_rich; specificity gate respects work identity |
| `tests/test_local379_prose_grounding_r3.py` | NEW — 20 tests covering all 4 defects |

## Red-on-Revert Count

**14 tests** break when LOCAL-379 logic is reverted:
- 13 break if `build_work_identity_block` is neutered (returns '')
- 1 breaks if recap counting reverts to the `>= 30` word threshold

The revert breaks the **logic** (empty block → no artist in prompt → no grounding;
word threshold → miscount), not the symbol (D296).

## Env for Live Verification

```bash
DISABLE_TOUR_CACHE=1
DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours
STORIED_MODE=true
```

Acceptance query: `Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA`, 8 requested.
