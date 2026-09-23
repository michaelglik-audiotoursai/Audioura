# LOCAL-530 - A verb followed by a preposition with the noun deleted

**Agent:** Mac Mini Kiro
**Branch:** LOCAL-530-mangled-sentence-missing-noun
**Base:** storied

> **PARKED.** Filename deliberately outside the dispatcher glob so this does not
> auto-claim and spend. Rename to `new_kiro_session_is_required_LOCAL-530.md` to release it.

## Why

LOGAN_2 stop 4, verbatim: **"They authorized of Public Works to lease this land to
the U.S. Army"** - the subject noun is gone ("[the Department] of Public Works").

`tour_quality._MANGLED` already exists and catches a doubled preposition
(`(?:engaged|which|that|and|of)\s+of\s+[A-Z]`). It does not catch a VERB followed
directly by "of" where the noun was dropped.

Note the shape: this is the same family as D583, where a gate deleted a span and
closed the gap badly. Check whether a gate removed the noun here before assuming the
model wrote it that way - see the D583 commit for the method.

**Source:** `CRITIQUE_ROUND7_517.md` - the second, independent critique of round 7.
It is evidence, not fact: the brief it was given contained a claim that turned out to
be wrong, and the critic correctly refused it. Verify each quote against the tour file
in `TOURS_FOR_REVIEW/round7/` before acting on it.

## Acceptance

- The real sentence is detected as a defect.
- If a gate is deleting the noun, fix the gate; if the model wrote it, detect and
  regenerate.
- No false positives across TOURS_FOR_REVIEW - report the scan, do not assert it.

## PROCESS

Write `SUBMISSION_LOCAL-530.md` recording what you changed and the evidence for it.
**`git add` and `git commit` on your branch before finishing** - verify with
`git rev-list --count storied..HEAD`; if it prints 0 you have delivered nothing.

Gemini is returning HTTP 402 (prepayment credits depleted). If your task needs a
grounded call, say so in the submission and deliver the offline part - do not
fabricate a verification run. OpenAI and Serper are up.

Do NOT edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md or
.continuous_dev/STATUS.md.
