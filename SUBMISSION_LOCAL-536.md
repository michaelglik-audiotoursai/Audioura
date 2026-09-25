# SUBMISSION — LOCAL-536: A tour must not contradict itself

**Branch:** `LOCAL-536-self-contradiction`
**Base:** `storied` (HEAD `8fa0080`; `git merge-base --is-ancestor 8fa0080 HEAD` exits 0)

## What changed

- **`tour_quality.py`** — added a `self_contradiction` defect built from four
  independent sub-checks, and added `'self_contradiction'` to `REQUIRED_CLEAN` so
  it gates.
- **`test_local536_self_contradiction.py`** — regression tests built from the
  **verbatim** round-9 sentences (read from the files, asserted present, then fed
  to the checker), the end-to-end `score_tour` assertions, a negative control, and
  a false-positive survey.

No evidence files, no `DECISIONS.md`/`CLAUDE.md`/`BACKLOG.md`/`WORK_QUEUE.md`/
`.continuous_dev/STATUS.md`, and no round7/8/9 tour files were edited.

## Why this check and not another pattern

Round 9 scored `defects: {}` on both tours. LOCAL-527 was merged at 19:21 to gate
fabricated founder attribution; round 9 generated at 20:10 and evaded it, because
`"constructed in 1887-1889 by Gustave Eiffel"` became
**`"Gustave Eiffel's iconic Control Tower"`** — no verb, no year, no "by". Writing
another surface pattern invites round 10 to use an appositive. Self-contradiction
has no such weakness: it needs no corpus, no grounded call and no outside
knowledge. Every sub-check fires **only on a positive, quotable pair of statements
from the same tour**, and both quotes are reported so the decision is inspectable.
It never decides which statement is right — the contradiction itself is the finding
(D577).

## The four sub-checks

1. **`attribution_conflict`** — the same named structure credited to two different
   agents. `(structure, agent)` pairs are extracted from a **possessive** frame
   (`"Gustave Eiffel's iconic Control Tower"` — the form that got through) and a
   **passive** frame (`"Designed by … Kubitz & Papi, Inc. and Desmond & Lord, Inc.,
   this tower"`). A possessive whose owner is the venue itself (`"the Airport's
   Control Tower"`) is *ownership*, not authorship, and is excluded.
2. **`absent_subject`** — a stop's title names a thing and the stop's own body says
   that thing is absent (`"in the absence of"`, `"there is no"`, `"does not hold"`,
   `"no longer has"`, `"without"`). Title-to-body only; no cross-stop inference.
3. **`epilog_stop_mismatch`** — the closing summary names a stop/place that was not
   delivered. **Only the EXTRA direction is reported.** The omission direction was
   implemented, measured, and **dropped**: the epilog format always teases two of
   four stops (`"That's N stops — X and Y. This tour covered A and B."`), so
   "omits a delivered stop" fired on *every* tour — worse than none. A person named
   in a teaser is guarded out; the flagged name must be a proper place reference.
4. **`orientation_stop_mismatch`** — the stop-1 orientation previews "endpoints"
   that are not delivered stops. LOGAN_1 states its endpoints twice in consecutive
   sentences and gives different answers; the second names **St. Mary's Cathedral**,
   which is not a stop.

## Acceptance evidence

### Both round-9 tours now report `self_contradiction` (they were CLEAN — the bug)

```
round9/LOGAN_1.txt   -> attribution_conflict, orientation_stop_mismatch
round9/CHURCH_1.txt  -> absent_subject, epilog_stop_mismatch
```

Mapping to the four real cases:

- **A (two designers, LOGAN_1)** → `attribution_conflict`, quoting
  `"Gustave Eiffel's iconic Control Tower mark the endpoints."` against
  `"Designed by the Boston architectural firms Kubitz & Papi, Inc. and Desmond &
  Lord, Inc., this tower …"`.
- **B (absent subject, CHURCH_1)** → `absent_subject`: stop titled
  **"Stained Glass Windows"** whose body says **"In the absence of stained glass …"**.
- **C (route described is not the delivered one, LOGAN_1)** → `orientation_stop_mismatch`:
  the orientation's `"… mark the endpoints"` sentence names St. Mary's Cathedral,
  not a delivered stop. (The delivered stops are Main Concourse, Jetbridge, Control
  Tower, Baggage Claim.)
- **D (epilog adopts a different church, CHURCH_1)** → `epilog_stop_mismatch`: the
  epilog previews **"Mary Immaculate of Lourdes showcases collaborative stained
  glass art"** — a different church its own stop 2 distinguishes.

The self-contradiction check catches all four of the four cases. (The brief noted
it would catch at least three; D is caught here as an epilog EXTRA, without any
world knowledge — "Mary Immaculate of Lourdes" is simply not among this tour's
delivered stops.)

### Negative control — stays CLEAN

**`TOURS_FOR_REVIEW/round8/CHURCH_1.txt`.** It credits **one** designer for the
church (`"The church designed by James Murphy, a student of Patrick Keely"`), its
stop titles (Nave, Narthex, Stained Glass Windows, Side Chapels) match their bodies
— its "Stained Glass Windows" stop actually describes stained glass, unlike round 9
— and its epilog names delivered stops (`"This tour covered Stained Glass Windows
and Side Chapels."`). `_find_self_contradictions` returns `[]` and `score_tour`
reports no `self_contradiction`. Believed clean because there is no second agent for
any structure, no title-vs-body absence, and no epilog/orientation name outside the
delivered list.

### False-positive rate — every round 7 and round 8 tour

Run over all eight tours in `round7/` and `round8/`:

| tour | hits | classification |
|------|------|----------------|
| round7/CHURCH_1.txt | 0 | — (correctly silent) |
| round7/CHURCH_2.txt | 0 | — |
| round7/CHURCH_3.txt | 0 | — |
| round7/LOGAN_1.txt | 0 | — |
| round7/LOGAN_2.txt | 0 | — |
| round7/LOGAN_3.txt | 0 | — |
| round8/CHURCH_1.txt | 0 | — |
| round8/LOGAN_1.txt | 0 | — |

**Zero false positives across round 7 and round 8.** Extending the same survey to
every tour in `TOURS_FOR_REVIEW/` (rounds 2–9, 48 files) yields hits on **only** the
two round-9 files. Two intermediate false positives were found and eliminated during
development, both recorded in code comments:

- the possessive frame first matched every plural noun (`windows`, `Christians`,
  `departures`) as a possessive → tightened to require a real apostrophe and a
  Capitalised named structure;
- the epilog check first flagged a **person** named in a teaser
  (`"… Betty Ann Ong and Madeline Amy Sweeney acted heroically"`, round7/LOGAN_3) →
  guarded so only proper place references count.

## Tests

`python3 test_local536_self_contradiction.py` → **10/10 pass**; also `pytest` clean.
Existing `tour_quality.py` consumers unaffected: `tests/test_local527_fabricated_attribution.py`,
`tests/test_local530_verb_object_dropped.py`, `tests/test_d585_person_counter.py`
→ **60 passed**.
