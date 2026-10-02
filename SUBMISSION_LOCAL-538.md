# SUBMISSION — LOCAL-538: the noun is gone and no rule sees it

**Branch:** `LOCAL-538-dangling-reference-round2`
**Base:** `storied` (`eded48a`) — verified `git merge-base --is-ancestor eded48a HEAD` exits 0.

## What was broken

Round 9 scored CLEAN while carrying two sentences broken in exactly the way
LOCAL-530 exists to catch, in shapes its `<verb> of <Capital>` regex cannot match.
Both are one grammatical fault: **a phrase that requires a complement, standing
without one.**

**A — a relational noun that lost its complement.** `round9/LOGAN_1.txt`, Control
Tower, verbatim:

> "Trippe, **the founder** and later Pan American World Airways, helped connect
> Boston to New York, ..."

"the founder" needs "of <what>". Here the "of" was deleted (and the given name,
Juan, with it). LOCAL-530's `_OBJECT_DROPPED` matches the "of" — the very part
that was deleted — so it has nothing to match.

**B — a referent that does not exist.** `round9/CHURCH_1.txt`, Stained Glass
Windows, verbatim:

> "In the absence of stained glass, we find the church's story told through
> different means. **This event**, deeply etched into the church's modern history,
> demonstrates that ..."

No event has been narrated — not in this stop, not in the one before. "This event"
points at nothing.

## What was added

Two detectors in `tour_quality.py`, wired into `score_tour()` as the defects
`dangling_complement` (A) and `dangling_reference` (B), both added to
`REQUIRED_CLEAN` so a tour carrying either no longer scores CLEAN.

### A — relational noun with no complement

An appositive `, the <AGENTIVE>` coordinated by `and`/`,` **directly to a
proper-noun phrase that stands alone** (a comma or period follows it, not a
lowercase head noun), with **no** `of`, possessive, or `who` complement in the
coordinator span or immediately after the proper noun.

- "the founder **of** Pan American" — clears (complement present).
- "the founder and chairman **of** Pan American" — clears (late complement).
- "the founder and later Pan American World Airways**,** helped ..." — flags: the
  proper-noun phrase stands where the `of`-complement was, followed by a comma and a
  finite verb.

### B — demonstrative / pronoun with no antecedent

Two sibling shapes:

- **Demonstrative.** A sentence-initial encapsulating anaphor `This/These
  <EVENTIVE-NOUN>` opening a stop body (its 2nd or 3rd body sentence) whose
  preceding **two** sentences contain neither a year nor a multi-word proper noun.
  An eventive noun denotes a *happening*, and a narrated happening is normally
  dated or names an actor; when neither is present, the anaphor has nothing to bind
  to.
- **Pronoun** (the ticket's second case — round 7's "Her presence ... with no woman
  anywhere"). A sentence-initial **singular gendered** pronoun (she/he/her/his/him)
  with no person named anywhere earlier **in the whole tour** (searched backwards
  across stops, using the scorer's own `_PERSON` frame).

## Is the fix a word list? — No.

This is the trap LOCAL-530 named against itself ("a hand-listed set of verbs is the
enumeration trap D476 warns about") and then fell into. None of the three
alternations below is a catalogue of the specific words seen in round 9; each is a
**grammatical class**, and the discrimination is done by a **structural test on the
surrounding syntax**, not by membership in the list:

- **A** keys on the `-er` / `-or` / `-ist` suffix — the morphology of agent/relational
  nouns. "founder" is not enumerated; it is caught because it is a `-er` agentive
  sitting in an appositive whose complement was deleted. "author", "designer",
  "architect" fall in the same class by the same rule.
- **B (demonstrative)** keys on the `[+eventive]` noun class — nouns denoting an
  occurrence (event, incident, episode, ceremony, visit, ...). The list enumerates a
  *semantic class*, and what actually fires the check is the structural absence of a
  dated/named happening in the two preceding sentences.
- **B (pronoun)** keys on the closed grammatical class of singular gendered personal
  pronouns; the check is the structural absence of any named person earlier in the
  tour.

Adding "founder" or "event" to a flat list would have been the same thing round 10
walks around. A tour that instead writes "Trippe, **the pioneer** and later Pan
American" or "**This incident**, etched into ..." is caught by the same rules with
no edit, because "pioneer" is a `-er` agentive and "incident" is `[+eventive]`.

## Measured false-positive rate (not asserted)

Both checks were run over **all 48 `.txt` files** under `TOURS_FOR_REVIEW/` via
`measure_local538_false_positives.py`. (LOCAL-530 reported "46 tours"; the recursive
`**/*.txt` glob it and this measurement use both see 48 files — the extra two are
the `buckets/` variants. The standard to match is its "fires exactly twice, both
true positives".)

Result — **exactly two hits, both true positives, zero false positives**:

| Check | File | Sentence | Verdict |
|---|---|---|---|
| A `dangling_complement` | `round9/LOGAN_1.txt` | "Trippe, the founder and later Pan American World Airways, ..." | **TP** |
| B `dangling_reference` (demonstrative) | `round9/CHURCH_1.txt` | "This event, deeply etched into the church's modern history, ..." | **TP** |

No other file in the corpus flags. Reproduce with:

```
python3 measure_local538_false_positives.py
```

### Two false positives were found during measurement and removed structurally

The value of measuring rather than asserting: two ordinary-English hits appeared in
intermediate versions and were eliminated by tightening the *structure*, not by
blacklisting the words.

1. **"This recognition emphasized ..."** (`round7/LOGAN_1`), after "achieved LEED
   certification". A looser version that flagged any `This <abstract-noun>` with no
   dated/named preceding sentence hit this — but "recognition" legitimately packages
   the certification just described. Fixed by restricting B to the `[+eventive]`
   class: "recognition" is not eventive, so it is never a candidate. This is also
   the honest limit below.
2. **"They argue that without an airfield, Boston risks ..."** (`round6/LOGAN_2`),
   where "They" refers to "Military aviation officers" in the previous sentence.
   The pronoun check flagged it because `_PERSON` recognises a titled/named
   individual, not a plural common-noun group. Fixed by restricting the pronoun
   check to **singular gendered** pronouns: "they/their" routinely corefer with a
   group and are unsafe; "she/he" demand a specific named individual.

## The honest limit

The **general** demonstrative-referent check — deciding whether *any* `This <noun>`
has a real antecedent — cannot be made both sensitive and zero-false-positive with
structure alone. Whether "This recognition" is grounded by an earlier "achieved
certification" is a **semantic** relation (recognition ↔ certification) that a regex
cannot compute. "This moment", "these stories", "her work" are ordinary and correct
whenever the referent is genuinely earlier, and a check that fired on them would be
worse than no check.

The structural escape used here is to narrow the demonstrative check to the
`[+eventive]` noun class, where the referent must be a *narrated happening* and a
narrated happening carries a structural signature (a date or a named actor). That
catches the round-9 defect ("This event" with no happening) with zero false
positives, and deliberately declines the abstract cases it cannot judge without
semantics. A future round could route only the eventive-flagged sentences to a
model for a semantic antecedent check — the structural filter makes that cheap by
handing it one candidate, not 127.

## Files changed

- `tour_quality.py` — two detectors (`_find_relational_no_complement`,
  `_find_dangling_references`) + patterns; wired into `score_tour()`; both defect
  keys added to `REQUIRED_CLEAN`.
- `tests/test_local538_dangling_reference.py` — 21 regression tests reading the
  defect sentences **verbatim** from `round9/LOGAN_1.txt` and `round9/CHURCH_1.txt`
  (sliced from the file, not retyped), the legit-passes cases, a real
  `round7/CHURCH_2.txt` pronoun with a valid antecedent (must NOT fire), and the
  corpus scan asserting exactly the two known hits.
- `measure_local538_false_positives.py` — the measurement artifact.

### Note on the pronoun test being synthetic

The ticket names round 7's "Her presence ... with no woman anywhere" as a second
test case. No tour on disk actually carries that defect: every "Her"/"His"/"She" in
round 7 and round 9 has a person named earlier (verified — e.g. `round7/CHURCH_2`
names "Mother Teresa's visit in June 1995" one sentence before "Her presence
highlighted ..."). The pronoun check therefore fires on **no** corpus file (0 false
positives), its positive case is exercised on a documented **synthetic** sentence,
and a real round-7 pronoun-with-valid-antecedent is included as a true-negative
regression so the check is proven not to over-fire on the shape it targets.

## Verification

- `python3 measure_local538_false_positives.py` → 2 hits, both TP, 0 FP.
- `python3 -m pytest tests/test_local538_dangling_reference.py` → 21 passed.
- Relevant scorer/gate subset (`test_local538`, `test_local530`, `test_d585`,
  `test_d583`, `test_local289`, `test_local479`, `test_local269`, `test_local287`)
  → 184 passed.
- `score_tour()` on `round9/LOGAN_1.txt` → `dangling_complement`, `clean=False`.
- `score_tour()` on `round9/CHURCH_1.txt` → `dangling_reference`, `clean=False`.

(The repo has 37 pre-existing pytest collection errors in unrelated scraper/network
test modules — `ModuleNotFoundError: No module named 'selenium'` and similar — that
are not touched by this change.)
