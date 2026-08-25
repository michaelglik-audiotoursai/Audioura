# SUBMISSION_LOCAL-465.md — Exhibition Not Found

**Branch:** LOCAL-465-exhibition-not-found
**Base:** storied (803c1b8)
**Agent:** Mac Mini Kiro
**Date:** 2026-08-24

## What was built

### 1. `exhibition_resolution.py` — Pure decision function

```python
def resolve_request(request, resolved_venue, coverage, candidates) -> Dict
```

Verdicts, in this order:
1. **NOT_FOUND (city mismatch)** — request names a city; resolved venue is in a different one.
   - Uses `text_fold.fold()` for accent-insensitive comparison.
   - "MFA Boston, MA" → extracts "Boston". Resolved entity "Museum of Fine Arts, Houston" → "Houston". Mismatch → reject.
2. **NOT_FOUND (zero coverage)** — `0 COVERED` with every candidate EMPTY or VENUE_ONLY.
3. **DID_YOU_MEAN** — zero coverage BUT a near-match title clears the similarity threshold (≥ 0.30 token-set Jaccard with fuzzy Levenshtein matching).
4. **FOUND** — otherwise (the gate is not triggered).

Near-match search:
- Accent-folds via `text_fold.fold()`
- Strips punctuation before tokenizing
- Fuzzy token matching: Levenshtein distance ≤ 1 for short tokens, ≤ 2 for longer
- Returns at most 3 suggestions, best first
- **If nothing clears the bar, returns NOT_FOUND with no suggestions** (a wrong suggestion is worse than none)

### 2. Typed exception: `ExhibitionNotFound`

Carries `verdict`, `reason`, `user_message`, `suggestions`.

### 3. Wired into `generate_tour_text.py`

Inserted after LOCAL-212 coverage selection (line ~7258), before Phase 5 descriptions.

On NOT_FOUND or DID_YOU_MEAN:
- Logs `[LOCAL-465] EXHIBITION NOT FOUND: <reason> | request=… | resolved=… | coverage=…`
- Sets `_LAST_CLEAN_FAIL_EVIDENCE` with `error_type='exhibition_not_found'`
- Returns `(None, None, (None, None))` — no tour generated, no file written

### 4. Service layer handling in `generate_tour_text_service.py`

Added `exhibition_not_found` case to the evidence handler. The `user_message` is surfaced verbatim to the app. Suggestions are included in the error payload.

### 5. `EXHIBITION_STRICT=0` restores pre-fix behaviour

One env var. Default ON (`EXHIBITION_STRICT=1`). Set `EXHIBITION_STRICT=0` to disable the gate entirely — all requests proceed as before.

## Design decisions

1. **Pure function, no network calls.** `exhibition_resolution.py` uses only data already computed by the pipeline (venue entity, coverage verdicts, canonical titles). No new latency.

2. **Gate placement.** After LOCAL-212 coverage selection, before the existence gate and Phase 5. This is the earliest point where all three signals are available and the latest point before cost is incurred on descriptions.

3. **City extraction from request.** Multi-strategy: regex for "in City" patterns, comma-segment parsing with state/country filtering, fallback to terminal capitalized words. Case-insensitive via `fold()`.

4. **City extraction from resolved entity.** Checks entity name for post-comma segments (e.g. "Museum of Fine Arts, Houston" → "Houston") and a URL domain map for known museums.

5. **Only fires for exhibition-scoped requests.** The gate checks `_exhibition_scope is not None` — plain museum tours without a specific exhibition requirement pass through untouched.

6. **Fail-open on error.** If the exhibition_resolution module can't be imported or raises an unexpected exception, the gate is skipped (non-fatal log).

## Test output

```
$ python3 -m pytest test_local465_exhibition_not_found.py -v

test_local465_exhibition_not_found.py::TestResolveRequest::test_city_mismatch_case_insensitive PASSED
test_local465_exhibition_not_found.py::TestResolveRequest::test_city_mismatch_rejects PASSED
test_local465_exhibition_not_found.py::TestResolveRequest::test_city_same_as_resolved_passes PASSED
test_local465_exhibition_not_found.py::TestResolveRequest::test_did_you_mean_bad_match_returns_not_found PASSED
test_local465_exhibition_not_found.py::TestResolveRequest::test_did_you_mean_with_near_match PASSED
test_local465_exhibition_not_found.py::TestResolveRequest::test_found_when_coverage_partial PASSED
test_local465_exhibition_not_found.py::TestResolveRequest::test_found_with_full_coverage PASSED
test_local465_exhibition_not_found.py::TestResolveRequest::test_no_city_in_request_passes PASSED
test_local465_exhibition_not_found.py::TestResolveRequest::test_ordinary_museum_tour_passes PASSED
test_local465_exhibition_not_found.py::TestResolveRequest::test_walking_tour_france_not_rejected PASSED
test_local465_exhibition_not_found.py::TestResolveRequest::test_zero_coverage_rejects PASSED
test_local465_exhibition_not_found.py::TestExhibitionStrictEnvVar::test_default_is_strict PASSED
test_local465_exhibition_not_found.py::TestExhibitionStrictEnvVar::test_strict_0_disables PASSED
test_local465_exhibition_not_found.py::TestExhibitionStrictEnvVar::test_strict_1_is_on PASSED
test_local465_exhibition_not_found.py::TestCityExtraction::test_boston_ma PASSED
test_local465_exhibition_not_found.py::TestCityExtraction::test_in_pattern PASSED
test_local465_exhibition_not_found.py::TestCityExtraction::test_nice_france PASSED
test_local465_exhibition_not_found.py::TestCityExtraction::test_no_city PASSED
test_local465_exhibition_not_found.py::TestExhibitionTermExtraction::test_bare_name PASSED
test_local465_exhibition_not_found.py::TestExhibitionTermExtraction::test_preserves_colon_format PASSED
test_local465_exhibition_not_found.py::TestExhibitionTermExtraction::test_strips_venue PASSED
test_local465_exhibition_not_found.py::TestNearMatchSearch::test_exact_match_scores_high PASSED
test_local465_exhibition_not_found.py::TestNearMatchSearch::test_find_near_matches_empty_for_garbage PASSED
test_local465_exhibition_not_found.py::TestNearMatchSearch::test_find_near_matches_returns_best PASSED
test_local465_exhibition_not_found.py::TestNearMatchSearch::test_unrelated_scores_low PASSED
test_local465_exhibition_not_found.py::TestExhibitionNotFoundExc::test_exception_carries_fields PASSED
test_local465_exhibition_not_found.py::TestExhibitionNotFoundExc::test_exception_is_catchable PASSED

============================== 27 passed in 0.09s ==============================
```

## Acceptance mapping

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | "blue green and silva in MFA Boston, MA" → NOT_FOUND, no tour | ✅ | `test_city_mismatch_rejects`, `test_zero_coverage_rejects` |
| 2 | "Picasso, Miro, Dali: Unbound at MFA, Boston, MA" → FOUND | ✅ | `test_found_with_full_coverage` |
| 3 | Misspelling of real exhibition → DID_YOU_MEAN | ✅ | `test_did_you_mean_with_near_match` |
| 4 | Unit tests for all four verdicts, offline with fixtures | ✅ | 27 tests, all pass |
| 5 | False-positive regression on ordinary input | ✅ | `test_ordinary_museum_tour_passes`, `test_walking_tour_france_not_rejected`, `test_no_city_in_request_passes` |

## Files changed

- **NEW:** `exhibition_resolution.py` — the decision function
- **NEW:** `test_local465_exhibition_not_found.py` — 27 unit tests
- **MODIFIED:** `generate_tour_text.py` — gate insertion + helper function
- **MODIFIED:** `generate_tour_text_service.py` — error surfacing
- **NEW:** `SUBMISSION_LOCAL-465.md` — this file
