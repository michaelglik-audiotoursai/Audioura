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

## LEAD has now done steps 1 and 2, and the answer changes your job (D421)

**The 18 tests pass** — `18 passed, 1 warning in 0.17s`, LEAD-run at `5ac25c6`. Do not
redo this except as a regression after your changes.

**They also pass with the validator completely neutralised.** LEAD deleted the validator's
one load-bearing line —

```python
poi_list = _validated_pois
```

— leaving every comment, log line, guard, counter and the `title_appears_in_page` call
untouched. Hallucinated candidates then flow straight into the tour. Result: `18 passed`.
The file was restored from backup immediately.

They miss it because none of them executes the validator. The suite is
`title_appears_in_page` in isolation (a different function, and unaffected by the
neutralisation), plus `open(source_path).read()` and `find()` on marker strings — and the
class named `TestValidatorNeutralisation` claims in its own docstring to be *"not a mock,
not a source grep"* while its body is exactly that. **This is the defect D418 bounced
LOCAL-453 for, one task earlier.**

### 1. Extract the validator so a test can reach it — do this first

The validator is inline in `generate_tour_text()`, a function needing an API key, a DB and
network. That is *why* the tests grep. Fix the cause:

```python
def validate_candidates_against_checklist(poi_list, checklist_text) -> list:
```

Module scope, pure, no I/O; the same drop logging; called from exactly where the block
sits now, so behaviour is unchanged. Then rewrite the suite to call it with a list and
assert on what comes back.

### 2. Re-prove the neutralisation against the new suite

Delete the assignment that installs the filtered list, run the tests, show **red**. Then
restore and show green. Paste both, verbatim, with counts. Do the same for the ligature
expansion: break `œ`→`oe` and show a test notice.

**Nothing else in this task is worth doing until a test can fail.** Live runs against a
suite that cannot detect a neutralised validator are not evidence.

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

- `validate_candidates_against_checklist` at module scope, called from where the inline
  block sits now, behaviour unchanged.
- The rewritten suite run by you, output pasted.
- Neutralisation before/after counts for both the validator and the ligature fix, each
  showing red — against the rewritten suite, not the one you inherited.
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
