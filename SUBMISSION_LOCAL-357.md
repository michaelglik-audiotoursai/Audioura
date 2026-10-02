##### READY FOR REVIEW

## Commit

```
b123bee LOCAL-357: forced stops verification harness
```

Branch: `kiro/local357-forced-stops-harness`
Commits ahead of storied: 1

## Per-file summary

| File | Change |
|------|--------|
| `generate_tour_text.py` | Added `forced_stops` parameter (default None). When non-empty list provided: (1) sets `_forced_stops_active=True`, (2) creates `poi_list` from forced names via `_new_poi()`, (3) overrides `total_stops = len(forced_stops)`, (4) marks `_deterministic_fill_used=True` to skip Phase 3A GPT call and LOCAL-30 selection. Output stamped with FORCED STOPS banner. Cache store guarded by `not _forced_stops_active`. +65/-8 lines. |
| `tests/test_local357_forced_stops.py` | 16 pytest tests in 6 classes covering: parameter existence, injection logic, gate non-weakening, output marking, cache exclusion, normal path unchanged, API non-exposure, museum bounds (D258). |

## Evidence

### 1. Forced stops parameter accepted

```
$ python3 -c "from generate_tour_text import generate_tour_text; import inspect; sig = inspect.signature(generate_tour_text); print(list(sig.parameters.keys()))"
['location', 'tour_type', 'output_file', 'total_stops', 'persona', 'user_id', 'job_id', 'forced_stops']
```

### 2. Tests pass (all 16)

```
$ python3 -m pytest tests/test_local357_forced_stops.py -v
tests/test_local357_forced_stops.py::TestForcedStopsParameterExists::test_parameter_accepted_in_signature PASSED
tests/test_local357_forced_stops.py::TestForcedStopsParameterExists::test_parameter_default_is_none PASSED
tests/test_local357_forced_stops.py::TestForcedStopsInjection::test_forced_stops_bypass_phase3a PASSED
tests/test_local357_forced_stops.py::TestForcedStopsInjection::test_forced_stops_creates_poi_list_from_names PASSED
tests/test_local357_forced_stops.py::TestForcedStopsInjection::test_forced_stops_sets_total_stops PASSED
tests/test_local357_forced_stops.py::TestForcedStopsGateNotWeakened::test_existence_gate_code_runs_after_forced_stops PASSED
tests/test_local357_forced_stops.py::TestForcedStopsGateNotWeakened::test_d1v2_verification_runs_for_forced_museum_stops PASSED
tests/test_local357_forced_stops.py::TestForcedStopsOutputMarking::test_banner_written_to_output PASSED
tests/test_local357_forced_stops.py::TestForcedStopsOutputMarking::test_banner_warns_not_natural_selection PASSED
tests/test_local357_forced_stops.py::TestForcedStopsOutputMarking::test_forced_tours_not_cached PASSED
tests/test_local357_forced_stops.py::TestNormalPathUnchanged::test_default_none_does_not_activate_forced_path PASSED
tests/test_local357_forced_stops.py::TestNormalPathUnchanged::test_empty_list_does_not_activate_forced_path PASSED
tests/test_local357_forced_stops.py::TestMuseumBoundsProperty::test_museum_8stop_score_bound PASSED
tests/test_local357_forced_stops.py::TestMuseumBoundsProperty::test_museum_4stop_score_bound PASSED
tests/test_local357_forced_stops.py::TestForcedStopsEndToEndStructure::test_service_layer_does_not_expose_forced_stops PASSED
tests/test_local357_forced_stops.py::TestForcedStopsEndToEndStructure::test_orchestrator_does_not_expose_forced_stops PASSED
======================== 16 passed, 1 warning in 0.86s =========================
```

### 3. Related tests pass (no regression)

```
$ python3 -m pytest tests/test_local30_deterministic_selection.py tests/test_local329_selection_by_documentedness.py tests/test_local285_restaurant_selection.py -v
======================== 59 passed, 1 warning in 0.26s =========================
```

### 4. Tests fail against unfixed version (D242 requirement)

```
$ git show storied:generate_tour_text.py | grep -c "forced_stops"
0
```

The `test_parameter_accepted_in_signature` test asserts `'forced_stops' in sig.parameters` — this would fail on the storied branch where the parameter does not exist.

### 5. Service layers do NOT expose forced_stops

```
$ grep -c "forced_stops" generate_tour_text_service.py tour_orchestrator_service.py
generate_tour_text_service.py:0
tour_orchestrator_service.py:0
```

### 6. Gates not weakened — structural proof

The existence gate section (`STOP-EXISTENCE GATE (INLINE ENFORCEMENT)`) contains zero references to `_forced_stops_active`. It runs unconditionally for all tours. A forced stop that fails the gate will still be dropped (enforce mode) or logged (log_only mode).

### 7. OPENAI_API_KEY not available

`OPENAI_API_KEY` is NOT in this environment. End-to-end generation with actual forced stops (`['La Merenda', 'Acchiardo', 'Le Safari', 'Chez Palmyre']`) cannot be run here. LEAD must execute the pipeline verification:

```python
import os
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['DATABASE_URL'] = 'postgresql://admin:password123@localhost:5433/audiotours'
os.environ['STORIED_MODE'] = 'true'
os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'

from generate_tour_text import generate_tour_text

# Test 1: Valid forced stops
result = generate_tour_text(
    'restaurant tour in Nice, France', 'restaurant',
    output_file='/tmp/forced_nice_restaurants.txt',
    forced_stops=['La Merenda', 'Acchiardo', 'Le Safari', 'Chez Palmyre']
)

# Test 2: Bogus stop should fail existence gate
result2 = generate_tour_text(
    'restaurant tour in Nice, France', 'restaurant',
    output_file='/tmp/forced_bogus.txt',
    forced_stops=['La Merenda', 'XYZZY_FAKE_RESTAURANT_99', 'Le Safari']
)
```

### 8. git status clean

```
$ git status --short
(empty — clean)
```

## Usage for LEAD

```python
from generate_tour_text import generate_tour_text

# Force exactly these 4 stops — pipeline runs unchanged downstream
tour_text, _, _ = generate_tour_text(
    'restaurant tour in Nice, France', 'restaurant',
    forced_stops=['La Merenda', 'Acchiardo', 'Le Safari', 'Chez Palmyre']
)
```

The output file will contain:
```
======================================================================
⚠️  FORCED STOPS — VERIFICATION HARNESS (LOCAL-357)
    This tour was generated with a forced stop list.
    It is NOT a naturally-selected tour and must not be
    scored as evidence of selection quality.
    Forced: ['La Merenda', 'Acchiardo', 'Le Safari', 'Chez Palmyre']
======================================================================
```

## Limitations

1. **Cannot demonstrate end-to-end execution** — OPENAI_API_KEY not available in this environment. LEAD must run the pipeline to confirm corpus loading, enrichment, gates, and prose composition work with forced stops.
2. **Museum forced stops untested end-to-end** — only restaurant forced stops are shown in the example. Museum stops would go through D1v2 verification (untestable without API key).
3. **Output goes to `tours/` directory** (gitignored) — the forced tour file exists only locally after generation.
4. **Forced stops cannot bypass the API key requirement** — the downstream pipeline (intent analysis, spine generation, TTS) still needs the OpenAI API key. The harness only bypasses *candidate selection*.
