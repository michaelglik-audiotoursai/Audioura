**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-223
**Base:** storied
**Branch:** kiro/local223-theme-threads

# ⛔ PARKED — do not start until LEAD moves this to `new_kiro_session_is_required_LOCAL-223.md`

Held back deliberately: Michael is running a read-evaluation of
`RIVIERA_2STOP_ROUND2.md`. Landing a change this large in the generation path
while he is reading would mean he evaluates one system and comments on another.
LEAD unparks it once that evaluation is done.

---

# Theme threads: the one thing a phone camera cannot do

Read `STORY_QUALITY_DESIGN.md` **§SQ-S6b** (the full spec — Michael wrote it
2026-07-07 and it has never been built), `DECISIONS.md` **D101**,
`EVALUATION_BY_MICHAEL_RIVIERA_2STOP.txt`.

## ⚠️ NO container rebuilds (D48). Ceiling **$0.50**.
Do not modify the detectors, `claim_check.py`, or `corpus_coverage.py` (D55).
Do not edit `DECISIONS.md`, `CLAUDE.md`, `.continuous_dev/*`.

## Why this and why now

Michael, 2026-08-04, on why anyone would use our tour at all:

> *"Lena said she would not use any museum tour because nowadays she can ask
> Google about any painting by pointing her phone camera at it and get precise
> factual information. I said that she can, but then this information will be
> out of context of her tour, her interests, and will be dry."*

Point-and-ask already beats us on isolated facts, for free. Three things make a
tour worth using instead: the information is **correct**, it **fits the
listener**, and it **connects across stops**. The first has four rounds of work
behind it. The third has none — and it is the one a camera cannot replicate.

The symptom, from his own marks: both connective sentences scored **0/5**, and
his reason was that they *"can be placed in millions of stops."* A generic
transition is what a tour produces when it has no thread to carry.

## Scope — discovery and scoring only. Do not touch narration yet.

§SQ-S6b specifies more than one task can hold. Build the first half:

1. **Cross-stop element clustering** — deterministic first: group story
   elements from `stop_corpus` across stops by shared entities, people, eras,
   motifs. No LLM in this step.
2. **One grounded LLM pass to NAME candidate themes**, which must cite the
   element IDs supporting each. A theme is a claim and obeys claim rules — an
   uncited theme is an invented one (B3).
3. **Score each theme** on the four axes in the spec: coverage (fraction of
   stops with ≥1 supporting element), evidence strength, distinctiveness, arc
   potential.
4. **Emit the ranked threads with their coverage weights** — do not wire them
   into generation. That is the next task.

## The worked example is your acceptance test

Michael verified this himself on 2026-07-07, on the Nice walking tour:

> thread **"An Italian city that became French"** covers **7/7 stops** — Vieux
> Nice, Place Masséna (Turin-style ochre arcades), Castle Hill (Savoyard
> citadel razed 1706), Port Lympia (Sardinian-era harbour), Cours Saleya
> (Ligurian market culture), Promenade des Anglais (renamed at the 1860 Treaty
> of Turin), Promenade du Paillon.
>
> Alternates from the same elements: *"a city built by winters"*, *"walked by
> seekers of light"*.

**Run your discovery over that venue and report what it finds.** If it does not
surface something recognisably like his thread, say so and show what it found
instead — that is a more useful result than a thread that looks plausible and
was not derived from the elements.

## Degradation is part of the spec, not an afterthought

> *"no theme reaches ~60% coverage → organizing-principle fallback
> (chronological or geographic), else honest mosaic mode. A forced theme is an
> invented claim and violates B3."*

Implement the fallback and show it firing on a venue with thin corpus. **A
forced theme is worse than no theme** — it is a fabrication at the structural
level, harder to spot than a wrong date and just as damaging.

## Traps

- **Coverage is not co-occurrence.** Two stops mentioning "Nice" do not share a
  theme. This project has produced false links from keyword overlap three times
  (LOCAL-178, D62, D74). The clustering must be about entities and events, and
  you must show the elements behind each claimed link.
- **Do not blend threads yet.** Michael's multi-thread weighting (7/16, 5/16,
  4/16) is the *next* task; produce the ranked list it will consume.
- `audio_tours` at **130** — report before and after. Nice list
  `[1,12,14,17,21,24,27,28,29,152]` unchanged. Never `DELETE FROM audio_tours`.

## Acceptance criteria

- Deterministic clustering, then one cited LLM naming pass.
- Themes scored on all four axes, ranked, with coverage weights.
- Run over the Nice walking tour, compared against Michael's 7/7 thread.
- Run over at least two other venues, including one where degradation fires.
- Every claimed stop-to-theme link shown with the element behind it.
- Nothing wired into narration.
- `git status --short` clean. No container rebuilt.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
**Run every example you paste and confirm the output matches** (D97, D103).
A curated test set does not substitute for a measurement over stored data (D98).
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-223.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
