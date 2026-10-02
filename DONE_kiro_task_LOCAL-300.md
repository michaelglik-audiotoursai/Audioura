**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-300
**Base:** storied
**Branch:** kiro/local300-test-db-schema

# audiotours_test has 6 tables. Production has 43. The safety switch points at a stub.

Read `DECISIONS.md` **D214**, **D216**, **D217**, `tests/db_connection.py`.

## ⚠️ NO container rebuilds (D48). Ceiling **$0.40**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.
**Do not delete or modify any row in `audiotours`.** Production is read-only to
this task. You may create and populate schema in `audiotours_test` freely.

## The problem

LOCAL-296 built `AUDIOURA_DB_TARGET=test` so tests stop writing to production.
The switch works. But the database it points at is a stub:

```
audiotours       43 tables, 147 rows
audiotours_test   6 tables,   0 rows
```

Measured consequence — the same suite, same commit, differing only in target:

```
audiotours       ->  26 failed, 960 passed, 16 skipped
audiotours_test  ->  10 failed, 990 passed,  2 skipped
```

**More tests passed against the thinner schema, and fewer were skipped.** That is
backwards. A database missing 37 tables should cause *more* failures, not fewer.
The likely explanation is tests passing **vacuously** — an assertion like "row
count preserved" is trivially true against an empty table.

So the switch currently trades one problem for a worse one: production-data risk
becomes silently meaningless passes. **A green suite that proves nothing is more
dangerous than a red one.**

## Scope

**Give `audiotours_test` production's schema — structure only, no data.**

1. Dump the **schema** of `audiotours` (`pg_dump --schema-only`) and apply it to
   `audiotours_test`. No rows. Tests create their own fixtures.
2. **Make it reproducible.** A committed script — `tests/init_test_db.sh` or
   equivalent — that can rebuild `audiotours_test` from scratch. Anyone cloning
   this repo should be able to run it.
3. **Verify table parity.** Report table count and the list of any tables still
   differing, with a reason for each.

## The line you must not cross

**`pg_dump --schema-only`. Never `--data-only`, never a full dump.** Production
rows must not be copied into the test database — `audio_tours` holds 29 real
tours including Michael's field-tested ones, and copying them anywhere is both
pointless and a way to lose track of what is real.

**Do not write to `audiotours`.** Read its schema; change nothing. Report its
row count before and after your work to prove it: currently **147 = 29 real +
118 test**, Nice list `[1,12,14,17,24,29,152]`.

**Do not fix any failing test.** If parity changes the failure count — up or
down — report the new number and the diff in which tests fail. A test that
starts failing once the schema is real was passing vacuously, and that is a
finding, not a regression to hide.

## Verification

- Table count in `audiotours_test` before and after; target is parity with 43.
- `AUDIOURA_DB_TARGET=test python3 -m pytest tests/ -q` — run **once**, redirect
  to a file. Report pass/fail/skip/errors against the current **10 / 990 / 2 /
  50**, and list every test whose status changed.
- Production `audio_tours` row count and Nice list, before and after.
- Confirm `tests/init_test_db.sh` rebuilds the database from empty.

## Traps

- **`python3 -m pytest`** — no PATH lookup, no `find`. **If a command has not
  returned in ~2 minutes it is the wrong command** (D213).
- The suite takes ~225s against the test DB. Run it once.
- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base`, never `storied..HEAD` (D147).
- Expect the failure count to **rise**. That is the likely correct outcome and is
  not a reason to stop or to soften anything.

## Acceptance criteria

- `audiotours_test` has production's schema; parity reported with any gaps explained.
- A committed, runnable script rebuilds it from scratch.
- No data copied from production; production unchanged and proven so.
- New suite result reported with a per-test status diff.
- No test modified.
- `git status --short` clean. No container rebuilt.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-300.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.

---

# ⚠️ RESUMING — third session lost to a filesystem search. Read this first.

**LEAD, 2026-08-06 06:40.** Your predecessor **completed the schema work** —
`audiotours_test` now has **43 tables, parity with production**. Verify that
before redoing it:

```bash
docker exec development-postgres-2-1 psql -U admin -d audiotours_test \
  -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
```

It then spent 20 minutes in `find /Users/micha -maxdepth 3 -name "python3*"`,
was interrupted, and immediately launched `find / -maxdepth …` across the whole
root filesystem. Killed.

## The environment, stated so you never search for it

```
python3   /usr/bin/python3      Python 3.9.6
pytest    python3 -m pytest     pytest 8.4.2   (module form; there is NO pytest binary on PATH)
psql      docker exec development-postgres-2-1 psql -U admin -d <db>
repo      /Users/micha/Audioura      your worktree: /Users/micha/audioura-worktrees/LOCAL-300
```

**Never run `find` against `/` or `/Users/micha`.** Those paths include Docker
volumes, iCloud, and Library caches; even `-maxdepth 3` took 20 minutes. To
locate a program use `command -v <name>`, which is instant. If it is not on
PATH, it is not installed — say so and continue.

**Hard rule: if any command has not returned within ~2 minutes, it is the wrong
command.** Stop it and reconsider. This is the third session lost this way
(D213, and LOCAL-298 before it).

## What remains

The schema is done. Still outstanding from the task above:

- **2.** a committed, runnable rebuild script (`tests/init_test_db.sh` or
  equivalent) that recreates `audiotours_test` from empty;
- **3.** table-parity report, with any remaining differences explained;
- the verification section — suite run against **10 / 990 / 2 / 50** with a
  per-test status diff, and production row counts before and after
  (**147 = 29 real + 118 test**, Nice `[1,12,14,17,24,29,152]`).

**Commit the schema work first**, before anything else, so a fourth session does
not start from zero.

Everything else in the task above stands — no data copied from production, no
test modified, and **expect the failure count to rise**.
