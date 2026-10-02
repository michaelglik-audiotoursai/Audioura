##### READY FOR REVIEW

**Task:** LOCAL-154 — Wire the wallet Blueprint into the orchestrator the app actually talks to  
**Branch:** `kiro/local154-wire-wallet-into-shared`  
**Commit:** `3fccd56abebfce6efd435e1c44a264d18503e428`  
**Date:** 2026-08-02  

---

## Summary

The wallet Blueprint and swipe preference routes were already registered in
the `subscribed` branch's `tour_orchestrator_service.py` source — the problem
found by LOCAL-152 was that the running container (built from `storied`) does
not have this code. The `storied` branch has no reference to `wallet_api` at all.

This task upgraded the registration blocks to match the LOCAL-146/D31 pattern:
log at ERROR on ImportError instead of silently printing, and document the
consequence of failure in comments. The test proves the five routes resolve
in-process; deployment waits for a container rebuild (which is blocked by the
hung Docker builder).

---

## Per-file changes

| File | Change |
|---|---|
| `tour_orchestrator_service.py` | Upgraded wallet_bp + preference routes registration to log at ERROR on ImportError; added consequence-of-failure comments matching storied's LOCAL-146 pattern |
| `tests/test_local154_wallet_routes_registered.py` | New in-process test: url_map inspection, test_client exercise, break-probe with replacement count, ERROR-level logging verification |

---

## Verbatim test output (exit code 0)

```
======================================================================
  LOCAL-154: Wallet Routes Registered on Shared Orchestrator
======================================================================

──────────────────────────────────────────────────────────────────────
  PHASE 1: url_map — five routes must resolve
──────────────────────────────────────────────────────────────────────
[ORCHESTRATOR] Wallet API blueprint registered (LOCAL-68)
[ORCHESTRATOR] Preference routes registered (LOCAL-107)

  Registered routes (17 total):
    DELETE /delete-account/<secret_id>
    GET    /download/<job_id>
    GET    /health
    GET    /jobs
    GET    /plans/available
    GET    /serve/<job_id>
    GET    /static/<path:filename>
    GET    /status/<job_id>
    GET    /user/<user_id>/preferences
    GET    /wallet/<user_id>
    GET    /wallet/<user_id>/transactions
    POST   /generate-complete-tour
    POST   /stops/biased-order
    POST   /tour-status
    POST   /user/<user_id>/stop-feedback
    POST   /wallet/<user_id>/change-tier
    POST   /wallet/<user_id>/topup

  Checking five required wallet/preference routes:
    ✓ FOUND: GET /wallet/<user_id>
    ✓ FOUND: GET /wallet/<user_id>/transactions
    ✓ FOUND: GET /plans/available
    ✓ FOUND: POST /wallet/<user_id>/topup
    ✓ FOUND: POST /user/<user_id>/stop-feedback

──────────────────────────────────────────────────────────────────────
  PHASE 2: test_client() — no generic Flask HTML 404
──────────────────────────────────────────────────────────────────────
    ✓ PASS: GET /wallet/test-user-154 → 500 (route registered, not generic 404)
    ✓ PASS: GET /wallet/test-user-154/transactions → 500 (route registered, not generic 404)
    ✓ PASS: GET /plans/available → 200 (route registered, not generic 404)
    ✓ PASS: POST /wallet/test-user-154/topup → 400 (route registered, not generic 404)
    ✓ PASS: POST /user/test-user-154/stop-feedback → 400 (route registered, not generic 404)

──────────────────────────────────────────────────────────────────────
  PHASE 3: /plans/available returns plan list
──────────────────────────────────────────────────────────────────────
    Plans returned: ['free', 'ppu', 'unlimited']
    ✓ PASS — All three plans present

──────────────────────────────────────────────────────────────────────
  PHASE 4: Break-probe
──────────────────────────────────────────────────────────────────────

  Replacement count for 'from wallet_api import wallet_bp': 1
  Neutered: wallet_api import raises ImportError
[LOCAL-154] Wallet API NOT registered — wallet screens will fail: BREAK_PROBE_LOCAL_154
[ORCHESTRATOR] ERROR: wallet API unavailable: BREAK_PROBE_LOCAL_154
[ORCHESTRATOR] Preference routes registered (LOCAL-107)
  ✓ BREAK confirmed: wallet routes vanished from url_map
  ✓ Preference route still registered (independent of wallet)
  Restored: original source written back
  ✓ Source verified identical to original

──────────────────────────────────────────────────────────────────────
  PHASE 5: ERROR-level logging on import failure
──────────────────────────────────────────────────────────────────────
  ✓ PASS — Wallet import failure logs at ERROR level
  ✓ PASS — Preference import failure logs at ERROR level

──────────────────────────────────────────────────────────────────────
  SUMMARY
──────────────────────────────────────────────────────────────────────
  Passed: 14/14
  Failed: 0/14

  ✓ OVERALL: PASS
```

---

## Running container unchanged

### Before work
```
audioura-tour-orchestrator-1   Up 46 hours
```

### After work
```
audioura-tour-orchestrator-1   Up 46 hours
```

### Container has no wallet_api reference
```
$ docker exec audioura-tour-orchestrator-1 grep -c wallet_api /app/tour_orchestrator_service.py
0
```

### All audioura containers — identical uptimes before and after
```
audioura-tour-generator-1                 Up 39 hours (unhealthy)
audioura-tour-orchestrator-1              Up 46 hours
audioura-tour-generation-modernized-1-1   Up 46 hours
audioura-coordinates-fromai-1             Up 46 hours (healthy)
audioura-user-api-2-1                     Up 46 hours
audioura-map-delivery-1                   Up 46 hours (unhealthy)
audioura-tour-id-resolution-1             Up 2 days
audioura-translation-service-1            Up 2 days
audioura-treats-1                         Up 4 days
audioura-tour-update-1                    Up 4 days
audioura-tour-processor-1                 Up 47 hours (unhealthy)
audioura-polly-tts-1-1                    Up 47 hours
audioura-voice-control-1                  Up 4 days (unhealthy)
```

---

## Acceptance criteria checklist

| Criterion | Evidence |
|---|---|
| Five routes resolve in url_map in-process | Phase 1: all 5 ✓ FOUND |
| Registration failure logs at ERROR and does not raise | Phase 5 + break-probe output shows `_wallet_logging.getLogger(...).error(...)` fires, service continues |
| Break-probe with replacement count | Phase 4: count=1, routes vanish, restored |
| Running containers untouched; uptimes shown before and after | 46 hours before, 46 hours after; `grep -c wallet_api` = 0 |
| Verbatim exit codes for named suites | `test_local154_wallet_routes_registered.py` → exit 0 |
| `git status --short` clean | Empty (verified) |

---

## Verbatim exit code

```
$ python3 tests/test_local154_wallet_routes_registered.py; echo "EXIT: $?"
...
EXIT: 0
```

---

## git status

```
$ git status --short
(empty)
```

---

## Limitations

1. **Source changed, not deployed.** The running container at port 5002 is
   built from `storied`, which has no wallet_api registration. A container
   rebuild is required to make the wallet reachable from the app — and the
   Docker builder is hung. This is the expected outcome per the task scope.

2. **The `subscribed` branch already had the registration.** The actual code
   change here is the ERROR-level logging upgrade (matching the LOCAL-146
   pattern from `storied`) and consequence-of-failure documentation, not the
   registration itself. The registration existed since LOCAL-68 on this branch.

3. **When `subscribed` merges into `storied`, the wallet routes will be live
   on the shared orchestrator.** Until then, both the wallet registration (on
   `subscribed`) and the preference-route-only registration (on `storied`)
   coexist in their respective branches. The merge is Michael's call.

4. **The test exercises routes in-process without a real database.** Wallet
   routes return 500 (DB unreachable) and stop-feedback returns 400 (bad body).
   Both prove the route is registered — application code runs, not Flask's
   generic HTML 404. Functional correctness of wallet operations is covered
   by the existing 53 contract tests in `test_wallet_api.py`.

5. **No Docker build performed.** Per constraints. The source is correct;
   deployment waits for the builder.
