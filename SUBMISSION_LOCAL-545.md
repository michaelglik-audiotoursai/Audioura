# LOCAL-545 — Split the alert channels

**Branch:** LOCAL-545-split-alert-channels
**Base:** storied @ 047e7e5 (`git merge-base --is-ancestor 047e7e5 HEAD` → exit 0)

## The problem, restated

`restart.sh` printed `ALERTS.md: 40 alert line(s) in the last 40` at every session
start. Every one of the last 40 was a false `*** DELIVERED NOTHING ***` (D590 found
`verify_deliverables.sh` measured `storied..$branch`, which is 0 for any branch that
delivered and was then merged). An alarm channel at 100% false positives is switched
off — which is exactly how tour 29's deletion went unnoticed. D590 fixed the cause;
this fixes the consequence by **splitting the channel by what a human must do about
each line.**

## What ALERTS.md contained before the split (5990 lines)

| Marker | Count | Writer | New channel |
|---|---:|---|---|
| `*** DISK LOW ***` | 2740 | prune_worktrees.sh | **ALERTS (urgent)** — kept |
| `*** SECRET DETECTED ***` | 1711 | autonomy_tick.sh | **ALERTS (urgent)** — kept |
| `*** DELIVERED NOTHING ***` | 1347 | verify_deliverables.sh | **hygiene** |
| `*** BACKLOG LOW ***` | 63 | verify_deliverables.sh | **hygiene** |
| `*** USER-VISIBLE DRIFT ***` | 60 | check_user_visible.sh | **ALERTS (urgent)** — kept |
| `*** TICK STEP TIMED OUT ***` | 7 | autonomy_tick.sh | **hygiene** (judgement) |
| `*** THREE IDENTICAL FAILURES ***` | 3 | verify_deliverables.sh | **hygiene** (judgement) |
| `*** ROW LOSS ***` | 3 | backup_tours.sh | **ALERTS (urgent)** — kept |
| `*** QUARANTINED ***` | 3 | reap_orphans.sh | **hygiene** (judgement) |
| `*** UNFLAGGED TEST TOURS VISIBLE ***` | 1 | check_user_visible.sh | **ALERTS (urgent)** — kept |
| `*** PRODUCTION DNS DEAD ***` | 1 | check_production.sh | **ALERTS (urgent)** — kept |
| `protected-file edits` | — | check_protected_files.sh | **hygiene** (judgement) |
| non-marker / continuation lines | 48 | (LOST ROW detail etc.) | preserved in archive |

## The rule I applied

**ALERTS.md = a human must act now.** Row loss in `audio_tours`, a production
endpoint down, a domain near expiry, disk low enough to stop the queue, wrong/test
tours served to real users, a leaked secret in commits. These are rare; a non-empty
ALERTS.md is itself the signal.

**task_hygiene.log = routine and self-correcting.** It matters, but it is already
handled automatically and nothing user-facing is broken while it waits.

## Judgement calls (mine to make)

- **`TICK STEP TIMED OUT` → hygiene.** The watchdog already killed the hung step and
  the next launchd tick re-runs every check. It names which step stalled, worth
  recording, but it is an operational hiccup, not a production emergency.
- **`THREE IDENTICAL FAILURES` → hygiene.** It says "needs Michael", but nothing
  user-facing is broken and the queue keeps running; it asks a human to *rethink an
  approach*, not to *stop an incident*. It is also derived from the same
  delivered-nothing stream, so keeping it with its siblings is coherent.
- **`QUARANTINED` → hygiene.** A task died 3× and its file is moved aside
  automatically; the queue runs on without it. "Needs LEAD" eventually, but no
  production data or user is at risk while it waits.
- **`protected-file edits` → hygiene.** Fires on an *unmerged* task branch and is
  caught again by LEAD before merge. Nothing is at risk until someone merges it, and
  the script's own comment warns that reporting these every tick is how an alarm
  stops being read.
- **`SECRET DETECTED` → kept URGENT** (despite 1711 historical lines). A leaked
  credential in committed history needs a person now; volume was historical
  accumulation, shed by starting the file empty.
- **`DISK LOW` → kept URGENT.** The task names "disk low enough to stop the queue"
  explicitly. (2740 lines was the same low-disk condition re-logged every 5-minute
  tick; the count reflects duration, not 2740 distinct incidents.)

## Changes made

### Version-controlled (on this branch, in git)
- **`restart.sh`** — replaced the single "N alert line(s) in the last 40" line with
  two: an ALERTS.md line that reads `0 urgent — clear.` in the normal case and
  `*** N URGENT alert line(s) — READ .continuous_dev/ALERTS.md NOW ***` otherwise,
  plus a separate `task_hygiene.log: N routine event(s) ...` informational line. The
  count anchors on a leading UTC timestamp so the file's own `***` legend is not
  counted.
- **`.continuous_dev/autonomy_tick.sh`** — added `HYGIENE` path var; routed
  `TICK STEP TIMED OUT` to it. `SECRET DETECTED` left in ALERTS.md.
- **`.continuous_dev/reap_orphans.sh`** — routed `QUARANTINED` to task_hygiene.log.

`backup_tours.sh`, `check_production.sh`, `check_user_visible.sh` were already correct
(they only ever wrote genuinely-urgent lines to ALERTS.md) and needed no change.

### NOT in version control — `.continuous_dev/` is gitignored
`.gitignore` line 33 ignores `.continuous_dev/`; the `!.continuous_dev/*.sh` negation
on line 63 only re-includes files git already tracks. These three scripts were never
committed, so they are fully ignored and `git add -f` would be needed to track them.
I edited them in place in the live checkout (`/Users/micha/Audioura/.continuous_dev/`)
and **these edits are therefore NOT in the repo:**
- **`verify_deliverables.sh`** — `DELIVERED NOTHING`, `THREE IDENTICAL FAILURES`,
  `BACKLOG LOW` → task_hygiene.log.
- **`prune_worktrees.sh`** — unchanged in behaviour; `DISK LOW` stays urgent.
- **`check_protected_files.sh`** — protected-file edits → task_hygiene.log.

The **ALERTS.md files** (archive + new empty one) and **task_hygiene.log** also live
under `.continuous_dev/` and are **NOT in version control** for the same reason.

## Archive, not delete

`ALERTS.md` (5990 lines) was moved to
`.continuous_dev/ALERTS_archive_pre_D590.md` and kept. It is the evidence D590 rests
on. A new ALERTS.md was started with only a header legend (no alarm lines).

## Line counts

- **Moved out of the urgent channel (to hygiene, by writer reroute going forward):**
  1347 `DELIVERED NOTHING` + 63 `BACKLOG LOW` + 7 `TICK STEP TIMED OUT`
  + 3 `THREE IDENTICAL FAILURES` + 3 `QUARANTINED` = **1423 hygiene lines**
  (plus protected-file edits, 0 historically present).
- **Kept as urgent (writers still target ALERTS.md):** 2740 `DISK LOW`
  + 1711 `SECRET DETECTED` + 60 `USER-VISIBLE DRIFT` + 3 `ROW LOSS`
  + 1 `PRODUCTION` + 1 `UNFLAGGED` = **4516 urgent-class lines** + 48 continuation.
- **Archived:** the whole file, **5990 lines**, in `ALERTS_archive_pre_D590.md`.
- **New ALERTS.md:** **0 alarm lines** (14 lines, all header legend).

Note: the 5990 historical lines were **not re-split into the two new files** — per the
task, the existing file is archived whole and the new one starts empty. The
classification above governs where each writer sends *future* lines. The counts show
that of the 5942 historical marker lines, 1423 would now go to hygiene and 4516 would
still be urgent — but 4451 of those "urgent" are `DISK LOW`/`SECRET DETECTED` repeats
that starting-empty deliberately sheds.

## Acceptance evidence

### New ALERTS.md contents
```
# ALERTS — production-urgent only (LOCAL-545)
#
# A line here means a HUMAN MUST ACT NOW. This file is meant to be EMPTY in the
# normal case; a non-empty ALERTS.md is itself the signal. Only these belong:
#   - *** ROW LOSS *** in audio_tours          (backup_tours.sh / restart.sh)
#   - *** PRODUCTION ... *** endpoint down      (check_production.sh)
#   - *** DOMAIN ... *** near expiry / parked   (check_production.sh)
#   - *** DISK LOW *** enough to stop the queue (prune_worktrees.sh)
#   - *** USER-VISIBLE DRIFT *** / *** UNFLAGGED TEST TOURS *** (check_user_visible.sh)
#   - *** SECRET DETECTED *** in commits        (autonomy_tick.sh)
#
# Routine task-hygiene (delivered-nothing, backlog-low, three-identical-failures,
# quarantines, tick-step timeouts, protected-file edits) goes to task_hygiene.log,
# NOT here. History before this split is in ALERTS_archive_pre_D590.md.
```

### A real row-loss alarm still reaches ALERTS.md — proven by effect
Ran the **unmodified** `backup_tours.sh` in a sandbox (fake `$HOME`, stubbed `docker`
returning a fixture count) so the live DB and live ALERTS.md were never touched. The
fixture said the table went 3 → 2 with real tour 29 among the lost ids:
```
=== BEFORE: alarm lines in sandbox ALERTS.md ===
0
=== AFTER: ALERTS.md new content (alarm lines) ===
2026-09-24T01:35:50Z | *** ROW LOSS: audio_tours went 3 -> 2 (1 non-test) ***
    LOST ROW: 29|false|Michael's French Riviera biking tour
```
The alarm fires, names the exact lost row, and lands in a starts-empty ALERTS.md. No
row was deleted from the live `audio_tours` table to test this.

### restart.sh distinguishes the two states
```
=== STATE 1: fresh empty ALERTS, no hygiene log ===
ALERTS.md: 0 urgent — clear.

=== STATE 2: one urgent row-loss line + 40 hygiene lines ===
ALERTS.md: *** 1 URGENT alert line(s) — READ .continuous_dev/ALERTS.md NOW ***
task_hygiene.log: 40 routine event(s) in the last 200 — informational, auto-refiled, not an emergency.
```
The old failure mode — 40 routine lines masking 1 real one behind a number nobody
reads — is gone: routine volume now lands in the informational hygiene line and can
never hide an urgent one.

### Syntax
`bash -n`/`zsh -n` pass on all five modified scripts.
