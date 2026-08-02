##### READY FOR REVIEW

# LOCAL-131: Fix the persona guard — split source/HTTP, skip stale container

**Branch:** `kiro/local131-persona-guard-fix`  
**Commit:** `e15bbae`  
**Agent:** Mac Mini Kiro  
**Date:** 2026-08-02  

---

## Summary

The persona wiring guard (`test_local113_persona_wiring_guard.py`) was
permanently red because it conflated two independent questions:

1. **Is the registration in the source?** — Answerable now, statically.
2. **Does the running service serve the route?** — Not answerable — the
   container at port 5000 predates the persona_bp registration and Docker
   builds are hung.

A permanently red guard carries no information and trains readers to ignore
the board (D35 cry-wolf pattern).

**Fix:** Split source-level and live-HTTP assertions. Source assertions
pass/fail independently. HTTP assertions SKIP (not fail) when the container
is stale — detected by: port reachable + route 404 + source guard passed.
When the container is rebuilt, the 404 disappears and HTTP assertions begin
running automatically. No hardcoded skip.

---

## Changes

| File | Lines | What |
|------|-------|------|
| `tests/test_local113_persona_wiring_guard.py` | +187 −96 | Split guard: source always answerable, HTTP skips when stale |

---

## Evidence

### Run 1: Registration PRESENT — exit 0, HTTP SKIPPED with reason

```
======================================================================
test_local113_persona_wiring_guard.py
LOCAL-113 + LOCAL-131: Persona blueprint registration guard
Service: http://localhost:5000
======================================================================

[SOURCE GUARD] Verifying persona_bp registration in source code
  File: /Users/micha/audioura-worktrees/LOCAL-131/generate_tour_text_service.py
    (import matches: 1)
  PASS: Import statement present
    (register_blueprint matches: 1)
  PASS: register_blueprint(persona_bp) call present
  PASS: AST confirms register_blueprint(persona_bp) is live code

[BEHAVIOUR GUARD] Verifying persona is opt-in only
  PASS: No cost_meter import in persona_endpoints.py
  PASS: No wallet_ledger reference in persona_endpoints.py
  PASS: No audio_tours modification in persona_endpoints.py
  PASS: Persona store uses user_preferences table
  PASS: Persona store does NOT touch audio_tours

[LIVE HTTP] Testing against http://localhost:5000
  SKIP: POST /user/persona is not 404 — Container at http://localhost:5000 returns 404 for /user/persona — image predates persona_bp registration (source is correct per Part 1). Cannot rebuild (Docker builds hung). Will auto-run when container is rebuilt with current source.
  SKIP: POST /user/persona returns 200 — (same reason)
  SKIP: GET /user/persona is not 404 — (same reason)
  SKIP: GET /user/persona returns 200 — (same reason)
  SKIP: Round trip: persona value matches — (same reason)

======================================================================
Results: 8 PASS, 0 FAIL, 5 SKIP
SOURCE ASSERTIONS PASSED — live HTTP skipped (see reasons above)
======================================================================
EXIT=0
```

### Run 2: Registration REMOVED — exit 1

**Break method:**
```bash
sed -i '' 's/^from persona_endpoints import persona_bp$/# from persona_endpoints import persona_bp/' generate_tour_text_service.py
sed -i '' 's/^app.register_blueprint(persona_bp)$/# app.register_blueprint(persona_bp)/' generate_tour_text_service.py
```

**Replacement counts:**
```
grep -c "# from persona_endpoints import persona_bp" → 1
grep -c "# app.register_blueprint(persona_bp)" → 1
```

**Guard output when broken:**
```
======================================================================
test_local113_persona_wiring_guard.py
LOCAL-113 + LOCAL-131: Persona blueprint registration guard
Service: http://localhost:5000
======================================================================

[SOURCE GUARD] Verifying persona_bp registration in source code
  File: /Users/micha/audioura-worktrees/LOCAL-131/generate_tour_text_service.py
    (import matches: 1)
  PASS: Import statement present
    (register_blueprint matches: 1)
  PASS: register_blueprint(persona_bp) call present
  FAIL: AST confirms register_blueprint(persona_bp) is live code — Call exists in text but not in AST — possibly commented out or in a string

[BEHAVIOUR GUARD] Verifying persona is opt-in only
  PASS: No cost_meter import in persona_endpoints.py
  PASS: No wallet_ledger reference in persona_endpoints.py
  PASS: No audio_tours modification in persona_endpoints.py
  PASS: Persona store uses user_preferences table
  PASS: Persona store does NOT touch audio_tours

[LIVE HTTP] Testing against http://localhost:5000

  POST /user/persona:
  FAIL: POST /user/persona is not 404 — Got 404 — blueprint not registered!
  FAIL: POST /user/persona returns 200 — Got 404: <!DOCTYPE HTML PUBLIC...

  GET /user/persona:
  FAIL: GET /user/persona is not 404 — Got 404 — blueprint not registered!
  FAIL: GET /user/persona returns 200 — Got 404: <!DOCTYPE HTML PUBLIC...

======================================================================
Results: 7 PASS, 5 FAIL
SOME TESTS FAILED
======================================================================
EXIT=1
```

**Key behaviour:** When the source guard fails, the HTTP 404 is NOT excused as
"stale container" — it falls through to normal assertions and fails. This means
the guard correctly detects both removal paths:
- Source broken + container stale → FAIL (source guard + HTTP)
- Source broken + container rebuilt → FAIL (source guard + HTTP)
- Source correct + container stale → PASS + SKIP (current state)
- Source correct + container rebuilt → PASS + PASS (future state)

**Restored:** `git checkout -- generate_tour_text_service.py` → exit 0 again.

---

## Design Decisions

1. **No hardcoded skip.** Reachability detected at runtime: `is_port_reachable()`
   checks TCP, then a POST probe checks the route. The skip triggers only when
   both conditions hold: port open AND route 404 AND source guard passed.

2. **Match counts printed (D36).** Import and register_blueprint occurrence
   counts are printed so a zero-match sed cannot masquerade as a result.

3. **A skip is not a pass.** Summary line shows SKIP count separately:
   `Results: 8 PASS, 0 FAIL, 5 SKIP`. The final message explicitly states
   HTTP was skipped.

4. **HTTP will auto-activate.** When someone eventually rebuilds the container
   with the current source, `/user/persona` will respond non-404 and the HTTP
   assertions will run as normal PASS/FAIL checks.

5. **Source guard failure unblocks HTTP failure.** If the source guard fails
   (registration removed), the HTTP 404 is NOT skipped — it correctly fails,
   giving maximum signal about what's broken.

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

1. **HTTP assertions are currently skipped.** The container at port 5000
   (`audioura-tour-generator-1`) was never rebuilt with persona_bp. Docker
   builds are hung (constraint). The source guard proves the registration
   is correct; the HTTP guard will activate automatically when the container
   is eventually rebuilt.

2. **Text-match checks pass on commented code.** The string
   `"from persona_endpoints import persona_bp"` appears inside the comment
   `# from persona_endpoints import persona_bp`. The AST check (Check 3) is
   the real guard — it correctly identifies commented-out code as not live.
   Text checks 1 and 2 are a fast first-line (helpful for deletions), not the
   sole defence.

3. **No container-level verification possible.** Cannot prove the fix works
   end-to-end through the container because Docker builds are blocked. The
   guard will provide that evidence automatically once builds resume.
