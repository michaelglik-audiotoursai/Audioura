# SUBMISSION — LOCAL-537: the people counter only saw a person when a title preceded it

**Agent:** Mac Mini Kiro
**Branch:** LOCAL-537-people-counter-prefix-blind
**Base:** storied = 8fa0080 (`git merge-base --is-ancestor 8fa0080 HEAD` → exit 0)

---

## The defect, reproduced before touching anything

`_count_people` on the real `TOURS_FOR_REVIEW/round9/LOGAN_1.txt` returned **1**, for a
tour that names four people. Verified by running the shipped code:

```
$ python3 -c "import tour_quality as tq; print(tq._PERSON.findall(open('TOURS_FOR_REVIEW/round9/LOGAN_1.txt').read()))"
[('Edward Lawrence Logan',''), ('Court',''), ('Edward Lawrence Logan',''),
 ('Edward Lawrence Logan',''), ('Edward Lawrence Logan','Control Tower')]
```

(In this worktree `Court` and `Control Tower` are already discarded — `court` and
`tower` are in `derepetition_guard._NOT_PERSON` — so the old count was 1, not 2. The
double-counting-`Court` symptom named in the task had already been fixed here; the
*structural blindness* had not.)

The cause is structural. `_PERSON` fires only when a **title** or a **role word sits
immediately before** the name. Three shapes of a bare name are therefore invisible,
and LOGAN_1 has one of each:

| missed | verbatim text | why the old `_PERSON` could not see it |
|---|---|---|
| Gustave Eiffel | *"**Gustave Eiffel's** iconic Control Tower"* | possessive, no trigger word before it |
| Juan Trippe | *"**Trippe, the founder** and later Pan American World Airways"* | the occupation word *follows* the name |
| Fr John Therry | *"pioneer priest **Fr John Therry**"* | the role word *priest* IS present, but `_NAME` then has to start on the two-letter token `Fr`, which fails `[A-Z][a-z]{2,}`, so the whole match dies |

Diagnosis was confirmed per name, not inferred:

```
priest Fr John Therry   -> _PERSON.findall == []   ; _NAME on "Fr John Therry" == ["John Therry"]
Gustave Eiffel's ...     -> _PERSON.findall == []
Trippe, the founder ...  -> _PERSON.findall == []
```

---

## The change

All edits are in `tour_quality.py`. `derepetition_guard.py` was **not** touched.

1. **Honorific skip inside the introducer** (`_HONORIFIC`). Between a trigger word and
   the name, an optional `Fr|St|Ss|Mr|Mrs|Ms|Dr|Rev|Msgr|Sr|Jr|Prof` token may be
   stepped over so `_NAME` anchors on the real name (`priest Fr John Therry` →
   `John Therry`). It is *optional*, so a name with no honorific still matches.

2. **Possessive rule** (`_PERSON_POSSESSIVE`). A name in `'s` form is the same person
   as the bare form. It requires the **full given+surname** (`_NAME2`, two or more
   tokens). That single constraint is what stops it from turning `Mary's`,
   `Christ's`, `Peter's Basilica` and `That's 4 stops` into people — a bare
   single-token possessive is overwhelmingly a place, a dedication, or a pronoun.

3. **Appositive-after-name rule** (`_PERSON_APPOSITIVE`). `<Name>, (the|a|an)? <role>`
   — `Trippe, the founder`. An occupation after the name is as strong a signal as one
   before it (constraint 3).

4. De-dup is still by surname, so the possessive folds onto any bare mention and
   never double-counts (constraint 2): "Gustave Eiffel" and "Gustave Eiffel's" are
   one man.

5. `_count_people` now also tests `_NOT_A_NAME` on the **first** token, not only the
   surname — a possessive place phrase is betrayed by either end
   (`Boston Logan's` by its first word, `New England's` by its last).

### What I added to the existing lists (constraint 4), and the real text that motivated it

Extended `_NOT_A_NAME` (the tour_quality-local "capitalised token that is not a
personal name" set) — **not** a third list:

```
'boston','east','west','north','south','new','massachusetts',
'middlesex','england','globe','legislature','attorney','district'
```

Each is a token inside a possessive place/organisation phrase that the new
possessive rule would otherwise have counted. Verbatim sources, all from round7–9:

| added word(s) | verbatim possessive in the tours |
|---|---|
| `boston`, `east` | "Boston Logan's iconic …", "East Boston's tidal flats" |
| `new`, `england` | "New England's busiest …" |
| `massachusetts`, `legislature` | "Massachusetts Legislature's decision" |
| `boston`, `globe` | "Boston Globe's Spotlight" |
| `middlesex`, `district`, `attorney` | "Middlesex District Attorney's office" |

`logan` is **deliberately absent**: it is the surname of a real person, Major General
Edward Lawrence Logan — the airport's namesake. An earlier draft that blocked `logan`
re-hid the tour's central figure (dropped LOGAN_1 from 4 back to 3). This is why the
first-token place words (`boston`, `east`, `new`, `massachusetts`, `middlesex`) do the
work for phrases like "Boston Logan's": they reject the *phrase* without blacklisting
the surname.

I added **nothing** to `_NOT_PERSON` (see the cap section for why that matters).

---

## Measured false-positive table (constraint 1)

The new counter run over **every** tour in round7, round8 and round9, listing **every
name it returns per file**, each marked real person (✓) or false positive (✗). Names
verified against the surrounding sentence in each file.

| file | new count | names returned — all ✓, no ✗ |
|---|---|---|
| round7/CHURCH_1 | 5 | Cardinal Bernard Law ✓, Deacon Jim ✓, Eric Boeglin ✓, Father Walter Cuenin ✓, James Murphy ✓ |
| round7/CHURCH_2 | 5 | Bernard F. Law ✓, Deacon Jim ✓, Eric Boeglin ✓, Mother Teresa ✓, Walter H. Cuenin ✓ |
| round7/CHURCH_3 | 5 | James Murphy ✓, Law ✓ (Cardinal Bernard Law), Mother Teresa ✓, Sean ✓ (Archbishop Sean O'Malley, truncated at `O'`), Walter H. Cuenin ✓ |
| round7/LOGAN_1 | 3 | Channing H. Cox ✓, Charles Lindbergh ✓, Gustave Eiffel ✓ (a hallucination, but genuinely a named person in the text — counting him is correct; grounding is a separate concern, see LOCAL-527) |
| round7/LOGAN_2 | 4 | Curley ✓, Governor Cox ✓, Gustave Eiffel ✓, John Winthrop ✓ |
| round7/LOGAN_3 | 5 | Betty Ann Ong ✓, Channing H. Cox ✓, Edward Lawrence Logan ✓, Madeline Amy Sweeney ✓, Mohamed Atta ✓ |
| round8/CHURCH_1 | 7 | Bernard Law ✓, James Murphy ✓, Michael M. Green ✓, Monsignor Capik ✓, Mother Teresa ✓, Patrick Keely ✓, Walter H. Cuenin ✓ |
| round8/LOGAN_1 | 5 | Cesar Pelli ✓, Charles Lindbergh ✓, Gustave Eiffel ✓, James Michael Curley ✓, John Paul ✓ (Pope John Paul II) |
| round9/CHURCH_1 | 8 | Bernard Law ✓, Deacon Jim ✓, Eric Boeglin ✓, James Murphy ✓, Monsignor Capik ✓, Patrick Keely ✓, Teresa ✓ (Mother Teresa), Walter H. Cuenin ✓ |
| round9/LOGAN_1 | 4 | Edward Lawrence Logan ✓, Gustave Eiffel ✓, John Therry ✓, Trippe ✓ (Juan Trippe, truncated to surname) |

**Measured false-positive rate across all 10 files: 0/52 returned names.**

Names that are real people but shown truncated (`Law`, `Sean`, `Trippe`, `Teresa`,
`John Paul`) are still the *right count* — each is one distinct person, de-duplicated
by surname. Truncation of `O'Malley`/`D'Amore`-style apostrophe names into their given
name is a pre-existing `_NAME`-shape limitation, out of scope here and not a
false positive (the person is real).

### False positives that earlier drafts produced and this version eliminates

While iterating I measured what a naive possessive rule returns, and removed each:

| earlier FP | source text | how it is now excluded |
|---|---|---|
| `That` | "That's 4 stops" (every closing recap) | possessive requires 2+ tokens; `That` is one |
| `Mary` | "St. Mary's Cathedral", "Mary's intercession" | single token — rejected by 2-token rule |
| `Christ` | "Christ's Kingdom" | single token |
| `Peter` | "St. Peter's Basilica" | single token |
| `Boston Logan`, `East Boston` | "Boston Logan's …", "East Boston's …" | first token in `_NOT_A_NAME` |
| `New England` | "New England's busiest" | both tokens in `_NOT_A_NAME` |
| `Massachusetts Legislature` | "Massachusetts Legislature's decision" | both tokens in `_NOT_A_NAME` |
| `Boston Globe` | "Boston Globe's Spotlight" | first token in `_NOT_A_NAME` |
| `Middlesex District Attorney` | "Middlesex District Attorney's office" | all tokens in `_NOT_A_NAME` |

---

## Before / after per file

Old counter (`_PERSON` only, `_NOT_A_NAME` without the LOCAL-537 place words),
reconstructed and run on the same files:

| file | old | new | delta — what changed and why |
|---|---|---|---|
| round7/CHURCH_1 | 5 | 5 | no change |
| round7/CHURCH_2 | 5 | 5 | no change |
| round7/CHURCH_3 | 5 | 5 | no change |
| round7/LOGAN_1 | 3 | 3 | no change (pinned by test_d585) |
| round7/LOGAN_2 | 4 | 4 | no change (pinned) |
| round7/LOGAN_3 | 5 | 5 | no change (pinned) |
| round8/CHURCH_1 | 6 | 7 | **+Monsignor Capik** — "Monsignor **Capik's** 50th Anniversary", possessive-only, previously invisible. Real person. |
| round8/LOGAN_1 | 5 | 5 | no change |
| round9/CHURCH_1 | 7 | 8 | **+Patrick Keely** — "his mentor **Patrick Keely's** style", possessive-only. Real architect. Nothing removed. |
| round9/LOGAN_1 | 1 | 4 | **+Gustave Eiffel, +John Therry (Fr), +Trippe** — the three structural misses. This is the task target. |

Every increase is a real person the old instrument could not see; no file lost a
real person, and no file gained a false one.

### CHURCH_1 specifically (acceptance requirement)

- **round9/CHURCH_1: before 7, after 8.** Before:
  `Bernard Law, Deacon Jim, Eric Boeglin, James Murphy, Monsignor Capik, Teresa, Walter H. Cuenin`.
  After: the same seven **plus Patrick Keely**. The delta is one real person
  ("his mentor Patrick Keely's style") newly seen through the possessive rule.
  Justified as an improvement, not a regression — the set is a strict superset and
  every member is a real person.

---

## Effect on the D584 person-cap (checked, not assumed)

The task warned that a counter that suddenly finds four people where it found one may
trip a cap tuned against the old number. I checked; it does not.

- `cap_person_across_stops` (D584) does **not** consume `_count_people` or the
  `named_people` metric. It independently walks each stop, extracts surnames via
  `derepetition_guard._PROPER` / `_entity_year_key`, and caps any surname that carries
  more than `max_stops` (=2) stops. Its behaviour is a function of *how many stops a
  given person appears in*, never of the total headcount. Grep confirms no reference
  to `_count_people`/`named_people` anywhere in `derepetition_guard.py`.
- The only surface shared between the counter and the cap is `_NOT_PERSON`. I added
  **nothing** to `_NOT_PERSON`; the place words went into `_NOT_A_NAME`, which lives
  in `tour_quality.py` and which the cap never imports. Verified at runtime:
  `'boston' in derepetition_guard._NOT_PERSON` → `False`.
- `tests/test_d584_person_cap.py` passes unchanged (see below).

What the cap does now: exactly what it did before this task. It still caps a person
present in >2 stops, keeping the two earliest, never emptying a stop, never cutting a
recap sentence. My change to the *metric* does not reach it.

---

## Test evidence

New regression tests read the **verbatim** sentences from the real round9 files (they
`assert needle in text` first, so they fail loudly if the evidence ever changes) —
nothing is retyped:

`tests/test_local537_prefix_blind.py`

```
$ python3 -m pytest tests/test_local537_prefix_blind.py tests/test_d585_person_counter.py -q
21 passed
```

Full relevant suite (counter, cap, repetition, attribution, recap, substance):

```
$ python3 -m pytest tests/test_d584_person_cap.py tests/test_d585_person_counter.py \
    tests/test_local537_prefix_blind.py tests/test_local527_fabricated_attribution.py \
    tests/test_local530_verb_object_dropped.py tests/test_local532_event_repeat.py \
    tests/test_d533_cross_stop_facts.py tests/test_d534_any_repetition.py \
    tests/test_local280_closing_recap.py tests/test_local44_stop_preaching.py \
    tests/test_local48_substance_rebase.py -q
159 passed
```

The pre-existing `test_d585_person_counter.py` pins the round7 counts (CHURCH 5/5/5,
LOGAN 3/4/5); all still hold, so the fix is purely additive on those files.

---

## Files changed

- `tour_quality.py` — `_NAME2`, `_HONORIFIC`, honorific-skip in `_PERSON`,
  `_PERSON_POSSESSIVE`, `_PERSON_APPOSITIVE`, first-token `_NOT_A_NAME` check in
  `_count_people`, and the place-word additions to `_NOT_A_NAME`.
- `tests/test_local537_prefix_blind.py` — new regression tests, verbatim from the
  real files.
