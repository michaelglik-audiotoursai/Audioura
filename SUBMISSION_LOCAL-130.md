##### READY FOR REVIEW

# LOCAL-130: Fix the referral abuse guard — permanently red and bypassable

**Branch:** `kiro/local130-fix-abuse-guard`  
**Agent:** Mac Mini Kiro  
**Date:** 2026-08-02  
**Commit:** `e17bd99`

---

## Changes

| File | Lines | What |
|------|-------|------|
| `tests/test_local115_referral_abuse_controls_guard.py` | +131 / −49 | Rewrote guard: AST checks + row-count invariant |

---

## Defects fixed

### 1. Hardcoded row count (audio_tours == 88)

The table has 94 rows. The test was permanently red regardless of whether
controls work. Replaced with before/after invariant:

```python
cur.execute("SELECT COUNT(*) FROM audio_tours")
audio_tours_before = cur.fetchone()[0]
# ... test runs ...
cur.execute("SELECT COUNT(*) FROM audio_tours")
audio_tours_after = cur.fetchone()[0]
check("audio_tours row count unchanged across test",
      audio_tours_after == audio_tours_before,
      f"audio_tours changed: {audio_tours_before} -> {audio_tours_after}")
```

### 2. Substring identifier check (`"_check_rate_limit" in source`)

Passed even when all call sites replaced with `if False:`. Now uses AST walk
to verify `_check_rate_limit()` is **called** inside `@route`-decorated
functions:

```python
for node in ast.walk(ep_tree):
    if isinstance(node, ast.FunctionDef) and node.decorator_list:
        is_route = any(isinstance(d, ast.Call) and ... d.func.attr == "route" ...)
        if is_route:
            for child in ast.walk(node):
                if (isinstance(child, ast.Call)
                        and isinstance(child.func, ast.Name)
                        and child.func.id == "_check_rate_limit"):
                    rate_limit_calls_in_routes += 1
```

---

## Evidence: Guard exits 0 (baseline)

```
PART 1: AST Guard — abuse controls present in referral_endpoints.py
  PASS: referral_endpoints.py exists
  PASS: referral_engine.py exists
  PASS: Self-referral guard: equality check in AST (new_user_id == referrer_user_id)
  PASS: Self-referral: returns 403 with 'self_referral' error
  PASS: Rate limiter: _check_rate_limit() called in route handlers (AST)
  PASS: Rate limiter: called in ≥2 route handlers (both create & redeem)
  PASS: Rate limiter: returns 429 with 'rate_limit_exceeded'
  PASS: Duplicate redemption: redeem_referral handles 'duplicate' → 409
  PASS: Engine: catches UniqueViolation and returns 'duplicate'
PART 2: Live HTTP Guard — abuse controls respond correctly
  SKIP: Cannot connect to http://localhost:5100
PART 3: Database Guard — UNIQUE constraint + row-count invariant
  PASS: UNIQUE constraint 'uq_referral_redemptions_code_user' exists
  PASS: Constraint covers (referral_code, new_user_id)
  INFO: audio_tours row count = 94
  INFO: stop_metrics row count = 1002
  PASS: audio_tours row count unchanged across test
  PASS: stop_metrics row count unchanged across test
Results: 13 PASS, 0 FAIL
ALL ASSERTIONS PASSED — referral abuse controls are working
EXIT CODE: 0
```

---

## Evidence: Break/restore cycles (3 controls)

### Cycle 1: Self-referral guard

**Break:** `sed 's/if new_user_id == referrer_user_id:/if False:/'`

```
  FAIL: Self-referral guard: equality check in AST (new_user_id == referrer_user_id)
        — No live AST comparison of new_user_id == referrer_user_id found
Results: 12 PASS, 1 FAIL
EXIT CODE: 1
```

**Restore:** exit 0, 13 PASS.

### Cycle 2: Rate limiter

**Break:** `sed 's/if not _check_rate_limit(rate_key):/if False:/'`

```
  FAIL: Rate limiter: _check_rate_limit() called in route handlers (AST)
        — Found 0 calls — expected ≥1 in decorated routes
  FAIL: Rate limiter: called in ≥2 route handlers (both create & redeem)
        — Found 0 calls — expected ≥2 (both routes)
Results: 11 PASS, 2 FAIL
EXIT CODE: 1
```

**Restore:** exit 0, 13 PASS.

### Cycle 3: Duplicate redemption guard

**Break:** `sed 's/except.*UniqueViolation.*/except Exception as _never_matches_dummy:/'`

```
  FAIL: Engine: catches UniqueViolation and returns 'duplicate'
        — Expected except handler with UniqueViolation returning 'duplicate'
Results: 12 PASS, 1 FAIL
EXIT CODE: 1
```

**Restore:** exit 0, 13 PASS.

---

## Evidence: No hardcoded row counts

```
$ grep -n "== 88\|== 94\|== 1002" tests/test_local115_referral_abuse_controls_guard.py
(none found)
```

---

## Evidence: No substring identifier checks

```
$ grep -n 'in ep_source\|in eng_source' tests/test_local115_referral_abuse_controls_guard.py
(none found)
```

---

## Evidence: Row counts

```
audio_tours row count = 94
stop_metrics row count = 1002
```

---

## Evidence: git status clean

```
$ git status --short
(empty — working tree clean after commit)
```

---

## Limitations

1. **Part 2 (Live HTTP) skipped.** The container at localhost:5100 is not
   running and Docker builds are prohibited (builder hangs). The HTTP guard
   exercises the controls end-to-end (403, 409, 429) but cannot be verified
   without a container rebuild. LEAD verified these by hand when LOCAL-115
   merged; the AST guard (Part 1) ensures the code paths remain live.

2. **No container touches.** Per constraints, no Docker build, no container
   restart, no `DELETE FROM` on any table.
