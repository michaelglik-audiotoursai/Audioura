##### READY FOR REVIEW

## LOCAL-81: Port-fix two subscribed-only test suites

**Branch:** `kiro/local81-port-fix-subscribed-tests`  
**Base:** `origin/subscribed` (`3411407`)  
**Commit:** `953c787`

---

### Summary

Converted `tests/test_wallet_api.py` and `tests/test_local67_entitlement_gate.py`
to use the shared `tests/db_connection.py` helper (introduced by LOCAL-77).
Both previously hardcoded port 5432, causing "connection refused" on the Mac Mini
where Docker maps postgres to host port 5433.

---

### Sweep results

| Metric | Count |
|--------|-------|
| Test files importing psycopg2 | 25 |
| Already using db_connection.py | 23 (after this fix) |
| db_connection.py itself | 1 |
| Mock-only (test_t4_db_down_unit, already has setdefault 5433) | 1 |
| **Files needing conversion** | **2** |
| **Files changed** | **2** |

No file already using the helper was modified.

---

### Per-file changes

#### `tests/test_wallet_api.py`
- Removed: `DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://admin:password123@localhost:5432/audiotours")`
- Removed: `psycopg2.connect(DATABASE_URL)` in `get_db()`
- Added: `from db_connection import get_database_url, get_connection, get_db_config`
- Added: `os.environ.setdefault` calls from helper config (so service modules find DB)
- Added: `get_db()` now calls `get_connection()` from helper

#### `tests/test_local67_entitlement_gate.py`
- Removed: Hand-rolled `DB_CONFIG` dict with `'port': os.getenv('DB_PORT', '5432')`
- Added: `from db_connection import get_db_config`
- Added: `os.environ.setdefault` calls from helper config (so entitlements/wallet_ledger modules find DB)
- Added: `DB_CONFIG` now derived from `get_db_config()` (defaults to 5433)

---

### Evidence: tests pass with NO environment variables

```
$ env -u DATABASE_URL -u DB_HOST -u DB_PORT -u DB_NAME -u DB_USER -u DB_PASSWORD python3 tests/test_wallet_api.py
============================================================
LOCAL-68: Wallet API — Contract Test Suite
============================================================
Target: http://localhost:5002
Database: postgresql://admin:password123@localhost:5433/audiotours
...
Results: 53/53 passed, 0 failed
ALL TESTS PASSED ✓
============================================================
```

```
$ env -u DATABASE_URL -u DB_HOST -u DB_PORT -u DB_NAME -u DB_USER -u DB_PASSWORD python3 tests/test_local67_entitlement_gate.py
======================================================================
LOCAL-67: Entitlement Gate Enforcement — Test Suite
======================================================================
✓ Database connected (localhost:5433)
...
RESULTS: 23/23 passed, 0 failed
======================================================================
```

### Evidence: tests pass with explicit DATABASE_URL

```
$ DATABASE_URL="postgresql://admin:password123@localhost:5433/audiotours" python3 tests/test_wallet_api.py
Results: 53/53 passed, 0 failed

$ DATABASE_URL="postgresql://admin:password123@localhost:5433/audiotours" python3 tests/test_local67_entitlement_gate.py
RESULTS: 23/23 passed, 0 failed
```

---

### Commit hash

```
953c787
```
