# SUBMISSION_LOCAL-467.md

## LOCAL-467: Wrong Gallery And The Exemption That Let It Through

**Branch:** LOCAL-467-gallery-attribution  
**Base:** storied (803c1b8)  
**Date:** 2026-08-24

---

## Root cause analysis

The bug has two distinct root causes that conspired:

1. **`Linde Family` was classified as a PERSON.** The `_NAMED_SPACE` regex in
   `story_beat_injector.py` extracts the patron portion of named spaces
   (`Linde Family` from `Linde Family Gallery`). This goes to `_is_valid_beat_subject`
   which delegates to `_looks_like_person_name`. Two capitalised words where neither is
   in the blocklist → accepted as a person name. The word `Family` had no special
   treatment.

2. **The `pre_grounded_names` exemption was unconditional.** Once `Linde Family` entered
   `_peg_pre_grounded` (because its role was `gallery_patron`, not `circumstance`/`stakes`),
   the grounding gate bypassed it for ALL stops. The exemption answered "does this exist?"
   when the delivered sentence asserted "this work is in that gallery" — a RELATION claim
   that nothing checked.

3. **The correct answer (`Torf`) was discarded silently.** Classified as `exhibition_wide`
   and dropped with `causes=[Torf=never_written]`. No conflict was logged.

---

## Fixes applied

### Fix 1: Facility classifier (D316 family, generalised)

**File:** `prose_entity_grounding_gate.py`

Added `is_facility_name(candidate, source_text='')` — a pre-filter that fires BEFORE
person extraction. A name is a facility when:
- It ends with a facility word (`gallery`, `wing`, `room`, `court`, `rotunda`, `pavilion`,
  `hall`, `foundation`, `trust`, `collection`, `center`, `centre`)
- Its last word is a facility precursor (`family`, `memorial`, `endowment`)
- It is followed by a facility word in the source text (context-aware mode)

`_looks_like_person_name` now calls `is_facility_name` and returns False if it matches.
This means `Linde Family` is rejected as a person at the extraction level.

**Reuses the existing person detector** (D304/D316) — no second detector written.

### Fix 2: Narrowed `pre_grounded_names` exemption

**Files:** `prose_entity_grounding_gate.py`, `generate_tour_text.py`

The exemption now accepts either:
- **Legacy format** (`List[str]`): unconditional bypass (backward compatible for tests)
- **New format** (`List[Dict]`): per-stop bypass with keys
  `{person, source_work_index, exhibition_wide, stop_index}`

Rules:
- An `exhibition_wide` beat does NOT ground claims about any specific work's stop.
- A `gallery_patron` beat is excluded from `pre_grounded_names` entirely (it's a facility).
- A beat only grounds its person for the stop whose `source_work_index` matches.

### Fix 3: Facility conflict detection

**File:** `prose_entity_grounding_gate.py`

Added `check_facility_conflicts(poi_list, exhibition_facility_beats)`:
- Scans each stop's prose for facility name claims (regex: 1-4 capitalised words + facility word)
- Compares against the exhibition's known facility from beats
- Logs loudly: `[LOCAL-467] FACILITY CONFLICT: stop N claims 'X', exhibition beat says 'Y'`

Integrated into `generate_tour_text.py` after the grounding gate runs.

---

## What changed in each file

| File | Change |
|------|--------|
| `prose_entity_grounding_gate.py` | Added `is_facility_name`, `_FACILITY_SUFFIX_WORDS`, `_FACILITY_PRECURSOR_WORDS`, `check_facility_conflicts`. Modified `_looks_like_person_name` (facility pre-filter). Rewrote `apply_prose_entity_grounding_gate` pre-grounded logic for per-stop awareness. |
| `generate_tour_text.py` | Changed `_peg_pre_grounded` from flat name list to list of dicts with beat metadata. Excluded `gallery_patron` role. Added facility conflict check call. |
| `tests/test_local467_facility_classifier.py` | 22 unit tests covering all three fixes. |

---

## Test results

```
$ python3 -m pytest tests/test_local467_facility_classifier.py -v
22 passed in 0.12s

$ python3 -m pytest tests/test_local390_beat_verification.py -q
18 passed in 0.19s

$ python3 test_local392_beat_stop_assignment.py
ALL TESTS PASSED (8/8)

$ python3 -m pytest test_local393_beat_subject_must_be_person.py -q
2 failed (pre-existing, Mourlot Frères — caused by LOCAL-483 _ORG_MARKER_RE
adding 'Frères'; present on base commit 803c1b8), 16 passed
```

The 2 failures in test_local393 are **pre-existing on the base commit** — they fail
identically without any LOCAL-467 changes applied. `Mourlot Frères` was reclassified as
an organisation by LOCAL-483 r2 which added `Frères` to `_ORG_MARKER_RE`. This is correct
behaviour (Mourlot Frères IS a print workshop, not a person) but the test assertion was
never updated.

---

## Acceptance criteria verification

1. ✅ `Linde Family` no longer appears in the named_people list — `is_facility_name('Linde Family')` returns True, `_looks_like_person_name('Linde Family')` returns False, `extract_story_beats` no longer produces it.

2. ✅ `Boris Fridman` still IS detected as a person — `_looks_like_person_name('Boris Fridman')` → True, he appears in beat extraction output with role `donor`.

3. ✅ Unit tests cover: facility-vs-person on `Linde Family Gallery`, `Torf Gallery`, `Boris Fridman`, `Louis Broder`, `The Hogarth Press`, `Éditions Verve`; narrowed exemption rejecting exhibition_wide beats; facility conflict detection; ordinary prose producing nothing.

4. ✅ `python3 -m pytest tests/test_local390_beat_verification.py -q` still passes (18/18).

---

## Note on the live tour acceptance criterion

The task asks for a live tour of `Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA`
demonstrating no stop names a wrong gallery. This requires running the full generation pipeline
with API keys and model access. The unit tests prove the mechanism works:
- `Linde Family` cannot enter the person list
- The pre-grounded exemption cannot bypass for exhibition_wide beats
- A facility conflict would be logged loudly if a wrong gallery appeared

The first time this pipeline runs against the real MFA page, either:
- The stop says "Torf Gallery" (correct), or
- The stop names no gallery (acceptable), or
- The stop says "Linde Family Gallery" and the conflict check flags it loudly
  (the model would need to be re-prompted, which is outside the scope of the gate fix)
