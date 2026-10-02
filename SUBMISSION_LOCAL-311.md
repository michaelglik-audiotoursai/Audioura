##### READY FOR REVIEW

**Commit:** `19ccdc3`  
**Branch:** `kiro/local311-versioned-evaluator`  
**Commits since storied:** 3

---

## Per-file summary

| File | Change |
|------|--------|
| `tour_evaluator.py` | (1) Added cross-population of `callbacks_to` in `evaluate()` matching `score_tour_file`'s logic. (2) Changed threshold reads from frozen `from X import Y` bindings to live `_scorer.RICH_MIN_FACTS` via `import tour_rubric_scorer as _scorer`. (3) `_validate_version_consistency()` now rebuilds config fresh from live module values on every call. (4) `_compute_config_hash()` accepts zero arguments (uses current config). (5) New public `get_current_config_hash()` for external stale-version validation. |

---

## Verification evidence

### 1. Scores provably unchanged (both paths identical)

```
tours/LOCAL303_museum_8stop_gate.txt (N=8, no callbacks):
  score_tour_file: total=94.5  base=87.5  corr=+0.0
  evaluate():      total=94.5  base=87.5  corr=+0.0

tours/LOCAL262_asian_arts_8stop_restored.txt (N=8, has callbacks):
  score_tour_file: total=103.1  base=78.1  corr=+23.4
  evaluate():      total=103.1  base=78.1  corr=+23.4

tours/matisse_nice.txt (N=10, highest callback density):
  score_tour_file: total=82.5  corr=+27.5
  evaluate():      total=82.5  corr=+27.5

tours/Palais_Lascaris__Nice_museum_tour_20260727_174018.txt (N=8):
  score_tour_file: total=40.6  corr=+21.9
  evaluate():      total=40.6  corr=+21.9

All 46 tours in tours/: 0 mismatches (checked total_score to 0.01 tolerance).
```

### 2. Stale-version detection demonstrated

```
=== Before threshold change ===
ALGORITHM_ID: LOCAL-311-v1@41db0d2f
validate: OK

=== Simulating: RICH_MIN_FACTS changed from 4 to 5 ===
=== Calling _validate_version_consistency() ===
CAUGHT AlgorithmVersionError:
  Stale version detected! ALGORITHM_VERSION='LOCAL-311-v1' was registered with
  config_hash='41db0d2f', but current thresholds produce hash='404d85e4'.
  A threshold or weight changed without bumping the version.
  Bump ALGORITHM_VERSION in tour_evaluator.py.

=== Calling evaluate() with changed threshold ===
CAUGHT on evaluate(): AlgorithmVersionError
  (same message — evaluate() calls _validate on every invocation)

=== After restoring threshold ===
validate: OK
```

### 3. No caller touches internals (grep proof)

```
$ grep -rn "analyze_stop\|classify_stop\|compute_score\|score_tour_file" --include="*.py" \
    | grep -v tour_rubric_scorer.py | grep -v tour_evaluator.py | grep -v test_ | grep -v __pycache__
(no output — zero hits)
```

`parse_tour` is imported by `groundedness_check.py` and `run_local291_adjudication.py` for **parsing only** (not scoring). These never call `analyze_stop`/`classify_stop`/`compute_score`. Data types (`TourScore`, `StopAnalysis`) are imported by `tour_scoring_service.py` and `quality_guardrails.py` — acceptable, as types don't encode scoring logic.

### 4. Registry lookup — two versions

```
Registry has 2 entries:
  LOCAL-311-v1@41db0d2f (current)
    rich_min_facts: 4, adequate_min_facts: 3
  LOCAL-306-v1@03bbb773 (historical, pre-refactoring)
    rich_min_facts: 4, adequate_min_facts: 3
```

`lookup_algorithm("LOCAL-306-v1@03bbb773")` returns the full config snapshot including all thresholds and weights — interpretable without checking out the repo.

### 5. All three generation paths record scores

| Path | Location | Evidence |
|------|----------|----------|
| **Orchestrator** | `tour_orchestrator_service.py:932` | `score_tour_text(tour_content, n_requested=...)` |
| **Direct generate** | `generate_tour_text_service.py:430` | `score_tour_text(tour_content_str, n_requested=total_stops, ...)` |
| **Edit** | `tour_editing_phase2.py:1715` | `score_edited_tour(...)` with delta |

All three were already present (LOCAL-306 + first submission). No new hooks needed.

### 6. Performance

```
Average: 4.3ms per evaluation (sub-200ms requirement: PASS)
```

### 7. What the fix actually changed

**Before fix:** `evaluate()` skipped the cross-population loop. Only `callbacks_from` was populated; `callbacks_to` was always empty. `compute_score` saw half the callback set, producing a lower correlation bonus on any tour with cross-stop references (27 of 46 tours affected, differences ranging from 3.1 to 21.9 points).

**After fix:** `evaluate()` performs the identical loop that `score_tour_file` performs:
```python
for sa in stop_analyses:
    for ref_idx in sa.callbacks_from:
        for other_sa in stop_analyses:
            if other_sa.index == ref_idx:
                other_sa.callbacks_to.append(sa.index)
```

---

## Limitations

1. **Cross-population lives in `evaluate()`, not in `compute_score`.** The bounce suggested moving it into `compute_score` — but LOCAL-309 is actively editing `compute_score`, and placing it there would create a merge conflict. The architectural guarantee holds: `evaluate()` is the single entry point, so the loop cannot be forgotten by any caller.

2. **`parse_tour` is still importable by non-scoring modules.** `groundedness_check.py` uses it as a text parser (not for scoring). Making it fully private would require duplicating the parser or adding a `parse_only()` export. The scoring-relevant internals (`analyze_stop`, `classify_stop`, `compute_score`, `detect_venue_identity`) are fully encapsulated.

3. **Registry is in-memory only.** Historical versions are registered at import time via `register_historical_version()`. If the process restarts, only explicitly-registered versions are available. A persistent registry (DB or file) would survive restarts but is not required by the task scope.

4. **Stale-version detection requires the process to have imported `tour_evaluator` before the threshold changed.** It cannot detect a stale version if the module is imported fresh with already-changed thresholds and a matching (bumped) version string. The guard catches drift within a session and across edits where the version string was not updated.
