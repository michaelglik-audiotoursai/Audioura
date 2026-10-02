# SUBMISSION LOCAL-542 — The people counter finds 8 where there are 17

**Agent:** Mac Mini Kiro
**Branch:** LOCAL-542-people-counter-round2
**Base:** storied = 43d407e (`git merge-base --is-ancestor 43d407e HEAD` → exit 0)

## Result in one line

`_count_people` on `TOURS_FOR_REVIEW/round9/CHURCH_1.txt` was **8**; it is now
**15**. `LOGAN_1` stays at exactly **4**. No net-new false positives appear on any
of the 48 tour files (full audit below).

## The 15 people CHURCH_1 now returns, reconciled against the critique's 17

The counter returns these 15 (verbatim from the run):

    Cardinal Bernard Law, Deacon Jim, Don Bosco, Eric Boeglin,
    Father Walter H. Cuenin, Gilda "Jill" D'Amore, James Murphy, Jean Bazaine,
    John Chrysostom, Lucia Arpino, Monsignor Capik, Mother Teresa, Patrick Keely,
    Timothy Danahy, Vincent Pallotti

`CRITIQUE_ROUND9_FACTS.md` enumerates 17:

    Jean Bazaine, Monsignor Capik, Mother Teresa, James Murphy, Patrick Keely,
    Timothy Danahy, Eric Boeglin, "Deacon Jim", Walter H. Cuenin,
    Cardinal Bernard Law, John Chrysostom, Don Bosco, Vincent Pallotti,
    Gilda "Jill" D'Amore, Bruno D'Amore, Lucia Arpino, Christopher Ferguson

Reconciliation — the two I do **not** return, and why:

1. **Bruno D'Amore.** He and Gilda "Jill" D'Amore share the surname *D'Amore*. The
   counter's identity is the surname — that is the mechanism that (correctly) folds
   *Law*, *Bernard Law*, and *Cardinal Bernard Law* into one man, and it is what the
   task's own LOGAN_1 acceptance ("Trippe" counted once) depends on. Two different
   people with the same surname therefore collapse to one. I built and measured a
   `(given, surname)` variant that separates the two D'Amores (CHURCH_1 → 16), but it
   **splits LOGAN_1 back to 5** — "General Edward Lawrence Logan" and "Edward Lawrence
   Logan" acquire different phantom surnames once a middle token is treated as the
   surname. Splitting same-surname people is not worth regressing the hard LOGAN_1
   requirement, so I kept surname identity and count the D'Amores as one. This is a
   principled consequence of the de-dup rule, not a blind miss.

2. **Christopher Ferguson.** Introduced by a bare active verb with no title and no
   role word: *"Authorities arrested Christopher Ferguson, a local resident…"*. I
   measured every structural handle for it (see "What I rejected"); each one either
   needs a verb list (the D476 trap) or drags in more false positives than it fixes.
   I left him uncounted rather than grow a list. Detail below.

On **"Deacon Jim"**: the task flags it as a half-name reasonable people could count
either way. I count it (1 of the 15). It is a real introduced person ("local artisans
Eric Boeglin and Deacon Jim"); "Deacon" is a title and "Jim" a given name, so the
counter keeps it. I have no basis to exclude it that would not also exclude other
single-token real names.

## What changed, and why it is not the enumeration trap

The task warns — correctly — that adding `authorities` / `figures` / `arrested` /
`described` to `_PERSON_ROLE` or the verb list repeats LOCAL-530's mistake a third
time. **I added no verb to any list.** Every new rule keys on a *grammatical
construction*. All are in `tour_quality.py`:

- **`_PERSON_AGENT` — the passive agent.** The construction *"<past participle> …
  by <Name>"* names the agent, whatever the verb. I match the verb as a **class** —
  any word ending `-ed`/`-en` — not from a list. This finds *"Designed by Jean
  Bazaine"*, *"first described by John Chrysostom"*, and *"propagated by figures like
  Don Bosco and Vincent Pallotti"* (the coordinated pair both count). It requires a
  two-token name, which is what keeps *"renamed … by These committees"* and *"by
  September"* out — I verified single-word agents are the entire false-positive
  population of a looser version and the two-token rule removes all of them.

- **`_PERSON_HON_INTRO` — a standalone honorific.** `Fr./Dr./Rev./Msgr.` before a
  full given+surname is a person (*"Fr. Timothy Danahy"*). The full-name requirement
  is why *"Rev. Parishioners"* and *"Fr. During the war"* are **not** counted.

- **`_PERSON_APPOS_LIST` — a role-noun apposition list.** *"three longtime
  congregants: Gilda "Jill" D'Amore, her husband Bruno D'Amore, and … Lucia
  Arpino"*. This is punctuation-driven (a collective role noun, a colon, a
  comma/"and" list), not a role-word enumeration.

- **`_PERSON_TITLED` — keep the title in the fullest form.** The old code ate the
  title and stored *"Teresa"*; it now keeps *"Mother Teresa"* (and *"Cardinal Bernard
  Law"*). Surname de-dup still folds these onto bare mentions, so no double count.

Supporting pieces, all closed grammatical classes rather than name lists:

- A name token may carry an internal apostrophe (*D'Amore*, *O'Brien*) and skip a
  quoted nickname (*Gilda "Jill" D'Amore*). Kept in a **separate** `_PNAME`/`_PNAME2`
  so LOCAL-537's tested `_NAME`/`_NAME2` behaviour is untouched.
- `_PERSON_LEAD_STOP`: a name never begins with a determiner/deictic (*These*,
  *Every*, *Inside*). This removes pre-existing FPs like "Inside".
- **Prefix subsumption**: a name whose token sequence (titles stripped) is a prefix
  of another's is the same person truncated — bare *"Sean"* folds into *"Archbishop
  Sean O'Malley"*, *"Edward Lawrence"* into *"Edward Lawrence Logan"*. This removes
  the double-counts a title/agent capture would otherwise create.
- `_PERSON_ORG_SUFFIX`: a small generative set of institution/collective head-nouns
  (*Architects*, *Administration*, *Corps*, *Parishioners*, …) — never a person's
  identifying token. This is the one place I list words; it is a *disqualifier* of a
  productive linguistic class (org/collective nouns), not the recall mechanism, and
  it is far shorter than the 40-word `_PERSON_ROLE` it lets me avoid extending.

**Is the fix a longer list?** No. Recall comes from four constructions, not from new
verbs or roles. The only list I grew is a disqualifier of organisation/collective
head-nouns, which shrinks false positives rather than chasing recall.

## Measured false-positive rate over all 48 files (matches LOCAL-537's format)

Every name the counter returns per file, marked **real person (✓)** or **false
positive (✗)**. "cosmetic" marks a name that is the same person as another entry with
a title reattached (no effect on the count).

Legend for the target pair is spelled out; other files list only the FPs to keep this
readable (every other name on those files was verified a real person).

**round9/CHURCH_1 [15]** — all ✓: Cardinal Bernard Law, Deacon Jim, Don Bosco, Eric
Boeglin, Father Walter H. Cuenin, Gilda "Jill" D'Amore, James Murphy, Jean Bazaine,
John Chrysostom, Lucia Arpino, Monsignor Capik, Mother Teresa, Patrick Keely, Timothy
Danahy, Vincent Pallotti. **0 false positives.**

**round9/LOGAN_1 [4]** — all ✓: General Edward Lawrence Logan, Gustave Eiffel, John
Therry, Trippe. (Eiffel and Therry are hallucinations in the source text but are
genuinely *named*, so counting them is correct — a grounding problem, not a counting
one, exactly as LOCAL-537 noted.) **0 false positives.**

False positives on the remaining 46 files (name → why it is an FP). **Every one of
these is pre-existing — present in the counter before this change** (confirmed by
diffing old vs new output on all 48 files); this change removed several and added
none:

| file | false positive | note |
|---|---|---|
| CHURCH_tour_2 | Meyer | bare surname, pre-existing |
| CHURCH_tour_3 | Saint Mother Teresa | cosmetic (double title on Mother Teresa) |
| buckets/CHURCH_6stops_v2 | Bishop. This | pre-existing (title + sentence start) |
| buckets/CHURCH_6stops_v2 | Jesus Christ | pre-existing (deity, not a tour person) |
| round2/CHURCH_1 | Rev.⏎Directions, Saint Anne, Saint Louis | pre-existing (titles + place/heading) |
| round2/LOGAN_1, LOGAN_3 | Operational Details | pre-existing heading |
| round3/LOGAN_3 | Jeffries Point | pre-existing place |
| round4/LOGAN_2 | Baggage Claim, Operational Details | pre-existing headings |
| round4/LOGAN_3 | United States Army | pre-existing org |
| round5/CHURCH_1 | Mary | pre-existing (Marian title) |
| round5/LOGAN_3 | Desmond, Skanska | pre-existing (firm names) |
| round6/CHURCH_1 | Maria | pre-existing |
| round6/CHURCH_3 | Saint Mary | pre-existing (Marian title) |
| round6/LOGAN_3 | London Heathrow | pre-existing place |
| round7/CHURCH_3 | Saint Mother Teresa | cosmetic double title |

Pre-existing FPs this change **removed** (net improvement): "Inside" (LOGAN_tour_2),
"Our Lady" (round3/CHURCH_3, round6/CHURCH_3), "The Cardinal" / "Cardinal" (round5,
round6), "Parishioners" (CHURCH_tour_2), and several bare-token duplicates ("Bernard"
folded into Cardinal Bernard Law) via prefix subsumption.

**Corpus totals:** distinct people counted rose from 220 → 224 across the 48 files.
Every per-file delta was verified to be either a real person gained (Don Bosco, John
Chrysostom, Luis Vidal, Jean Bazaine, Timothy Danahy, Vincent Pallotti, Lucia Arpino,
Gilda D'Amore, Archbishop O'Malley) or an FP/duplicate removed — **no file gained a
new false positive.**

## What I rejected, and why (so the next round need not re-derive it)

- **A bare "by <Name>" rule** (no participle): finds the targets but also "by
  September", "by Your", "by Skanska". The participle requirement is what discriminates.
- **The flip — count every capitalised 2-token phrase minus a blocklist**: floods with
  "Baggage Claim", "Control Tower", "Army Air Corps", "New York". Filtering that is a
  bigger, more brittle list than the one it replaces — the enumeration trap mirrored.
- **Active verb + name for Ferguson** (*"arrested Christopher Ferguson"*): measured
  across all 48 files it returns "Operational Details" (93×), "Stained Glass Windows",
  "Terminal A. Walk" and other headings/places; Ferguson is one match buried in noise.
  Not viable without a verb list.
- **Indefinite appositive** *"Name, a/an <noun>"* (would catch *"Ferguson, a local
  resident"*): catches Ferguson **and 4 other real people**, but reintroduces place/org
  FPs ("Baggage Claim", "Mary Help", "Jeffries Point", "Every July") that then require
  re-growing the disqualifier list. It regressed LOGAN_1 to 5. Net-negative, rejected.
  **This is why Ferguson is left uncounted.**

## Effect on the D584 person-cap (checked, per the acceptance criterion)

**My change does not touch the D584 person-cap.** `cap_person_across_stops`
(`derepetition_guard.py`) and `_count_people` (`tour_quality.py`) **share no code**:

- The cap extracts names with `derepetition_guard._entity_year_key` / `_person_names`,
  a different code path from `_PERSON`/`_count_people`. It caps how many **stops** one
  surname may appear in (≤ 2). It never reads the scorer's total. Raising the scorer's
  count from 8 to 15 changes nothing the cap looks at.
- The tests prove this: `tests/test_d584_person_cap.py` and `test_local532_event_repeat.py`
  pass unchanged (208 person/tour tests pass; see below).

The scorer's `named_people` metric has two consumers, and I checked both:
1. `score_tour`: `named_people == 0` → `no_story` defect. My change only ever *raises*
   the count, so it can never newly trigger `no_story`.
2. `score_dir`'s cross-variant consistency heuristic: `consistent = all_clean and
   min(people) > 0 and (max−min) ≤ 2`. This compares the *spread* of `named_people`
   across sibling variants; it is a reporting heuristic, **not** the D584 cap. Because
   the counter now measures every variant more completely, a batch whose variants
   genuinely differ in person density will show that difference rather than hide it
   behind a shared undercount. That is the metric doing its job, not a cap tripping.
   No numeric cap is tuned against the old "8".

## Tests

- Updated the two assertions that pinned the old undercounts (as LOCAL-537 did when it
  moved 7→8): `test_church1_round9_does_not_regress` 8→15 with the Ferguson/D'Amore
  reconciliation in the docstring; `test_round7_counts_are_stable[CHURCH_1]` 5→7
  (Don Bosco + John Chrysostom, both real, via the agent rule).
- Added `tests/test_local542_people_round2.py`: pins the four new constructions from
  the real file (passive agent incl. the coordinated pair, bare honorific, apposition
  list, kept title), the negative cases (`by These`, `Rev. Parishioners`, `Fr.
  During`), the acceptance counts (CHURCH_1 = 15, LOGAN_1 = 4), and the documented
  Ferguson miss.
- **208 passed, 2 skipped** across every test that imports `tour_quality` or
  `derepetition_guard` (the person counter, the D584 cap, event-repeat, closing-recap,
  fabricated-attribution, offsite-entity, cross-stop-facts). Command:
  `pytest $(grep -rl 'tour_quality\|derepetition_guard\|_count_people' tests/*.py)`.
  (37 unrelated web-scraper test modules fail to *collect* on this machine for lack of
  `selenium`; that is pre-existing and independent of this change.)

## Files changed

- `tour_quality.py` — new patterns (`_PERSON_AGENT`, `_PERSON_HON_INTRO`,
  `_PERSON_APPOS_LIST`, `_PERSON_TITLED`), separate apostrophe-aware `_PNAME`/`_PNAME2`,
  disqualifier sets (`_PERSON_ORG_SUFFIX`, `_PERSON_LEAD_STOP`, `_PERSON_TITLE_WORD`),
  and a rewritten `_count_people` with prefix subsumption.
- `tests/test_local537_prefix_blind.py`, `tests/test_d585_person_counter.py` — updated
  the two pinned counts to the corrected numbers.
- `tests/test_local542_people_round2.py` — new.
