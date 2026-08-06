##### READY FOR REVIEW

**Task:** LOCAL-299  
**Branch:** `kiro/local299-import-time-env`  
**Commit:** `bf3cd37`  
**Base:** `storied`

---

## Summary

Moved module-scope `os.environ.setdefault()` calls in `tests/test_t4_db_down_unit.py` (lines 16-20) into a `monkeypatch`-based autouse pytest fixture. These calls set `DB_NAME=audiotours` at import time, poisoning `os.environ` for the entire pytest session. D214 fixed the precedence (symptom removed); this commit removes the cause.

---

## Per-file changes

| File | Change |
|------|--------|
| `tests/test_t4_db_down_unit.py` | Removed 5 module-scope `os.environ.setdefault()` calls (DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, DB_PORT). Added `import pytest`. Added `@pytest.fixture(autouse=True) _db_env_for_news_orchestrator(monkeypatch)` that sets the same vars via `monkeypatch.setenv` (auto-restoring on teardown). No assertions changed. |

---

## Full inventory of module-scope side effects in collected test files

### Fixed in this task (DB_* / DATABASE_URL / AUDIOURA_DB_TARGET):

1. **`tests/test_t4_db_down_unit.py`** (lines 16-20) — `os.environ.setdefault('DB_HOST'/'DB_NAME'/'DB_USER'/'DB_PASSWORD'/'DB_PORT')` — **FIXED** → moved to fixture

### Deferred (non-DB vars, safe):

2. **`tests/test_spine_quality_gate.py`** (line 20) — `os.environ.setdefault("STORIED_MODE", "true")` — affects LLM mode, not database routing. No production-data risk.

### Not applicable (inside functions, not module scope):

- `tests/test_local110_sharing_wiring_guard.py` — `setdefault("DATABASE_URL", ...)` inside function body
- `tests/test_local113_persona_wiring_guard.py` — same, inside function
- `tests/test_local114_referral_wiring_guard.py` — same, inside function
- `tests/test_local153_tour_editing_shims_guard.py` — same, inside function
- `tests/test_local64_cost_ceiling.py` — env mutation inside test function with `finally` cleanup
- `tests/test_local281_dining_venue_kind.py` — env mutation inside test methods with cleanup
- `tests/test_tour_factory.py` / `tests/test_tour_helper.py` — inside test methods

### conftest.py (intentional):

- `tests/conftest.py:116` — `os.environ["_AUDIOURA_PYTEST_SESSION"] = "1"` — by design (D232 guard)

---

## Evidence: D214 already blocks the symptom

```
$ python3 -c "
import os, sys
sys.path.insert(0, 'tests')
for k in ['DB_HOST','DB_NAME','DB_USER','DB_PASSWORD','DB_PORT']:
    os.environ.pop(k, None)
os.environ['AUDIOURA_DB_TARGET'] = 'test'
os.environ['_AUDIOURA_PYTEST_SESSION'] = '1'
from db_connection import get_database_url
url_before = get_database_url()
print(f'BEFORE: {url_before}')
os.environ.setdefault('DB_NAME', 'audiotours')
url_after = get_database_url()
print(f'AFTER module-scope setdefault (with D214 fix): {url_after}')
"
BEFORE: postgresql://admin:password123@localhost:5433/audiotours_test
AFTER module-scope setdefault (with D214 fix): postgresql://admin:password123@localhost:5433/audiotours_test
```

D214 fix is in place: `AUDIOURA_DB_TARGET=test` outranks the leaked `DB_NAME`.
LOCAL-299 removes the **cause** (the module-scope setdefault itself).

---

## Evidence: no remaining module-scope DB mutations

```
$ grep -n "^os\.environ" tests/test_*.py | grep -i "DB_\|DATABASE_URL\|AUDIOURA_DB_TARGET"
(no output — clean)
```

AST-based scan of all `tests/test_*.py` module-scope statements confirmed zero mutations of DB_*, DATABASE_URL, or AUDIOURA_DB_TARGET.

---

## Test suite result

```
$ AUDIOURA_DB_TARGET=test python3 -m pytest tests/ -q --tb=short --continue-on-collection-errors
10 failed, 990 passed, 2 skipped, 82 warnings, 50 errors in 270.15s
```

**Baseline:** 26 failed, 960 passed, 16 skipped, 50 errors  
**After:** 10 failed, 990 passed, 2 skipped, 50 errors

Result is **strictly better** — 16 fewer failures, 30 more passing. The improvement comes from removing `DB_PASSWORD=test` (wrong credential) that was leaking from `test_t4_db_down_unit.py` and causing authentication failures in downstream tests. Errors unchanged at 50 (all pre-existing collection errors from standalone scripts).

### All 10 remaining failures are pre-existing:

- `test_full_decryption` — psycopg2 UndefinedTable (pre-existing)
- `test_local49_tour_content_persist` — STALE per triage (split-DB structural impossibility)
- `test_local88_tour_pollution` ×2 — pre-existing assertion failures
- `test_phase3_consolidation` — service not running (ConnectionError)
- `test_phase3_realistic` — psycopg2 error (credential/schema)
- `test_security_fix` ×2 — service not running (ConnectionError)
- `test_user_integration` — TypeError on None (pre-existing null-safety bug)
- `test_user_tracking_fix` — service not running (ConnectionError)

No previously-passing test now fails.

---

## Constraints verified

- [x] No assertions changed
- [x] No files renamed
- [x] No D214 precedence weakened
- [x] No container rebuilt
- [x] No database rows deleted
- [x] No edits to DECISIONS.md, CLAUDE.md, BACKLOG.md, .continuous_dev/*
- [x] `git status --short` clean
- [x] `git rev-list --count storied..HEAD` = 1

---

## Limitations

- `tests/test_spine_quality_gate.py` line 20 sets `STORIED_MODE` at module scope. This is a non-DB var with no production-data risk, deferred to a follow-up.
- The 50 collection errors (standalone scripts with parameterized functions) remain — these are the LOCAL-297 follow-up, not in scope.
- The `if __name__ == '__main__'` block in `test_t4_db_down_unit.py` still works for standalone execution but won't benefit from the fixture (it calls the functions directly). This is acceptable since standalone invocation is outside pytest context.
