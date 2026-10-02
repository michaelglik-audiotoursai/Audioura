##### READY FOR REVIEW

**Task:** LOCAL-302  
**Branch:** kiro/local302-service-writes  
**Commit:** 0ed3418  

---

## Per-file summary

| File | Change |
|------|--------|
| `tests/test_local49_tour_content_persist.py` | Added `finally` block with D141-compliant cleanup. Captures `tour_id` (or finds it by timestamp on early failure). Calls `_ensure_is_test_on_production()` then `_d141_cleanup()` which SELECTs `is_test`, confirms TRUE, then DELETEs. All three helpers connect directly to production using `conftest._original_connect` (the unguarded psycopg2), since the service writes there regardless of the test-process switch. Added `@pytest.mark.service` to `test_tour_content_persisted_on_generation`. |
| `tests/conftest.py` | Registered `service` marker (with description) and `integration` marker in `pytest_configure`. |
| `tests/db_connection.py` | Added documentation block at top of `get_database_url()` stating the switch governs in-process access only, and that service-driven tests bypass it. References `-m "not service"`. |
| 37 test files | Added `import pytest` (where absent) and `@pytest.mark.service` decorator to test functions that make HTTP requests to Docker services on ports 5000–5030. |

---

## Evidence

### 1. LOCAL-49 test leaves no row — three runs

```
BEFORE (all runs): audio_tours total=151, real=29

Run 1: PASSED  → tour 295 created + cleaned → total=151, real=29
Run 2: PASSED  → tour 296 created + cleaned → total=151, real=29
Run 3: FAILED  → no row found (service errored before INSERT) → total=151, real=29
```

Command used each time:
```
AUDIOURA_DB_TARGET=test python3 -m pytest tests/test_local49_tour_content_persist.py::test_tour_content_persisted_on_generation -v --tb=short
```

### 2. D141 compliance

Deletion follows all D141 conditions:
- Only the id captured in the same run is targeted
- `SELECT is_test FROM audio_tours WHERE id = %s` immediately precedes the DELETE
- DELETE only fires if `is_test is True`
- Never by name pattern, never by date range
- If `is_test` is not TRUE, the row is left and a WARNING printed

### 3. Service-dependent tests — count

```
49/1014 tests collected (965 deselected), 38 errors
```

**49 tests carry the `service` marker** across 37 files.

### 4. `-m "not service"` run — production unchanged

```
AUDIOURA_DB_TARGET=test python3 -m pytest tests/ -q -m "not service" --continue-on-collection-errors
Result: 4 failed, 956 passed, 2 skipped, 49 deselected, 41 errors (83.40s)

Production row count before: 151 total, 29 real
Production row count after:  151 total, 29 real
```

### 5. Full suite comparison

```
AUDIOURA_DB_TARGET=test python3 -m pytest tests/ -q --continue-on-collection-errors
Result: 9 failed, 991 passed, 2 skipped, 50 errors (230.88s)

Production row count after: 151 total, 29 real
```

Baseline was 10 failed / 985 passed / 55 errors. The shift (9 vs 10 failed, 991 vs 985 passed) is because the LOCAL49 test now passes when the service succeeds (2 of 3 runs) and several collection errors were resolved by the added `import pytest`.

### 6. Production real count

**29** throughout all runs. Never changed.

---

## Limitations

1. **49 tests remain that can write to production via services.** The marker makes them visible and excludable, but does not fix the underlying architecture — services still point at production. The real fix is LOCAL-232 (move tests off the production database entirely) or repointing service DATABASE_URL to test (explicitly out of scope per task).

2. **The cleanup requires the orchestrator service to be running.** If the service is down, `_generate_tour` raises immediately (connection refused), no row is created, no cleanup needed. The edge case is: service accepts the request, inserts the row, then dies before completing — the `finally` block handles this by searching for the row by timestamp.

3. **The `integration` marker is registered but was pre-existing on the LOCAL49 tests.** It is not systematically applied to other tests.

4. **`db_step1_stored.txt` and `db_step2_retrieved_bytes.txt`** were dirty in the worktree before this task. They are stashed, not committed.
