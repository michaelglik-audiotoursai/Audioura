**Agent:** Mac Mini Kiro
**Task ID:** LOCAL-302
**Base:** storied
**Branch:** kiro/local302-service-writes

# The DB safety switch is in-process only. Tests that call a service still write to production.

Read `DECISIONS.md` **D141**, **D214**, **D217**, `tests/db_connection.py`,
`tests/test_local49_tour_content_persist.py`.

## ENVIRONMENT — stated so you never search for it
```
python3   /usr/bin/python3      Python 3.9.6
pytest    python3 -m pytest     pytest 8.4.2   (module form; NO binary on PATH)
psql      docker exec development-postgres-2-1 psql -U admin -d <db>
repo      /Users/micha/Audioura
```
Use `command -v <name>` to locate a program. **Never run `find` against `/` or
`/Users/micha`** — three sessions were lost that way (D213, D218). **If a command
has not returned in ~2 minutes it is the wrong command.** **Commit early.**

## ⚠️ NO container rebuilds (D48). Ceiling **$0.40**.
Do not edit `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/*`.

## The evidence

Production `audio_tours` test rows have grown 118 → 122 across two suite runs
tonight, while the switch was set to `test`. The rows:

```
id=294  2026-08-06 11:36:49  LOCAL49 Regression Test 1786016159 - Walking Tour
id=293  2026-08-06 11:12:47  LOCAL49 Regression Test 1786014717 - Walking Tour
id=292  2026-08-06 10:46:10  LOCAL49 Regression Test 1786013120 - Walking Tour
...one per suite run, going back hours
```

Cause, confirmed:

```
tests/test_local49_tour_content_persist.py:24  ORCHESTRATOR_URL = http://localhost:5002
tests/test_local49_tour_content_persist.py:72  requests.post(...)

docker inspect audioura-tour-generator-1:
  DATABASE_URL=postgresql://admin:password123@postgres-2:5432/audiotours
```

The test asks a **running service** to generate a tour. That service has
production hardcoded in its own environment. `AUDIOURA_DB_TARGET` lives in the
*test process* and the service never sees it.

**LOCAL-296's switch redirects in-process database access only.** Any test that
drives a container writes wherever the container is pointed. That is a real
limitation of the design, not a bug in the switch.

The test is also one of the 10 known failures — *"Tour generation service call
failed"* — so it creates the row and then dies before any cleanup it may have.

## Scope

### 1. Make the leak stop

`test_local49_tour_content_persist` must not leave a row behind, whether it
passes or fails. Capture the id at creation and remove it in a `finally`.

**D141's narrow exception applies and its conditions are mandatory:** delete only
an id captured in the same run, and only after a `SELECT is_test` on that id
returns `true` immediately before the `DELETE`. Never by name pattern, never by
date range.

### 2. Make service-dependent tests visible

Any test that drives a running container is not hermetic and cannot honour the
target switch. Mark them — a `@pytest.mark.service` or equivalent — and register
the marker so `-m "not service"` gives a run that provably cannot touch
production through a service.

**Report how many tests carry the marker.** That number is the real size of the
gap.

### 3. Document the limitation where it will be read

`tests/db_connection.py` currently implies the switch protects the suite. Add a
short note at the top of `get_database_url()` stating plainly that it governs
in-process access only, and that tests driving a service write wherever the
service points.

## The line you must not cross

**Do not repoint any container at the test database.** Changing a running
service's `DATABASE_URL` affects the app Michael tests from his phone. Out of
scope and not reversible from inside a test run.

**Do not delete the 122 existing test rows.** Row deletion is on Michael's
ask-first list. Report the count; leave them.

**Do not skip the failing test to stop the leak.** Fixing the symptom by
disabling the check is the wrong trade — the test failing is a separate, real
signal.

## Verification

- Run `test_local49_tour_content_persist` **three times** with
  `AUDIOURA_DB_TARGET=test`. Report production `audio_tours` count before and
  after each. It must be **identical** all three times.
- Report the count of tests carrying the new marker.
- `AUDIOURA_DB_TARGET=test python3 -m pytest tests/ -q -m "not service"
  --continue-on-collection-errors` — run once, redirect to a file. Report
  pass/fail/errors, and production row count before and after: unchanged.
- Full suite for comparison against **10 failed / 985 passed / 55 errors**.
- Production real count must stay **29** throughout.

## Traps

- **Run every example you paste and confirm the output matches** (D97, D103).
- Judge protected-file changes from `git merge-base`, never `storied..HEAD` (D147).
- Under pytest with no env var, `_default_dbname()` already routes to
  `audiotours_test`; only an explicit `AUDIOURA_DB_TARGET=production` reaches
  production. State the target explicitly in every command you report (D219).
- `test_local294_sparql_quality.py` errors under full-suite load from Wikidata
  429s and passes standalone (D220). Not yours; do not chase it.

## Acceptance criteria

- The LOCAL49 test leaves no row, pass or fail; proven over three runs.
- Deletion is D141-compliant: captured id, `SELECT is_test` confirmed first.
- Service-dependent tests marked and counted; marker registered.
- `-m "not service"` run leaves production row count unchanged.
- Limitation documented in `tests/db_connection.py`.
- No container repointed, no existing rows deleted, no test skipped.
- `git status --short` clean. No container rebuilt.

## PROCESS

Work in YOUR worktree only. Use `tests/db_connection.py`.
Never hardcode a credential; read `os.environ[...]` with no literal fallback.
Not finished until: (1) committed, `git rev-list --count storied..HEAD` >= 1;
(2) `SUBMISSION_LOCAL-302.md` starting `##### READY FOR REVIEW`;
(3) commit hash, per-file summary, verbatim evidence, limitations section.

Report evidence only — do NOT self-score.
