# LOCAL-529 - Jefferies / Jeffery / Jeffrey / Jeffries in one batch

**Agent:** Mac Mini Kiro
**Branch:** LOCAL-529-one-name-four-spellings
**Base:** storied

> **PARKED.** Filename deliberately outside the dispatcher glob so this does not
> auto-claim and spend. Rename to `new_kiro_session_is_required_LOCAL-529.md` to release it.

## Why

The critic found Logan's original airfield name spelled four ways across round 7:
**Jefferies, Jeffery, Jeffrey, Jeffries.** LOGAN_1 stop 4 says "marked Jeffrey
Field, as it was then known."

**Verified, and the sharpest case is within ONE file: LOGAN_1 contains both
"Jefferies" and "Jeffrey".** Counts across the batch: Jefferies (LOGAN_1 x1),
Jeffery (LOGAN_2 x2), Jeffrey (LOGAN_1 x1), Jeffries (LOGAN_3 x1). A listener who
hears two spellings in one tour has caught the system being careless.

This is deterministic and needs no grounding: within ONE tour, a proper noun should
be spelled one way. Pick the spelling the sources support; if they disagree, pick the
most frequent in the tour and normalise the rest.

Cheap, self-contained, and it removes a visible sloppiness the listener will notice
if two stops disagree.

**Source:** `CRITIQUE_ROUND7_517.md` - the second, independent critique of round 7.
It is evidence, not fact: the brief it was given contained a claim that turned out to
be wrong, and the critic correctly refused it. Verify each quote against the tour file
in `TOURS_FOR_REVIEW/round7/` before acting on it.

## Acceptance

- Near-identical proper nouns within a tour are normalised to one spelling.
- Genuinely distinct names are NOT merged - "Logan" and "Logan Airport" are not the
  same token, and two different people with similar surnames must survive.
- A test using the four real spellings.

## PROCESS

Write `SUBMISSION_LOCAL-529.md` recording what you changed and the evidence for it.
**`git add` and `git commit` on your branch before finishing** - verify with
`git rev-list --count storied..HEAD`; if it prints 0 you have delivered nothing.

Gemini is returning HTTP 402 (prepayment credits depleted). If your task needs a
grounded call, say so in the submission and deliver the offline part - do not
fabricate a verification run. OpenAI and Serper are up.

Do NOT edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md or
.continuous_dev/STATUS.md.
