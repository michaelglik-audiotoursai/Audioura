# LOCAL-675 item 3 — critic rubric made category-aware

The listener-critique harness lives OUTSIDE the git worktree, at:

    ~/Audioura/.continuous_dev/calib/critique.sh

(the worktree root is `/Volumes/AudiouraSSD/audioura-worktrees/LOCAL-675`; the
calib harness is a per-machine tool under `~/Audioura`, not a tracked repo file).
It therefore cannot be captured by a branch commit directly — this directory
vendors the modified copy (`critique.sh`) so the change is reviewable on the
branch, and this note records what changed and why.

## What changed

Criterion 3 of the rubric was museum-only:

    3) hours and admission are SPOKEN, not 'check the website';

A walking tour has no admission desk, so the critic penalised every walking tour
on a criterion it can never satisfy. The script now reads `Tour-Category:` from
the raw `tour_content` (BEFORE the field lines are stripped out of the spoken
text it writes to `tour_<ID>.txt`) and selects criterion 3 accordingly:

    CAT = lowercased Tour-Category value
    walking  -> "directions between stops are clear, with distances"
    anything -> "hours and admission are SPOKEN, not 'check the website'"  (unchanged)

Everything else in the rubric — criteria 1, 2, 4–8, the output format, the
read-only contract — is untouched.

## Implementation notes

- The raw content is now pulled once into `$RAW` and reused, so the category can
  be read before the `Tour-Category:` line is filtered out of the spoken text.
- Category match is case-insensitive (`Museum`, `WALKING`, `walking` all work).
- Unknown / missing category falls back to the original museum criterion, so
  museum and restaurant tours are scored exactly as before.

## Verification (offline, no paid call)

- `zsh -n critique.sh` → syntax OK.
- Category-selection logic exercised in isolation:
  - `Tour-Category: walking`   → directions/distances criterion
  - `Tour-Category: Museum`    → original hours/admission criterion
  - `Tour-Category: WALKING`   → directions/distances criterion
  - no category / `restaurant` → original hours/admission criterion
