##### READY FOR REVIEW

# LOCAL-117: Dead Code Removal (Corrected per LEAD Bounce)

**Branch:** `kiro/local117-dead-code-removal`  
**Agent:** Mac Mini Kiro  
**Date:** 2026-08-01 (corrected 2026-08-02)

---

## Correction Summary

LEAD bounce identified one deletion (`news_search_service.py`) as potentially
dangerous. This correction:

1. **Restores `news_search_service.py`** per LEAD directive.
2. **Re-verifies all 14 findings against entry points** — not just import graphs.
3. **Amends UNWIRED_AUDIT.md** method section with limitation #7 (entry-point
   blind spot).

### Factual note on the bounce

The LEAD's bounce states: "Dockerfile.simple-news-search references
news_search_service.py". Re-verification shows this is not the case:

```
$ cat Dockerfile.simple-news-search | grep -E "CMD|COPY.*\.py"
COPY simple_news_search_service.py .
CMD ["python", "simple_news_search_service.py"]
```

The Dockerfile copies and runs `simple_news_search_service.py` (with `simple_`
prefix). `simple_news_search_service.py` does not import `news_search_service`.
They are independent files. No other Dockerfile, docker-compose file, or shell
script references `news_search_service.py` by name.

Nevertheless, the LEAD directive to keep the file is followed. The file is
restored and reclassified.

---

## Per-Symbol Table (all 14 DEAD findings re-verified)

| # | Symbol | File | Entry-point check | Import check | Verdict | Action |
|---|--------|------|-------------------|--------------|---------|--------|
| 1 | `register_routes(app, get_db)` | `user-tracking/routes.py` | Not in any Dockerfile CMD, docker-compose command, or shell script. `user-tracking/Dockerfile` CMD = `app.py` | Only importer: `app_with_routes.py` (also deleted) | DEAD ✓ | **Removed** (commit `baac74b`) |
| 2 | `init_database()` | `custom_audio_service.py` | Not in any Dockerfile CMD or docker-compose command | Zero importers | DEAD ✓ | **Removed** (commit `6b6a02b`) |
| 3 | `init_db()` | `user-tracking/app_fixed_final.py` | Not in any Dockerfile CMD. `user-tracking/Dockerfile` CMD = `app.py` | Zero importers | DEAD ✓ | **Removed** (commit `baac74b`) |
| 4 | `setup_logging()` | `enhanced_logging.py` | Not in any Dockerfile CMD or docker-compose command | Zero importers | DEAD ✓ | **Removed** (commit `4588380`) |
| 5 | `content_validation.py` (module) | root | Not in any Dockerfile CMD or docker-compose command | Zero importers | DEAD ✓ | **Removed** (commit `6b6a02b`) |
| 6 | `pdf_processor.py` (module) | root | Not in any Dockerfile CMD or docker-compose command | Zero importers | DEAD ✓ | **Removed** (commit `6b6a02b`) |
| 7 | `service_config.py` (module) | root | Not in any Dockerfile CMD or docker-compose command | Zero importers | DEAD ✓ | **Removed** (commit `6b6a02b`) |
| 8 | `custom_audio_service.py` (module) | root | Not in any Dockerfile CMD or docker-compose command | Zero importers | DEAD ✓ | **Removed** (commit `6b6a02b`) |
| 9 | `news_search_service.py` (module) | root | Not in any Dockerfile CMD or docker-compose command. `Dockerfile.simple-news-search` runs `simple_news_search_service.py` (different file). | Zero importers. `simple_news_search_service.py` does NOT import it. | Reclassified KEPT | **Restored** (commit `fe90eff`, per LEAD directive) |
| 10 | `voice_control_service.py` (module) | root | Not in any Dockerfile CMD or docker-compose command. `voice_control/Dockerfile` CMD = `app.py` | Zero importers | DEAD ✓ | **Removed** (commit `6b6a02b`) |
| 11 | `coordinates_fromai_service.py` (module) | root | Not in any Dockerfile CMD or docker-compose command. `coordinates_fromAI/Dockerfile` CMD = `app.py` | Zero importers | DEAD ✓ | **Removed** (commit `6b6a02b`) |
| 12 | `store_audio_tours.py` (module) | root | Not in any Dockerfile CMD or docker-compose command | Zero importers. `tour_orchestrator_service.py` has its own `def store_audio_tour`. | DEAD ✓ | **Removed** (commit `6b6a02b`) |
| 13 | `tour_delivery_service.py` (module) | root | Not in any Dockerfile CMD or docker-compose command. `map_delivery/Dockerfile` CMD = `app.py` | Zero importers | DEAD ✓ | **Removed** (commit `6b6a02b`) |
| 14a | `validate_poi_knowledge()` | `generate_tour_text.py:576` | N/A (function in a live file) | Zero call sites across entire codebase | DEAD ✓ | **Removed** (commit `9f3d254`) |
| 14b | `call_coordinates_service()` | `tour_orchestrator_service.py:1167` | N/A (function in a live file) | Zero call sites across entire codebase | DEAD ✓ | **Removed** (commit `9f3d254`) |

**Result:** 12 removed, 1 kept (LEAD directive), 1 not removed (see below).

---

## What Was NOT Removed (and why)

| Symbol | File | Reason kept |
|--------|------|-------------|
| `news_search_service.py` | root | LEAD directive. Although re-verification shows zero references in any Dockerfile CMD, docker-compose command, or shell script, the LEAD identified potential entry-point risk and directed restoration. Complied. |
| `except ImportError` block | `content_qa_runner.py:768` | Not dead code — it is a control-flow pattern (try/except for optional dependency). The code runs; the import might or might not succeed at runtime. This is defensive programming, not unreachable code. |

---

## Entry-Point Verification Method (per LEAD requirement)

For each of the 14 symbols, verified against:

1. **All `Dockerfile*` files** (29 files) — checked `CMD` and `ENTRYPOINT` lines
2. **All `docker-compose*.yml` files** (15 files) — checked `command:` directives
3. **All shell scripts** (8 `.sh` files) — checked for Python file references
4. **No crontab, launchd plist, or systemd unit** references any deleted file
5. **No `getattr`/`importlib`/`__import__` dynamic dispatch** references any deleted symbol

Verification command per symbol:
```bash
grep -rn "\b<stem>\b" Dockerfile* */Dockerfile docker-compose*.yml */docker-compose*.yml *.sh .continuous_dev/*.sh
```

All returned zero results for every removed file.

---

## Commits

| Hash | Description | Files changed |
|------|-------------|---------------|
| `6b6a02b` | Remove 9 dead standalone service files | -8 files (was 9, `news_search_service.py` restored in `fe90eff`) |
| `baac74b` | Remove 3 dead user-tracking files | -3 files |
| `4588380` | Remove enhanced_logging.py | -1 file |
| `9f3d254` | Remove 2 dead functions from live service files | generate_tour_text.py, tour_orchestrator_service.py |
| `a04ecf8` | Add SUBMISSION_LOCAL-117.md | +1 file |
| `fe90eff` | Restore news_search_service.py + audit method update | +1 file, UNWIRED_AUDIT.md updated |

---

## Test Results

### Before (storied baseline)

```
RESULTS: 56 passed, 4 failed (of 60 total)

FAILURES:
  ✗ tests/test_local113_persona_wiring_guard.py
  ✗ tests/test_spine_quality_baseline.py
  ✗ tests/test_spine_quality_e2e.py
  ✗ tests/test_spine_quality_noise_floor.py
```

### After (all commits applied + news_search_service.py restored)

```
RESULTS: 56 passed, 4 failed (of 60 total)

FAILURES:
  ✗ tests/test_local113_persona_wiring_guard.py
  ✗ tests/test_spine_quality_baseline.py
  ✗ tests/test_spine_quality_e2e.py
  ✗ tests/test_spine_quality_noise_floor.py
```

**Identical.** All 4 failures are pre-existing on storied (verified by running
tests on the storied branch directly).

---

## AST Parse Verification

```bash
python3 -c "import ast; ast.parse(open('news_search_service.py').read())"   # OK
python3 -c "import ast; ast.parse(open('generate_tour_text.py').read())"    # OK
python3 -c "import ast; ast.parse(open('tour_orchestrator_service.py').read())"  # OK
```

All Python files touched parse cleanly.

---

## Database Row Count

```
audio_tours row count: 88 (before and after — no DELETE FROM audio_tours)
```

---

## UNWIRED_AUDIT.md Changes

Added **limitation #7** to the "What This Method Cannot Detect" section:

> **Entry-point invocations outside the import graph** — a module can be
> reachable via `Dockerfile` `CMD`/`ENTRYPOINT`, `docker-compose` `command:`,
> a `launchd`/cron invocation, or by being run directly as a script. None of
> these appear in a Python import graph. Static analysis that only walks
> `import` statements will correctly report zero callers for such a module
> while it is in fact the live entry point of a running container or scheduled
> job. **Mitigation:** before classifying any standalone `.py` file as DEAD,
> grep all `Dockerfile*`, `docker-compose*.yml`, `*.sh`, crontabs, and launchd
> plists for its filename.

Reclassified `news_search_service.py` from DEAD to KEPT. Updated totals
(DEAD: 13→12).

---

## Limitations

1. **No Docker builds available** — Docker builder is hung (trivial Alpine
   image times out at 180s). All verification is static analysis + host-side
   tests only.
2. **Cannot verify Cloud Run production deployment** — `Dockerfile.cloudrun`
   copies all `*.py` files with no CMD. The actual CMD is specified externally
   at Cloud Run deploy time, which we cannot inspect from this repo.
3. **Cannot verify runtime behavior** — without a build, cannot confirm that
   containers would start correctly after deletion. The evidence is limited to:
   files are not in any CMD/ENTRYPOINT/command, files have zero importers,
   and tests pass unchanged.
4. **Dynamic dispatch** — if any code uses `getattr`, `importlib`, or string
   interpolation to reference these modules at runtime, that would not appear
   in grep. I checked for this pattern and found none, but cannot fully
   rule it out.
