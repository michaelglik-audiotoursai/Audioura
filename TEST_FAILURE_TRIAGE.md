# Test Failure Triage — LOCAL-298

**Suite run:** `python3 -m pytest tests/ -q --tb=short --continue-on-collection-errors`  
**Result:** `26 failed, 960 passed, 16 skipped, 77 warnings, 50 errors in 355.00s`  
**Date:** 2026-08-06  
**Branch:** kiro/local298-failure-triage  

---

## Summary by Category

| Category | Count (failures) | Count (runtime errors) |
|----------|:---:|:---:|
| REAL | 2 | 0 |
| ENVIRONMENT | 23 | 0 |
| STALE | 1 | 12 |
| UNCLEAR | 0 | 0 |
| **Total** | **26** | **12** |

**Root causes are few.** The 26 failures reduce to 4 distinct causes:

1. **DB credential mismatch** (19 failures) — `password authentication failed for user "admin"` at localhost:5433. The postgres container is running but rejects the hardcoded `admin:password123` credentials.
2. **Service not running** (4 failures) — newsletter-processor (port 5017) is not running; orchestrator at hardcoded IP `192.168.0.217` is unreachable.
3. **Environment contamination from test_t4_db_down_unit.py** (1 failure) — sets `DB_NAME=audiotours` at module import time, polluting `os.environ` for the rest of the suite.
4. **Null-safety bug in test_user_integration** (1 failure) — `tour['request_string']` is None in DB data; test does `[:50]` on it.
5. **Standalone scripts miscollected as pytest tests** (12 runtime errors) — functions have parameters pytest interprets as fixtures.

---

## 26 FAILED Tests

### REAL (2)

---

| field | content |
|---|---|
| test | `tests/test_local296_db_target_switch.py::test_target_test_resolves_to_audiotours_test` |
| assertion | `AssertionError: Expected audiotours_test, got: postgresql://admin:password123@localhost:5433/audiotours` |
| category | **REAL** |
| feature still live? | Yes — `tests/db_connection.py` `get_database_url()` is the sole DB routing function for all tests |
| evidence | `tests/test_t4_db_down_unit.py:17` does `os.environ.setdefault('DB_NAME', 'audiotours')` at module level. Pytest imports this during collection, poisoning `os.environ['DB_NAME']` for the entire session. `get_database_url()` checks `DB_NAME` before calling `_default_dbname()`, so `AUDIOURA_DB_TARGET` is never consulted. Test passes in isolation (`pytest tests/test_local296_db_target_switch.py` = 4 passed). |
| recommended action | Fix test — `test_t4_db_down_unit.py` must not set env vars at module level, or `test_local296_db_target_switch.py` must monkeypatch `DB_NAME` away (like its `test_unset_under_pytest_resolves_to_test_db` already does). |

---

| field | content |
|---|---|
| test | `tests/test_user_integration.py::test_user_integration` |
| assertion | `TypeError: 'NoneType' object is not subscriptable` at line 109: `tour['request_string'][:50]` |
| category | **REAL** |
| feature still live? | Yes — user-api-2 is running on port 5003 (`docker ps` confirms `audioura-user-api-2-1`); the test successfully fetches 27 tours. One tour has `request_string=NULL` in the database. |
| evidence | Captured stdout shows `Tours: 27 records` — the API call succeeded. The crash is at the print statement, not at the API call. Either the test must handle NULL `request_string`, or the API/schema should enforce NOT NULL. |
| recommended action | Fix test — add `or ''` guard on `tour['request_string']`. Separately: ask Michael whether `request_string` should be NOT NULL in the schema (it is the user's original prompt). |

---

### ENVIRONMENT (23)

All 23 share one of three root causes. Grouped below.

#### Group A: DB credential mismatch — `FATAL: password authentication failed for user "admin"` (19 tests)

The postgres container (`development-postgres-2-1`) is running on port 5433, but rejects `admin:password123`. All tests use `tests/db_connection.py` defaults. The password was likely changed in the container or the `audiotours_test` database was never created with those credentials.

| # | test | assertion (verbatim) |
|---|------|---------------------|
| 1 | `tests/test_apple_processing.py::test_final_article_content` | `SystemExit: 7` |
| 2 | `tests/test_database_storage.py::test_database_storage` | `SystemExit: 7` |
| 3 | `tests/test_full_decryption.py::test_decryption` | `SystemExit: 7` |
| 4 | `tests/test_local232_guard_demo.py::test_guard_blocks_production_insert` | `psycopg2.OperationalError: ... password authentication failed for user "admin"` |
| 5 | `tests/test_local232_guard_demo.py::test_guard_blocks_production_update` | `psycopg2.OperationalError: ... password authentication failed for user "admin"` |
| 6 | `tests/test_local232_guard_demo.py::test_guard_blocks_production_delete` | `psycopg2.OperationalError: ... password authentication failed for user "admin"` |
| 7 | `tests/test_local232_guard_demo.py::test_guard_allows_test_db_insert` | `psycopg2.OperationalError: ... password authentication failed for user "admin"` |
| 8 | `tests/test_local232_guard_demo.py::test_guard_allows_production_select` | `psycopg2.OperationalError: ... password authentication failed for user "admin"` |
| 9 | `tests/test_local88_tour_pollution.py::test_tours_near_returns_michaels_9` | `SystemExit: 7` |
| 10 | `tests/test_local88_tour_pollution.py::test_test_mode_tour_flagged_and_excluded` | `SystemExit: 7` |
| 11 | `tests/test_local88_tour_pollution.py::test_helper_cleanup_selective` | `SystemExit: 7` |
| 12 | `tests/test_local88_tour_pollution.py::test_backfill_verification` | `SystemExit: 7` |
| 13 | `tests/test_local88_tour_pollution.py::test_row_count_preserved` | `SystemExit: 7` |
| 14 | `tests/test_nytimes_newsletter.py::test_nytimes_newsletter` | `SystemExit: 7` |
| 15 | `tests/test_phase3_realistic.py::test_realistic_consolidation` | `SystemExit: 7` |
| 16 | `tests/test_spotify_processing.py::test_final_article_content` | `SystemExit: 7` |
| 17 | `tests/test_system_health.py::test_database_connectivity` | `SystemExit: 7` |
| 18 | `tests/test_system_health.py::test_recent_articles` | `SystemExit: 7` |
| 19 | `tests/test_translation_implementation.py::test_tour_generation_with_content` | `SystemExit: 7` |

**Feature still live?** Yes for all — every test above uses `tests/db_connection.py::get_connection()` or direct `psycopg2.connect()` to reach the same postgres instance that the production services use.

**Evidence:** `docker ps` shows `development-postgres-2-1` is up at `0.0.0.0:5433->5432/tcp`. Error is `FATAL: password authentication failed` — the container is reachable but credentials are wrong.

**Recommended action:** Fix environment — verify the postgres container's actual credentials match `admin:password123`, or update `db_connection.py` defaults to match reality. This is a single fix that clears 19 of 26 failures.

---

#### Group B: Service not running — newsletter-processor on port 5017 (3 tests)

| # | test | assertion (verbatim) |
|---|------|---------------------|
| 20 | `tests/test_phase3_consolidation.py::test_consolidation_status` | `requests.exceptions.ConnectionError: HTTPConnectionPool(host='localhost', port=5017): ... Connection refused` |
| 21 | `tests/test_security_fix.py::test_fake_credentials` | `requests.exceptions.ConnectionError: HTTPConnectionPool(host='localhost', port=5017): ... Connection refused` |
| 22 | `tests/test_security_fix.py::test_verified_credentials_check` | `requests.exceptions.ConnectionError: HTTPConnectionPool(host='localhost', port=5017): ... Connection refused` |

**Feature still live?** Yes — `docker-compose.yml` defines `newsletter-processor` on port 5017; `user_consolidation_service.py` exists.

**Evidence:** `docker ps | grep 5017` returns nothing. Container is defined but not currently running.

**Recommended action:** Fix environment — start the newsletter-processor container, or mark these tests with `@pytest.mark.skipif` when the service is down.

---

#### Group C: Hardcoded unreachable IP / service-writes-to-wrong-DB (1 test)

| # | test | assertion (verbatim) |
|---|------|---------------------|
| 23 | `tests/test_user_tracking_fix.py::test_tracking_fix` | `requests.exceptions.ConnectionError: HTTPConnectionPool(host='192.168.0.217', port=5002): ... Operation timed out` |

**Feature still live?** Yes — orchestrator is running at localhost:5002 (`audioura-tour-orchestrator-1`).

**Evidence:** Test hardcodes `192.168.0.217` instead of `localhost` at lines 39, 54, 80. The orchestrator container is running but at localhost.

**Recommended action:** Fix test — replace hardcoded IP with `os.environ.get("ORCHESTRATOR_URL", "http://localhost:5002")`.

---

### STALE (1)

| field | content |
|---|---|
| test | `tests/test_local49_tour_content_persist.py::test_tour_content_persisted_on_generation` |
| assertion | `AssertionError: Tour row not found in DB for 'LOCAL49 Regression Test 1786003620'` |
| category | **STALE** |
| feature still live? | The orchestrator is live, but this test's architecture is broken by design: it generates a tour via HTTP (orchestrator writes to `audiotours` inside Docker) then queries `audiotours_test` (pytest routing via LOCAL-232). The tour will never be in `audiotours_test`. |
| evidence | `docker-compose-master.yml` line 64: orchestrator uses `DATABASE_URL: postgresql://admin:password123@postgres-2:5432/audiotours`. Test uses `get_db_config()` which routes to `audiotours_test` under pytest (LOCAL-232). These are different databases. This test was designed before LOCAL-232 introduced test DB routing, making it structurally impossible to pass under the current architecture. |
| recommended action | Delete test or rewrite — the test cannot work with split DBs. If the regression it guards matters, it must either (a) query the production DB directly, or (b) use a unit test pattern that doesn't depend on the orchestrator writing to the same DB. Ask Michael. |

---

## 12 Runtime Errors

All 12 share the same root cause: **standalone scripts with `test_*` functions that take parameters**. Pytest collects them as tests and interprets their parameters as fixture requests. They were missed by LOCAL-297's rename pass because they DO contain functions named `test_*` (LOCAL-297 only renamed files with zero test functions).

| Category | All 12 |
|---|---|
| category | **STALE** |
| feature still live? | Mixed — some test live endpoints, but they are all standalone scripts designed to be run with `python3 tests/test_xxx.py`, not via pytest |
| evidence | Every file has `if __name__ == "__main__"` and a function like `def test_service(service_name, url, ...)` where `service_name` has no pytest fixture. Error is always `fixture 'X' not found`. |
| recommended action | Rename to `run_*.py` (same treatment as LOCAL-297's 40 files) |

| # | test | error (verbatim) |
|---|------|-----------------|
| 1 | `tests/test_all_newsletter_technologies.py::test_newsletter_technology` | `fixture 'name' not found` |
| 2 | `tests/test_connectivity.py::test_service` | `fixture 'service_name' not found` |
| 3 | `tests/test_enhanced_newsletters.py::test_newsletter` | `fixture 'url' not found` |
| 4 | `tests/test_existing_endpoints.py::test_endpoint` | `fixture 'url' not found` |
| 5 | `tests/test_newsletter_cloud.py::test_health` | `fixture 'base_url' not found` |
| 6 | `tests/test_newsletter_cloud.py::test_newsletters_list` | `fixture 'base_url' not found` |
| 7 | `tests/test_newsletter_cloud.py::test_process_newsletter` | `fixture 'base_url' not found` |
| 8 | `tests/test_newsletter_cloud.py::test_get_articles` | `fixture 'base_url' not found` |
| 9 | `tests/test_newsletter_cloud.py::test_download_article` | `fixture 'base_url' not found` |
| 10 | `tests/test_newsletter_technologies.py::test_newsletter_processing` | `fixture 'newsletter_url' not found` |
| 11 | `tests/test_tour_editing.py::test_endpoint` | `fixture 'method' not found` |
| 12 | `tests/test_zip_verification.py::test_zip_download` | `fixture 'article_id' not found` |

---

## Key Insight

**19 of 26 failures have the same fix:** correct the postgres credentials (or confirm they match the running container). This is one environment problem, not 19 test defects. Once credentials are aligned, only 7 failures remain, and of those:

- 3 need the newsletter-processor container running
- 1 needs a hardcoded IP fixed
- 1 is structurally impossible (split-DB architecture)
- 1 is env-var pollution from another test file
- 1 is a null-safety bug in a print statement

The 12 runtime errors are a straightforward LOCAL-297 follow-up (rename 8 files).
