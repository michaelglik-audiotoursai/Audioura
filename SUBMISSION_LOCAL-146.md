##### READY FOR REVIEW

## LOCAL-146: Stop swallowing import and registration failures silently

**Commit:** `7996e1d`  
**Branch:** `kiro/local146-no-silent-swallow`  
**Base:** `storied`

---

## Per-file changes

| File | Lines changed | What |
|------|--------------|------|
| `generate_tour_text.py` | +4 / -2 | Split `except (ImportError, Exception): pass` into two handlers with ERROR logging |
| `generate_tour_text_service.py` | +17 / -7 | Added `import logging` + `_svc_logger`; replaced 4 silent `pass` sites and 1 bare `{}` with ERROR logging |
| `tour_orchestrator_service.py` | +5 / -1 | Added `import logging` + `_orch_logger`; replaced 1 bare `{}` with ERROR logging |

---

## Audit table — all silent-swallow sites found and fixed

| # | File:line | What was caught | Import succeeds today (tested) | What is now logged |
|---|-----------|----------------|-------------------------------|-------------------|
| 1 | `generate_tour_text.py:6454` | `except (ImportError, Exception): pass` around `directions_generator.generate_walking_directions` | ✅ YES | `[ERROR] [LOCAL-146] MISSING: directions_generator …` or `[LOCAL-146] directions_generator… FAILED: {type}: {msg}` |
| 2 | `generate_tour_text_service.py:178` | `except (ImportError, AttributeError): pass` around `generate_tour_text._LAST_CLEAN_FAIL_EVIDENCE` | ✅ YES | `[ERROR] [LOCAL-146] MISSING: generate_tour_text._LAST_CLEAN_FAIL_EVIDENCE …` |
| 3 | `generate_tour_text_service.py:286` | `except (ImportError, AttributeError): pass` around `generate_tour_text._LAST_VERIFICATION_TIER` | ✅ YES | `[ERROR] [LOCAL-146] MISSING: generate_tour_text._LAST_VERIFICATION_TIER …` |
| 4 | `generate_tour_text_service.py:394` | `except (ImportError, AttributeError): pass` around `generate_tour_text._LAST_POI_LIST` | ✅ YES | `[ERROR] [LOCAL-146] MISSING: generate_tour_text._LAST_POI_LIST …` |
| 5 | `generate_tour_text_service.py:449` | `except ImportError: _ceiling_stats = {}` around `cost_ceiling_monitor.get_ceiling_stats` | ✅ YES | `[ERROR] [LOCAL-146] MISSING: cost_ceiling_monitor …` |
| 6 | `tour_orchestrator_service.py:1241` | `except ImportError: _ceiling_stats = {}` around `cost_ceiling_monitor.get_ceiling_stats` | ✅ YES | `[ERROR] [LOCAL-146] MISSING: cost_ceiling_monitor …` |

**Import verification command:**
```
python3 -c "import directions_generator, generate_tour_text, cost_ceiling_monitor, practical_facts_gate, content_qa_runner; print('ALL OK')"
→ ALL OK
```

---

## Probes (3 of 6 sites probed with break-and-restore)

### Probe 1: `directions_generator` (generate_tour_text.py:6454)

```
REPLACEMENT COUNT (rename): 1
[ERROR] generate_tour_text.imports: [LOCAL-146] MISSING: directions_generator (generate_walking_directions) — walking directions DISABLED: No module named 'directions_generator'
PROBE SUCCESS: ERROR line emitted
RESTORED: directions_generator.py
POST-RESTORE: import OK (silent, no error logged)
```

### Probe 2: `_LAST_CLEAN_FAIL_EVIDENCE` (generate_tour_text_service.py:178)

```
REPLACEMENT COUNT (attr removal): 1
[ERROR] generate_tour_text_service: [LOCAL-146] MISSING: generate_tour_text._LAST_CLEAN_FAIL_EVIDENCE — degradation evidence unavailable: cannot import name '_LAST_CLEAN_FAIL_EVIDENCE' from 'generate_tour_text' (/Users/micha/audioura-worktrees/LOCAL-146/generate_tour_text.py)
PROBE SUCCESS: ERROR line emitted (ImportError)
RESTORED: _LAST_CLEAN_FAIL_EVIDENCE
POST-RESTORE: attribute accessible (type=dict, no error logged)
```

### Probe 3: `cost_ceiling_monitor` (tour_orchestrator_service.py:1241)

```
REPLACEMENT COUNT (rename): 1
[ERROR] tour_orchestrator_service: [LOCAL-146] MISSING: cost_ceiling_monitor (get_ceiling_stats) — ceiling stats unavailable in health endpoint: No module named 'cost_ceiling_monitor'
PROBE SUCCESS: ERROR line emitted
RESTORED: cost_ceiling_monitor.py
POST-RESTORE: import OK (type=function, no error logged)
```

---

## No behaviour change beyond logging

Every site preserves the identical control flow:
- Site 1: still falls through to use `directions` from the prior source (or generic transition)
- Sites 2–4: still proceed with `_error_extra = {}` / `_gen_tier = ''` / no verified-flag propagation
- Sites 5–6: still return `_ceiling_stats = {}` in health response

The only difference is that these failures are now visible at ERROR level instead of invisible.

---

## Test suites run

| Suite | Exit code | Result |
|-------|-----------|--------|
| `tests/test_local64_cost_ceiling.py` | 0 | 31 passed, 0 failed |
| `tests/test_local60_cost_metering.py` | 0 | 7 passed |
| `tests/test_orchestrator_pipeline.py` | 0 | Pipeline preserved |
| `test_g4_false_positives.py` | 0 | All pass (G4 + fail-closed) |

These suites were chosen because they exercise the imports and code paths around the modified sites. Full `tests/` run was not performed per D38 (writes to live database).

---

## Row counts (before and after — unchanged)

| Table | Count |
|-------|-------|
| `audio_tours` | 106 |
| `stop_metrics` | 1011 |

---

## `git status --short`

```
(empty — clean working tree)
```

---

## Recommendation (not acted on — visibility-only scope)

Site 1 (`directions_generator` at generate_tour_text.py:6454) catches `Exception` broadly — this means a runtime bug inside `generate_walking_directions()` (e.g. a `KeyError`, API timeout, division by zero) is logged but the tour is still delivered without directions. A case can be made that a *runtime* error in an already-imported module should propagate or at minimum mark the transition as degraded, rather than silently falling back to "Continue to X." This would be a behavior change and is out of scope for LOCAL-146.

---

## Limitations

- Only top-level service files were audited (`generate_tour_text.py`, `generate_tour_text_service.py`, `tour_orchestrator_service.py`). Other files (e.g. `content_qa_runner.py`, `subscription_article_processor.py`) have `except ImportError` blocks that already log or are in test/utility code — not audited for this task.
- Health endpoint sites (#5, #6) are instrumentation that fails open (per D14, this is correct). The log ensures visibility but the endpoint still returns healthy with empty stats. An operator may want to alert on these rather than ignore them.
- `stop_metrics` count (1011) differs from the task's stated expectation (1002). No rows were added or removed by this task — the 9-row difference pre-existed.
