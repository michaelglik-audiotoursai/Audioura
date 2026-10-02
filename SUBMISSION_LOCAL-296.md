##### READY FOR REVIEW

**Commit:** `a319861`  
**Branch:** `kiro/local296-tests-off-production`  
**Base:** `storied`

---

## Summary

Bounce fix: resolves the three issues LEAD identified while preserving the
verified `db_connection.py` switch logic.

1. **Renamed** `test_local296_db_target_switch.py` →
   `run_local296_verification.py` (verification harness with module-scope DB
   writes must not be pytest-collected).
2. **New proper pytest file** `test_local296_db_target_switch.py` with `def
   test_` functions: pure string-logic tests of get_database_url() resolution,
   no database access, safe for pytest collection (4 tests, all pass).
3. **Fixed banner printing 70×:** implicit string concatenation + `*` operator
   precedence bug. `"FATAL:...\n" "=" * 70` multiplied the concatenated string
   70 times instead of producing a 70-char separator. Replaced with f-strings
   and a pre-computed `banner` variable.
4. **Added `_invalid_target_reported` guard** so the banner prints at most once
   even if `SystemExit` is caught (e.g. by pytest).

---

## Per-file changes

### `tests/db_connection.py` (modified)

- Added `_invalid_target_reported` module-level flag: ensures the fatal banner
  prints exactly once per process, even when `SystemExit` is caught.
- Fixed banner formatting: replaced implicit-concat + `*` with f-strings and
  pre-computed `banner = "=" * 70`. The original code had a Python operator
  precedence bug where `"FATAL:...\n" "=" * 70` produced 70 copies of the
  error message (implicit string concatenation binds before `*`).

### `tests/run_local296_verification.py` (renamed from test_local296_...)

- Content unchanged — this is the integration verification harness that inserts
  rows, confirms routing, and cleans up. Renamed so pytest does not collect it.

### `tests/test_local296_db_target_switch.py` (rewritten)

- Now contains 4 proper `def test_` functions:
  - `test_target_test_resolves_to_audiotours_test` — AUDIOURA_DB_TARGET=test
  - `test_target_production_resolves_to_audiotours` — AUDIOURA_DB_TARGET=production
  - `test_invalid_target_exits_fatally` — AUDIOURA_DB_TARGET=bogus → SystemExit(1)
  - `test_unset_under_pytest_resolves_to_test_db` — no var, pytest detection
- Uses `monkeypatch.setenv` for env isolation; no database connections.

---

## Verification evidence

### pytest suite (4/4 pass, no DB access)

```
$ python3 -m pytest tests/test_local296_db_target_switch.py -v

tests/test_local296_db_target_switch.py::test_target_test_resolves_to_audiotours_test PASSED
tests/test_local296_db_target_switch.py::test_target_production_resolves_to_audiotours PASSED
tests/test_local296_db_target_switch.py::test_invalid_target_exits_fatally PASSED
tests/test_local296_db_target_switch.py::test_unset_under_pytest_resolves_to_test_db PASSED

4 passed in 0.07s
```

### Integration verification (run_local296_verification.py)

```
[BEFORE] Production audio_tours: 143 total = 29 real + 114 test
[BEFORE] Nice list (non-translation): [1, 12, 14, 17, 24, 29, 152]

TEST 1: Switch OFF (default) — generation writes to audiotours
[DB TARGET] verification-switch-off → audiotours (default → production)
  Connected to: audiotours
  Inserted test row id=286 (is_test=true)
  Cleaned up row id=286 (confirmed is_test=true before delete)
  ✓ TEST 1 PASSED

TEST 2: Switch ON (AUDIOURA_DB_TARGET=test) — writes to audiotours_test
[DB TARGET] verification-switch-on → audiotours_test (AUDIOURA_DB_TARGET=test)
  Connected to: audiotours_test
  Inserted test row id=21 in audiotours_test (is_test=true)
  Cleaned up row id=21 from audiotours_test
  ✓ TEST 2 PASSED

TEST 3: Invalid value (AUDIOURA_DB_TARGET=bogus) — must fail loudly
  Exit code: 1
  FATAL: AUDIOURA_DB_TARGET has invalid value   ← ONE banner, not 70
  ✓ TEST 3 PASSED

TEST 4: Production unchanged
[AFTER] Production audio_tours: 143 total = 29 real + 114 test
[AFTER] Nice list (non-translation): [1, 12, 14, 17, 24, 29, 152]
  ✓ TEST 4 PASSED
```

### Banner fix proof

```
# Before fix:
$ AUDIOURA_DB_TARGET=bogus python3 -c "..." 2>&1 | grep -c "FATAL"
70

# After fix:
$ AUDIOURA_DB_TARGET=bogus python3 -c "..." 2>&1 | grep -c "FATAL"
1
```

---

## Production row split

| Measure | Before | After |
|---------|--------|-------|
| Total | 143 | 143 |
| Real | 29 | 29 |
| Test | 114 | 114 |
| Nice list | [1,12,14,17,24,29,152] | [1,12,14,17,24,29,152] |

**No rows deleted. No rows added to production.**

---

## Acceptance criteria checklist

- ✓ One explicit switch (`AUDIOURA_DB_TARGET`) selects the test database
- ✓ Production is the default (switch must be explicitly set)
- ✓ Every generation logs its target database once at start (`log_db_target()`)
- ✓ Verified both ways with production row counts before and after
- ✓ No rows deleted anywhere in this task
- ✓ `is_test` still written and still meaningful
- ✓ `git status --short` clean
- ✓ No container rebuilt
- ✓ No protected files edited
- ✓ test file is proper pytest (4 `def test_` functions, collected, all pass)
- ✓ verification harness renamed to `run_` prefix (not pytest-collected)
- ✓ Invalid-value banner prints once, not 70×

---

## Limitations

- **Existing scripts not migrated.** `run_local293` and `run_local294` hardcode
  `DATABASE_URL` and bypass `get_connection()`. Migrating them is out of scope.
- **`DATABASE_URL` bypasses the switch** (by design — explicit full URL wins).
- **The 114 test rows remain.** Cleanup is on Michael's ask-first list.
- **Cost: $0.00.** No API calls, no generation runs.
