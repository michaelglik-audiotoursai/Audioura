# SUBMISSION — LOCAL-530: a verb welded onto "of" after its object noun was deleted

**Agent:** Mac Mini Kiro · **Branch:** LOCAL-530-mangled-sentence-missing-noun
**Base:** storied = `65de385` (`git merge-base --is-ancestor 65de385 HEAD` exits 0)

## The defect (verified against the tour file, not taken on the critic's word)

`CRITIQUE_ROUND7_517.md` quotes LOGAN_2 stop 4:

> "They authorized of Public Works to lease this land to the U.S. Army"

Verified verbatim in `TOURS_FOR_REVIEW/round7/LOGAN_2.txt`, Stop 4 (Control Tower).
The object noun is gone: the sentence meant **"the Department of Public Works"** and
reads "authorized **of** Public Works". Subject ("They") and verb ("authorized") are
intact — so this is *not* the subject-loss defect LOCAL-475 already guards.

## Did a gate delete the noun, or did the model write it? — a gate did it

Following the D583 method (trace the mangle to the excision that made it) I
reproduced it exactly:

```
_excise_governed_construction(
    "They authorized the Department of Public Works to lease this land to the U.S. Army.",
    "Department")
-> "They authorized of Public Works to lease this land to the U.S. Army."
```

The gate treats "Department" as an unglossed reference and excises the head noun. Its
"Entity rest" branch strips the preceding article ("the"), then concatenates
`before` ("They authorized ") + `after` (" of Public Works …") — leaving the verb
abutting "of". Crucially `_degrade_sentence_is_wellformed` returned **True** for the
wreckage: all seven guards passed it, exactly as in LOCAL-475 defect C and D583. The
broken sentence therefore shipped.

This is the same family as D583/LOCAL-475: a gate deletes a mid-sentence span and the
degrade guards fail to notice the result is broken English.

## The fix — two parts, mirroring D583

**1. The gate (root cause). `unglossed_reference_gate.py`**
Added an eighth degrade guard `_DEGRADE_GUARD_OBJECT_DROPPED` and wired it into
`_degrade_sentence_is_wellformed` (used by both `_degrade_reference_in_text` and the
final net `validate_and_repair_full_text`) and into `validate_degrade_output`
(reports guard `object_dropped`). Now the mangled sentence is judged ill-formed and
**dropped whole** rather than voiced — the fail-safe LOCAL-475 established.

**2. The scorer (net). `tour_quality.py`**
Added `_OBJECT_DROPPED` and folded it into the existing `truncated` defect. The old
`_MANGLED` caught the round-3 sibling ("engaged of Public Works") only because
`engaged` was hand-listed; the round-7 verb `authorized` was not — the enumeration
trap D476 warns of. So if this shape ever ships again, the loop counts it and
regenerates.

### Why it does not false-positive on ordinary "-ed of" English

Both detectors match a **transitive verb that governs a direct object** welded onto
"of", restricted to a family of verbs of official action on an institution
(`authoriz|engag|establish|appoint|commission|task|direct|instruct|order|permit|
enabl|allow|assign|designat|elect|nominat|compel|urg|request|requir|forbid|prohibit|
mandat`). It deliberately does **not** fire on the legitimate idioms — *comprised of,
composed of, consisted of, deprived of, accused of, approved of, died of, informed
of, conceived of, made of* — which are covered by tests.

## Scan across TOURS_FOR_REVIEW (reported, not asserted)

`tour_quality._OBJECT_DROPPED` over all **46** tour files fires **exactly twice**,
both true positives, zero false positives:

```
  round3/LOGAN_1.txt   "...foresight that once engaged of Public Works."
  round7/LOGAN_2.txt   "...They authorized of Public Works to lease this land"
```

Both are the same deleted "the Department of Public Works" noun. (The round-3 hit was
already caught by `_MANGLED`; the round-7 hit was the gap this task closed.)

## Tests

- `tests/test_local530_verb_object_dropped.py` — 31 passed. Carries the real
  sentence verbatim; proves the gate reproduces it, now rejects it, still passes the
  intact original, drops it in full-text repair, and the scorer counts it; 10 legit
  "-ed of" idioms neither rejected by the gate nor scored; corpus scan asserts
  exactly the two known hits.
- Regression: `test_d583_possessive_splice`, `test_local289_degrade_path`,
  `test_local269_unglossed_reference_gate`, `test_local371_fragment_repair`,
  `test_d584_person_cap` — 108 passed. `test_local475_gate_caused_corruption` —
  13/13. `test_d585_person_counter`, `test_local494_cache_key_buckets` — 30 passed.
- One unrelated pre-existing failure noted:
  `test_local256 …::test_r7_does_not_fire_on_factual_sensory` fails identically on a
  clean `65de385` (confirmed via `git stash`); it concerns an R7 sensory rule, not
  this change.

## Grounded call

None required — the diagnosis is a deterministic reproduction of the gate and a
regex scan of files already in the repo. Gemini's HTTP 402 did not affect this task;
nothing here was verified by a live model run.

## Files changed

- `unglossed_reference_gate.py` — new degrade guard + wiring (gate root-cause fix)
- `tour_quality.py` — `_OBJECT_DROPPED` detector wired into the `truncated` defect
- `tests/test_local530_verb_object_dropped.py` — new
