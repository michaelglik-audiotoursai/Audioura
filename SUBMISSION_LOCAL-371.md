# SUBMISSION_LOCAL-371.md

## Summary

`_take_in_handler` Case 3 in `style_validator_detector.py` blindly appended
"stretches out before you" to any noun phrase that lacked a relative clause.
This produced ungrammatical sentences for museum objects and mangled input alike.

The fix adds two guards:
1. **Broken-tail detection** — refuses when the input is already mangled.
2. **Subject-type routing** — uses "stretches out before you" only for vistas;
   uses "is displayed here" for objects/artifacts.

---

## Before / After on the Real Sentences

### Sentence 1 (guitar)

**Input tail:** `this guitar for its influence on future string instruments, marking a crucial moment in the history of guitar-making`

| | Output |
|---|---|
| **Before** | `This guitar for its influence on future string instruments, marking a crucial moment in the history of guitar-making stretches out before you.` |
| **After** | `None` (deleted — tail is unrepairable; participial pile + dangling purpose clause) |

### Sentence 2 (remarkable piece)

**Input tail:** `this remarkable piece with an understanding of its historical context`

| | Output |
|---|---|
| **Before** | `This remarkable piece with an understanding of its historical context stretches out before you.` |
| **After** | `None` (deleted — "with an understanding of" is an abstract clause, not an object attribute) |

---

## Vista Case Still Working

**Input tail:** `the panoramic view of the Mediterranean coastline`

| | Output |
|---|---|
| **Before** | `The panoramic view of the Mediterranean coastline stretches out before you.` |
| **After** | `The panoramic view of the Mediterranean coastline stretches out before you.` |

**Input tail:** `the stunning coastline of the Riviera`

| | Output |
|---|---|
| **Before** | `The stunning coastline of the Riviera stretches out before you.` |
| **After** | `The stunning coastline of the Riviera stretches out before you.` |

No regression for walking/outdoor tours.

---

## Object Case (New Behavior)

**Input tail:** `the ornate harpsichord`

| | Output |
|---|---|
| **Before** | `The ornate harpsichord stretches out before you.` (nonsense) |
| **After** | `The ornate harpsichord is displayed here.` (grammatical) |

---

## Relationship to `empty_sentence_count` (LOCAL-356)

**Both ticket sentences are exactly what `empty_sentence_count` counts.**

```
>>> _is_empty_sentence('This guitar for its influence on future string instruments, marking a crucial moment in the history of guitar-making stretches out before you.')
True

>>> _is_empty_sentence('This remarkable piece with an understanding of its historical context stretches out before you.')
True
```

The Palais tour scored 75.0 with stop 1 reporting `empty_sentence_count=4`.
These sentences (produced by the repair pass) are being counted by the structural
metric — the scorer detects the defect, and the repair pass keeps creating it.

**Note:** Even "The ornate harpsichord is displayed here." returns `True` from
`_is_empty_sentence` because it carries no named entity, number, orientation cue,
or attributable claim. The `is_empty_sentence` metric is structural — it flags
sentences without information content regardless of grammaticality. The fix here
addresses the grammaticality defect (TTS reads nonsense aloud); the information-
content defect is a separate concern handled by the metric's eventual enforcement.

**Implication for LOCAL-356 promotion:** The repair pass was manufacturing empty
sentences that the metric correctly detected but could not act on (D276:
reporting-only). Once this fix lands, the repair pass stops creating new empties.
Whether to promote `empty_sentence_count` from reporting to enforcing is a
separate decision for LEAD — it depends on whether the remaining empties (those
not produced by the repair pass) warrant gating.

---

## Sibling Handlers — Stock Predicate Audit

| Handler | Stock Predicate | Vista Assumption? | Exposure? |
|---|---|---|---|
| `_take_in_handler` Case 3 | ~~"stretches out before you"~~ → now subject-typed | **Was yes, now fixed** | **Fixed** |
| `_look_for_handler` Case 2 | "can be found here" | No — universally appropriate | None |
| `_as_you_arrive_handler` | "From X, Y is visible" | No — "is visible" works for objects too | None |
| `_as_you_mid_handler` | "you can admire {tail}" | No — "you" is the subject | None |
| `_take_a_moment_handler` | Delegates to participle extraction or `_take_in_handler` | Inherited from `_take_in_handler` | **Fixed by this change** |

No other handler blindly assumes the subject is a landscape.

---

## Red / Green Evidence

### RED (reverted code, fix not present):

```
$ git stash  # revert fix
$ python3 -c "from style_validator_detector import _take_in_handler; ..."

REVERTED CODE result: 'This guitar for its influence on future string instruments, marking a crucial moment in the history of guitar-making stretches out before you.'
FAIL: produced the broken sentence with stretches out before you
```

Test collection fails with:
```
ImportError: cannot import name '_take_in_tail_is_unrepairable' from 'style_validator_detector'
```
(The helpers don't exist without the fix — tests structurally cannot pass against old code.)

### GREEN (fix applied):

```
$ git stash pop  # restore fix
$ python3 -m pytest tests/test_local371_fragment_repair.py -v

30 passed in 0.11s
```

All 30 tests pass. Museum bounds hold:
```
tests/test_local345_corpus_in_body.py::TestMuseumScoreBounds::test_museum_8stop_bound PASSED
tests/test_local345_corpus_in_body.py::TestMuseumScoreBounds::test_museum_palais_bound PASSED
tests/test_local357_forced_stops.py::TestMuseumBoundsProperty::test_museum_8stop_score_bound PASSED
tests/test_local357_forced_stops.py::TestMuseumBoundsProperty::test_museum_4stop_score_bound PASSED
```

No bound changed. (The fix prevents future broken sentences from being emitted;
it does not retroactively re-score existing stored tours.)

---

## Limitations

1. **"is displayed here" is still structurally empty.** The metric correctly
   identifies it as carrying no information. This fix addresses grammaticality,
   not information density. A sentence like "The ornate harpsichord is displayed
   here." won't be read aloud as nonsense, but it also won't teach the listener
   anything. Whether that matters depends on LOCAL-356 enforcement.

2. **Vista detection is lexical.** `_tail_is_vista_subject` checks the head noun
   phrase against a word list. An unusual vista description without any standard
   vista words would fall through to "is displayed here" — grammatically harmless
   but semantically imprecise. This is conservative by design: false-negative on
   vista (gets "is displayed here") is better than false-positive (a guitar
   "stretches out before you").

3. **The broken-tail detector is pattern-based.** It catches the two patterns
   observed in production (participial piles, dangling purpose clauses, abstract
   "with an understanding" clauses). Novel forms of mangled input may still slip
   through. The `empty_sentence_count` metric remains the backstop.

4. **Deletion vs. repair trade-off.** When Case 3 declines (returns None), the
   sentence is deleted. This reduces word count. The empty-sentence accounting
   already handles shortfall, so this is safe — but a tour with many declined
   sentences would be shorter than intended. In practice this is rare: the broken
   tails come from upstream rewriting that damages the NP before it reaches Case 3.
