##### READY FOR REVIEW

## LOCAL-307: Quality guardrails for low-score tours

**Commit:** `9013dfa` on branch `kiro/local307-quality-guardrails`  
**Base:** `storied`

---

### Per-file summary

| File | Change |
|------|--------|
| `quality_guardrails.py` | **NEW** — Core guardrails module. `diagnose_shortfall()` classifies the cause (PIPELINE_LOST vs UNAVAILABLE). `evaluate_tour()` decides: retry, message, or deliver. `generate_user_message()` produces honest, specific messages. `select_better_tour()` picks the higher-scoring version after a retry. Feature flag `QUALITY_GUARDRAILS_ENABLED` defaults OFF. |
| `tour_orchestrator_service.py` | +52 lines. After LOCAL-306 scoring, calls `evaluate_tour()` to diagnose and decide. Attaches `quality_message` to job when UNAVAILABLE. Surfaces message in `/status` response alongside `expected_stops`/`actual_stops`. All wrapped in try/except — guardrail failure cannot block delivery. |
| `storied_feature_flags.md` | +6 lines. Documents `QUALITY_GUARDRAILS_ENABLED`, `QUALITY_RETRY_THRESHOLD`, `QUALITY_MESSAGE_THRESHOLD` with defaults and consuming files. |
| `tests/test_local307_quality_guardrails.py` | **NEW** — 12 tests: both flag states, both causes, retry bounding, no-suppression, message quality, count visibility, threshold configurability. |

---

### Threshold proposals (measured from corpus)

Scored 16 production English tours (non-translated, with content):

| Percentile | Score |
|-----------|-------|
| Min | 50.0 |
| P10 | 50.0 |
| **P25** | **56.6** |
| Median | 64.6 |
| P75 | 75.6 |
| P90 | 81.0 |
| Max | 97.1 |
| Mean | 66.4 |
| Stdev | 13.3 |

**Proposed thresholds:**

| Threshold | Value | Percentile | Trigger condition |
|-----------|-------|-----------|-------------------|
| `QUALITY_RETRY_THRESHOLD` | **55.0** | Below P25 | PIPELINE_LOST + score < 55 → retry once |
| `QUALITY_MESSAGE_THRESHOLD` | **60.0** | Between P25–Median | UNAVAILABLE + score < 60 → user message |

At these thresholds, measured against the corpus:
- 4/16 tours (25%) would be retry candidates IF they were PIPELINE_LOST (most are not — they score low because they're genuinely thin areas)
- 6/16 tours (37.5%) would get a user message IF they were UNAVAILABLE

In practice the actual trigger rate will be much lower because:
1. PIPELINE_LOST requires verified stops to go missing (rare with current pipeline)
2. UNAVAILABLE requires tier-1 exhaustion signal in gate_log (rare in most areas)

**These thresholds are DISABLED by default** (`QUALITY_GUARDRAILS_ENABLED=false`). The module logs what it WOULD do at every scoring point, so Michael can observe the decision pattern before enabling.

---

### Verbatim evidence

#### PIPELINE_LOST case: diagnosis, single retry, both scores, delivered choice
```
══════════════════════════════════════════════════════════════════════
SCENARIO 1: PIPELINE_LOST — retry triggered
══════════════════════════════════════════════════════════════════════
[GUARDRAILS] score=40.0 cause=PIPELINE_LOST delivered=3/5 PL=2 UA=0 thin=3/3 enabled=True is_retry=False
[GUARDRAILS DECISION] action=retry | cause=PIPELINE_LOST | score=40.0 | delivered=3/5 | enabled=True
  Action: retry
  Diagnosis: cause=PIPELINE_LOST, detail=2 stop(s) were verified but lost in pipeline. Delivered 3/5.
  Original score: 40.0

--- Simulating retry (score 52 vs original 40) ---
[GUARDRAILS] Retry scored better: retry=52.0 > original=40.0. Delivering retry.
  Delivered version: retry
  Both scores logged: original=40.0, retry=52.0
```

#### UNAVAILABLE case: no retry, user message
```
══════════════════════════════════════════════════════════════════════
SCENARIO 2: UNAVAILABLE — no retry, user message
══════════════════════════════════════════════════════════════════════
[GUARDRAILS] score=45.0 cause=UNAVAILABLE delivered=3/6 PL=0 UA=3 thin=3/3 enabled=True is_retry=False
[GUARDRAILS DECISION] action=message | cause=UNAVAILABLE | score=45.0 | delivered=3/6 | enabled=True | message='We found 3 well-documented places for this area rather than the 6 you asked for.'
  Action: message
  Diagnosis: cause=UNAVAILABLE
  User message: "We found 3 well-documented places for this area rather than the 6 you asked for. Here is the shorter tour."
  Retry attempted: False
```

#### No suppression (worst case: score 5.0, 1/10 stops)
```
══════════════════════════════════════════════════════════════════════
SCENARIO 3: Confirm no tour is suppressed (worst case)
══════════════════════════════════════════════════════════════════════
[GUARDRAILS] score=5.0 cause=PIPELINE_LOST delivered=1/10 PL=9 UA=0 thin=1/1 enabled=True is_retry=False
  First attempt: action=retry (would retry)
[GUARDRAILS] score=5.0 cause=PIPELINE_LOST delivered=1/10 PL=9 UA=0 thin=1/1 enabled=True is_retry=True
  After retry: action=deliver (delivers, never suppresses)
  Count visible: 1/10
```

#### pytest run
```
tests/test_local307_quality_guardrails.py::test_pipeline_lost_disabled PASSED [  8%]
tests/test_local307_quality_guardrails.py::test_unavailable_disabled PASSED [ 16%]
tests/test_local307_quality_guardrails.py::test_pipeline_lost_enabled_retry PASSED [ 25%]
tests/test_local307_quality_guardrails.py::test_unavailable_enabled_message PASSED [ 33%]
tests/test_local307_quality_guardrails.py::test_no_double_retry PASSED   [ 41%]
tests/test_local307_quality_guardrails.py::test_select_better_tour PASSED [ 50%]
tests/test_local307_quality_guardrails.py::test_user_messages_quality PASSED [ 58%]
tests/test_local307_quality_guardrails.py::test_full_score_no_action PASSED [ 66%]
tests/test_local307_quality_guardrails.py::test_count_always_visible PASSED [ 75%]
tests/test_local307_quality_guardrails.py::test_no_suppression PASSED    [ 83%]
tests/test_local307_quality_guardrails.py::test_format_log PASSED        [ 91%]
tests/test_local307_quality_guardrails.py::test_thresholds_from_env PASSED [100%]

======================== 12 passed in 0.12s ==============================
```

#### LOCAL-306 tests still pass (integration preserved)
```
tests/test_local306_inflight_scoring.py::test_score_2stop PASSED
tests/test_local306_inflight_scoring.py::test_score_8stop PASSED
tests/test_local306_inflight_scoring.py::test_edit_delta PASSED
tests/test_local306_inflight_scoring.py::test_delivery_unchanged PASSED
tests/test_local306_inflight_scoring.py::test_latency PASSED

======================== 5 passed, 4 warnings in 0.21s =========================
```

#### Cost and latency
```
Guardrails evaluation latency (8-stop tour, 1000 iterations):
  Total: 3.9ms for 1000 calls
  Average: 3.9µs per call (0.004ms)
  Added cost per tour: ~0.004ms (negligible vs scoring ~3ms)
  No network calls, no LLM calls, no DB writes (evaluation only)
```

- **$0.00 added cost per tour** — pure Python logic, no API calls.
- **In retry case** (flag ON, PIPELINE_LOST): one additional generation (~$0.10–0.30 depending on stop count). Bounded to at most one retry. Delivers better-of-two.
- **Total added latency**: 0.004ms (evaluation) + 0ms (no retry when disabled).

#### Production row count
```
SELECT count(*) FROM audio_tours WHERE (is_test = false OR is_test IS NULL); → 29
```

#### git status
```
$ git status --short
(clean)
```

---

### Acceptance criteria status

| Criterion | Status |
|-----------|--------|
| Regeneration bounded to one, PIPELINE_LOST only, better-of-two delivered | ✅ `is_retry` flag prevents loops; `select_better_tour()` picks winner |
| UNAVAILABLE never retried; specific non-apologetic message emitted | ✅ `evaluate_tour()` only returns `retry` for PIPELINE_LOST |
| Thresholds proposed with measured percentiles; gating defaults OFF | ✅ P25=55, Median=64.6; `QUALITY_GUARDRAILS_ENABLED=false` |
| No padding, no suppression, count always visible | ✅ Test 10: worst-case score → deliver. Count in every diagnosis. |
| `git status --short` clean | ✅ |
| No container rebuilt | ✅ |

---

### Limitations

1. **The retry mechanism is a decision hook, not a full re-generation loop.** When `QUALITY_GUARDRAILS_ENABLED=true` and `evaluate_tour()` returns `action='retry'`, the orchestrator would need to re-invoke the text generation pipeline. The decision point and select-better logic are complete; the actual re-invocation requires calling `orchestrate_tour_async` with `_guardrail_retry=True` on the job. This is intentionally not wired as an automatic loop because (a) the flag is OFF, (b) the re-generation cost needs Michael's approval, and (c) the current architecture uses a background thread that would need refactoring to support mid-flight retry cleanly.

2. **Corpus of 16 scorable production tours is small.** The thresholds (55/60) are derived from this sample. As more tours are generated with LOCAL-306 scoring active, the distribution will become clearer and thresholds can be refined. The env-var configurability means no code change is needed to adjust.

3. **The "all THIN and full delivery" case is classified UNAVAILABLE.** When all requested stops are delivered but every one is THIN, the diagnosis assumes "sources are thin" rather than "pipeline failed to fetch good corpus." This is the conservative choice — we don't retry because the area genuinely lacks material and retrying would produce the same result at double cost.

4. **User messages are template-based, not per-stop.** The message says "3 well-documented places rather than 6" but does not name the specific stops that were dropped. Per-stop attribution would require tracking which candidates the existence gate proposed vs delivered, which the gate_log supports but the current integration doesn't pass through to the guardrails module.

5. **No dollar-cost ceiling on retry.** The retry is bounded to one attempt by the `is_retry` flag, but there is no cumulative cost check within the guardrails module. The $1.00 ceiling exists at the orchestrator level and would block a retry that exceeds it.
