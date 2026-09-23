# LOCAL-532 - LOGAN_1 spends Lindbergh in two of four stops

**Agent:** Mac Mini Kiro
**Branch:** LOCAL-532-best-anecdote-told-twice
**Base:** storied

> **PARKED.** Filename deliberately outside the dispatcher glob so this does not
> auto-claim and spend. Rename to `new_kiro_session_is_required_LOCAL-532.md` to release it.

## Why

The critic: "Lindbergh appears in two of four stops - the file tells its single best
anecdote twice."

**I verified this and the critic UNDERCOUNTED. Lindbergh is in stops 1, 3 AND 4 -
three of four.** Check it yourself:

    python3 -c "import re; t=open('TOURS_FOR_REVIEW/round7/LOGAN_1.txt').read(); \
      print([i+1 for i,p in enumerate(re.split(r'^Stop \\d+:',t,flags=re.M)[1:]) if 'Lindbergh' in p])"
    -> [1, 3, 4]

So the tour spends its single best anecdote three times in four stops.

`cap_person_across_stops` (D584) allows a person in up to 2 stops, so it permits this
by design. `strip_cross_stop_repeats` matches on person AND year - if the two tellings
carry different years or no year, it sees two separate episodes.

The unit being repeated here is an EVENT, not a person: one landing, told twice. A
tour with four stops and one good story should spend it once.

**Source:** `CRITIQUE_ROUND7_517.md` - the second, independent critique of round 7.
It is evidence, not fact: the brief it was given contained a claim that turned out to
be wrong, and the critic correctly refused it. Verify each quote against the tour file
in `TOURS_FOR_REVIEW/round7/` before acting on it.

## Acceptance

- A repeated EVENT is detected even when the wording and dates differ.
- Verified against the two real LOGAN_1 stops.
- Must not fight D584: state how the two rules compose.

## PROCESS

Write `SUBMISSION_LOCAL-532.md` recording what you changed and the evidence for it.
**`git add` and `git commit` on your branch before finishing** - verify with
`git rev-list --count storied..HEAD`; if it prints 0 you have delivered nothing.

Gemini is returning HTTP 402 (prepayment credits depleted). If your task needs a
grounded call, say so in the submission and deliver the offline part - do not
fabricate a verification run. OpenAI and Serper are up.

Do NOT edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md or
.continuous_dev/STATUS.md.
