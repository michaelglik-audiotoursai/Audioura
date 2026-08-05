##### READY FOR REVIEW

## Commit

- Hash: `3824590`
- Branch: `kiro/local230-distinguish-failure-from-absence`
- `git rev-list --count storied..HEAD`: 1

## Per-file summary

| File | Changes |
|------|---------|
| `venue_resolver.py` | Added `_network_failure_count`, `get_network_failure_count()`, `reset_network_failure_count()`. Fixed `_search_entities` (→ `None` on failure vs `[]`), `_get_coordinates` (→ `(None, None)` vs `(0.0, 0.0)`), `_geocode_city` (propagates `None`), `_get_instance_of` (logs ERROR, counts). Updated callers `_geo_disambiguate` and `_validate_city_match` to handle `None` identically to `(0.0, 0.0)`. |
| `generate_tour_text.py` | Coverage-selection DB: replaced bare `except: pass` with ERROR logging and `_cs_db_failure` flag. `else` branch distinguishes "FAILED" from "unavailable". Failure counted in `venue_resolver._network_failure_count`. Counter reset at generation start, reported at generation end. |
| `tests/test_local228_glue_falsification.py` | Updated 5 swallowed-exception tests to assert failure IS now distinguishable. All 5 now report `notices_breakage: True` / "✓ CONTRACT HOLDS". |

## Acceptance criteria evidence

### 1. All five sites distinguish failure from absence

```
_search_entities failure: None ≠ [] ✓
_get_instance_of failure: None (counted) ✓
_get_coordinates failure: (None, None) ≠ (0.0, 0.0) ✓
_geocode_city failure: (None, None) ≠ (0.0, 0.0) ✓
coverage-selection DB: _cs_db_failure=True, ERROR logged, counter incremented ✓
```

### 2. The (0.0, 0.0) sentinel gone from the failure path

`_get_coordinates` and `_geocode_city` now return `(None, None)` on failure.
The `(0.0, 0.0)` sentinel remains only for the legitimate "entity has no P625 claim" case.

### 3. Per-run failure counter surfaced in generation log

```
  [LOCAL-230] Network failures: 0 (all API calls succeeded)
  — or —
  [LOCAL-230] ⚠ NETWORK FAILURES: 4 API call(s) failed during this generation — tour may be degraded
```

### 4. LOCAL-228 falsification tests updated and passing

```
  test_swallowed_exception_venue_resolver_get_instance_of... ✓ CONTRACT HOLDS
  test_swallowed_exception_venue_resolver_get_coordinates... ✓ CONTRACT HOLDS
  test_swallowed_exception_venue_resolver_geocode_city... ✓ CONTRACT HOLDS
  test_swallowed_exception_venue_resolver_sparql... ✓ CONTRACT HOLDS
  test_swallowed_exception_coverage_selection_db... ✓ CONTRACT HOLDS
```

### 5. Healthy tour byte-identical

On healthy runs, return values are unchanged:
- `_search_entities`: returns `[]` (list, not `None`) → callers get same falsy value
- `_get_coordinates`: returns `(0.0, 0.0)` (floats, not `None`) → callers see same values
- `_geocode_city`: returns `(0.0, 0.0)` → same
- `_get_instance_of`: returns `None` → same

Callers check `if lat is None or (lat == 0.0 and lng == 0.0)` — on healthy runs
`lat` is never `None`, so only the `(lat == 0.0 and lng == 0.0)` branch activates,
which is identical to the old `if lat == 0.0 and lng == 0.0`. Tour text (`complete_tour`)
is constructed entirely independently of the counter — the only new output is
`print()` to stdout (not written to the tour file).

Verified by:
- `test_local186_venue_disambiguation.py` — PASS (full end-to-end tour generation)
- `test_local227_falsification.py` — all 16 instruments PASS
- `test_local119_prolog_resilience.py` — 25 tests OK
- Mocked healthy-path unit test: all return values match pre-LOCAL-230 exactly

### 6. Database unchanged

```
BASELINE: audio_tours = 138, Nice list = [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
POST-CHECK: audio_tours = 138, Nice list = [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
  ✓ Database unchanged.
```

### 7. git status clean

```
$ git status --short
(empty — clean worktree)
```

## Test output (verbatim)

```
======================================================================
LOCAL-228: GLUE FALSIFICATION REPORT
======================================================================

BASELINE: audio_tours = 138, Nice list = [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]

  test_key_contract_style_validator_findings_vs_violations... ✗ DOES NOT NOTICE
  test_key_contract_style_validator_rule_key... ✗ DOES NOT NOTICE
  test_key_contract_corpus_coverage_verdict... ✓ CONTRACT HOLDS
  test_key_contract_claim_check_verdict_counts... ✓ CONTRACT HOLDS
  test_key_contract_anchor_detector_classification... ✓ CONTRACT HOLDS
  test_swallowed_exception_venue_resolver_get_instance_of... ✓ CONTRACT HOLDS
  test_swallowed_exception_venue_resolver_get_coordinates... ✓ CONTRACT HOLDS
  test_swallowed_exception_venue_resolver_geocode_city... ✓ CONTRACT HOLDS
  test_swallowed_exception_venue_resolver_sparql... ✓ CONTRACT HOLDS
  test_swallowed_exception_coverage_selection_db... ✓ CONTRACT HOLDS
  test_unconsumed_outputs_survey... ✗ DOES NOT NOTICE
  test_unconsumed_contradicted_in_generation... ✓ CONTRACT HOLDS
  test_format_agreement_claim_check_to_external_verify... ✗ DOES NOT NOTICE
  test_format_agreement_style_findings_structure... ✓ CONTRACT HOLDS
  test_format_agreement_scorer_output_for_downstream... ✓ CONTRACT HOLDS

POST-CHECK: audio_tours = 138, Nice list = [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]
  ✓ Database unchanged.

======================================================================
SUMMARY
======================================================================
  Glue points where contract HOLDS:        11
  Glue points that DO NOT NOTICE breakage: 4
  Tests with errors:                       0
```

## Limitations

1. **`_get_instance_of` return value is still `None` for both failure and absence** — because both cases lead to the same caller behavior (skip the candidate). The distinction is via the ERROR log + per-run counter, not the return value. This is the correct tradeoff: forcing a different sentinel here would require callers to add a third code path with no behavioral difference.

2. **Coverage-selection DB failure counter is approximate** — if `_get_db_connection()` in venue_resolver fails internally (it has its own error handling from D91), the counter may not double-count. Only the direct psycopg2 connect failure in generate_tour_text.py increments.

3. **No container rebuild** — verified by only modifying Python source files. `docker-compose.yml` untouched.

4. **Cost: $0.00** — no LLM API calls made. All verification via unit tests and mocked responses.
