**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-298
**Base:** storied
**Branch:** kiro/local298-failure-triage

# Triage the 26 failing tests. Fix NOTHING.

Read `DECISIONS.md` **D212**, `SUBMISSION_LOCAL-297.md`.

## ⚠️ NO container rebuilds (D48). Ceiling **$0.30**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.

## ⛔ THIS TASK CHANGES NO CODE AND NO TESTS.

**Do not fix a single failure.** Do not edit a test, do not edit an
implementation, do not install a package, do not delete anything. The only
artifact this task produces is a markdown document. If you find yourself
editing a `.py` file, you have misread the task.

The reason is in D212: some of these 26 will be stale tests for removed
features, some will be real defects, and mass-fixing them unattended is how a
green suite gets manufactured rather than earned. Michael needs to see the list
before anything is touched.

## Background

LOCAL-297 made `pytest tests/` completable for the first time in months. The
first honest result:

```
26 failed, 960 passed, 16 skipped, 50 errors in 335s
```

Those 26 have been invisible because collection previously aborted with
`INTERNALERROR: SystemExit` or hung. Nobody has looked at them.

## Scope

Run the full suite, then for **each of the 26 failures** produce one entry:

| field | content |
|---|---|
| test | file::name |
| assertion | the actual failure line, verbatim |
| category | see below |
| feature still live? | does the code under test still exist and get called? |
| evidence | the grep or file path that answers the previous column |
| recommended action | fix test / fix code / delete test / ask Michael |

**Categories** — assign exactly one:

- **STALE** — tests a feature that no longer exists or was deliberately changed.
  The test is wrong, not the code.
- **REAL** — the code is broken. This is a genuine defect the suite has been
  hiding.
- **ENVIRONMENT** — fails from a missing service, credential, network or fixture,
  not from logic.
- **UNCLEAR** — you cannot tell without a product decision. Say what the decision
  is.

**"Feature still live?" is the column that matters most.** A test failing against
a function nothing calls is very different from one failing against the tour
pipeline. Check whether the module under test has callers — that check has
already caught a dead-code problem tonight (D200: `tour_rubric_scorer` had none).

Also cover the **12 runtime errors** the same way. Ignore the 38 collection
errors — those are known missing pip modules (bs4, selenium, Crypto,
cryptography) and are recorded already.

## Deliverable

`TEST_FAILURE_TRIAGE.md` at the repo root: a summary count by category, then the
26 entries, then the 12 errors. Sort so **REAL** appears first — if the suite is
hiding genuine defects, that is what Michael should see at the top.

Commit only that file plus your submission.

## The line you must not cross

**Do not guess a category to fill the table.** UNCLEAR is a correct answer and is
more useful than a confident wrong one. D209 is on record for exactly this: a
submission headed CONFIRMED whose own evidence showed nothing.

**Do not report a failure as STALE because the test looks old.** Show that the
feature is gone — a grep for callers, a deleted module, a superseding decision in
`DECISIONS.md`. Age is not evidence.

## Traps

- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base`, never `storied..HEAD` (D147).
- The suite takes ~335s. Run it once, capture the output to a file, and work from
  that rather than re-running per test.
- Some failures may share a root cause. Say so — 26 entries pointing at 4 causes
  is a far more useful document than 26 unrelated ones.

## Acceptance criteria

- `TEST_FAILURE_TRIAGE.md` exists with all 26 failures and 12 runtime errors.
- Every entry has a verbatim assertion and a category.
- Every STALE claim carries evidence the feature is gone.
- REAL entries sorted first.
- **Zero changes to any `.py` file.** `git diff --stat` shows only the triage doc
  and the submission.
- No packages installed, nothing deleted.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-298.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.

---

# ⚠️ RESUMING — the previous session burned 27 minutes on a filesystem scan.

**LEAD, 2026-08-06 04:07.** The first attempt produced nothing. It spent its
entire run inside:

```
find /Users/micha -name "pytest" -type f
```

26 minutes and still going when LEAD killed it. That path contains Docker
volumes, `node_modules`, and `~/audioura-backups` with twelve 224 MB dumps. It
was looking for the pytest binary.

**Do not search the filesystem for tooling.** The suite runs as:

```bash
cd ~/audioura-worktrees/LOCAL-298
python3 -m pytest tests/ -q > /tmp/local298_suite.log 2>&1
```

`python3 -m pytest` needs no binary on PATH. It takes ~335 seconds. Run it
**once**, redirect to a file, and read that file — do not re-run per test.

**If any command has not returned within about two minutes, it is the wrong
command.** Stop it and reconsider rather than waiting. Nothing in this task
needs to scan a home directory.

Everything else in the task above stands unchanged. In particular: **this task
changes no `.py` file.** The only deliverable is `TEST_FAILURE_TRIAGE.md`.
