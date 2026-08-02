##### READY FOR REVIEW

# LOCAL-134: Fix tautological assertion in referral wiring guard

**Branch:** `kiro/local134-tautological-assertions`  
**Commit:** `79db85f`  
**Agent:** Mac Mini Kiro  
**Date:** 2026-08-02  

---

## Summary

The behavioural check for `/referral/redeem` in `test_local114_referral_wiring_guard.py:193`
contained a disjunct that matched the failure condition itself:

```python
route_exists = (
    resp2.status_code != 404
    or b"referral" in resp2.data.lower()
    or b"not found" in resp2.data.lower()      # ← TAUTOLOGICAL
)
```

Flask's default 404 body reads *"The requested URL was **not found** on the server."*
The third disjunct always matches on a 404, so the assertion passes regardless of
whether the blueprint is registered.

**Fix:** Replace the body-content sniffing with a direct `app.url_map` lookup via
`werkzeug`'s routing adapter. This asks the router itself whether it knows the route —
unambiguous, zero false positives.

---

## Changes

| File | Lines | What |
|------|-------|------|
| `tests/test_local114_referral_wiring_guard.py` | +19 −16 | Replace body-content disjunction with url_map adapter lookup |

---

## Evidence: Neutering probe PASS → FAIL

### Before fix (old code, neutered blueprint)

The old assertion PASSED under neutering because `b"not found"` matched Flask's 404:

```
  PASS: POST /referral/redeem route registered (behavioural)   ← HOLLOW
```

(This is documented in SUBMISSION_LOCAL-133.md — neutering probe showed 9 PASS, 1 FAIL,
with only `/referral/create` catching the regression.)

### After fix (new code, neutered blueprint)

```
Replacement count: 1
  FAIL: POST /referral/create is not 404 (behavioural) — Got 404 — blueprint not registered or route unreachable!
  FAIL: POST /referral/redeem route registered (behavioural) — Route /referral/redeem not found in app.url_map — blueprint not registered!
Results: 8 PASS, 2 FAIL
EXIT=1
```

Both behavioural assertions now catch the neutering.

---

## All Three Guards: Probe Summary

| Guard | Baseline | Comment-out | Neutering |
|-------|----------|-------------|-----------|
| LOCAL-110 (sharing_bp) | exit=0 ✓ | exit=1 ✓ (repl count: 1) | exit=1 ✓ (repl count: 1) |
| LOCAL-113 (persona_bp) | exit=0 ✓ | exit=1 ✓ (repl count: 1) | exit=1 ✓ (repl count: 1) |
| LOCAL-114 (referral_bp) | exit=0 ✓ | exit=1 ✓ (repl count: 1) | exit=1 ✓ (repl count: 1) |

---

## Sweep: All `or` disjuncts in assertions across `tests/`

### Search commands used

```bash
grep -rn 'or.*in.*\.data' tests/ --include="*.py"
grep -rn 'or.*in.*(resp|response).*(text|data|content)' tests/ --include="*.py"
grep -rn 'any(.*resp' tests/ --include="*.py"
grep -rn 'status_code != 404' tests/ --include="*.py"
```

### Results

| File:Line | Disjunct | Tautological? | Disposition |
|-----------|----------|---------------|-------------|
| `test_local114_referral_wiring_guard.py:195` | `b"not found" in resp2.data.lower()` | **YES** — Flask's 404 body always contains "not found" | **FIXED** — replaced with url_map lookup |
| `test_local114_referral_wiring_guard.py:194` | `b"referral" in resp2.data.lower()` | No — Flask's 404 body does not contain "referral" | Removed (superseded by url_map fix) |
| `test_local110_sharing_wiring_guard.py:155` | `b"tour" in resp2.data.lower()` | **No** — Flask's 404 body does not contain "tour" | Fragile, not tautological; left as-is |

### Verification of `b"tour"` (LOCAL-110, line 155)

```
>>> Flask default 404 body:
b'<!doctype html>\n<html lang=en>\n<title>404 Not Found</title>\n
<h1>Not Found</h1>\n<p>The requested URL was not found on the server.
If you entered the URL manually please check your spelling and try again.</p>\n'

>>> b"tour" in body.lower()
False
```

LEAD's assessment is **correct** — `b"tour"` is not in Flask's default 404 body.
The assertion is fragile (if Flask ever changed its error template to include "tour"
it would become tautological) but is not tautological today. The neutering probe
for LOCAL-110 confirms it fails correctly (exit=1 with 2 FAIL).

**No other tautological assertions found in the test suite.**

---

## Flask 404 Body Proof

```
Status: 404
Body: b'<!doctype html>\n<html lang=en>\n<title>404 Not Found</title>\n
<h1>Not Found</h1>\n<p>The requested URL was not found on the server.
If you entered the URL manually please check your spelling and try again.</p>\n'

Contains b"not found": True    ← PROVES the tautology
Contains b"tour": False        ← LOCAL-110 is safe
Contains b"referral": False    ← line 194 was not tautological on its own
```

---

## Row Counts (before and after)

| Table | Before | After |
|-------|--------|-------|
| audio_tours | 94 | 94 |
| stop_metrics | 1002 | 1002 |

---

## Design Decision: url_map vs. status-code check

Two options for proving route registration:

1. **Status-code check** (`resp.status_code != 404`): Simple, but when the route
   handler itself returns 404 as business logic (e.g., "referral code not found"),
   the assertion needs body-sniffing to distinguish business-404 from routing-404.
   Body-sniffing is where the tautology crept in.

2. **url_map adapter lookup**: Asks the router directly. A matched rule means the
   blueprint registered the route — full stop. No HTTP request needed, no body
   parsing, no ambiguity. If `werkzeug.exceptions.NotFound` is raised, the route
   is genuinely absent.

Chose (2) because it eliminates the entire class of body-sniffing bugs. The
`/referral/create` assertion still uses status-code check (it works cleanly
because that route returns 400/500 on valid registration, never 404).

---

## Limitations

- The url_map check proves the route is registered but does not exercise the route
  handler's business logic. That's LOCAL-115's job.
- If werkzeug's internal API changes the exception hierarchy, the try/except would
  need updating. This is unlikely (stable since werkzeug 1.0) and would surface as
  an import error, not a silent pass.
- The `b"tour"` fragile assertion in LOCAL-110 is left unfixed. It works today but
  could become tautological if Flask's error template changes. Consider migrating
  to url_map in a future cleanup pass.

---

## git status

```
$ git status --short
(clean)
```
