##### READY FOR REVIEW

## LOCAL-102: Dead Test Cleanup (REVISED per LEAD bounce)

### Commit

```
Branch: kiro/local102-dead-tests
```

### What changed from the bounced attempt

The first attempt deleted 50 tests, treating `ModuleNotFoundError` from PyPI
packages (bs4, Crypto, selenium, cryptography) as evidence that modules were
removed. LEAD correctly identified this as wrong: those packages ARE declared
in requirements*.txt. The modules exist — only the pip environment is
incomplete.

**Key finding: there are ZERO truly dead tests.** Every project module
imported by every test file still exists in the repository. All 41 import
failures are caused by missing pip packages, not removed project files.

### Inventory (corrected)

| Category | Count | Treatment |
|----------|-------|-----------|
| Live tests (pass without services/deps) | 51 | Run by default — all green |
| Needs-services (Docker/DB/network/API keys) | 69 | Listed in `tests/NEEDS_SERVICES.txt`, skipped by default |
| Needs-dependency (bs4/selenium/Crypto/cryptography/Py3.12 syntax) | 42 | Listed in `tests/NEEDS_DEPENDENCY.txt`, skipped by default |
| CLI utilities (not tests) | 8 | Moved to `tools/` |
| Dead tests (import removed project module) | **0** | None exist |
| **Total** | **170** | |

### Needs-dependency breakdown (42 files)

| Missing package | Declared in | Count |
|----------------|-------------|-------|
| bs4 (beautifulsoup4) | requirements-browser.txt, requirements-newsletter.txt | 16 |
| selenium | requirements-browser.txt | 14 |
| Crypto (pycryptodome) | requirements.txt | 5 |
| cryptography | requirements.txt | 1 |
| selenium (via browser_automation) | requirements-browser.txt | 3 |
| Python 3.12+ syntax (f-string) | N/A — version issue | 3 |

### CLI utilities moved to `tools/` (8 files)

```
tests/test_coordinates.py         -> tools/coordinates_test_tool.py
tests/test_coordinates_direct.py  -> tools/coordinates_direct_tool.py
tests/test_coordinates_endpoint.py -> tools/coordinates_endpoint_tool.py
tests/test_coordinates_service.py -> tools/coordinates_service_tool.py
tests/test_coordinates_service_v2.py -> tools/coordinates_service_v2_tool.py
tests/test_mapbox.py             -> tools/mapbox_tool.py
tests/test_tour_generation.py    -> tools/tour_generation_tool.py
tests/test_zip_quality.py        -> tools/zip_quality_tool.py
```

### Suite runner output (AFTER)

```
======================================================================
  TEST SUITE RUNNER — 51 tests
  (skipping 69 needs-services, 42 needs-dependency)
======================================================================

  RESULTS: 51 passed, 0 failed (of 51 total)
======================================================================
```

Exit code: 0. Green means green.

### Raw pytest collection (BEFORE — this is what people see without the runner)

```
344 tests collected, 41 errors in 0.81s
```

Those 41 errors are ALL `ModuleNotFoundError` for PyPI packages (38) plus
3 Python 3.12 syntax errors on the host's Python 3.9.

### Prepush-baseline confirmation

Checked `~/audioura-worktrees/prepush-baseline`: the same 41 files error at
collection. None of them were passing. Nothing removed was passing.

### Real failures that still exist (needs-services category)

These are real code-level or data-level failures that surface when you run
with `--include-services`. They are NOT deleted — they remain and will report
correctly when services are available:

1. `tests/test_local49_tour_content_persist.py` — 33 tours with NULL tour_content (LOCAL-88 test data)
2. `tests/test_user_integration.py` — TypeError: NoneType subscript (code bug)
3. `tests/test_phase3_consolidation.py` — connection refused to localhost service
4. `tests/test_security_fix.py` — connection refused to localhost service
5. `tests/test_user_tracking_fix.py` — connection refused to localhost service
6. `tests/test_news_quota_integration.py` — SystemExit: 7 (DB unreachable)
7. `tests/test_tour_quota_integration.py` — SystemExit: 7 (DB unreachable)
8. `tests/test_apple_processing.py` — SystemExit: 7 (DB unreachable)
9. `tests/test_database_storage.py` — SystemExit: 7 (DB unreachable)
10. `tests/test_spotify_processing.py` — SystemExit: 7 (DB unreachable)
11. `tests/test_system_health.py` — SystemExit: 7 (DB unreachable)
12. `tests/test_nytimes_newsletter.py` — SystemExit: 7 (DB unreachable)

The first 2 are genuine code/data bugs. The rest are infrastructure
(running services / DB). All preserved, all listed.

### Database constraint

```
audio_tours row count: 86 (before and after — no DELETE FROM audio_tours)
```

### Per-file changes

| File | Action |
|------|--------|
| `run_tests.py` | NEW — suite runner with --include-services, --include-deps, --all flags |
| `tests/NEEDS_SERVICES.txt` | NEW — 69 tests requiring Docker/DB/network |
| `tests/NEEDS_DEPENDENCY.txt` | NEW — 42 tests requiring pip packages or Python 3.12 |
| `tools/README.md` | NEW — describes CLI tools |
| `tools/*.py` (8 files) | MOVED from tests/ — CLI diagnostic utilities |
| `tests/test_coordinates*.py` (5) | DELETED (moved to tools/) |
| `tests/test_mapbox.py` | DELETED (moved to tools/) |
| `tests/test_tour_generation.py` | DELETED (moved to tools/) |
| `tests/test_zip_quality.py` | DELETED (moved to tools/) |

### Limitations

- The `needs-dependency` tests cannot be verified without installing bs4,
  selenium, pycryptodome, and cryptography. On the Docker container (which has
  these packages), they should pass — but that wasn't verified here.
- Python 3.12 syntax tests (`test_multiple_spotify_urls.py`,
  `test_regex_behavior.py`, `test_boston_globe_auth_enhanced.py`) will only
  work on Python 3.12+. The host runs 3.9.
- The 69 needs-services tests were classified by code inspection (looking for
  `requests.get/post` to localhost, `psycopg2.connect`, etc.) — not by
  exhaustive runtime verification with services up.
