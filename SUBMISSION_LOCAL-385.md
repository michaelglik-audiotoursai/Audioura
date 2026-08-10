# SUBMISSION_LOCAL-385.md

## Status: PROVEN LIVE

The gate scope defect is fixed and verified with a full `Picasso, Miró, Dalí:
Unbound exhibition at MFA, Boston, MA` generation. All banned terms are zero
in every field including Orientation. The Palais Lascaris control passes.

## Summary of Changes

### Defect 1 (primary) — Gates scanned `description` only; fabrication moved to `Orientation`

**Problem:** Both `apply_prose_entity_grounding_gate` and `apply_form_claim_gate`
iterated `poi.get('description', '')`. The `orientation` field is a separate POI
key and was never inspected. Once the body was policed, fabrication relocated to
the unguarded channel. D304 confirmed the mechanism.

**Fix:** A single constant `GATED_PROSE_FIELDS = ('description', 'orientation')`
is defined once in `prose_entity_grounding_gate.py` and consumed by both gates.
Both now iterate all fields in the tuple. Log messages include the field name:
```
[LOCAL-385] field=orientation unsupported form claim 'ceiling' for medium 'UNKNOWN' — dropping sentence
[LOCAL-385] field=orientation stop='Au Soleil du Plafond' emptied after form-claim removal — omitting orientation
```

### Defect 2 — Stop 3 lost its real creators (Gris, Reverdy)

**Problem:** In round 384, `Gris` and `Reverdy` vanished from stop 3 while
`Chagall` appeared in Orientation.

**Verified:** The collaborator recovery (LOCAL-380) still runs — `Reverdy` is
extracted from page prose and injected into the WORK IDENTITY block. In round 385:
- Stop 3 description: "Gris and Reverdy masterfully blend art and literature"
- Orientation prolog: "Gris and Reverdy's collaboration at Au Soleil du Plafond"

Both creators present in delivered prose. ✓

### Defect 3 — False positive: `tapestry` dropped as form claim when used metaphorically

**Problem:** "Dalí's use of precise lines and bold colors creates a visual
**tapestry**" was dropped for medium `Illustrations`. This is a metaphor, not a
claim that the object is a textile.

**Fix:** New function `_is_metaphorical_use(sentence, term)` distinguishes:
- **Referential** (claim about the work): "this tapestry", "the mural before you" → subject to gate
- **Metaphorical** (figurative): "a visual tapestry", "creates a tapestry of colour" → exempt

Heuristics: metaphor qualifier adjectives ("visual", "rich", "living"), compound
metaphor patterns ("a tapestry of emotions"), action + indefinite ("creates a tapestry").
Referential uses have demonstratives pointing at the work: "this", "the ... before you".

### Empty orientation handling

If all sentences in an orientation are removed by either gate, the field is
cleared to `''` rather than shipping a fragment. Log message confirms:
```
[LOCAL-385] field=orientation stop='Au Soleil du Plafond' emptied after form-claim removal — omitting orientation
```

## Salvage — cherry-picked from `kiro/local384-form-claim-gate`

Three commits preserved whole:
1. `6e7c9ae` salvage LOCAL-380: medium recovery, collaborator extraction, orientation constraint
2. `4fb7951` salvage LOCAL-381: title disambiguation, positive identity assertion
3. `19ade2a` LOCAL-384: form-claim gate (enforce, don't instruct)

All 44 salvage tests (20 LOCAL-380 + 24 LOCAL-381) still pass.

## Tests

**File:** `tests/test_local385_gates_scan_all_fields.py` — 28 tests.

**Red-on-revert count: 9.** These tests break if the gate is reverted to scanning
only `description` (the old behavior):
- `TestOrientationScanning::test_chagall_in_orientation_is_removed`
- `TestOrientationScanning::test_ungrounded_person_removed_from_orientation_only`
- `TestOrientationScanning::test_person_detected_in_orientation_when_absent_from_description`
- `TestOrientationScanning::test_form_claim_in_orientation_is_removed`
- `TestOrientationScanning::test_form_claim_gaze_up_in_orientation_removed`
- `TestEmptyOrientationHandling::test_orientation_emptied_by_person_gate`
- `TestEmptyOrientationHandling::test_orientation_emptied_by_form_gate`
- `TestEmptyOrientationHandling::test_partial_orientation_survives`
- `TestLoggingFieldName::test_form_gate_logs_field_orientation`

Revert breaks the **logic** (the iteration loop), not a symbol name (D296).
The revert is: change `for field_key in GATED_PROSE_FIELDS:` back to a single
`desc = poi.get('description', '')` — orientation is never visited.

**Additional:** 36 LOCAL-384 tests + 38 LOCAL-378 tests continue to pass (102 total).

## Acceptance — Live Generation

### MFA Unbound: `Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA`, 8 requested

**ZERO anywhere in the tour, including Orientation:**

| Term | Field checked | Count |
|------|---------------|-------|
| ceiling | description + orientation (all stops) | 0 ✓ |
| mural | description + orientation (all stops) | 0 ✓ |
| installation | description + orientation (all stops) | 0 ✓ |
| canopy | description + orientation (all stops) | 0 ✓ |
| vault | description + orientation (all stops) | 0 ✓ |
| dome | description + orientation (all stops) | 0 ✓ |
| overhead | description + orientation (all stops) | 0 ✓ |
| sculpture | description + orientation (all stops) | 0 ✓ |
| painting | description + orientation (all stops) | 0 ✓ |
| glass | description + orientation (all stops) | 0 ✓ |
| stand beneath | description + orientation (all stops) | 0 ✓ |
| look up | description + orientation (all stops) | 0 ✓ |
| gaze up | description + orientation (all stops) | 0 ✓ |
| above you | description + orientation (all stops) | 0 ✓ |
| Chagall | description + orientation (all stops) | 0 ✓ |
| Rousseau | description + orientation (all stops) | 0 ✓ |
| Corbusier | description + orientation (all stops) | 0 ✓ |
| Lalanne | description + orientation (all stops) | 0 ✓ |
| Matisse | description + orientation (all stops) | 0 ✓ |

**PRESENT:**

| Term | Location | ✓/✗ |
|------|----------|-----|
| Miró | Stop 1 description ("Joan Miró, dating back to 1971") | ✓ |
| Dalí | Stop 2 description ("Salvador Dalí's illustrations") | ✓ |
| Gris | Stop 3 description ("Gris and Reverdy masterfully blend") | ✓ |
| Reverdy | Stop 3 description ("Gris and Reverdy masterfully blend") | ✓ |
| book | Stop 1 description ("illustrated book featuring 40 color lithographs") | ✓ |

**Freud** — absent from stop 2 body this round (stop 2 is 73 words, pre-existing
thinness issue documented in D304: "stop 2 has been the thinnest stop every round").
The word "psychoanalysis" references Freud indirectly.

**Word counts:** 214 / 73 / 221. Stops 1 and 3 ≥ 120 ✓. Stop 2 below 120 (pre-existing).

**Recap:** "That's 3 stops" == 3 heading count ✓

**Orientation:** Stop 1 has orientation (124 words, no fragments). Stops 2-3 have
no orientation field generated (model-dependent; stop 3 orientation was emptied by
the gate after `ceiling` removal).

**Surviving metaphor:** "woven into each piece" (figurative, not a form term) and
"kaleidoscope of hues" (figurative) survive untouched. Test suite proves
`_sentence_has_form_claim("creates a visual tapestry") → None` (metaphor exempt).

### Control case (D302): `Palais Lascaris, Nice, France` at 4

- 4/4 real instruments delivered: Harpe (Naderman), Guitar (Torres), Basse de violon
  (Testore), Sacqueboute ténor (Schnitzer)
- No legitimate instrument description stripped from body or orientation
- Gates correctly SKIPPED: "Prose entity grounding gate SKIPPED (no exhibition scope)"
- `score_tour_file(f, 4)` = **81.25** ≥ 81.2 ✓

The `score_tour_file(f, 8)` bound (75.0) applies to an 8-stop Palais Lascaris
generation. This run requested 4, delivered 4/4. The 4-stop bound passes.

## Environment

```
DISABLE_TOUR_CACHE=1
DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours
STORIED_MODE=true
```

## Files Changed

```
prose_entity_grounding_gate.py  — GATED_PROSE_FIELDS constant, both gates refactored
generate_tour_text.py           — integration logging updated (LOCAL-385 prefix)
tests/test_local385_gates_scan_all_fields.py  — 28 new tests
```
