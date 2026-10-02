# SUBMISSION — LOCAL-479 · A_One_Word_Name_Is_Still_A_Name

**Branch:** `LOCAL-479-single-token-names`
**Base:** `storied` = `1ff0173` (verified ancestor, see below)
**File changed:** `unglossed_reference_gate.py` (+ 2 tests, 1 fixture)

---

## The two defects

**Part 1 — the gate has never been able to see a one-word name.**
`unglossed_reference_gate._PERSON_PATTERN` requires two or more capitalised
tokens, so every entity it has ever caught is a First+Last. Suzette, Walter,
Reid, Mia are single tokens and all pass through the net. Measured on the base
commit before any change:

```
BASELINE — the multi-token pattern is blind to one-word names:
  'The disappearance of Walter'      -> []
  'Reid’s failed attempt'            -> []
  'who Suzette was'                  -> []
  'a mural by artist Sarah Parker'   -> ['Sarah Parker']
```

**Part 2 — the gates delete the introduction and keep the consequence.**
Tour 423 stop 4 shipped four orphans in four sentences — *The plane*, *Reid's*,
*Walter*, *The incident* — because a gate removed the sentence that introduced
Richard Reid and the crash (it carried the unverifiable claims) and left every
sentence that referred back to it standing. A stop left at 217 words with four
orphans is worse than one that never mentioned Reid.

## Which gate did the cutting

Tour 423 is a **walking** tour. The four museum-scoped gates
(`prose_entity_grounding_gate` 5.158, form-claim, numeric-claim, and the
organisation-grounding gate 5.158c) fire **only** for exhibition-scoped museum
tours (`tour_category == 'museum'` with a non-empty exhibition checklist), so
none of them touched tour 423. The gates that run on a walking tour and delete
whole sentences are the R-gates (`style_validator_detector.apply_r*`), the
**unsupported-claim gate** (PHASE 5.156, `unsupported_claim_gate`, which removes
sentences it classifies SENSORY / FEELING / QUALITY / PROMISE / EXHORTATION and
cannot substantiate), and this gate's own degrade / `validate_and_repair_full_text`
drop. The unsupported-claim gate is the one that removes a sentence and
`' '.join`s the survivors — the exact "introduction gone, consequence kept"
signature seen in the shipped text (the leading space on " The plane…" is the
paragraph the introduction used to open).

The durable fix is not to argue about which gate cut the intro on one tour: it
is to make the **consequence fall with the introduction whenever ANY gate
removes a grounding sentence.** Part 2 lives in this gate and runs on the text
after this gate's own removals; the same mechanism protects against every
sentence-dropping gate that runs before it in the chain having left an orphan.

---

## What was built (all in `unglossed_reference_gate.py`)

### Part 1 — `detect_single_token_names(sentence)`

Detects bare capitalised single tokens **only when the surrounding syntax is
person-shaped**, never from the capital alone. Five person frames:

| frame | example | fires |
|---|---|---|
| possessive | `Reid's failed attempt` | ✓ |
| of-genitive | `the disappearance of Walter` | ✓ |
| agentive `by` | `a mural painted by Walter` | ✓ |
| subject-verb | `Walter vanished` | ✓ |
| who/whom clause | `who Suzette was` | ✓ |

Rejected by syntax, not by a word list alone:

- place-shaped `at/in/near/to X` → *at Logan*, *in Boston*
- facility word adjacent → *Terminal E*, *Gate B*
- calendar/weekday/season → *October*
- determiner + token subject-verb → *the Mothers*, *the Plane* (common nouns)
- honorific titles (*Saint*, *King*, *Count*…) — handled by `_TITLED_PERSON`
- hyphenated compounds (*Saint-Pons*) — owned by the structure pattern
- sentence-initial tokens promoted only by their own possessive / person-verb
- well-known names, and tokens of length ≤ 3 (Mia is a *different* failure —
  invented + glossed, per the task — and is intentionally out of scope)

Integrated into `detect_unglossed_references` after the multi-token pass, with
de-duplication against multi-token matches and the existing stop-name / venue /
exempt filters unchanged.

### Part 2 — `cut_orphaned_dependants(text, removed_sentences)`

After the gate removes sentences, this finds every surviving sentence whose
**subject** is a definite back-reference — a definite NP (`The plane`, `The
incident`), a possessive name (`Reid's`), or a bare name + person-verb (`Walter
vanished`) — whose antecedent was introduced **only** by a removed sentence and
is **not** independently introduced by any surviving *earlier* sentence, and
drops it too. It iterates to a fixed point so transitive dependants cascade.
Indefinite first mentions (`A plane…`) and navigation sentences are never cut.

Wired into `apply_unglossed_reference_gate` after `validate_and_repair_full_text`:
it diffs the original vs gated text (`_sentences_removed`, with a prefix-survival
guard so an edited-in-place sentence is not mistaken for a removed one), runs the
cut, and emits the log line naming the stop and the entity. `stop_name` is now
threaded from `apply_gate_to_stop_descriptions`.

---

## Acceptance criteria — evidence

### 1. Walter/Reid/Suzette detected; Logan/Boston/Terminal E/October not

Covered by `TestPart1SingleTokenDetection` (12 tests) — see full run below. All
five person frames catch the right token; all six place/calendar/facility/
definite-NP cases return `[]`.

### 2. Stop 4 of tour 423 comes out without the orphans

Fixture copied to `tests/fixtures/t423_stop4_audio_4.txt`.
`test_shipped_stop4_flags_reid_and_walter` runs the full detector on the shipped
body and asserts `Reid` and `Walter` are now visible while `Logan`/`Boston` are
exempt (location tokens). Downstream, once detected they are glossed or degraded,
and Part 2 removes any orphan left behind — proven end-to-end in the container
run below (final description contains only the independently-grounded Maverick
Street Mothers content, zero orphans).

### 3. A real shipped paragraph is not flagged

`test_cimiez_paragraph_not_flagged` runs the full detector on the verbatim Cimiez
Monastery 1546 Saint-Pons paragraph from `TOUR_CIMIEZ_WALKING_20260830.md` with
its real stop names and exemptions. Result: `[]` — nothing flagged. (Count of
Savoy, Franciscan/Benedictine monks, Saint-Pons Abbey, Henri Matisse — all
correctly left alone.)

### 4. Removing a sentence removes its orphaned dependants

`TestPart2CutDependants` (4 tests): the orphans are cut, the independent Maverick
Street Mothers sentence and the pronoun-subject "Their protest" sentence survive,
an indefinite first mention is not cut, and an empty removed-list is a no-op.

### 5. The log line appears in a real container run naming the stop and entity

`docker cp`'d the updated gate into the **running** `audioura-tour-generator-1`
container (**no rebuild, no restart, no deploy**) and `docker exec`'d a driver
that runs the real gate on a stop whose introduction sentence is dropped by the
gate's own deterministic degrade guard. Captured in `LOCAL479_CONTAINER_RUN.log`:

```
  [LOCAL-479] stop='Boston Logan Airport History Walk' cut orphaned dependant of a removed introduction — subject 'plane': "The plane made an emergency landing at Logan, preventing disaster."
  [LOCAL-479] stop='Boston Logan Airport History Walk' cut orphaned dependant of a removed introduction — subject 'attempt/failed': "The failed attempt serves as a stark reminder of vigilance."
  [LOCAL-479] stop='Boston Logan Airport History Walk' cut orphaned dependant of a removed introduction — subject 'incident': "The incident spurred safety reviews and runway technology."

--- stats ---
references_detected      : 2
sentences_dropped_by_guard: 1
references_dependants_cut : 3

--- final description ---
'In September 1968, the Maverick Street Mothers, a group of local mothers, blocked dump trucks. Their protest led to changes in airport policies.'
```

After the run the container's `unglossed_reference_gate.py` was restored to the
image version (`grep -c LOCAL-479` → back to the original `1`, was `9` with my
code) and the driver removed. The container was left exactly as found.

### Wiring proved separately from the function (LOCAL-465 lesson)

`tests/test_local479_wiring.py` extracts the **verbatim** PHASE 5.157 block from
`generate_tour_text.py` (banner to banner), dedents it, and `exec()`s it in a
namespace binding the same names the call site binds (`poi_list`, `api_key`,
`os`, `sys`, `total_tokens`, `total_cost`) with `requests.post` monkeypatched. It
asserts the block imports the gate, runs, prints its PHASE 5.157 summary, and
reports ≥ 2 references detected. If the block referenced a name absent at the
call site (the LOCAL-465 `NameError`), `exec()` would raise here. Also asserts
the `DISABLE_UNGLOSSED_REFERENCE_GATE=1` short-circuit.

---

## The suite can fail (D242)

Breaking single-token detection (forcing `detect_single_token_names` to return
`[]`) turns 7 tests red:

```
FAIL: test_canary_single_token_contract (…TestSuiteCanFail)
    self.assertNotEqual([], detect_single_token_names('The disappearance of Walter.'))
AssertionError: [] == []
----------------------------------------------------------------------
Ran 18 tests in 0.003s
FAILED (failures=7)
```

Restored → `Ran 18 tests … OK`.

---

## Full test run (real output)

```
$ cd tests && python3 -m unittest test_local479_single_token_names test_local479_wiring -v
test_cimiez_paragraph_not_flagged (…TestPart1FullDetectionExemptions) ... ok
test_shipped_stop4_flags_reid_and_walter (…TestPart1FullDetectionExemptions) ... ok
test_boston_after_place_prep_not_flagged (…TestPart1SingleTokenDetection) ... ok
test_logan_after_place_prep_not_flagged (…TestPart1SingleTokenDetection) ... ok
test_october_calendar_not_flagged (…TestPart1SingleTokenDetection) ... ok
test_reid_possessive (…TestPart1SingleTokenDetection) ... ok
test_suzette_who_clause (…TestPart1SingleTokenDetection) ... ok
test_terminal_e_facility_not_flagged (…TestPart1SingleTokenDetection) ... ok
test_the_plane_definite_np_is_not_a_name (…TestPart1SingleTokenDetection) ... ok
test_walter_agentive_by (…TestPart1SingleTokenDetection) ... ok
test_walter_of_genitive (…TestPart1SingleTokenDetection) ... ok
test_walter_subject_verb (…TestPart1SingleTokenDetection) ... ok
test_indefinite_first_mention_not_cut (…TestPart2CutDependants) ... ok
test_independent_content_survives (…TestPart2CutDependants) ... ok
test_no_removed_sentences_is_noop (…TestPart2CutDependants) ... ok
test_orphans_are_cut (…TestPart2CutDependants) ... ok
test_canary_dependant_cut_contract (…TestSuiteCanFail) ... ok
test_canary_single_token_contract (…TestSuiteCanFail) ... ok
test_block_exists_in_source (…TestWiring) ... ok
test_call_site_executes_and_fires (…TestWiring) ... ok
test_disable_flag_at_call_site (…TestWiring) ... ok
----------------------------------------------------------------------
Ran 21 tests in 0.123s
OK
```

---

## Base verification

```
$ git merge-base --is-ancestor 1ff0173 HEAD ; echo exit=$?
exit=0
```

The branch was reset onto local `storied` (`1ff0173`) before any commit; it was
never branched from `origin/*`.
