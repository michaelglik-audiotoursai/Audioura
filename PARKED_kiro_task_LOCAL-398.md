# LOCAL-398 (PARKED — unpark when LOCAL-397 merges) — Earn the adjective or delete it

**Park reason:** same prose path as LOCAL-397 (story sourcing), in flight.

---

## Michael's ruling, 2026-08-11

> "We should be providing **context instead of describing what users should see** —
> that is annoying. I hate every time when I read '**intricate detail**' here and
> there: **why do you call something intricate and do not explain why it is so.**"

## Measured, in the current merged tour (812 words)

**17 empty evaluative adjectives — one every 48 words:**

| adjective | count | | adjective | count |
|---|---|---|---|---|
| seamless | 3 | | remarkable | 1 |
| intricate | 2 | | extraordinary | 1 |
| unique | 2 | | whimsical | 1 |
| striking | 1 | | vibrant | 1 |
| mesmerizing | 1 | | boundless | 1 |
| captivating | 1 | | thought-provoking | 1 |
| | | | dynamic | 1 |

Both `intricate` instances are the complaint verbatim:

> "Position yourself at the center of the exhibit to fully appreciate the
> **intricate details**…"
> "Stand close to observe the **intricate details** that unfold upon the pages…"

Neither says what is intricate about them.

## Part A — the earning-clause rule

**An evaluative adjective is a claim, and a claim needs its evidence.**

- Where the prose calls something intricate / striking / masterful / exquisite /
  remarkable / seamless / vibrant / mesmerizing / captivating / extraordinary /
  whimsical / boundless / thought-provoking / dynamic / unique, the same sentence
  (or the next) must say **what earns it**, from grounded material.
  - Not earned: "the intricate details of the lithographs"
  - Earned: "forty separate lithographic stones, each inked and pulled by hand at
    Mourlot Frères" — *if* the corpus supports it
- If no earning clause can be supplied from the grounding corpus, **delete the
  adjective**. The noun survives without it; the sentence is better.
- This runs as a gate on delivered text, in `prose_entity_grounding_gate.py`
  alongside the others, and last (D288). Log:
  `[LOCAL-398] unearned '<adjective>' in stop '<title>' — removed`

**Do not** simply delete every listed adjective unconditionally. An earned one is
good prose and is the point of the exercise.

## Part B — relevance test for story beats (D325)

Michael also warned that the widened corpus must not admit interesting-but-unrelated
material:

> "If the story is not connected with the stop, its author, the exhibit, it would
> feel like irrelevant… The story needs to widen his understanding of what he is
> seeing and provide the context."

Apply, in order, to every story beat before it reaches the prompt:

1. **Attachment** — does it concern this stop's work, its maker, publisher,
   printer, donor, or the exhibition's own subject? If not, drop it however
   interesting.
2. **Invisibility** — does it tell the listener something they cannot see from
   where they stand? If not, it is description, not story.
3. **Grounding** — is it supported by the retrieved corpus? If not, drop it.

Log rejections with the reason: `[LOCAL-398] beat rejected: '<beat>' — unattached`.

## Part B2 — a wrong fact CORRECTS the story; it does not delete it (Michael, D327)

> "If a fact is incorrect, let's say it was a wrong year when someone dies or met
> with someone else, that does not invalidate the whole story, just changes the
> correct date; **unless the date change makes the story unbelievable**: like
> someone met with someone after they died."

LEAD had specified verify-or-drop. That is too blunt and would throw away good
stories over a typo. The correct behaviour:

1. **Verification returns a correction, not a verdict.** If the corpus says 1938
   and the draft says 1939, rewrite it to 1938 and keep the story.
2. **Drop only on a coherence failure** — where the corrected fact makes the story
   impossible or absurd. Test the *relation*, not the digit:
   - a meeting dated after a participant's death
   - a collaboration dated before either party was born
   - a gift dated before the object existed
3. **If the corpus cannot confirm the fact at all** (not contradict — simply no
   support), the claim goes but the surrounding story may stay if the rest is
   supported. Do not delete a paragraph over one unsupported clause.
4. Log the distinction: `[LOCAL-398] corrected '<claim>' 1939->1938 source=…` vs
   `[LOCAL-398] dropped '<claim>' — coherence failure: meeting postdates death`.

**This is the difference between a fact-checker and a censor**, and it is why the
posthumous-Gris candidate is a good test: if Gris's death year verifies as 1927 and
the book as 1955, the story stands and is remarkable. If the death year came back
as 1957, the *story* collapses (you cannot posthumously publish a living man) —
that is a coherence failure, and the right response is to drop it. If instead the
book turned out to be 1953 rather than 1955, nothing collapses: correct the date
and keep the story.

## Part C — re-read the empty-sentence population (D324)

`EMPTY_SENTENCE_CLASSIFICATION.md` (LOCAL-375) classified 22.4% of
`empty_sentence_count` hits as "false positives — visual descriptions of artwork".
**By Michael's standard those are not false positives**; unexplained evaluative
description is the defect.

- Re-read that file's class-3 entries against the earning-clause rule and report
  how many would survive it. A sentence naming a technique *and* explaining it
  should survive; "the intricate details" should not.
- Report the revised class distribution. **Do not change the metric's
  reporting-only status in this task** — D295's threshold decision is Michael's,
  and it needs the revised numbers first.

## Acceptance — live, per D284, case-insensitive in python (D299), delivered text only (D312)

`Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA`, 8 requested:

- **Zero unearned evaluative adjectives.** For every one of the listed adjectives
  remaining in the delivered text, quote the sentence and its earning clause in the
  submission. LEAD will check each by hand.
- Every stop still has ≥1 story beat passing all three relevance tests, with the
  rejection log for anything dropped
- Revised class distribution for the LOCAL-375 population
- **Nothing regressed** — everything LOCAL-397 delivered plus: 3 stops incl.
  `Le Lézard aux plumes d'or`; `That's N stops` == heading count;
  `Broder`/`Mourlot`/`Fridman` in stop 1; `Miró` stop 1; `Dalí` and `Freud`
  stop 2; `Gris` and `Reverdy` stop 3; `livre d'artiste`, `collabor*`,
  `typography`, `book` present; every stop ≥250 words; ZERO
  `thesis`/`framing`/`premise` as narration and the full D305 zero-list

**Control (D302 + D320):** `Palais Lascaris, Nice, France` at 4 → 4/4 real
instruments, dates intact, `framing=venue_purpose`, **live base score reported**
(baseline 56.2; do not make it worse — and note this gate may *raise* it, since
unearned adjectives are part of what the scorer penalises).

Env: `DISABLE_TOUR_CACHE=1`,
`DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours`,
`STORIED_MODE=true`, plus `SERP_API_KEY`/`SERP_PROVIDER`.

## Tests

Expected red-on-revert count stated; revert breaks the **logic, not the symbol**
(D296). Required: a test that "the intricate details of the lithographs" loses its
adjective while "forty lithographic stones, each inked and pulled by hand" keeps
its earned one. **Test the gate on ordinary prose that must produce nothing**
(D311 — four detectors shipped false positives before this rule was adopted).

## PROCESS
- Branch `kiro/local398-earn-the-adjective` off `storied`.
- Write `SUBMISSION_LOCAL-398.md`.
- Do NOT edit DECISIONS.md / CLAUDE.md / BACKLOG.md / .continuous_dev/STATUS.md.
- Do NOT `DELETE FROM audio_tours`.
