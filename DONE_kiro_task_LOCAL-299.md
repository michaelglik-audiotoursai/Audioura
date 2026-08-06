**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-299
**Base:** storied
**Branch:** kiro/local299-import-time-env

# Test modules mutate os.environ at import. One of them defeated the DB safety switch.

Read `DECISIONS.md` **D214**, **D210**, **D211**, `TEST_FAILURE_TRIAGE.md`,
`tests/db_connection.py`, `tests/test_t4_db_down_unit.py`.

## ⚠️ NO container rebuilds (D48). Ceiling **$0.40**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.
**Do not delete database rows.** That is Michael's call.

## What happened

`tests/test_t4_db_down_unit.py:16-20` sets `DB_HOST`, `DB_NAME`, `DB_USER`,
`DB_PASSWORD`, `DB_PORT` via `os.environ.setdefault` **at module scope**. pytest
imports it during collection, so those values are live for the entire session.

Measured before the D214 fix:

```
AUDIOURA_DB_TARGET=test, clean env   -> audiotours_test
after importing test_t4_db_down_unit -> audiotours        <- PRODUCTION
```

The LOCAL-296 safety switch — whose whole purpose is stopping tests touching
production — was silently overridden by an env var another module happened to
set. D214 fixed the precedence so an explicit target now wins.

**That fix removes the consequence. This task removes the cause.**

LOCAL-297 renamed 40 script-shaped files, but its criterion was "zero test
functions". `test_t4_db_down_unit.py` **has** test functions and also mutates
the environment at import, so it was never a candidate. The defect class is
**module-scope side effects in collected files**, which is broader.

## Scope

**Find every collected test module that mutates process-global state at import,
and move that mutation into a fixture.**

Look for, at module scope (not inside a function or fixture):

- `os.environ[...] = ` / `os.environ.setdefault(...)` / `os.putenv`
- `os.chdir`
- monkeypatching of imported modules
- writes to files or the database
- `sys.path` mutation **is acceptable** — it is the established pattern here and
  is harmless.

For each one found, move it into a `pytest` fixture that **restores the previous
value on teardown** — `monkeypatch.setenv` does this for free and is the
preferred form.

**Report the full list first.** If there are more than ten, fix the ones that
touch `DB_*`, `DATABASE_URL` or `AUDIOURA_DB_TARGET` in this task and list the
rest for a follow-up. Those are the ones that can reach production data.

## The line you must not cross

**Do not change what any test asserts.** If a test needs `DB_NAME` set to run,
it still gets it — from a fixture instead of at import. A test that passes for a
new reason is worse than one that fails.

**Do not rename files.** LOCAL-297 did the renames; these files are legitimate
pytest modules and stay where they are.

**Do not weaken the D214 precedence** to make anything pass. If a test now fails
because it can no longer override the target, that is the fix working — report
it.

## Verification

- Reproduce the original defect on `storied` **before** your change and paste the
  output — it should already be fixed by D214, so state plainly that you are
  removing the cause, not the symptom.
- After your change, confirm no collected module mutates `DB_*`, `DATABASE_URL`
  or `AUDIOURA_DB_TARGET` at import. Show the grep.
- `python3 -m pytest tests/ -q` — the suite takes ~355s. Run it **once**,
  redirect to a file, read the file. Report pass/fail against the current
  baseline of **26 failed, 960 passed, 16 skipped, 50 errors**.
- The count must not get worse. If a previously-passing test now fails because it
  relied on leaked environment, that is a real finding — report it, do not paper
  over it.

## Traps

- **`python3 -m pytest`** — no PATH lookup, no `find`. **If a command has not
  returned in ~2 minutes it is the wrong command** (D213: a previous session
  burned 27 minutes inside `find /Users/micha`).
- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base`, never `storied..HEAD` (D147).

## Acceptance criteria

- Every module-scope mutation of `DB_*` / `DATABASE_URL` / `AUDIOURA_DB_TARGET`
  moved into a restoring fixture.
- Full list of all module-scope side effects reported, fixed or deferred.
- No assertion changed, no file renamed, no D214 precedence weakened.
- Suite result reported against 26/960/16/50; not worse.
- `git status --short` clean. No container rebuilt.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-299.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
