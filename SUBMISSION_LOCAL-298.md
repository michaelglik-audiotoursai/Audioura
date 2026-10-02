##### READY FOR REVIEW

**Commit:** 554f683  
**Branch:** kiro/local298-failure-triage  
**Task:** Triage 26 failing tests and 12 runtime errors. No code changes.

---

## Summary

Ran the full test suite (`26 failed, 960 passed, 16 skipped, 50 errors in 355s`),
then investigated each failure to determine whether it reflects a real defect,
a stale test, or an environment problem.

**Category breakdown:**

| Category | Failures | Runtime Errors |
|----------|:---:|:---:|
| REAL | 2 | 0 |
| ENVIRONMENT | 23 | 0 |
| STALE | 1 | 12 |

The 26 failures reduce to 4 root causes:
1. DB credential mismatch (19 failures) — postgres rejects `admin:password123`
2. Service not running (4 failures) — port 5017 down, hardcoded IP unreachable
3. Env-var pollution from `test_t4_db_down_unit.py` (1 failure)
4. Null-safety bug in `test_user_integration.py` (1 failure)

---

## Files Changed

| File | Change |
|------|--------|
| `TEST_FAILURE_TRIAGE.md` | New — 177 lines. All 26 failures and 12 errors categorized with verbatim assertions, evidence, and recommendations. |

---

## Verbatim Evidence

### Suite run output (final line)
```
26 failed, 960 passed, 16 skipped, 77 warnings, 50 errors in 355.00s (0:05:55)
```

### REAL #1 — test_local296_db_target_switch (env contamination)
```
tests/test_t4_db_down_unit.py:17:os.environ.setdefault('DB_NAME', 'audiotours')
```
This sets `DB_NAME` at module import time. The LOCAL-296 test then calls
`get_database_url()` which checks `DB_NAME` before `AUDIOURA_DB_TARGET`.
Confirmed by running in isolation (passes) vs full suite (fails).

### REAL #2 — test_user_integration (null-safety)
```
tests/test_user_integration.py:109: in test_user_integration
    print(f"     Tour {i+1}: {tour['tour_id']} - {tour['request_string'][:50]}...")
E   TypeError: 'NoneType' object is not subscriptable
```
Captured stdout shows: `Tours: 27 records` — API call succeeded, one tour has
`request_string=NULL` in DB.

### ENVIRONMENT — 19 tests share this error
```
psycopg2.OperationalError: connection to server at "localhost" (::1), port 5433
failed: FATAL: password authentication failed for user "admin"
```
Docker container is running: `development-postgres-2-1 0.0.0.0:5433->5432/tcp`

### No .py files modified
```
$ git diff --stat $(git merge-base storied HEAD)..HEAD
 TEST_FAILURE_TRIAGE.md | 177 +++++++++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 177 insertions(+)
```

---

## Verification

```
$ git status --short
(empty — clean working tree after commit)

$ git rev-list --count storied..HEAD
1

$ git diff --name-only $(git merge-base storied HEAD)..HEAD | grep -E "\.py$"
(empty — no .py files touched)
```

---

## Limitations

1. **DB credentials not verified against the actual container.** The triage identifies
   that `admin:password123` is rejected, but does not investigate what the correct
   password is (that would require inspecting container config or docker-compose
   secrets, which is outside scope).

2. **test_user_integration's null tour data not traced to source.** The test shows
   `request_string=NULL` exists in the user-api response, but this could be a data
   migration issue, an old tour from before the column was required, or a legitimate
   NULL for system-generated tours. Michael needs to decide if NULL is valid.

3. **Test ordering for LOCAL-296 failure is inferred, not proven by bisection.**
   The evidence (`test_t4_db_down_unit.py` sets `DB_NAME` at module level +
   test passes in isolation) is strong but I did not run the suite with
   `--randomly-seed` or test-ordering plugins to confirm the exact contaminator.

4. **The 12 runtime errors were not individually verified for feature liveness.**
   They are all standalone scripts (confirmed by `if __name__ == "__main__"`) and
   their fixture errors prove they cannot run under pytest. Whether the features
   they test when run directly are still live was not checked per-file.
