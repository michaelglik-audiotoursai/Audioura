**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-301
**Base:** storied
**Branch:** kiro/local301-corpus-fixtures

# Three existence-gate tests need corpus rows the test database does not have.

Read `DECISIONS.md` **D219**, **D217**, `tests/test_local281_dining_venue_kind.py`,
`tests/init_test_db.sh`, `stop_existence_gate.py`.

## ENVIRONMENT — stated so you never search for it
```
python3   /usr/bin/python3      Python 3.9.6
pytest    python3 -m pytest     pytest 8.4.2   (module form; NO binary on PATH)
psql      docker exec development-postgres-2-1 psql -U admin -d <db>
repo      /Users/micha/Audioura
```
Use `command -v <name>` to locate a program — it is instant. **Never run `find`
against `/` or `/Users/micha`.** Three sessions have been lost that way (D213,
D218). **If a command has not returned in ~2 minutes it is the wrong command.**

## ⚠️ NO container rebuilds (D48). Ceiling **$0.30**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.
**Production `audiotours` is read-only to this task.** You may write freely to
`audiotours_test`.

## The measurement

LOCAL-300 gave `audiotours_test` real schema. Three tests then began failing:

```
AUDIOURA_DB_TARGET=production  ->  14 passed, 0 failed   venue_corpus 18, stop_corpus 94
AUDIOURA_DB_TARGET=test        ->   3 failed             venue_corpus  0, stop_corpus  0
```

```
test_local281_dining_venue_kind.py:143  AssertionError: assert 'unknown' == 'institution'
test_local281_dining_venue_kind.py:152  assert False is True
test_local281_dining_venue_kind.py:163  AssertionError: Eze Village should verify
```

The tests are correct. They exercise `_classify_venue_kind` and the existence
gate, both of which read `venue_corpus` and `stop_corpus`. Those tables are empty
in the test database, so the gate answers "unknown" and nothing verifies.

## Scope

**Give these tests the corpus rows they need, as fixtures they create
themselves.**

- A pytest fixture that inserts the minimum `venue_corpus` / `stop_corpus` rows
  the assertions require, and removes them on teardown.
- **Rows must be created by the fixture, not seeded into the database by
  `init_test_db.sh`.** A test that depends on ambient data is the problem being
  fixed, not the solution. `init_test_db.sh` stays schema-only.
- Derive the minimum from what the assertions actually need — a museum venue
  with a canonical title, and Eze Village as a geographic stop. Read the test to
  find out; do not copy production rows wholesale.

## The line you must not cross

**Do not change what any test asserts.** If `test_riviera_stops_verify` expects
Eze Village to verify, it still must. The fixture supplies the data; it does not
soften the check.

**Do not copy rows out of production.** Construct the fixture data explicitly in
code so a reader can see exactly what the test depends on.

**Do not seed `audiotours_test` permanently.** Schema-only is deliberate (D217) —
ambient data is how tests start passing vacuously.

## Verification

- `AUDIOURA_DB_TARGET=test python3 -m pytest tests/test_local281_dining_venue_kind.py -q`
  → 14 passed, matching the production result.
- Full suite: `AUDIOURA_DB_TARGET=test python3 -m pytest tests/ -q
  --continue-on-collection-errors`, run **once**, redirected to a file. Report
  against **13 failed / 987 passed / 2 skipped / 50 errors**. The count should
  drop to 10; if it does not, say what else moved.
- Confirm `venue_corpus` and `stop_corpus` in `audiotours_test` are **empty again
  after** the run — the fixture must clean up.
- Production `audio_tours`: report before and after. Real count must stay **29**.

## Traps

- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base`, never `storied..HEAD` (D147).
- Under pytest with no env var, `_default_dbname()` already routes to
  `audiotours_test`. To reach production you must pass
  `AUDIOURA_DB_TARGET=production` explicitly — LEAD ran an A/B where both arms
  were the same database and drew a wrong conclusion (D219). Set the target
  explicitly in every command you report.
- **Commit early.** Three sessions have lost completed work by committing only at
  the end.

## Acceptance criteria

- The 3 tests pass against `audiotours_test` via fixtures, with no assertion changed.
- Fixture data constructed in code, not copied from production.
- `init_test_db.sh` still schema-only.
- Corpus tables empty after the run.
- Suite reported against 13/987/2/50; production real count still 29.
- `git status --short` clean. No container rebuilt.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-301.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
