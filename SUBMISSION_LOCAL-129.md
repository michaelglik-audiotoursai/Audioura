##### READY FOR REVIEW

# LOCAL-129: Guard Test Audit — Which guards actually fail when broken?

**Branch:** `kiro/local129-guard-test-audit`  
**Agent:** Mac Mini Kiro  
**Date:** 2026-08-02  

---

## Summary

Audited all 4 guard tests in `tests/` whose docstrings claim they protect a
registration, wiring, or control. Method: comment out the guarded code, run
the test, check exit code, restore.

**Result: 2 work, 2 are broken (already permanently red before any break).**

---

## Audit Table

| # | Guard Test | Claims to protect | Failed when broken? | Reason if not |
|---|---|---|---|---|
| 1 | `test_local110_sharing_wiring_guard.py` | sharing_bp registration in generate_tour_text_service.py | ✅ YES | Exits 0 baseline → exits 1 when `register_blueprint(sharing_bp)` commented out. AST parse detects commented-out code. |
| 2 | `test_local113_persona_wiring_guard.py` | persona_bp registration in generate_tour_text_service.py | ❌ NO (permanently red) | Already exits 1 in baseline because live HTTP part targets port 5000 (unrebuilt container returns 404). Cannot distinguish "source correct but container stale" from "source broken." |
| 3 | `test_local114_referral_wiring_guard.py` | referral_bp registration in generate_tour_text_service.py | ✅ YES | Exits 0 baseline → exits 1 when `register_blueprint(referral_bp)` commented out. AST parse catches it. Port 5100 SKIPs gracefully. |
| 4 | `test_local115_referral_abuse_controls_guard.py` | Self-referral prevention, duplicate redemption guard, rate limiting | ❌ NO (permanently red + substring bypass) | Already exits 1 in baseline due to stale `audio_tours` row count check (expects 88, finds 94). Also: rate limiter check uses substring `"_check_rate_limit" in source` which passes even when call sites are replaced with `if False:` — function definition satisfies the check. |

---

## Counts

- **Guards audited:** 4
- **Guards that work:** 2 (LOCAL-110, LOCAL-114)
- **Guards that do not work:** 2 (LOCAL-113, LOCAL-115)

---

## Detailed Break/Restore Evidence

### LOCAL-110 (sharing_bp) — ✅ WORKS

**Break command:**
```bash
sed -i '' 's/^from sharing_endpoints import sharing_bp$/# from sharing_endpoints import sharing_bp/' generate_tour_text_service.py
sed -i '' 's/^app.register_blueprint(sharing_bp)$/# app.register_blueprint(sharing_bp)/' generate_tour_text_service.py
```

**Result when broken:**
```
  PASS: Import statement present
  PASS: register_blueprint(sharing_bp) call present
  FAIL: AST confirms register_blueprint(sharing_bp) is live code — Call exists in text but not in AST — possibly commented out or in a string
  ...
Results: 7 PASS, 1 FAIL
exit=1
```

**Baseline (unbroken):** exit=0

**Restore:** `git checkout -- generate_tour_text_service.py`

---

### LOCAL-113 (persona_bp) — ❌ PERMANENTLY RED

**Baseline (UNBROKEN source, no changes):**
```
  FAIL: POST /user/persona is not 404 — Got 404 — blueprint not registered!
  FAIL: POST /user/persona returns 200 — Got 404
  FAIL: GET /user/persona is not 404 — Got 404 — blueprint not registered!
  FAIL: GET /user/persona returns 200 — Got 404
Results: 8 PASS, 4 FAIL
exit=1
```

**Why it's broken:** The live HTTP test targets `http://localhost:5000` (the running
`audioura-tour-generator-1` container). That container was never rebuilt with
persona_bp — per constraint, containers aren't touched. So it returns 404 for
persona routes regardless of whether the source file is correct.

**The AST guard part (Part 1) does detect removal** — but since the test is
already exit=1, it cannot signal the new breakage. A permanently red test
occupies the slot without providing information.

**Root cause:** LOCAL-110 and LOCAL-114 target port 5100 (subscribed-generator)
and SKIP gracefully when unreachable. LOCAL-113 targets port 5000 (live container)
and FAILS when the container doesn't have the blueprint — even though the source
code is correct.

---

### LOCAL-114 (referral_bp) — ✅ WORKS

**Break command:**
```bash
sed -i '' 's/^from referral_endpoints import referral_bp$/# from referral_endpoints import referral_bp/' generate_tour_text_service.py
sed -i '' 's/^app.register_blueprint(referral_bp)$/# app.register_blueprint(referral_bp)/' generate_tour_text_service.py
```

**Result when broken:**
```
  PASS: Service file exists
  PASS: import referral_bp present in source
  PASS: register_blueprint(referral_bp) call present
  FAIL: AST confirms register_blueprint(referral_bp) is live code — Call exists in text but not in AST — possibly commented out or in a string
  ...
Results: 8 PASS, 1 FAIL, 6 findings (informational)
exit=1
```

**Baseline (unbroken):** exit=0

**Restore:** `git checkout -- generate_tour_text_service.py`

---

### LOCAL-115 (referral abuse controls) — ❌ PERMANENTLY RED + BYPASS

**Baseline (UNBROKEN, no changes):**
```
  FAIL: audio_tours row count unchanged (88) — Got 94 (expected 88)
Results: 11 PASS, 1 FAIL
exit=1
```

**Problem 1 — Permanently red:** The row count check expects 88 but `audio_tours`
now has 94 rows (grew since the test was written). The test has been exit=1 since
at least 6 tours were added. It cannot signal new breakage because it's already
broken.

**Problem 2 — Rate limiter bypass:**
```bash
sed -i '' 's/if not _check_rate_limit(rate_key):/if False:  # rate limit disabled/' referral_endpoints.py
```
Result: Still passes the rate limiter check because the test does:
```python
has_rate_limit = "_check_rate_limit" in ep_source
```
The function *definition* (`def _check_rate_limit(...)`) still contains the
substring. Disabling the actual *calls* is not detected.

**What IS detected (for completeness):**
- Removing `new_user_id == referrer_user_id` from source → FAIL (self-referral check)
- Removing `UniqueViolation` from referral_engine.py → FAIL
- Removing ALL references to `_check_rate_limit` → FAIL (but this means deleting the function itself, not just disabling it)

**Restore:** `git checkout -- referral_endpoints.py` / `git checkout -- referral_engine.py`

---

## Inventory Method

Searched `tests/` and repo root for files whose docstring or name claims they
protect a registration, wiring, or constraint:

```bash
grep -rn "guard" tests/ --include="*.py" | head -20
grep -rn "protect\|wiring\|registration" tests/ --include="*.py" | head -20
```

Files identified as guard tests (by name + docstring claim):
1. `test_local110_sharing_wiring_guard.py` — "Guard test for sharing blueprint registration"
2. `test_local113_persona_wiring_guard.py` — "Guard test for persona blueprint registration"
3. `test_local114_referral_wiring_guard.py` — "Guard test for referral blueprint registration"
4. `test_local115_referral_abuse_controls_guard.py` — "Guard test for referral abuse controls"

Files examined and excluded (not guards — they test behavior/evidence):
- `test_local48_substance_rebase.py` — mentions "fabrication guards" but tests function correctness
- `test_local119_prolog_resilience.py` — tests retry logic via mocks
- `test_local127_icon_aggregate.py` — evidence test proving no key exists
- `test_local101_swipe_prefs.py` — evidence test for acceptance criteria

---

## Constraint Verification

```
audio_tours: 94 (unchanged)
stop_metrics: 1002 (unchanged)
git status --short: (empty — clean tree)
```

---

## Limitations

1. **LOCAL-128 referenced in task brief does not exist in this worktree.** No file
   matching `*LOCAL*128*` found. The LEAD's mention appears to reference a task in
   a different worktree or one not yet submitted. Cannot audit what doesn't exist.

2. **LOCAL-126 healthcheck has no guard test file.** The LEAD verified it by hand.
   The compose change itself is the guard (revert to `curl` → healthchecks fail).
   No Python test guards this.

3. **Live HTTP guard parts could not be tested both ways** for LOCAL-110 and
   LOCAL-114 because port 5100 (subscribed-generator) is not running. The AST
   guards were tested — they are the parts that fire host-side.

4. **Did not fix any guards.** Per task scope, broken guards are reported only.
