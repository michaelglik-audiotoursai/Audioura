# SUBMISSION_LOCAL-393.md

## Summary

**Beat extraction now validates that the subject is a person — places are never
beat subjects.** Also fixes Reverdy's misattribution to the wrong work and adds
a 120-word floor retry.

## Three defects fixed

### Defect 1 — "France" extracted as a person (primary)

The `_PERSON_ACTION` regex in `extract_story_beats` matches any capitalized word
followed by an action verb (`established`, `founded`, `created`). "France
established a tradition..." was captured as person=`France`, demanded of all 4
Palais Lascaris stops, and burned a retry on each.

**Fix:** New function `_is_valid_beat_subject(candidate)` gates every extraction
point. It delegates to `_looks_like_person_name` from `prose_entity_grounding_gate`
(single source of truth per D304) for multi-word candidates, and maintains a
`_KNOWN_PLACE_NAMES` frozenset for single-word candidates (countries, cities,
regions). All six `len(person) > 3` checks are replaced with
`_is_valid_beat_subject(person)`.

Result: `France`, `Nice`, `Paris`, `Milan`, `Almeria`, `Nuremberg` are all rejected.
Single-word surnames (`Dalí`, `Freud`, `Torf`, `Carlone`) remain valid.

### Defect 2 — Reverdy attributed to the wrong work

The source sentence names both pairs in one breath:
> "…as Dalí did…for…Moses and Monotheism; …as in Juan Gris and…Pierre Reverdy's
> Au Soleil du Plafond"

The weak title match (strength=1) found "Moses and Monotheism" in the same
source sentence as Reverdy and attributed him there (iterate-order wins).

**Fix:** Proximity-weighted weak matching. When both person name and work title
appear in the source sentence, we measure the character distance. Closer titles
get higher fractional strength (1.0 to 2.0 range), so "Au Soleil du Plafond"
(10 chars from "Reverdy") beats "Moses and Monotheism" (92 chars away).

### Defect 3 — Stop 3 at 107 words vs 120-word floor

The `_classify_placeholder_leak` function only catches <30-word template-like
outputs. A 107-word honest description passed as `short_valid` without retry.

**Fix:** Post-generation word-count floor check. After the placeholder/short_valid
classification, if the output is real prose but below 120 words AND retry budget
remains, a reinforcement message asks the model to expand using verifiable details.
If still below after retry, the output is kept (thin corpus is an honest outcome)
with a diagnostic log line.

## Changes

### `story_beat_injector.py`

- **New:** `_KNOWN_PLACE_NAMES` — frozenset of ~120 geographic names (countries,
  cities, regions) commonly encountered in art/museum corpus text.
- **New:** `_is_valid_beat_subject(candidate)` — validates single-word vs multi-word
  candidates using the place blocklist and `_looks_like_person_name`.
- **Changed:** All 6 extraction points use `_is_valid_beat_subject(person)` instead
  of `len(person) > 3`.
- **Changed:** `attribute_beats_to_works` uses proximity-weighted weak title matching.
  Distance between person name and work title in the source sentence determines
  fractional match strength (1.0–2.0), ensuring the nearest title wins.

### `generate_tour_text.py`

- **New:** `[LOCAL-393]` word-floor retry block (after `short_valid` classification).
  Retries once with a reinforcement message if output <120 words; keeps honest
  short output if retry doesn't reach 120.

## Tests

- `test_local393_beat_subject_must_be_person.py` — 18 unit tests:
  - `TestPlaceNamesRejected` — France, Nice, Paris, Milan, Almeria, Nuremberg, countries, regions
  - `TestPersonNamesAccepted` — Broder, Reverdy, Mourlot Frères, Gris, single-word surnames
  - `TestExtractStoryBeatsPlaceFilter` — extraction never yields place subject; places OK in action
  - `TestAttributionProximity` — Reverdy → Au Soleil (not Moses); Dalí → Moses; proximity without metadata
  - `TestWordFloorLogic` — real generation path has floor logic (D307)
  - `TestRevertBreaksLogic` — reverting _is_valid_beat_subject re-admits places (D296)

## Expected red-on-revert

**Count: 5** — Reverting `_is_valid_beat_subject` (restoring `len(person) > 3`)
causes these tests to fail on **logic** (places admitted as beat subjects), not
on a missing symbol:
- `test_france_rejected_as_beat_subject`
- `test_nice_paris_milan_almeria_nuremberg_rejected`
- `test_extract_story_beats_never_yields_place_subject`
- `test_place_in_action_context_is_fine`
- `test_real_generation_path_has_word_floor_logic`

## Retry impact (expected)

- **Before:** 4 retry lines for Palais Lascaris (`France` demanded, all fail)
- **After:** 0 place-as-person retries. Any remaining retry is either the word-floor
  mechanism (legitimate) or a genuine model miss.

## Files changed

- `story_beat_injector.py` — `_is_valid_beat_subject`, `_KNOWN_PLACE_NAMES`, proximity attribution
- `generate_tour_text.py` — 120-word floor retry block
- `test_local393_beat_subject_must_be_person.py` — new (18 unit tests)
- `SUBMISSION_LOCAL-393.md` — this file
