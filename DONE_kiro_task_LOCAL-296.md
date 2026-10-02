**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-296
**Base:** storied
**Branch:** kiro/local296-tests-off-production

# Tests write to the production tour table. It is now 114 test rows to 29 real ones.

Read `DECISIONS.md` **D141** and **D148**, `CLAUDE.md` "⛔ THE LIVE DATABASE IS
PRODUCTION DATA", `tests/db_connection.py`.

## ⚠️ NO container rebuilds (D48). Ceiling **$0.50**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.

## ⛔ DO NOT DELETE ANY ROWS IN THIS TASK

`audio_tours` deletion is on Michael's ask-first list and he is asleep. **This
task adds a safety rail; it does not clean up.** If you believe rows should be
removed, say so in the submission and stop. A cleanup task can be dispatched
after he rules on it.

## The measurement

Live `audio_tours`, tonight:

```
143 rows total  =  29 real  +  114 test (is_test = true)
```

Four test rows for every real one, in the table that backs the user-facing tour
list. Tonight's verification runs alone added dozens. The `is_test` flag and the
D141 cleanup rule keep this survivable, but the rule depends on every script
remembering to clean up after itself, and several do not.

**This is the residual risk behind the tour-29 incident.** A real tour Michael
had downloaded and field-tested was deleted during autonomous operation and the
cause was never identified; test cleanup reaching real rows is the leading
hypothesis. Every test row written to the production table is another chance for
that to recur.

## Scope

**Generation runs invoked by tests must persist to `audiotours_test`, not
`audiotours`.**

D148 already establishes that tests run against `audiotours_test`. The gap is
that a *generation* triggered from a verification script writes its tour through
the normal production path.

1. **A single switch.** `tests/db_connection.py` should expose one explicit way
   to target the test database, and generation must honour it — an env var such
   as `AUDIOURA_DB_TARGET=test` read in one place, not a parameter threaded
   through call sites.
2. **Default unchanged.** Production remains the default. A script must opt in.
   Nothing about the app's behaviour changes.
3. **Make the current run visible.** Every generation should log which database
   it is writing to, once, at start. Tonight it is not possible to tell from a
   log which table a run touched.

## The line you must not cross

**Do not change what the running services connect to.** The orchestrator, the
app and the live containers keep using `audiotours`. This is about scripts under
`tests/` and the `run_local*.py` verification harnesses.

**Do not add a fallback that silently picks a database.** If the target is
ambiguous, fail loudly. A silent wrong choice here is exactly how production data
gets touched.

**`is_test` stays.** It is the last line of defence and the thing that let LEAD
prove tonight that no real tour was lost.

## Verification

- Run one 2-stop Riviera generation with the switch **off**: confirm it writes to
  `audiotours` exactly as now, and that the log names the database.
- Run the same with the switch **on**: confirm the row appears in
  `audiotours_test` and that `audio_tours` in production is **unchanged** —
  report the count before and after, and the Nice list `[1,12,14,17,24,29,152]`.
- Report the production real/test row split before and after your work. It must
  not go up.

## Traps

- **Cleanup rule (D141):** delete only rows this run created, by an id captured
  at creation, and only after `SELECT is_test` on that id returns `true`. In this
  task, prefer writing to the test database over deleting anything at all.
- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base`, never `storied..HEAD` (D147).
- **D186:** the spine stays on gpt-4o.
- `tests/test_local115_referral_abuse_controls_guard.py` calls `sys.exit()` at
  module scope and aborts any `pytest tests/` run that collects it. Pre-existing
  — run your suites by filename.

## Acceptance criteria

- One explicit switch selects the test database; production is the default.
- Every generation logs its target database once at start.
- Verified both ways, with production row counts before and after.
- No rows deleted anywhere in this task.
- `is_test` still written and still meaningful.
- `git status --short` clean. No container rebuilt.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-296.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.

---

# ⛔ BOUNCED by LEAD — 2026-08-06 02:40. The switch is right; the test file is a hazard.

**Keep the implementation. It is verified and merge-ready.** LEAD tested
`get_database_url()` directly:

```
default (no env var):      audiotours
AUDIOURA_DB_TARGET=test:   audiotours_test
AUDIOURA_DB_TARGET=bogus:  fatal, no silent fallback
```

Production is untouched — 143 rows = 29 real + 114 test, Nice list intact — and
both `DELETE`s in your verification are textbook D141: id captured at creation,
`SELECT is_test` asserted `True` immediately before. You recommended the bulk
cleanup rather than performing it, exactly as the task required. All correct.

## The one problem

`tests/test_local296_db_target_switch.py` is **not a pytest file**. It has
**zero `def test_` functions** and runs its whole body at module scope —
including `INSERT INTO audio_tours`.

```
$ python3 -m pytest tests/test_local296_db_target_switch.py -q
no tests ran in 0.14s
```

pytest **imports** files during collection. A file named `test_*.py` that writes
to a database on import means `pytest tests/` performs database writes as a side
effect of collecting. On the production database, by default.

The task's own Traps section warned about this exact pattern:

> `tests/test_local115_referral_abuse_controls_guard.py` calls `sys.exit()` at
> module scope and aborts any `pytest tests/` run that collects it.

That file is the reason a full-suite run has been impossible all night. Your file
reproduces the anti-pattern and adds DB writes to it.

## The fix — small

1. **Rename to `tests/run_local296_verification.py`.** Every other verification
   harness in this repo uses `run_local*.py` precisely so pytest does not collect
   it. Content can stay exactly as it is; it is a good script.
2. **Add a real pytest suite** as `tests/test_local296_db_target_switch.py` with
   actual `def test_` functions covering the resolution logic **with no database
   access at all** — set `AUDIOURA_DB_TARGET`, call `get_database_url()`, assert
   the database name in the returned URL. Three tests: default, `test`, invalid
   raises. That is pure string logic and needs no connection.

## Also worth fixing while you are there

The invalid-value banner prints **dozens of times** in a single run. Failing
loudly is right; printing the same 6-line banner 70 times is not — it buries
everything else in the log. Print it once, then raise.

## Do not change

The `db_connection.py` switch, the default-to-production behaviour, the fatal on
invalid input, `is_test`, or your recommendation to leave the 114 test rows for
Michael to rule on. All of that is correct and this bounce does not touch it.
