# LOCAL-546 — A husband and wife with the same surname counted as one person

**Branch:** LOCAL-546-surname-collision
**Base:** storied (047e7e5)

## Result

`_count_people` on the real `TOURS_FOR_REVIEW/round9/CHURCH_1.txt` now returns **16**,
with **both** D'Amores named. The de-duplication that folds *Law* / *Bernard Law* /
*Cardinal Bernard Law* into one man (D585) is fully preserved. `LOGAN_1` stays at
exactly **4**. Across the whole corpus the change moves **two** files, both by +1,
both genuine two-person splits — measured false-positive rate **0**.

## The problem

`_count_people` keyed identity on the surname — the last capitalised token — and kept
the fullest form seen. That is deliberate and right for **one** person named several
ways: "Law", "Bernard Law" and "Cardinal Bernard Law" is one man, and counting him
three times inflated a 4-stop tour to nine people (D585).

It is wrong when **two different people share a surname**. CHURCH_1's memorial passage:

> *"the tragic murder of three longtime congregants: Gilda "Jill" D'Amore, her
> husband Bruno D'Amore, and Jill's mother, Lucia Arpino"*

Three victims. The old surname key folded Bruno into Gilda and returned 15. LOCAL-542
diagnosed this and left it deliberately, rather than break the de-dup that makes the
common case right (SUBMISSION_LOCAL-542.md, reconciliation item 1).

## The fix — distinguish "one person, several forms" from "two people, one surname"

The mechanism stays surname-keyed; it now looks **inside** each surname group at the
**given-name sequence**. Every form reduces to a *core* — its tokens with titles
removed (`_PERSON_TITLE_WORD`), ending in the shared surname. The tokens before the
surname are the given name(s). Within a surname group:

- forms whose given-name sequences are **prefix-compatible** are the **same person** —
  a bare surname (`Law`), a first+surname (`Bernard Law`) and a fuller form
  (`Bernard F. Law`) all nest, so they cluster into one and D585 is preserved intact;
- forms whose given-name sequences **conflict** — neither a prefix of the other, e.g.
  **Gilda** vs **Bruno** under *D'Amore*, or **James** vs **Margaret** under *Murphy* —
  are **different people**, and each seeds its own cluster.

One representative (the fullest form) survives per cluster. The cross-surname prefix
subsumption LOCAL-542 relies on (a bare given name that is the prefix of a fuller name
under a *different* surname key — "Sean" under "Archbishop Sean O'Malley") is kept,
now applied across cluster representatives.

### Why this is not "keying on the full name" (which would revert D585)

The task warns explicitly: *do not simply key on the full name instead of the surname —
that reverts D585 and re-inflates Law/Bernard Law/Cardinal Bernard Law to three.* This
fix does not do that. The surname is still the grouping key; a split happens **only**
on a genuine given-name conflict. The three Law forms carry no conflicting given name
(one is bare, the others extend "Bernard"), so they stay one. The two behaviours
coexist — which is the whole difficulty and the whole task.

### Why this succeeds where LOCAL-542's `(given, surname)` attempt failed

LOCAL-542 reported it built a `(given, surname)` variant that reached CHURCH_1 → 16 but
**split LOGAN_1 back to 5**, because "General Edward Lawrence Logan" and "Edward
Lawrence Logan" acquired different phantom surnames once a middle token was treated as
the surname. This fix avoids that trap two ways: (1) the surname is always the **last**
token, never a middle one; (2) titles/ranks ("General") are stripped before comparison,
so "General Edward Lawrence Logan" and "Edward Lawrence Logan" have the identical core
`(edward, lawrence, logan)` and prefix-unify into one person. LOGAN_1 therefore holds
at 4 — verified below.

### The text carries the signal this keys on

The ticket notes the text "usually says which": *"her husband Bruno D'Amore"* and
*"Jill's mother, Lucia Arpino"* carry explicit relations, and the list is introduced by
a count (*"three longtime congregants:"*). The given-name conflict is the structural
footprint of exactly those signals — a tour writes a **new** given name precisely when
it means a **new** person. Keying on the conflict rather than parsing each relational
phrase ("her husband", "Jill's mother") keeps the rule a closed structural test, not a
hand-listed vocabulary of kinship words (the D476 enumeration trap).

## Acceptance evidence

### 1. CHURCH_1 returns 16, both D'Amores named

The 16 people returned (verbatim from the run):

    Bernard Law, Bruno D'Amore, Deacon Jim, Don Bosco, Eric Boeglin,
    Gilda "Jill" D'Amore, James Murphy, Jean Bazaine, John Chrysostom,
    Lucia Arpino, Monsignor Capik, Mother Teresa, Patrick Keely,
    Rev. Walter H. Cuenin, Timothy Danahy, Vincent Pallotti

Both **Gilda "Jill" D'Amore** and **Bruno D'Amore** appear, and *Law* is a single
entry. This is 16 of the critique's 17. The one remaining miss is **Christopher
Ferguson** — introduced by a bare active verb (*"Authorities arrested Christopher
Ferguson"*) that shares no structural signal with scenery; catching him needs a verb
list, the D476 trap LOCAL-542 documented and the ticket explicitly says not to chase.

### 2. The D585 de-duplication still holds

Test `test_same_surname_forms_are_one_person`
(`tests/test_local546_surname_collision.py`) asserts "Law", "Bernard Law" and
"Cardinal Bernard Law" in one text count as **one** person. In the real corpus this
three-form pattern occurs in **round9/CHURCH_1.txt** (Bernard Law / Cardinal Bernard
Law), and the full "Law" / "Bernard Law" / "Cardinal Bernard Law" / "Cardinal Law"
spread occurs in **round3/CHURCH_2.txt, round6/CHURCH_1.txt, round7/CHURCH_2.txt,
round2/CHURCH_3.txt, round5/CHURCH_3.txt, buckets/CHURCH_4stops.txt,
buckets/CHURCH_6stops.txt, buckets/CHURCH_6stops_v2.txt** and most other CHURCH tours —
it is the single most common multi-form name in the corpus, and every one of those
files still counts it as one man (table below).

### 3. LOGAN_1 stays at exactly four

`Edward Lawrence Logan, Gustave Eiffel, John Therry, Trippe` — pinned by
`test_logan1_stays_at_four` in the new file and unchanged in the LOCAL-537/542 tests.
(The display form is "General Edward Lawrence Logan"; the title is stripped for
identity, so it is the same person the acceptance names.)

### 4. Tests

All 221 tour_quality-related tests pass (3 skipped, benign). The two pinned CHURCH_1
assertions were updated 15 → 16 (`test_local542::test_church1_round9_counts_sixteen`,
`test_local537::test_church1_round9_does_not_regress`); a new
`tests/test_local546_surname_collision.py` pins both halves of the coexistence, the
Murphy split, and LOGAN_1 = 4.

## Measured false-positive rate over the corpus

Same method as LOCAL-537/542: reconstruct the **old** counter (pure surname key +
cross-key prefix subsumption) and run both old and new over every tour file, so all
three tickets are comparable. The corpus now holds **49** `.txt` files (LOCAL-537/542
measured 48; `local540/LOGAN_1.txt` was added since). All 49 measured:

| file | old | new |
|---|---|---|
| CHURCH_tour_1.txt | 4 | 4 |
| CHURCH_tour_2.txt | 10 | 10 |
| CHURCH_tour_3.txt | 6 | 6 |
| LOGAN_handoff_1.txt | 1 | 1 |
| LOGAN_storyfirst_1.txt | 2 | 2 |
| LOGAN_tour_1.txt | 1 | 1 |
| LOGAN_tour_2.txt | 1 | 1 |
| LOGAN_tour_3.txt | 0 | 0 |
| buckets/CHURCH_4stops.txt | 7 | 7 |
| buckets/CHURCH_6stops.txt | 7 | 7 |
| **buckets/CHURCH_6stops_v2.txt** | **10** | **11** |
| local540/LOGAN_1.txt | 3 | 3 |
| round2/CHURCH_1.txt | 6 | 6 |
| round2/CHURCH_2.txt | 8 | 8 |
| round2/CHURCH_3.txt | 5 | 5 |
| round2/LOGAN_1.txt | 2 | 2 |
| round2/LOGAN_2.txt | 1 | 1 |
| round2/LOGAN_3.txt | 2 | 2 |
| round3/CHURCH_1.txt | 2 | 2 |
| round3/CHURCH_2.txt | 3 | 3 |
| round3/CHURCH_3.txt | 7 | 7 |
| round3/LOGAN_1.txt | 2 | 2 |
| round3/LOGAN_2.txt | 2 | 2 |
| round3/LOGAN_3.txt | 5 | 5 |
| round4/LOGAN_1.txt | 4 | 4 |
| round4/LOGAN_2.txt | 6 | 6 |
| round4/LOGAN_3.txt | 5 | 5 |
| round5/CHURCH_1.txt | 5 | 5 |
| round5/CHURCH_2.txt | 5 | 5 |
| round5/CHURCH_3.txt | 9 | 9 |
| round5/LOGAN_1.txt | 1 | 1 |
| round5/LOGAN_2.txt | 2 | 2 |
| round5/LOGAN_3.txt | 5 | 5 |
| round6/CHURCH_1.txt | 6 | 6 |
| round6/CHURCH_2.txt | 3 | 3 |
| round6/CHURCH_3.txt | 6 | 6 |
| round6/LOGAN_1.txt | 3 | 3 |
| round6/LOGAN_2.txt | 4 | 4 |
| round6/LOGAN_3.txt | 6 | 6 |
| round7/CHURCH_1.txt | 7 | 7 |
| round7/CHURCH_2.txt | 5 | 5 |
| round7/CHURCH_3.txt | 5 | 5 |
| round7/LOGAN_1.txt | 3 | 3 |
| round7/LOGAN_2.txt | 4 | 4 |
| round7/LOGAN_3.txt | 5 | 5 |
| round8/CHURCH_1.txt | 7 | 7 |
| round8/LOGAN_1.txt | 5 | 5 |
| **round9/CHURCH_1.txt** | **15** | **16** |
| round9/LOGAN_1.txt | 4 | 4 |

**Two files change, both +1. Every other count is identical** — including all of the
Law/Cuenin/Cox/Logan/Curley/Cushing/Teresa multi-form tours, which confirms the
name-form de-dup is untouched.

### The two splits are both true positives

| file | surname | forms found | verdict |
|---|---|---|---|
| round9/CHURCH_1.txt | D'Amore | `Gilda "Jill" D'Amore`, `Bruno D'Amore` | ✓ two people — *"her husband Bruno D'Amore"* |
| buckets/CHURCH_6stops_v2.txt | Murphy | `James Murphy`, `Margaret Murphy` | ✓ two people — *"architect James Murphy chose de[sign]…"* and *"…identified by Margaret Murphy from mem[ory]"* |

**Measured false-positive rate: 0 / 49 files.** No surname that denotes one person
(Law, Cuenin, Cox, Logan, Curley, Cushing, Teresa, Pius, Green, Reed, Kennedy, Daley,
Patrick, Winthrop, Fuller, …) was split.

## What I did not do

- **No verb list, no kinship-word list.** The split keys on a structural property
  (given-name conflict within a surname), not on parsing "husband"/"mother"/"wife".
- **Did not chase Christopher Ferguson.** He needs a bare-active-verb handle that is a
  verb list — the D476 trap the ticket names. He remains the one documented miss (17
  is the critique's figure; 16 is the reachable target the ticket sets).
- **Did not touch the tour files, DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md
  or .continuous_dev/STATUS.md.**

## Files changed

- `tour_quality.py` — `_count_people` de-dup rewritten to cluster by given-name
  conflict within each surname; cross-surname prefix subsumption preserved.
- `tests/test_local546_surname_collision.py` — new: split, de-dup, coexistence, LOGAN_1.
- `tests/test_local542_people_round2.py` — CHURCH_1 pin 15 → 16; added
  `test_both_damores_are_counted`; docstring updated.
- `tests/test_local537_prefix_blind.py` — CHURCH_1 regression pin 15 → 16; docstring
  updated.
