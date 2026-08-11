# LOCAL-395 (PARKED — unpark to dispatch) — Palais Lascaris lost 25 points tonight and nobody noticed

## The finding

Michael asked whether other tours were getting worse. They were.

**Palais Lascaris (the unscoped control venue), same prompt, same n=4, scored across
tonight's live runs:**

| run | base |
|---|---|
| palais373 (start of evening) | **81.2** |
| palais379 / 385 | 68.8 |
| palais387 / 389 / 390 | 75.0 |
| palais391 | **81.2** |
| palais392 | 75.0 |
| palais393 | 62.5 |
| **palais394 (current `storied`)** | **56.2** |

Per-stop breakdown, best vs current:

```
palais391  per_stop_base=[18.75, 18.75, 18.75, 25.0]  quality=0.75
palais394  per_stop_base=[18.75, 12.50, 12.50, 12.50] quality=0.5625
```

**Three of four stops dropped a quality tier.** All four stops are still delivered,
all instrument dates survive, nothing is fabricated — the tour is *correct* and
*worse*.

Scores vary run to run (68.8–81.2 across the early evening), so a single reading
proves nothing. But 62.5 and 56.2 are both **below the entire earlier range**, and
they are the two runs after LOCAL-393/394 landed. That is a signal worth chasing,
not a proven regression.

## The likely suspects, in order

1. **Beat machinery running on a venue with no exhibition.** LOCAL-383/388/391/392
   added story-beat extraction, required-content lists and regeneration retries.
   Palais is `framing=venue_purpose`, not `exhibition` — check whether beats are
   demanded of its stops at all, and what the retries do to the prose. A stop
   regenerated to satisfy a beat may come back blander than the original.
2. **The word-floor retry (LOCAL-393).** It regenerates a stop that is under 120
   words. A regenerated stop is not necessarily a better stop.
3. **The gates stripping content.** Person, form-claim and numeric gates all run on
   every prose field now. Count removals on a Palais run.

## The task

- **First, establish whether it is real.** Generate Palais Lascaris n=4 **three
  times** on current `storied` and three times on `origin/storied@0138e27~20`
  (before tonight's chain), and report all six base scores. Variance is high; one
  run each is not evidence.
- If real, find which change caused it — bisect over the merges
  (385 → 387 → 389 → 390 → 391 → 392 → 394) using the same three-run protocol.
- Report gate-removal counts and beat-retry counts per run.
- **Do not "fix" it by loosening a gate** until the cause is known.

## The methodological failure this exposes — read this part

LEAD checked "museum bounds 81.2 (n=4) / 75.0 (n=8)" on **every** round tonight and
reported them as holding. **Those are static fixture files** (`tours/LOCAL347_*`,
`tours/LOCAL320_*`) — pre-generated text that never changes. Scoring them tests the
*scorer*, not the *generator*. They could not have detected a generation regression
and they never varied all night, which should itself have been the clue.

**A check that cannot fail is not a check** — D242's standing rule, applied to
LEAD's own process rather than to an agent's tests. The correct regression signal
is scoring the *live output* of a control venue, which is free (the runs were
already being done) and would have caught this at LOCAL-393.

**Acceptance for this task includes fixing the harness:** the control-venue live
run must be scored and the score reported on every future round, and `restart.sh`'s
"honest tour scores" block should make clear that those four numbers are fixtures,
not live regressions.

## PROCESS
- Branch `kiro/local395-palais-regression` off `storied`.
- Write `SUBMISSION_LOCAL-395.md`.
- Do NOT edit DECISIONS.md / CLAUDE.md / BACKLOG.md / .continuous_dev/STATUS.md.
- Do NOT `DELETE FROM audio_tours`.
