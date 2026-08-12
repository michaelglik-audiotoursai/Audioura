# TASK LOCAL-456 — Finish the checklist validator: three runs and a real neutralisation

**Agent:** Mac Mini Kiro
**Branch:** LOCAL-456-checklist-validator-verified
**Base:** LOCAL-454-validate-phase3a-against-checklist

> **PARKED — do not dispatch until LEAD removes the `PARKED_` prefix.** This task needs
> live container runs, and the worktree port guard (LOCAL-455) has not landed yet. Until
> it does, a task doing container work can seize port 5000 — the iPhone app's port — the
> way LOCAL-454 did for roughly an hour on 2026-08-12 (D419, D420).

## Why this exists

LOCAL-454 was stopped by LEAD at ~37 minutes, mid-acceptance, so that port 5000 could be
returned to the canonical generator. **That was LEAD's call and not a criticism of the
work** — the code it produced is good and is committed on your base branch as `5ac25c6`,
labelled PARTIALLY VERIFIED. Your job is to finish the evidence, not to rebuild the thing.

**What already exists on your base:**

- Post-hoc validation of Phase 3A candidates against the checklist text, accent-folded,
  dropping non-matching titles with logged reasons in the `[LOCAL-454] DROPPED '<title>'`
  style, and handling the all-dropped case by letting the existing clean fail run.
- A **D243 ligature fix** — expanding ligatures that NFKD does not decompose. That is a
  genuine find and worth keeping; French and Œ/æ titles are common in this corpus.
- 18 tests in `tests/test_local454_validate_phase3a_against_checklist.py`.

**What is missing, and it is only evidence:**

1. LEAD never ran the tests. The claim "18 tests" is a count of `def test_`, nothing more.
2. No D242 behavioural neutralisation.
3. Three of the five required live runs.

## What LEAD did capture, so you do not redo it

Both completed runs (22:58:10Z and 23:19:38Z) produced **identical, correct** stops:

```
Stop 1: Le Lézard aux plumes d'or (The Lizard with Golden Feathers)
Stop 2: Moses and Monotheism
Stop 3: Au Soleil du Plafond
```

Banned works — *The Weeping Woman*, *The Farm*, *The Persistence of Memory* — **zero
occurrences** across both. Two for two. You need three more.

## What to do

### 1. Run the tests and paste the real output

All 18, verbatim. If any fail, fix them or explain the assertion is wrong and change it —
do not delete. LOCAL-453 claimed "13 tests, all pass" when one failed (D418); that is the
error this instruction exists to prevent.

### 2. A D242 neutralisation that binds to behaviour

**Source-grep tests do not count.** LOCAL-453 offered tests that read
`generate_tour_text.py` and asserted strings were present; LEAD destroyed the behaviour
while leaving every string intact and the results were byte-identical before and after
(D418). If any of your 18 tests work that way, they are not the evidence.

The check LEAD will run: **neutralise the validator so it drops nothing** — leave every
string, comment and variable name in place — and require a test to go **red**. Do that
yourself first and paste the before/after counts. Then do the same for the ligature
expansion: break it and show a test notice.

### 3. Three more live runs

Same MFA request, five total including LEAD's two. Every run produces a tour; every stop
appears in the checklist text; no banned work anywhere. Table: run, outcome, chars, stop
titles.

**Note the pace problem.** LOCAL-454's two runs were 21 minutes apart — far slower than
the 165s a generation costs, which is why it ran out of time. Find out why before
starting: if each run is rebuilding an image or re-fetching a cold corpus, fix that or
work around it, and say what you found. Three runs should cost ~10 minutes, not an hour.

### 4. Docker rules — read before your first container command

- Build from the worktree is fine: `docker build -f Dockerfile.generator -t audioura-tour-generator-local456 .`
- Run without publishing ports: `docker run --rm --network development_default ...`, **never `-p`**.
- **Never `docker-compose up` from the worktree.** Compose names its project after the
  directory, so it becomes `local-456` and any `ports:` mapping removes the canonical
  container and takes the host port. Port 5000 is the app's.
- If you need `audioura-tour-generator-1` itself, use `docker exec` against the running
  container rather than creating your own.

## Acceptance

- 18 tests run by you, output pasted.
- Neutralisation before/after counts for both the validator and the ligature fix, each
  showing red.
- Three live runs, table as above, no banned works.
- Regression: `test_sq4_merge.py`, `test_palais_fix_lead_fixture.py`,
  `test_local12_fact_retrieval_fix.py`, and the 447–451 suites (76 tests).
- `docker ps --filter publish=5000` at the end showing `audioura-tour-generator-1`. If
  your work displaces it, restoring it is part of the task.

## Time

Your two predecessors died or were stopped at 62 and 37 minutes with nothing committed,
and LEAD salvaged both by hand. **Commit as soon as anything works.** Partial and
committed beats complete and lost.

## PROCESS

- Work ONLY in your worktree on branch `LOCAL-456-checklist-validator-verified`.
- Do NOT edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`.
- Record reasoning in `SUBMISSION_LOCAL-456.md` at the worktree root.
- No `DELETE FROM audio_tours`, ever.
- Commit at least once
  (`git rev-list --count LOCAL-454-validate-phase3a-against-checklist..HEAD >= 1`).
- Run every test you cite and paste the real output. "Unproven, handing to LEAD" is always
  acceptable; "all pass" when one does not is not.
