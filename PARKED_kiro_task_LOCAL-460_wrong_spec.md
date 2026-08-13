# TASK LOCAL-460 — build the interrogation matrix from a stop description alone

**Agent:** Mac Mini Kiro
**Branch:** LOCAL-460-interrogation-matrix
**Base:** storied

## What this is

Michael, 2026-08-13: before we can interrogate the internet for a story, we need to know
**what to ask about**. That is a small fixed matrix of roles. Everything needed to fill it
is already in the tour — no corpus, no search, no DB, no network.

**The matrix is not art-catalogue metadata.** The field names come from the museum case,
but each one is a UNIVERSAL ROLE that has a different filler per tour type. Getting this
abstraction right is the task; a version that only works on livres d'artiste is a failure.

| slot | what it actually is | livre d'artiste | painting | exhibition | restaurant | walking tour |
|---|---|---|---|---|---|---|
| `canonical_title` | the **smallest containing set** | the exhibition | the exhibition | the exhibition | whatever criteria the user gave | the smallest named area |
| `english_title` | that same name in English | translation | translation | translation | translation | translation |
| `artist` | the **principal** — the main person | the publisher | the painter | the lead artist | the chef | whoever is in charge |
| `publisher` | **who pays** — the investor | the publisher | the patron | the funder | the owner | the sponsor |
| `printed_by` | **who manufactured it** | the printer | the foundry/workshop | the curator | — | the builder/architect |
| `credit_line` | **the keyword the story will be built around** | see below | see below | see below | see below | see below |
| `medium` | the **listener's interest** / the excursion title | theme | theme | theme | theme | theme |
| `venue` | the location **one level above** `canonical_title` | the museum | the museum | the museum | the city | the city |

**Michael's own words for the tricky ones, quote them in the docstring:**

- *canonical_title*: "the name of the smallest set: Exhibition, if not, then the name of
  Museum, if not, then the name of state, etc. If this is a restaurant tour, then whatever
  the user specified as the criteria for restaurant, if not the smallest area, if not then
  province, if not then the country."
- *english_title*: "the translation of canonical_title into English, as most of the trusted
  sources are in English."
- *artist*: "the main person for the exhibit: for livre d'artiste it is the publisher, for
  painting it is the painter, for restaurant is the chef, for walking tour — whoever is in
  charge."
- *publisher*: "the publisher for livre d'artiste, for a restaurant it is the owner (as this
  position is basically an investor: who pays)."
- *credit_line*: "the keyword for which we will produce the story, taken from the sentences
  we want to fulfill."
- *printed_by*: "manufacture; for Exhibition is curator, for livre d'artiste is the printer."
- *medium*: "the title for excursion, whatever interests are named by the listener."
- *venue*: "the location above canonical_title."

**Note the fall-through.** `canonical_title` is a LADDER, not a lookup: exhibition → museum
→ city → state → country, take the first that is identifiable. Same for a restaurant tour:
user criteria → smallest area → province → country. Implement it as an ordered ladder with
the rung recorded, so the caller knows how tight the scope is.

## Two things that are NOT the same, keep them separate

1. `canonical_title` is the **scope** — the smallest containing set. For MFA stop 2 that is
   *"Picasso, Miró, Dalí: Unbound"*, **not** *"Moses and Monotheism"*.
2. The stop's own subject still matters. Add a separate `stop_subject` field for the work
   or place the stop is about. Do not overload `canonical_title` with it and do not drop it.

## `credit_line` — the one that needs real thought

It is the keyword the story will be built around, "taken from the sentences we want to
fulfill". `story_opportunity_scan.py` (repo root, committed) already finds exactly these:
handles the delivered text NAMES and then FAILS TO DEVELOP, classified DEVELOPED / FLAT /
MENTIONED / DANGLING. **Use it — import it, do not reimplement it.** The best `credit_line`
is the highest-value non-DEVELOPED handle: prefer FLAT (an established subject carrying no
stakes), then MENTIONED, then DANGLING.

## Every field must carry provenance, never a bare value

`story_record_extract.py` (repo root, committed) sets the pattern and you should follow it:
every slot is `{value, status, source, rung}` where status is one of

```
STRUCTURAL   read off the tour's own scaffolding (headings, Address, Directions)
CLAIMED      the prose asserts it and nothing has checked it
DERIVED      inferred from tour type + ladder position
ABSENT       the stop description does not contain it
```

**A CLAIMED value is a question to go answer, not a fact.** This is not stylistic. Reading
MFA stop 2 naively yields `publisher = The Hogarth Press`, which is a fabrication the tour
shipped (D427/D435); promoting it to a bare value launders an invention into a search key.

## Input and output

Input: the stop description text as delivered, plus optional `tour_type` and
`user_interests` hints when the caller has them. **Nothing else. No network, no DB, no
corpus, no API key.** The routine must run offline and deterministically.

Suggested module: `interrogation_matrix.py` at repo root, with

```python
def build_matrix(stop_text: str, tour_type: str = '', user_interests: str = '',
                 tour_context: str = '') -> Dict[str, Dict]
```

plus a CLI mirroring `story_record_extract.py --text-file … `.

`tour_context` is the rest of the tour when available — the ladder often needs it, since a
single stop may not name its own museum while the tour header does.

## Acceptance criteria — it must generalise across all three tour types

Run against the real tours in the repo. These are the same nine stops LEAD swept in D433:

| tour file | type | stops |
|---|---|---|
| `TOUR_MFA_20260812_2030.txt` | museum exhibition | 1, 2, 3 |
| `fruitlands_museum_tour.txt` | museum, no exhibition scope | 1, 2, 3 |
| `Beacon_Hill__Boston_walking_tour_20260714_135649.txt` | walking tour | 1, 2, 3 |

1. **MFA stop 2**: `canonical_title` resolves to the exhibition if the tour names it, else
   falls to the museum with the rung recorded. `stop_subject = Moses and Monotheism`.
   `artist` and `publisher` are populated **and both marked CLAIMED** — `publisher` is
   `The Hogarth Press`, which is false, and the matrix must say CLAIMED, never GROUNDED.
2. **Fruitlands stops**: the ladder must fall through to the museum — there is no
   exhibition — and record which rung it landed on. A matrix that returns ABSENT here
   because it only knows how to find exhibitions has not generalised.
3. **Beacon Hill stops**: `artist` maps to "whoever is in charge" and `venue` to the city.
   ABSENT is a correct answer for `printed_by` on a walking tour — do not invent a filler.
4. `credit_line` is a real handle from `story_opportunity_scan` for all nine stops, and is
   never a DEVELOPED handle.
5. Print a coverage table over all nine: slot × status. Say plainly how many slots are
   ABSENT per tour type. **A low number is not the goal — an honest number is.**

## ⚠ THE TEST MUST BE ABLE TO FAIL, AND THE FIXTURES ARE NOT YOURS TO EDIT

Three tasks in a row have failed here. Read this twice.

- D418/D421 (LOCAL-453, LOCAL-454): suites that passed with the production logic
  neutralised, because they source-grepped instead of calling anything.
- **D432 (LOCAL-459): the acceptance fixture was REPLACED with a generated one — 81 of 104
  URLs invented — and three of the five quoted result sentences did not exist.** The code
  was fine and would have passed against the truth.

Binding, and LEAD will check all of it:

- **You may not modify any tour file, any file under `story_lab_state/`, or any other
  fixture you are judged against.** If a fixture looks wrong, say so in the submission and
  stop. Evidence is not an input to be tuned.
- `build_matrix` must be callable at module scope with a plain string. No network, no key.
- **Neutralise your own routine** (make it return empty slots), run the suite, paste the
  FAILING output. Restore, paste the passing output.
- Assert on values and statuses you extract at runtime, never on constants copied from this
  document.

## PROCESS

- Work ONLY in your worktree on branch `LOCAL-460-interrogation-matrix`.
- Do NOT edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`.
- Do NOT edit `story_opportunity_scan.py`, `story_material_check.py`, `story_writer.py`,
  `story_record_extract.py`, `story_sweep.py`, `story_claim_lab.py` — Michael and LEAD are
  working in those. Import them, verify against them, leave them alone.
- Record reasoning in `SUBMISSION_LOCAL-460.md` at the worktree root.
- No `DELETE FROM audio_tours`, ever.
- Commit at least once (`git rev-list --count storied..HEAD >= 1`).
- Run every test you cite and paste the real output. "Unproven, handing to LEAD" is always
  acceptable; "all pass" when one does not is not.
