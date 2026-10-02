##### READY FOR REVIEW

**Task:** LOCAL-325 — Lazy DB target resolution  
**Branch:** kiro/local325-lazy-db-target  
**Commit:** b7a6067  

---

## Per-file summary

| File | Change |
|------|--------|
| `tests/db_connection.py` | Removed import-time constants `DEFAULT_DBNAME` and `DEFAULT_DATABASE_URL`. Replaced with `__getattr__` that resolves lazily on access. All existing functions (`get_connection`, `get_db_config`, `get_database_url`) already resolved at call time — the constants were the only import-time resolution. |
| `tests/test_local320_nondining_regression.py` | Removed module-scope `os.environ['AUDIOURA_DB_TARGET'] = 'production'`. Added module-scoped `monkeypatch_module` fixture and autouse `_force_production_db` fixture. `db_conn` explicitly depends on `_force_production_db` to guarantee env is set before connection. |
| `tests/test_credential_store.py` | No change needed — already had autouse fixture, no module-scope assignment. |
| `tests/test_local306_inflight_scoring.py` | Removed module-scope `os.environ["AUDIOURA_DB_TARGET"] = "test"`. Added function-scoped autouse `_force_test_db` fixture. |
| `tests/test_local307_quality_guardrails.py` | Same as above. |
| `tests/test_local312_quality_comms_and_user_index.py` | Same as above. |
| `tests/test_local296_db_target_switch.py` | Updated `test_invalid_target_exits_fatally` to call `db.get_database_url()` (lazy resolution) instead of expecting import-time exit. |
| `tests/test_local325_db_target_isolation.py` | **New.** 12 tests proving per-test target isolation, invalid target fatality, and D214 precedence. |

---

## Verbatim evidence

### Order-independence (both directions pass)

```
=== ORDER 1: credential_store THEN nondining ===
tests/test_credential_store.py::test_plaintext_only_returns_none PASSED  [  9%]
tests/test_credential_store.py::test_encrypted_round_trip PASSED         [ 18%]
tests/test_credential_store.py::test_credential_store_query_excludes_plaintext_columns PASSED [ 27%]
tests/test_local320_nondining_regression.py::TestCyclingTourRegression::test_2stop_riviera_cycling_classification PASSED [ 36%]
tests/test_local320_nondining_regression.py::TestCyclingTourRegression::test_2stop_riviera_cycling_gate PASSED [ 45%]
tests/test_local320_nondining_regression.py::TestCyclingTourRegression::test_8stop_riviera_cycling_gate PASSED [ 54%]
tests/test_local320_nondining_regression.py::TestMuseumTourRegression::test_museum_classification PASSED [ 63%]
tests/test_local320_nondining_regression.py::TestMuseumTourRegression::test_8stop_museum_gate PASSED [ 72%]
tests/test_local320_nondining_regression.py::TestCodePathConfinement::test_geographic_area_never_calls_nominatim PASSED [ 81%]
tests/test_local320_nondining_regression.py::TestCodePathConfinement::test_institution_never_calls_nominatim PASSED [ 90%]
tests/test_local320_nondining_regression.py::TestCodePathConfinement::test_dining_does_call_nominatim PASSED [100%]
======================== 11 passed, 1 warning in 2.15s =========================

=== ORDER 2: nondining THEN credential_store ===
tests/test_local320_nondining_regression.py::TestCyclingTourRegression::test_2stop_riviera_cycling_classification PASSED [  9%]
tests/test_local320_nondining_regression.py::TestCyclingTourRegression::test_2stop_riviera_cycling_gate PASSED [ 18%]
tests/test_local320_nondining_regression.py::TestCyclingTourRegression::test_8stop_riviera_cycling_gate PASSED [ 27%]
tests/test_local320_nondining_regression.py::TestMuseumTourRegression::test_museum_classification PASSED [ 36%]
tests/test_local320_nondining_regression.py::TestMuseumTourRegression::test_8stop_museum_gate PASSED [ 45%]
tests/test_local320_nondining_regression.py::TestCodePathConfinement::test_geographic_area_never_calls_nominatim PASSED [ 54%]
tests/test_local320_nondining_regression.py::TestCodePathConfinement::test_institution_never_calls_nominatim PASSED [ 63%]
tests/test_local320_nondining_regression.py::TestCodePathConfinement::test_dining_does_call_nominatim PASSED [ 72%]
tests/test_credential_store.py::test_plaintext_only_returns_none PASSED  [ 81%]
tests/test_credential_store.py::test_encrypted_round_trip PASSED         [ 90%]
tests/test_credential_store.py::test_credential_store_query_excludes_plaintext_columns PASSED [100%]
======================== 11 passed, 1 warning in 2.22s =========================
```

### Invalid target still fatal

```
$ AUDIOURA_DB_TARGET=bogus python3 -c "import sys; sys.path.insert(0,'tests'); from db_connection import get_database_url; get_database_url()"

======================================================================
FATAL: AUDIOURA_DB_TARGET has invalid value
======================================================================
  Value: 'bogus'
  Valid: 'test' or 'production'

  An ambiguous database target is exactly how production data gets
  touched by test scripts. Set a valid value or unset the variable.
======================================================================
Exit code: 1
```

### Isolation test (12 pass — would have caught the bug)

```
tests/test_local325_db_target_isolation.py::TestModuleWantsTest::test_resolves_to_test_db PASSED [  8%]
tests/test_local325_db_target_isolation.py::TestModuleWantsTest::test_url_contains_test_db PASSED [ 16%]
tests/test_local325_db_target_isolation.py::TestModuleWantsProduction::test_resolves_to_production_db PASSED [ 25%]
tests/test_local325_db_target_isolation.py::TestModuleWantsProduction::test_url_contains_production_db PASSED [ 33%]
tests/test_local325_db_target_isolation.py::TestIsolationWithinSession::test_first_test_targets_test PASSED [ 41%]
tests/test_local325_db_target_isolation.py::TestIsolationWithinSession::test_second_test_targets_production PASSED [ 50%]
tests/test_local325_db_target_isolation.py::TestIsolationWithinSession::test_third_test_targets_test_again PASSED [ 58%]
tests/test_local325_db_target_isolation.py::TestIsolationWithinSession::test_fourth_unset_defaults_to_test_under_pytest PASSED [ 66%]
tests/test_local325_db_target_isolation.py::TestInvalidTargetStillFatal::test_invalid_target_exits PASSED [ 75%]
tests/test_local325_db_target_isolation.py::TestInvalidTargetStillFatal::test_empty_target_exits PASSED [ 83%]
tests/test_local325_db_target_isolation.py::TestPrecedencePreserved::test_target_overrides_database_url PASSED [ 91%]
tests/test_local325_db_target_isolation.py::TestPrecedencePreserved::test_target_overrides_db_name PASSED [100%]
============================== 12 passed in 0.07s ==============================
```

### audio_tours real count

```
BEFORE: SELECT count(*) FROM audio_tours WHERE is_test = false OR is_test IS NULL; → 29
AFTER:  SELECT count(*) FROM audio_tours WHERE is_test = false OR is_test IS NULL; → 29
```

### git status

```
$ git status --short
(clean)
$ git rev-list --count storied..HEAD
1
```

---

## Limitations

1. **Three `run_local*.py` scripts** (`run_local303_generation.py`, `run_local317_generation.py`, `run_local318_generate_tour.py`, `run_local314_dining_corpus.py`, `run_local314_quality_filter.py`) still set `AUDIOURA_DB_TARGET` at module scope. These are standalone generation/verification scripts (not `test_*.py` files collected by pytest), so they don't participate in combined test sessions and don't pollute.

2. **`__getattr__` requires Python 3.7+** for module-level `__getattr__`. The environment is Python 3.9.6 so this is safe, but older Pythons would not support it.

3. **`get_db_config()` does not enforce AUDIOURA_DB_TARGET over DB_NAME.** The precedence fix from D214 lives in `get_database_url()`, not `get_db_config()`. Code calling `get_db_config()` directly with `DB_NAME` set in the environment could still bypass the target switch. All test fixtures use `AUDIOURA_DB_TARGET` (not `DB_NAME`), so this is not an active hazard.
