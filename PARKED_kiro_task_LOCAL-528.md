# LOCAL-528 - Airport-origin stories bolted onto a jetbridge

**Agent:** Mac Mini Kiro
**Branch:** LOCAL-528-content-assigned-to-wrong-structure
**Base:** storied

> **PARKED.** Filename deliberately outside the dispatcher glob so this does not
> auto-claim and spend. Rename to `new_kiro_session_is_required_LOCAL-528.md` to release it.

## Why

The critic on LOGAN_1 stop 3: a jetbridge is a boarding bridge attached to a gate,
and the stop says Lindbergh "touched down... on the tarmac just beyond the bridge."
**Jetbridges did not exist in the 1920s.** LOGAN_2 stop 3 has the same shape -
1632 land grants and Fort Winthrop assigned to a boarding bridge.

This is D571's venue-parts problem in reverse: the parts were chosen correctly, then
filled with material belonging to the venue as a whole. A stop about a jetbridge that
says nothing about jetbridges is padding, however interesting the anecdote is.

Related and already fixed differently: D584 caps one PERSON across stops. This is
about a STORY landing on a part it cannot belong to.

**Source:** `CRITIQUE_ROUND7_517.md` - the second, independent critique of round 7.
It is evidence, not fact: the brief it was given contained a claim that turned out to
be wrong, and the critic correctly refused it. Verify each quote against the tour file
in `TOURS_FOR_REVIEW/round7/` before acting on it.

## Acceptance

- A date-vs-part anachronism check: material predating the part's existence is not
  assigned to it.
- Applies generally, not to jetbridges - a 1632 land grant cannot sit on a 1970s
  concourse any more than on a jetbridge.
- Tests from the two real LOGAN stops.

## PROCESS

Write `SUBMISSION_LOCAL-528.md` recording what you changed and the evidence for it.
**`git add` and `git commit` on your branch before finishing** - verify with
`git rev-list --count storied..HEAD`; if it prints 0 you have delivered nothing.

Gemini is returning HTTP 402 (prepayment credits depleted). If your task needs a
grounded call, say so in the submission and deliver the offline part - do not
fabricate a verification run. OpenAI and Serper are up.

Do NOT edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md or
.continuous_dev/STATUS.md.
