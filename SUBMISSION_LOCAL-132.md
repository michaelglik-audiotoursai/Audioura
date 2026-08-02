##### READY FOR REVIEW

# LOCAL-132: Guard Re-Audit — Every guard, both directions

**Branch:** `kiro/local132-guard-reaudit`  
**Agent:** Mac Mini Kiro  
**Date:** 2026-08-02  

---

## Summary

Re-audited all guard tests in the repo. Found 5 guards total (one more than
LOCAL-129's four). Each tested with comment-out AND the weakest plausible
evasion (`if False:` or equivalent neutering). Replacement counts printed
before every probe, per D36.

**Result: 2 WORKS (both directions), 3 WORKS (comment-out) but BLIND (`if False:`).**

---

## Guard Inventory

| # | Guard Test | Claims to protect | Baseline |
|---|---|---|---|
| 1 | `tests/test_local110_sharing_wiring_guard.py` | sharing_bp registration | exit=0 |
| 2 | `tests/test_local113_persona_wiring_guard.py` | persona_bp registration | exit=0 |
| 3 | `tests/test_local114_referral_wiring_guard.py` | referral_bp registration | exit=0 |
| 4 | `tests/test_local115_referral_abuse_controls_guard.py` | Self-referral, duplicate redemption, rate limiting | exit=0 |
| 5 | `tests/test_local128_stop_metrics_tourid.py` | stop_metrics.tour_id linkage via production function | exit=0 |

---

## Audit Results Table

| # | Guard | Comment-out | `if False:` evasion | Classification |
|---|---|---|---|---|
| 1 | LOCAL-110 (sharing_bp) | exit=1 ✓ | exit=0 ✗ | **BLIND (neutering)** |
| 2 | LOCAL-113 (persona_bp) | exit=1 ✓ | exit=0 ✗ | **BLIND (neutering)** |
| 3 | LOCAL-114 (referral_bp) | exit=1 ✓ | exit=0 ✗ | **BLIND (neutering)** |
| 4 | LOCAL-115 (abuse controls) | exit=1 ✓ | exit=1 ✓ | **WORKS** |
| 5 | LOCAL-128 (stop_metrics) | exit=1 ✓ | exit=1 ✓ | **WORKS** |

---

## Detailed Evidence — Per-Guard

### Guard 1: LOCAL-110 (sharing_bp) — BLIND (neutering)

**PROBE A: Comment out (detected)**

```bash
sed -i '' 's/^from sharing_endpoints import sharing_bp$/# from sharing_endpoints import sharing_bp/' generate_tour_text_service.py
sed -i '' 's/^app.register_blueprint(sharing_bp)$/# app.register_blueprint(sharing_bp)/' generate_tour_text_service.py
```

- Replacement count (import): **1**
- Replacement count (register): **1**
- Result: exit=1
- Failure: `FAIL: AST confirms register_blueprint(sharing_bp) is live code — Call exists in text but not in AST — possibly commented out or in a string`

**PROBE B: `if False:` neutering (NOT detected)**

```bash
sed -i '' 's/^app.register_blueprint(sharing_bp)$/if False: app.register_blueprint(sharing_bp)/' generate_tour_text_service.py
```

- Replacement count: **1**
- Result: exit=0
- All 8 assertions PASS including `AST confirms register_blueprint(sharing_bp) is live code`

**Root cause:** The AST walker finds `Call` nodes anywhere in the tree via `ast.walk`. `if False: app.register_blueprint(sharing_bp)` parses to a valid Call node inside an If body — the walker does not check whether the enclosing If has a constant-false test. The call is syntactically present but unreachable.

**Restore:** `git checkout -- generate_tour_text_service.py`

---

### Guard 2: LOCAL-113 (persona_bp) — BLIND (neutering)

**PROBE A: Comment out (detected)**

```bash
sed -i '' 's/^from persona_endpoints import persona_bp$/# from persona_endpoints import persona_bp/' generate_tour_text_service.py
sed -i '' 's/^app.register_blueprint(persona_bp)$/# app.register_blueprint(persona_bp)/' generate_tour_text_service.py
```

- Replacement count (import): **1**
- Replacement count (register): **1**
- Result: exit=1
- Failure: `FAIL: AST confirms register_blueprint(persona_bp) is live code — Call exists in text but not in AST — possibly commented out or in a string`

**PROBE B: `if False:` neutering (NOT detected)**

```bash
sed -i '' 's/^app.register_blueprint(persona_bp)$/if False: app.register_blueprint(persona_bp)/' generate_tour_text_service.py
```

- Replacement count: **1**
- Result: exit=0
- All 8 source assertions PASS (5 HTTP assertions SKIP as before, due to stale container)

**Root cause:** Same as Guard 1 — `ast.walk` does not check reachability. The HTTP assertions that would catch this are permanently SKIPped because the container image predates persona_bp. So the only defence is the AST check, and it is evadable.

**Restore:** `git checkout -- generate_tour_text_service.py`

---

### Guard 3: LOCAL-114 (referral_bp) — BLIND (neutering)

**PROBE A: Comment out (detected)**

```bash
sed -i '' 's/^from referral_endpoints import referral_bp$/# from referral_endpoints import referral_bp/' generate_tour_text_service.py
sed -i '' 's/^app.register_blueprint(referral_bp)$/# app.register_blueprint(referral_bp)/' generate_tour_text_service.py
```

- Replacement count (import): **1**
- Replacement count (register): **1**
- Result: exit=1
- Failure: `FAIL: AST confirms register_blueprint(referral_bp) is live code — Call exists in text but not in AST — possibly commented out or in a string`

**PROBE B: `if False:` neutering (NOT detected)**

```bash
sed -i '' 's/^app.register_blueprint(referral_bp)$/if False: app.register_blueprint(referral_bp)/' generate_tour_text_service.py
```

- Replacement count: **1**
- Result: exit=0
- All 9 assertions PASS including `AST confirms register_blueprint(referral_bp) is live code`

**Root cause:** Identical to Guards 1 and 2. Same `ast.walk` pattern, same blind spot. No live HTTP test for this guard either (port 5100 not running).

**Restore:** `git checkout -- generate_tour_text_service.py`

---

### Guard 4: LOCAL-115 (referral abuse controls) — WORKS

This guard uses **behavioural HTTP tests** (LOCAL-130 fix). It starts a real
Flask instance and fires actual requests. Source-level evasions cannot beat it.

**PROBE A: Self-referral — `if False:` evasion (detected)**

```bash
sed -i '' 's/    if new_user_id == referrer_user_id:/    if False:  # new_user_id == referrer_user_id/' referral_endpoints.py
```

- Replacement count: **1**
- Result: exit=1
- Failures:
  - `FAIL: Self-referral: equality check in AST — No live AST comparison of new_user_id == referrer_user_id found`
  - `FAIL: Self-referral returns 403 — Got 200`

**PROBE B: Rate limiter — `if False and` evasion (detected)**

```bash
sed -i '' 's/    if not _check_rate_limit(rate_key):/    if False and not _check_rate_limit(rate_key):/' referral_endpoints.py
```

- Replacement count: **2**
- Result: exit=1
- Failure: `FAIL: Rate limit fires within 8 requests (limit=5) — All requests returned 200 — rate limiting not active`

**PROBE C: Duplicate redemption — return value neutering (detected)**

```bash
sed -i '' 's/        return "duplicate"/        return "ok"/' referral_engine.py
```

- Replacement count: **1**
- Result: exit=1
- Failures:
  - `FAIL: Engine: catches UniqueViolation → 'duplicate'`
  - `FAIL: Duplicate redeem returns 409 (not 500) — Got 200`

**All three controls survive both comment-out and neutering-in-place.**

**Restore:** `git checkout -- referral_endpoints.py referral_engine.py`

---

### Guard 5: LOCAL-128 (stop_metrics.tour_id) — WORKS

This guard imports and **calls the production function**, then checks the
actual database state. Any neutering that prevents the UPDATE from executing
is caught.

**PROBE A: Replace UPDATE with no-op SQL (detected)**

```bash
sed -i '' 's|"UPDATE stop_metrics SET tour_id = %s WHERE job_id = %s AND tour_id IS NULL"|"SELECT 1 WHERE false"|' tour_orchestrator_service.py
```

- Replacement count: **1**
- Result: exit=1
- Failure: `FAIL: link_stop_metrics_to_tour updated 0 rows, expected 1. The UPDATE in the production function may be missing or broken.`

**PROBE B: Early `return 0` before the body (detected)**

```bash
# Inserted `return 0` as first line after docstring
```

- Replacement count: **1** (line 590: `return 0`)
- Result: exit=1
- Same failure: function returns 0, test asserts 1

**Restore:** `git checkout -- tour_orchestrator_service.py`

---

## Files Excluded from Guard Classification

The following test files were examined and are NOT guard tests (they test
behaviour/correctness, not wiring/registration/constraint presence):

- `test_local48_substance_rebase.py` — unit tests for outdoor retrieval + prompt content
- `test_local119_prolog_resilience.py` — retry logic via mocks
- `test_local127_icon_aggregate.py` — evidence of NULL tour_ids (finding, not guard)
- `test_local101_swipe_prefs.py` — acceptance criteria evidence
- `test_w7_wiring.py` — mocked pipeline integration (no break/detect cycle)
- `test_orchestrator_storied_wiring.py` — requires live containers (not a guard)
- `test_contained_regression.py` — regression test requiring live service
- `test_b6_generation_wiring.py` — unit tests for element selection
- `test_f4_cache_roundtrip.py` — mocked cache wiring
- `test_local64_cost_ceiling.py` — unit tests for ceiling logic
- `test_local88_tour_pollution.py` — acceptance test for tour pollution

---

## Counts

| Classification | Count | Guards |
|---|---|---|
| **WORKS** (fails on both comment-out AND neutering) | 2 | LOCAL-115, LOCAL-128 |
| **BLIND** (passes on `if False:` neutering) | 3 | LOCAL-110, LOCAL-113, LOCAL-114 |
| ALWAYS-RED | 0 | — |
| PROBE FAILED | 0 | — |
| **Total guards found** | **5** | — |

---

## The Pattern

All three BLIND guards share the same code pattern and the same vulnerability:

```python
for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        # walks ALL Call nodes in the tree
        # does NOT check if the node is reachable
```

`if False: app.register_blueprint(X)` passes because:
1. `if False:` is valid Python and parses fine
2. The `Call` node for `register_blueprint(X)` exists in the AST
3. The walker finds it and reports PASS
4. The code never executes at runtime

The two WORKS guards (LOCAL-115, LOCAL-128) are immune because they **exercise
the behaviour** — LOCAL-115 fires HTTP requests and checks status codes;
LOCAL-128 calls the function and checks the database state. Source-level evasions
cannot fake a 403 response or a database UPDATE.

This is exactly the pattern D35 documents: static checks cannot prove a control
is active.

---

## Row Counts

| Table | Before | After |
|-------|--------|-------|
| audio_tours | 94 | 94 |
| stop_metrics | 1002 | 1002 |

---

## git status --short

```
(clean — no output)
```

---

## Limitations

1. **No Docker builds.** The live HTTP portions of LOCAL-110 and LOCAL-114
   could not be tested (port 5100 not running, Docker builds hung). The
   HTTP assertions would catch `if False:` because the route would actually
   be unreachable — but those paths are SKIP in current state.

2. **LOCAL-113's HTTP assertions are permanently SKIPped.** The container at
   port 5000 predates persona_bp. If the container were rebuilt, the HTTP
   path would provide a second defence. In current state, the AST check is
   the only defence and it is evadable.

3. **No additional guard tests beyond the 5 found.** Searched `tests/` and
   the repo root for any file whose docstring or name claims to protect a
   registration, wiring, constraint, or control. The remaining test files
   are behaviour/correctness tests, not break-detect guards.

4. **Did not fix anything.** Per task scope, classification and evidence only.
