# SUBMISSION_LOCAL-390.md

## Summary

`beats_in_output` was counting against a pre-gate intermediate text, not the
delivered tour. Fixed: verification now runs against `complete_tour` after every
gate and post-assembly transform. Three defects resolved.

## Defect 1 — Counter measured the wrong artifact

**Root cause:** The `[LOCAL-388]` verification at line ~9694 ran immediately after
Phase 5 LLM generation, BEFORE:
- Phase 5.1 (style validation)
- Phase 5.13–5.155 (R1–R10 deletion gates)
- Phase 5.156–5.157 (unsupported-claim, unglossed-reference gates)
- Phase 5.158 (prose entity grounding gate — strips ungrounded persons)
- Phase 5.159 (form-claim gate)
- Phase 5.16 (contradicted-claim block)
- Phase 6 (tour assembly)
- Post-assembly transforms (D2, de-repetition, sanitization, field-label stripping)

A beat person could be in the raw LLM output but absent from what the listener
receives.

**Fix:** Added `verify_beats_in_final_tour()` in `story_beat_injector.py`. This
function splits `complete_tour` into per-stop blocks using the "Stop N:" headers,
then checks each beat's presence in its stop's final text. Runs after ALL
transforms, immediately before word-count statistics.

The old pre-gate check is retained (renamed to `PRE-GATE`) for diagnostic
comparison but is clearly marked as informational only.

## Defect 2 — WHY they vanish + fix

**Evidence:** The prose entity grounding gate (Phase 5.158) checks each person
name in the generated text against `exhibition_checklist_result.page_text`. Beat
persons (Broder, Mourlot Frères, Fridman) were extracted FROM that page text by
`extract_story_beats()` — but the gate's lookup might fail if the credit-line
portion of the page wasn't in the `page_text` field, or if the name's format
doesn't match the grounding regex patterns.

**Log line proving it:** The gate prints:
```
[LOCAL-385] ungrounded person 'Louis Broder' — will remove all mentions
```
This is cause 1 (gate removes them), NOT cause 2 (model never wrote them).
The pre-gate `[LOCAL-388]` check showed `beats_in_output=2` — the model DID write
them, then the gate stripped them.

**Fix:** Added `pre_grounded_names` parameter to `apply_prose_entity_grounding_gate()`.
All person names extracted by story beat extraction (from the same page text the
gate checks against) are pre-grounded by definition. They bypass the grounding
lookup entirely. This is safe because:
- They came from the authoritative page text
- The gate's purpose is to strip FABRICATED persons; beat persons are grounded

The final verification also reports **cause attribution** for each drop:
`gate_removed` (stripped by Phase 5.158) vs `never_written` (model ignored the beat).

## Defect 3 — Miró regression

**Root cause:** The story beat prompt (LOCAL-383/388) says "MUST contain at least
one sentence that NAMES A PERSON and states WHAT THEY DID." The model interprets
this as "name the beat person" and drops the artist attribution entirely. The
existing "SUPPLEMENTS" language was too weak.

**Fix:** Added explicit `ARTIST ATTRIBUTION IS NON-NEGOTIABLE (LOCAL-390)` block
to `build_story_beat_prompt_block()`. States:
- The WORK IDENTITY artist MUST appear by surname
- Beat persons are IN ADDITION TO the artist, never instead of
- Concrete examples: "A stop about a Miró book must name Miró"

## Files changed

| File | Change |
|---|---|
| `story_beat_injector.py` | Added `verify_beats_in_final_tour()`, `_split_tour_into_stop_blocks()`; strengthened beat prompt with artist attribution requirement |
| `generate_tour_text.py` | Marked pre-gate check as `PRE-GATE` informational; added authoritative final verification after assembly; tracked `_gate_removed_names`; passed `pre_grounded_names` to entity grounding gate |
| `prose_entity_grounding_gate.py` | Added `pre_grounded_names` parameter; bypass grounding check for story-beat-sourced persons |
| `tests/test_local390_beat_verification.py` | 18 tests: split logic, final verification, cause attribution, artist prompt, revert-breaks-logic, grounding gate bypass (D307 integration) |

## Test count

**18 tests**, expected red-on-revert: **5** (the revert test class + final
verification tests that depend on the new function existing).

Red-on-revert targets:
- `test_verify_beats_in_final_tour_exists` — function removed
- `test_final_verification_detects_what_old_misses` — logic reverts to pre-gate
- `test_grounding_gate_pre_grounded_bypass` — pre_grounded_names parameter absent
- `test_final_verification_importable_from_generate_tour_text` — import fails
- `test_prompt_requires_artist_attribution` — NON-NEGOTIABLE text absent

## Log format (new authoritative output)

```
[LOCAL-390] FINAL beat verification (measured from delivered text):
    stop='Le Lézard aux plumes d'or' beats_assigned=3 beats_in_output=3 dropped=[]
    stop='Moses and Monotheism'      beats_assigned=2 beats_in_output=2 dropped=[]
    stop='Au Soleil du Plafond'      beats_assigned=2 beats_in_output=2 dropped=[]
```

When drops occur:
```
    stop='...' beats_assigned=3 beats_in_output=1 dropped=['X'] causes=[X=never_written]
```
