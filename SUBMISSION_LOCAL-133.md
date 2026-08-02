##### READY FOR REVIEW

# LOCAL-133: Convert three blind blueprint guards to behavioural checks

**Branch:** `kiro/local133-blueprint-guards-behavioural`  
**Commit:** `3dd7be0`  
**Agent:** Mac Mini Kiro  
**Date:** 2026-08-02  

---

## Summary

Three blueprint wiring guards (LOCAL-110, LOCAL-113, LOCAL-114) used `ast.walk` to find `register_blueprint()` Call nodes — but `ast.walk` does not check whether the enclosing control flow is reachable. `if False: app.register_blueprint(bp)` parses to a valid Call node and the guards passed blindly. LOCAL-132 probed this and documented all three as BLIND (neutering).

**Fix:** Each guard now imports the Flask app in-process and uses `app.test_client()` to hit a route the blueprint provides. A 404 means the blueprint is not actually registered — regardless of what the AST says. This is the same pattern that makes LOCAL-115 and LOCAL-128 hold (D35).

AST checks are **kept** as a cheap first-line defence (catches the comment-out case fast, no app import needed). The behavioural assertion is the authoritative second line.

If the app cannot be imported, the behavioural guard SKIPs explicitly with a reason (LOCAL-131 pattern). Skips are counted separately and never masquerade as passes.

---

## Changes

| File | Lines | What |
|------|-------|------|
| `tests/test_local110_sharing_wiring_guard.py` | +119 −161 | Added BEHAVIOURAL GUARD via test_client(); removed live HTTP (required container); kept AST + no-charge guards |
| `tests/test_local113_persona_wiring_guard.py` | +113 −189 | Added BEHAVIOURAL GUARD via test_client(); removed live HTTP + stale-container skip logic; kept source + side-effect guards |
| `tests/test_local114_referral_wiring_guard.py` | +66 −93 | Added BEHAVIOURAL GUARD via test_client(); removed live HTTP + abuse audit (those belong to LOCAL-115); kept AST guard |

**Total:** 298 insertions, 443 deletions (net −145 lines — simpler, stronger).

---

## Evidence: Nine Probe Runs

### Guard 1: LOCAL-110 (sharing_bp)

**Baseline:**
```
Results: 10 PASS, 0 FAIL
ALL TESTS PASSED
EXIT=0
```

**Probe A — comment-out (replacement count: 1):**
```
  FAIL: AST confirms register_blueprint(sharing_bp) is live code — Call exists in text but not in AST
  FAIL: POST /tour/share is not 404 (behavioural) — Got 404
  FAIL: GET /tour/<id> route registered (behavioural) — Got 404
Results: 7 PASS, 3 FAIL
EXIT=1
```

**Probe B — `if False:` neutering (replacement count: 1):**
```
  PASS: AST confirms register_blueprint(sharing_bp) is live code   ← AST is BLIND (confirms D35)
  FAIL: POST /tour/share is not 404 (behavioural) — Got 404        ← behavioural CATCHES it
  FAIL: GET /tour/<id> route registered (behavioural) — Got 404
Results: 8 PASS, 2 FAIL
EXIT=1
```

---

### Guard 2: LOCAL-113 (persona_bp)

**Baseline:**
```
Results: 10 PASS, 0 FAIL
ALL TESTS PASSED
EXIT=0
```

**Probe A — comment-out (replacement count: 1):**
```
  FAIL: AST confirms register_blueprint(persona_bp) is live code
  FAIL: POST /user/persona is not 404 (behavioural) — Got 404
  FAIL: GET /user/persona is not 404 (behavioural) — Got 404
Results: 7 PASS, 3 FAIL
EXIT=1
```

**Probe B — `if False:` neutering (replacement count: 1):**
```
  PASS: AST confirms register_blueprint(persona_bp) is live code   ← AST is BLIND
  FAIL: POST /user/persona is not 404 (behavioural) — Got 404      ← behavioural CATCHES it
  FAIL: GET /user/persona is not 404 (behavioural) — Got 404
Results: 8 PASS, 2 FAIL
EXIT=1
```

---

### Guard 3: LOCAL-114 (referral_bp)

**Baseline:**
```
Results: 10 PASS, 0 FAIL
ALL ASSERTIONS PASSED — wiring is correct
EXIT=0
```

**Probe A — comment-out (replacement count: 1):**
```
  FAIL: AST confirms register_blueprint(referral_bp) is live code
  FAIL: POST /referral/create is not 404 (behavioural) — Got 404
Results: 8 PASS, 2 FAIL
EXIT=1
```

**Probe B — `if False:` neutering (replacement count: 1):**
```
  PASS: AST confirms register_blueprint(referral_bp) is live code  ← AST is BLIND
  FAIL: POST /referral/create is not 404 (behavioural) — Got 404   ← behavioural CATCHES it
Results: 9 PASS, 1 FAIL
EXIT=1
```

---

## Summary Table

| Guard | Baseline | Comment-out | `if False:` | Both detected? |
|-------|----------|-------------|-------------|----------------|
| LOCAL-110 (sharing_bp) | exit=0 ✓ | exit=1 ✓ | exit=1 ✓ | **YES** |
| LOCAL-113 (persona_bp) | exit=0 ✓ | exit=1 ✓ | exit=1 ✓ | **YES** |
| LOCAL-114 (referral_bp) | exit=0 ✓ | exit=1 ✓ | exit=1 ✓ | **YES** |

All replacement counts = 1 (probe applied, D36 satisfied).

---

## Row Counts (before and after)

| Table | Before | After |
|-------|--------|-------|
| audio_tours | 94 | 94 |
| stop_metrics | 1002 | 1002 |

---

## Design Decisions

1. **test_client() over subprocess server**: Flask's `app.test_client()` runs in-process with no port, no socket, no background process. Faster, simpler, no Docker needed.
2. **Keep AST checks**: They're not wrong, only insufficient. Comment-out is the most common regression; the AST catches it without importing anything.
3. **Skip on import failure**: If `generate_tour_text_service.py` has a broken import chain (missing module), the behavioural guard SKIPs with reason rather than crashing or passing hollow.
4. **Removed live HTTP / container-dependent code**: The old guards hit `localhost:5100` or `localhost:5000` which required running Docker containers. Those are now irrelevant — `test_client()` needs nothing external.
5. **Removed Part 3 abuse audit from LOCAL-114**: That was an informational inventory that belongs to LOCAL-115 (which already exercises all three controls behaviourally).

---

## Limitations

- The behavioural guard proves the route is registered (not 404) but does not exercise business logic (that's LOCAL-115's job for referral, and not in scope here).
- If `generate_tour_text_service.py` has import-time errors (e.g., missing psycopg2 at import), the behavioural guard will SKIP. Currently all imports succeed because the DB connection is lazy.
- The AST check remains blind to `if False:` — this is documented, expected, and the reason the behavioural check exists as the authoritative line.
