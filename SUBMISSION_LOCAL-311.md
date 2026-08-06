##### READY FOR REVIEW

**Commit:** `3714196` on branch `kiro/local311-versioned-evaluator`
**Base:** `storied` (merge-base `357f69f`)

---

## Per-file summary

| File | Change |
|------|--------|
| `tour_evaluator.py` | **New.** Single entry point `evaluate(tour_text, n_requested, **context) -> Evaluation`. Algorithm identity with version + config hash. In-memory registry. Stale version detection. Historical version registration (LOCAL-306-v1 pre-registered). |
| `tour_scoring_service.py` | Removed imports of `parse_tour`, `analyze_stop`, `classify_stop`, `compute_score`, `detect_venue_identity`. Now uses `evaluate()` exclusively. `SCORER_VERSION` is now the algorithm_id. `compute_edit_delta` uses `evaluate()` for both tour versions. |
| `generate_tour_text_service.py` | Added LOCAL-311 scoring block: tours generated via the direct generate path are now scored before delivery (gates nothing). |
| `tests/test_local311_versioned_evaluator.py` | 10 tests covering: identical scores, stale detection, registry, no-internals-in-callers, algorithm identity on Evaluation, empty input, config hash sensitivity. |

---

## Evidence

### 1. Single entry point; internals private; no caller reaches past it

```
$ grep -n "from tour_rubric_scorer import" tour_scoring_service.py tour_orchestrator_service.py tour_editing_phase2.py generate_tour_text_service.py quality_guardrails.py
tour_scoring_service.py:34:from tour_rubric_scorer import TourScore, StopAnalysis
quality_guardrails.py:39:from tour_rubric_scorer import TourScore
```

Only data classes (`TourScore`, `StopAnalysis`) imported — no algorithm functions
(`parse_tour`, `analyze_stop`, `classify_stop`, `compute_score`, `detect_venue_identity`).

### 2. Algorithm identity includes threshold/weight identity, with a registry

```
ALGORITHM_ID: LOCAL-311-v1@41db0d2f

Registry:
  LOCAL-311-v1@41db0d2f -> registered_at=2026-08-06T16:55:53.148701+00:00
  LOCAL-306-v1@03bbb773 -> registered_at=2026-08-06T16:55:53.148828+00:00

Lookup LOCAL-306-v1:
  Found: LOCAL-306-v1@03bbb773
  Config: rich_min_facts=4, adequate_min_facts=3, rich_min_density=0.60, ...
```

The config hash (`41db0d2f`) is derived from all thresholds and weights. Changing
any single value changes the hash. The version + hash together form the
algorithm_id stored in every `tour_scores.scorer_version` row.

### 3. Stale-version detection demonstrated

```
$ python3 -c "..." (injects conflicting registration)
SUCCESS: Caught AlgorithmVersionError
  Message: Stale version detected! ALGORITHM_VERSION='LOCAL-311-v1' was previously
  registered with config_hash='FAKE1234', but current config produces
  hash='41db0d2f'. A threshold or weight changed without bumping the version.
  Bump ALGORITHM_VERSION in tour_evaluator.py.
```

### 4. All three paths record; coverage stated

| Path | File | Mechanism | Status |
|------|------|-----------|--------|
| Orchestrator | `tour_orchestrator_service.py:929` | `score_tour_text()` | Already existed (LOCAL-306) |
| Direct generate | `generate_tour_text_service.py:423` | `score_tour_text()` | **Added by LOCAL-311** |
| Edit | `tour_editing_phase2.py:1734` | `score_edited_tour()` | Already existed (LOCAL-306) |

The orchestrator and edit paths were already covered by LOCAL-306. The direct
generate path was the gap — LOCAL-311 added it.

### 5. Scores provably unchanged

```
=== BEFORE (direct scorer internals) ===
  base=87.50, structural=0.00, correlation=0.00, venue_id=7.00
  TOTAL=94.50
  Stop 1: RICH, Stop 2: RICH, Stop 3: RICH, Stop 4: RICH, Stop 5: RICH
  Stop 6: ADEQUATE, Stop 7: THIN, Stop 8: ADEQUATE

=== AFTER (evaluate() entry point) ===
  base=87.50, structural=0.00, correlation=0.00, venue_id=7.00
  TOTAL=94.50
  Stop 1: RICH, Stop 2: RICH, Stop 3: RICH, Stop 4: RICH, Stop 5: RICH
  Stop 6: ADEQUATE, Stop 7: THIN, Stop 8: ADEQUATE
  algorithm_id=LOCAL-311-v1@41db0d2f

  ✓ All components match exactly
```

### 6. Latency and constraints

- Latency: min=4.2ms, max=8.6ms, avg=4.7ms (10 runs) — well under 200ms
- Production real count: 29 (unchanged)
- No container rebuilt
- `git status --short`: clean
- No LLM calls, no network in scorer path

### 7. Tests

```
tests/test_local311_versioned_evaluator.py  10 passed
tests/test_local306_inflight_scoring.py      5 passed
tests/test_local305_missing_stop_fairness.py 9 passed (regression)
tests/test_local291_groundedness.py         38 passed (regression)
```

---

## Limitations

1. **Registry is in-memory only.** The registry of algorithm versions lives in
   module-level state. A process restart loses registered historical versions
   (except LOCAL-306-v1 which is hardcoded). For production persistence, the
   registry should be backed by a DB table or a file. This is adequate for
   LOCAL-311's scope since every score row carries the algorithm_id string, and
   the config can be reconstructed from the source at that commit via `code_sha`.

2. **`groundedness_check.py` still imports `parse_tour` directly.** This module
   is not a scoring caller — it uses `parse_tour` as a text parser for its own
   groundedness measurement, not for scoring. Including it in the interface
   boundary would conflate parsing (a utility) with evaluation (the algorithm).
   Flagged but not changed.

3. **LOCAL-309 coordination.** LOCAL-309 is editing `compute_score`. If their
   changes alter thresholds or weights, the config hash will change and the stale
   version check will fire on their next import, requiring them to bump
   `ALGORITHM_VERSION`. This is by design — it's the "fail loudly" behaviour
   the task requested.

4. **Direct generate path scoring has no `tour_id` backfill.** When the generate
   service scores independently (not through orchestrator), the `tour_id` in the
   score row is NULL because the tour is not yet stored in `audio_tours`. The
   orchestrator path already handles backfill. If direct-generate tours need
   `tour_id` linkage, a similar backfill would be needed in whatever stores the
   tour downstream.
