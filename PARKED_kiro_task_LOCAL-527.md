# LOCAL-527 - An orientation invented the Eiffel Tower inside an airport tour

**Agent:** Mac Mini Kiro
**Branch:** LOCAL-527-orientation-describes-another-stop
**Base:** storied

> **PARKED.** Filename deliberately outside the dispatcher glob so this does not
> auto-claim and spend. Rename to `new_kiro_session_is_required_LOCAL-527.md` to release it.

## Why

LOGAN_1 stop 1 and LOGAN_2 stop 1 both open with the Control Tower described as
"a historic structure constructed in 1887-1889 by Gustave Eiffel." That is the
Eiffel Tower. Two things are wrong at once and BOTH matter:

1. It is a fabrication, and it is in the ORIENTATION - the first thing the listener
   hears at the first stop.
2. It describes the **Control Tower, which is stop 4**, in the orientation for
   **stop 1**. The orientation is supposed to tell the listener what they are
   standing in front of.

I checked for a hardcoded template: there is none. `grep -rn "Eiffel" *.py` finds
only the unrelated "Tour Eiffel, Paris" place-name test. So this is model output,
not a paste - the critic's "boilerplate template value" claim is INFERRED and wrong.

**Find out why a stop-1 orientation is describing a later stop's structure**, and
gate it. A stop's orientation must be about that stop.

**Source:** `CRITIQUE_ROUND7_517.md` - the second, independent critique of round 7.
It is evidence, not fact: the brief it was given contained a claim that turned out to
be wrong, and the critic correctly refused it. Verify each quote against the tour file
in `TOURS_FOR_REVIEW/round7/` before acting on it.

## Acceptance

- An orientation naming a *different* stop's subject is detected and regenerated
  or dropped.
- A regression test built from the two real LOGAN orientations, verbatim.
- State plainly whether the fabrication itself can be caught without a grounded
  call. If it cannot, say so - that is a useful answer (D577).

## PROCESS

Write `SUBMISSION_LOCAL-527.md` recording what you changed and the evidence for it.
**`git add` and `git commit` on your branch before finishing** - verify with
`git rev-list --count storied..HEAD`; if it prints 0 you have delivered nothing.

Gemini is returning HTTP 402 (prepayment credits depleted). If your task needs a
grounded call, say so in the submission and deliver the offline part - do not
fabricate a verification run. OpenAI and Serper are up.

Do NOT edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md or
.continuous_dev/STATUS.md.
