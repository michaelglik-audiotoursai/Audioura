# LOCAL-531 - A stop that admits it has no content must never ship

**Agent:** Mac Mini Kiro
**Branch:** LOCAL-531-never-emit-a-placeholder-stop
**Base:** storied

> **PARKED.** Filename deliberately outside the dispatcher glob so this does not
> auto-claim and spend. Rename to `new_kiro_session_is_required_LOCAL-531.md` to release it.

## Why

LOGAN_3 stop 1, in full: **"Terminal A Ticketing / Check-In - an exhibit at this
venue. Detailed information was not available at generation time."**

The SCORER now catches this (D586, `defects['placeholder']`). That is detection after
the fact. **This task is about generation: find where that string is emitted and make
the pipeline either fill the stop or drop it.**

D577 says unverified content ships hedged and only refuted content is dropped - a
placeholder is neither. It is an admission of failure formatted as a stop, which is
the D582 defect class: a failure indistinguishable from success.

Note LOCAL-420 ("never ship an empty stop") already exists and is merged. Establish
why it did not fire here - an empty stop and a stop full of apology are the same
defect wearing different clothes.

**Source:** `CRITIQUE_ROUND7_517.md` - the second, independent critique of round 7.
It is evidence, not fact: the brief it was given contained a claim that turned out to
be wrong, and the critic correctly refused it. Verify each quote against the tour file
in `TOURS_FOR_REVIEW/round7/` before acting on it.

## Acceptance

- The emitting site is identified and named in the submission.
- A stop with no material is filled or dropped, never shipped as an apology.
- Explain the interaction with LOCAL-420 and with D584's never-empty-a-stop rule,
  which deliberately keeps a weak stop rather than deleting it. These can conflict;
  say which wins and why.

## PROCESS

Write `SUBMISSION_LOCAL-531.md` recording what you changed and the evidence for it.
**`git add` and `git commit` on your branch before finishing** - verify with
`git rev-list --count storied..HEAD`; if it prints 0 you have delivered nothing.

Gemini is returning HTTP 402 (prepayment credits depleted). If your task needs a
grounded call, say so in the submission and deliver the offline part - do not
fabricate a verification run. OpenAI and Serper are up.

Do NOT edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md or
.continuous_dev/STATUS.md.
