**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-297
**Base:** storied
**Branch:** kiro/local297-test-collection-safety

# 25 files named test_*.py run database code when pytest merely collects them.

Read `DECISIONS.md` **D141**, **D148**, **D210**, `CLAUDE.md` "⛔ THE LIVE
DATABASE IS PRODUCTION DATA", and `tests/run_local296_verification.py` for the
convention that is already correct.

## ⚠️ NO container rebuilds (D48). Ceiling **$0.50**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.

## ⛔ DO NOT DELETE ANY DATABASE ROWS IN THIS TASK.
Row deletion is on Michael's ask-first list. This task renames files. Nothing
else.

## The measurement

```
test_*.py files in tests/:            188
  with ZERO test functions:            40
  ...of those, touching the database:  25
```

pytest **imports** every collected file. A file named `test_*.py` with no test
functions is a standalone script, and importing it runs its body. Twenty-five of
them open database connections, and several `INSERT` and `DELETE`.

**`pytest tests/` therefore executes 25 database-touching scripts as a side
effect of collecting** — against production by default, since
`AUDIOURA_DB_TARGET` (LOCAL-296) is unset unless a caller opts in.

Confirmed: full collection currently either aborts with `INTERNALERROR:
SystemExit` or hangs past two minutes. Nobody has been able to run the full
suite all night, which is *why* this went unnoticed.

The repo already has the right convention — `run_local*.py` for harnesses that
execute, `test_local*.py` for pytest suites. LOCAL-296 was bounced for violating
it and now follows it. Forty files predate that.

## Scope

**Rename every `test_*.py` that has no test functions to `run_*.py`.**

- Preserve the descriptive part of the name: `test_local183_evidence.py` →
  `run_local183_evidence.py`.
- **Use `git mv`** so history follows.
- **Change nothing inside the files.** This is a rename, not a rewrite. If a
  script is broken or obsolete, say so in the submission and leave it alone.

**Then find and fix every reference to the old names.** Other scripts, docs,
`.continuous_dev/*.sh`, CI config, task files. A rename that breaks a caller is
worse than the problem it fixes. Grep for each old basename before and after.

## The line you must not cross

**Do not add test functions to make a script "a real test".** That is a
rewrite, it is not this task, and it would bury a 40-file rename in
unreviewable diffs.

**Do not delete any file**, however obsolete it looks. Renaming is reversible;
deleting is not, and it is not yours to decide.

**Do not touch the 148 files that DO have test functions.** They are fine.

## Verification

- `pytest tests/ --collect-only` **completes**, with no `INTERNALERROR` and no
  hang. Report the collected count and the wall time.
- `pytest tests/ -q` runs to completion. Report pass/fail counts. **Pre-existing
  failures are expected and are not yours to fix** — report them as a list so
  LEAD can see the real state of the suite for the first time.
- Confirm **no database writes occur during collection**: record
  `SELECT COUNT(*) FROM audio_tours` and the Nice list `[1,12,14,17,24,29,152]`
  immediately before and after a `--collect-only` run. They must be identical.
- List every file renamed, and every reference updated.

## Traps

- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base`, never `storied..HEAD` (D147).
- Some of these scripts are referenced by `.continuous_dev/*.sh` guards that run
  on a launchd tick. Breaking one silently disables a production-data alarm.
  Check those first.

## Acceptance criteria

- Every `test_*.py` with zero test functions renamed to `run_*.py` via `git mv`.
- No file contents changed; no file deleted.
- All references updated; every one listed.
- `pytest tests/ --collect-only` completes cleanly; count and time reported.
- `pytest tests/ -q` completes; pre-existing failures listed, not fixed.
- `audio_tours` count and Nice list identical before and after collection.
- `git status --short` clean. No container rebuilt.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-297.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
