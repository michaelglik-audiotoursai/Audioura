# LOCAL-416 — Re-read the empty-sentence population under Michael's standard

## PARKED — do not dispatch until LOCAL-415 is merged.

This file sits outside the dispatcher glob deliberately. 415 is editing
`generate_tour_text.py`; so will this. Rename to
`new_kiro_session_is_required_LOCAL-416.md` once 415 lands.

## Why this exists

`empty_sentence_count` has been reported to Michael three times as "a threshold
decision waiting on him". **It is not.** D324 overturned D295's premise and the
remaining work is ours.

D295 classified 49 flagged sentences from 5 live tours and found 22.4% were "false
positives — visual descriptions of artwork that carry real information but trip the
heuristic". LEAD concluded the metric could not enforce until that class was
exempted.

**Michael's D324 rule says those are not false positives.** His words:

> "We should be providing **context instead of describing what users should see** —
> that is annoying. I hate every time when I read '**intricate detail**' here and
> there: **why do you call something intricate and do not explain why it is so.**"

The metric was measuring the defect correctly the whole time. The exemption LEAD was
about to build would have protected exactly the prose he dislikes. No threshold is
meaningful until the population is re-read under his standard.

## The task

### 1. Re-classify the flagged population

Take the 49 flagged sentences from D295's sample (LOCAL-375's data; re-collect from
live tours if it is not on disk) and classify each against **Michael's earning-clause
rule**, not LEAD's earlier one:

- **SURVIVES** — names a technique, material, or feature **and explains what makes
  it so** in the same or preceding sentence. "Forty lithographs pulled by hand" is
  content. "The intricate details of the binding, forty sheets pulled by hand"
  survives.
- **FLAGGED** — an evaluative adjective with no earning clause. "Position yourself
  to appreciate the intricate details" is the defect, whatever it trips.

Report the new distribution against D295's table (1 genuinely empty 61.2%, 2 broken
grammar 6.1%, 3 false positive 22.4%, 4 ambiguous 10.2%). **State plainly how many
of D295's "false positives" survive Michael's standard.** LEAD's expectation is that
most do not — but that is a prediction to test, not a conclusion to confirm.

### 2. Only then, propose a threshold

With the re-classified population, propose an enforce threshold per stop and show
the false-positive rate it implies. **Do not pick it in code.** Michael decides the
number once the classification is honest; your job is to make it a real choice by
supplying the data behind it.

### 3. Do not build the visual-description exemption

D295 recommended it. D324 killed it. If you find yourself writing a vocabulary
allowlist for descriptive language, stop — that is the reversal this task exists to
prevent.

## Acceptance

- The re-classified table, with per-sentence verdicts, quoted verbatim
- A direct comparison to D295's distribution and a statement of what changed
- A proposed threshold **with its implied false-positive rate**, presented as a
  recommendation for Michael, not applied
- A test asserting the earning-clause rule on real sentences, red before your change
- No exemption allowlist for visual description

## PROCESS
- Branch `kiro/local416-reread-empty-sentence-population` off `storied`.
- Use exactly that branch name (D348).
- Write `SUBMISSION_LOCAL-416.md`.
- Do NOT edit DECISIONS.md / CLAUDE.md / BACKLOG.md / .continuous_dev/STATUS.md.
- Do NOT `DELETE FROM audio_tours`.
