##### READY FOR REVIEW

# LOCAL-117: Dead Code Removal

**Branch:** `kiro/local117-dead-code-removal`  
**Agent:** Mac Mini Kiro  
**Date:** 2026-08-01

---

## Summary

Removed **14 dead code items** (13 files deleted, 2 functions removed from live files)
across 4 commits. Each finding from `UNWIRED_AUDIT.md` was independently re-verified
before removal. One finding was retained (explained below).

**Total deletions:** 1,945 lines across 14 files (13 deleted + 2 modified).

---

## Per-Symbol Verification Table

| # | Symbol | File | Re-verified verdict | Action | Justification |
|---|--------|------|---------------------|--------|---------------|
| 1 | `content_validation.py` (whole file) | `content_validation.py` | **CONFIRMED DEAD** | Removed | Zero importers. Test references to "content_validation" are to a data file (`step_3_after_is_binary_content_validation.txt`), not this module. |
| 2 | `pdf_processor.py` (whole file) | `pdf_processor.py` | **CONFIRMED DEAD** | Removed | Zero importers. `extract_pdf_text()` and `should_attempt_pdf_processing()` have zero call sites. |
| 3 | `service_config.py` (whole file) | `service_config.py` | **CONFIRMED DEAD** | Removed | Zero importers. Every service uses inline config (os.getenv). |
| 4 | `custom_audio_service.py` (whole file) | `custom_audio_service.py` | **CONFIRMED DEAD** | Removed | No Dockerfile runs it. `init_database()` only called in its own `__main__`. `tour_editing_phase2.py` implements its own custom audio handling inline. |
| 5 | `news_search_service.py` (whole file) | `news_search_service.py` | **CONFIRMED DEAD** | Removed | Zero importers. Docker uses `simple_news_search_service.py` (confirmed in `Dockerfile.simple-news-search`). |
| 6 | `voice_control_service.py` (whole file) | `voice_control_service.py` | **CONFIRMED DEAD** | Removed | Zero importers. Docker uses `voice_control/app.py`. |
| 7 | `coordinates_fromai_service.py` (whole file) | `coordinates_fromai_service.py` | **CONFIRMED DEAD** | Removed | Zero importers. Docker uses `coordinates_fromAI/app.py`. |
| 8 | `store_audio_tours.py` (whole file) | `store_audio_tours.py` | **CONFIRMED DEAD** | Removed | Zero importers. `store_audio_tour()` is defined inline at `tour_orchestrator_service.py:333`. `README_COORDINATES_DB.md` references it as documentation but that's not a code dependency. |
| 9 | `tour_delivery_service.py` (whole file) | `tour_delivery_service.py` | **CONFIRMED DEAD** | Removed | Zero importers. Functionality moved to `map_delivery/app.py`. |
| 10 | `register_routes()` + file | `user-tracking/routes.py` | **CONFIRMED DEAD** | Removed | Only importer is `app_with_routes.py` which is also dead. Docker CMD is `python app.py`. Removed both together to avoid broken import. |
| 11 | `app_with_routes.py` | `user-tracking/app_with_routes.py` | **CONFIRMED DEAD** | Removed | Not Docker entry point. Only file that imports `routes.py`. Zero references outside `user-tracking/`. |
| 12 | `init_db()` + file | `user-tracking/app_fixed_final.py` | **CONFIRMED DEAD** | Removed | `init_db()` only in `__main__`. Not Docker entry point. Zero references outside `user-tracking/`. |
| 13 | `setup_logging()` + file | `enhanced_logging.py` | **CONFIRMED DEAD** | Removed | Zero importers across entire codebase (grep + AST). |
| 14 | `validate_poi_knowledge()` | `generate_tour_text.py:576` | **CONFIRMED DEAD** | Removed | Zero call sites. Superseded by spine-based generation. Adjacent `verify_poi_matches_type()` (which IS called at line 2819) left intact. |
| 15 | `call_coordinates_service()` | `tour_orchestrator_service.py:1185` | **CONFIRMED DEAD** | Removed | Zero call sites. Stale predecessor to `get_coordinates_direct()` which is the live code path. |
| 16 | Silent `except ImportError: pass` | `content_qa_runner.py:768` | **NOT DEAD CODE** | **Kept** | See "What was NOT removed" below. |

---

## What Was NOT Removed (and Why)

### `content_qa_runner.py:768` — silent `except ImportError: pass` block

The audit classified this as "DEAD (QA path only)". On re-verification:

- `content_qa_runner.py` is a **live module** actively imported by `generate_tour_text_service.py:245` and used in production QA gating.
- The block at line 768 is an informational print of practical facts claims — it's a **code quality issue** (silent exception swallowing), not dead code.
- Removing the `try/except` block would either: (a) eliminate informational output that works when the module IS available, or (b) require converting it to a logged error, which is a feature change, not dead code removal.
- **Verdict:** This is an UNWIRED-style fix (add logging), not a removal target. Left in place.

---

## Commits

| # | Hash | Description | Files | Lines removed |
|---|------|-------------|-------|---------------|
| 1 | `6b6a02b` | Remove 9 dead standalone service files | 9 deleted | 1,308 |
| 2 | `baac74b` | Remove 3 dead user-tracking files | 3 deleted | 425 |
| 3 | `4588380` | Remove enhanced_logging.py | 1 deleted | 106 |
| 4 | `9f3d254` | Remove 2 dead functions from live files | 2 modified | 106 |
| **Total** | | | **15 changes** | **1,945** |

---

## Test Results

### Before (baseline)
```
RESULTS: 56 passed, 4 failed (of 60 total)

FAILURES:
  ✗ tests/test_local113_persona_wiring_guard.py
  ✗ tests/test_spine_quality_baseline.py
  ✗ tests/test_spine_quality_e2e.py
  ✗ tests/test_spine_quality_noise_floor.py
```

### After (all commits applied)
```
RESULTS: 56 passed, 4 failed (of 60 total)

FAILURES:
  ✗ tests/test_local113_persona_wiring_guard.py
  ✗ tests/test_spine_quality_baseline.py
  ✗ tests/test_spine_quality_e2e.py
  ✗ tests/test_spine_quality_noise_floor.py
```

**Identical.** All 4 failures are pre-existing (persona wiring guard tests a not-yet-wired feature; spine quality tests have known issues unrelated to this change).

### AST Parse Verification (every touched live file)
```
generate_tour_text.py: CLEAN
tour_orchestrator_service.py: CLEAN
```

### Database Row Count
```
audio_tours: 88 (unchanged)
```

---

## Verbatim Evidence

### Evidence: All 9 standalone files have zero importers

```
$ grep -rn "content_validation" --include="*.py" | grep -v content_validation.py | grep -v "__pycache__"
./tests/test_binary_contamination_source.py:93:   with open('step_3_after_is_binary_content_validation.txt'...
./tests/test_step3_binary_detection.py:82:   with open('step_3_after_is_binary_content_validation.txt'...
```
(References a DATA FILE, not the module)

```
$ grep -rn "pdf_processor\|extract_pdf_text\|should_attempt_pdf" --include="*.py" | grep -v pdf_processor.py
(empty)

$ grep -rn "service_config\|from service_config\|import service_config" --include="*.py" | grep -v service_config.py
(empty)

$ grep -rn "news_search_service\|NewsSearchService" --include="*.py" | grep -v news_search_service.py
(empty)

$ grep -rn "voice_control_service" --include="*.py" | grep -v voice_control_service.py
(empty)

$ grep -rn "coordinates_fromai_service" --include="*.py" | grep -v coordinates_fromai_service.py
(empty)

$ grep -rn "store_audio_tours\|from store_audio" --include="*.py" | grep -v store_audio_tours.py
(empty)

$ grep -rn "tour_delivery_service" --include="*.py" | grep -v tour_delivery_service.py
(empty)
```

### Evidence: Docker does NOT use the removed files

```
$ cat user-tracking/Dockerfile | grep CMD
CMD ["python", "app.py"]

$ grep -rn "custom_audio_service\|voice_control_service\|coordinates_fromai_service\|news_search_service\|store_audio_tours\|tour_delivery_service" Dockerfile* docker-compose*.yml
./Dockerfile.simple-news-search:8:COPY simple_news_search_service.py .
./Dockerfile.simple-news-search:18:CMD ["python", "simple_news_search_service.py"]
```
(Only `simple_news_search_service.py` — NOT `news_search_service.py`)

### Evidence: Dead functions have zero callers

```
$ grep -rn "validate_poi_knowledge" --include="*.py"
./generate_tour_text.py:576:def validate_poi_knowledge(poi_list, intent, location, api_key):

$ grep -rn "call_coordinates_service" --include="*.py"
./tour_orchestrator_service.py:1185:def call_coordinates_service(location):
```
(Each shows only its own definition — zero call sites)

### Evidence: No dynamic dispatch references

```
$ grep -rn "getattr.*routes\|getattr.*custom_audio\|getattr.*enhanced_log\|getattr.*content_valid\|getattr.*pdf_proc\|getattr.*service_config\|getattr.*news_search\|getattr.*voice_control_service\|getattr.*coordinates_fromai\|getattr.*store_audio\|getattr.*tour_delivery\|getattr.*validate_poi\|getattr.*call_coordinates" --include="*.py"
(empty)
```

---

## Limitations

1. **No Docker build available** — Docker builder is hung (180s timeout on trivial Alpine images). Cannot verify that container images build correctly after removal. The removed files were confirmed NOT referenced in any Dockerfile CMD or docker-compose command, so build should not be affected.

2. **Cannot verify runtime behavior** — Without a fresh container build, cannot confirm services start correctly after file removal. Confidence is high since removed files are never imported or referenced by any running code.

3. **Flutter app not audited for broken expectations** — The Dart mobile app (`audio_tour_app/lib/services/`) has its own `custom_audio_service.dart` and `voice_control_service.dart` that call HTTP endpoints. These call the LIVE services (running from different entry points), not the removed Python files. But if the mobile app expected any endpoint that ONLY the removed files provided, those calls would 404. Verified: the removed files' routes overlap with routes already provided by the live entry points.

4. **Production (GCloud/main branch) not examined** — This audit covers the local Docker stack only. If production wires things differently, removals here don't affect it (different branch).

5. **`getattr`/string-based dispatch** — Searched for dynamic dispatch patterns referencing any removed symbol. None found. Cannot rule out undiscovered plugin systems.

6. **`content_qa_runner.py:768`** — Audit item #16 (silent ImportError) was reclassified as a code quality issue rather than dead code. Removing the `try/except` block would break the informational output path when `practical_facts_gate` IS available.
