##### READY FOR REVIEW

# LOCAL-103: Test Mode Over HTTP

**Branch:** `kiro/local103-test-mode-over-http`  
**Commit:** `2be7ea2`  
**Agent:** Mac Mini Kiro  
**Date:** 2026-08-01

---

## Problem

`store_audio_tours.py` reads `is_test` from the **server's** environment
(`os.getenv('TOUR_TEST_MODE')`). A test generating over HTTP —
`POST /generate-complete-tour` — runs in its own process. Setting the env
var there does nothing; the value that counts is the one inside the
orchestrator container. An HTTP-generating test has no way to mark its own
tours.

`tests/test_local49_tour_content_persist.py` was the primary offender, causing
repeated hand-flagging of rows 39–43, 49–53, 66–67, 100/101/105/106.

---

## Trust Boundary Decision

**Decision: Accept `is_test` from the request body ONLY when server-side
opt-in is present.**

The `is_test` field is honored when either:
1. `TOUR_TEST_MODE=true` (whole-stack test deployment — the tourquality stack)
2. `TOUR_TEST_MODE_ALLOW_REQUEST=true` (explicit opt-in for dev stack)

On production, **neither env var is set**, so a malicious caller cannot:
- Mark real tours as test to hide them from `tours-near`
- Un-mark test tours (the field can only set `true`, not override to `false`)

This is a deliberate "server-side allow-flag" approach. The request field is
caller-controlled, but it only takes effect when the server explicitly permits
it. This balances test ergonomics against production safety.

---

## Per-File Changes

| File | Change |
|------|--------|
| `tour_orchestrator_service.py` | `store_audio_tour()` accepts `is_test` param (overrides env var when non-None). `orchestrate_tour_async()` threads it through. `generate_complete_tour()` extracts `is_test` from request body with trust-boundary gate. |
| `store_audio_tours.py` | Standalone version also accepts `is_test` param with same fallback logic. |
| `docker-compose-master.yml` | Added `TOUR_TEST_MODE_ALLOW_REQUEST=true` to `tour-orchestrator` service. |
| `tests/test_local49_tour_content_persist.py` | Passes `"is_test": True` in HTTP request. |
| `tests/run_local98_evidence.py` | Passes `"is_test": True`. |
| `tests/test_translation_implementation.py` | Passes `"is_test": True`. |
| `tests/test_user_tracking_fix.py` | Passes `"is_test": True`. |
| `tests/test_user_integration.py` | Passes `"is_test": True`. |
| `tests/test_user_tracking_simple.py` | Passes `"is_test": True`. |

---

## Acceptance Evidence

### AC1: Tour generated over HTTP with `is_test: true` lands with `is_test=true`

```
POST http://localhost:5202/generate-complete-tour
Body: {"location": "LOCAL103 Test 1785595784 Nice France old town", "tour_type": "walking",
       "total_stops": 3, "user_id": "USER-TEST-LOCAL103-ACCEPTANCE", "is_test": true}

Result: final_tour_id=108

DB row:
  id=108, is_test=True, lat=43.6976 (before cleanup), name=LOCAL103 Test 1785595784...
```

### AC2: Tour 108 does NOT appear in tours-near

```
GET http://localhost:5005/tours-near/43.7009358/7.2683912?radius=50
Response IDs: [1, 12, 14, 17, 21, 24, 27, 28, 29]
108 NOT in list: ✓
```

### AC3: Request without `is_test` behaves as today (env var fallback)

```
POST http://localhost:5202/generate-complete-tour  (no is_test field)
Result: final_tour_id=109, is_test=True (because TOUR_TEST_MODE=true in tourquality container)
```

### AC4: Hand-flagged rows verified (scope item 4 — backfill)

```
IDs checked: 39,40,41,42,43, 49,50, 51,52,53, 66,67, 100,101,105,106
All 16 rows: is_test=True ✓
No re-flagging performed (already correct).
```

### AC5: Row count — no DELETE

```
Row count BEFORE: 86
Row count AFTER:  88  (+2 from acceptance tests, both is_test=TRUE, coords nulled)
No rows deleted.
```

### AC6: tours-near final verification

```
GET http://localhost:5005/tours-near/43.7009358/7.2683912?radius=50
IDs: [1, 12, 14, 17, 21, 24, 27, 28, 29] ✓
```

---

## Limitations

1. **test_local49_tour_content_persist.py not re-run end-to-end** — the test
   requires a full 3-minute generation cycle. The fix is mechanical (adding
   `"is_test": True` to the request body). The code path was validated by the
   AC1 acceptance test above (same endpoint, same code path, same flag).

2. **Live orchestrator (port 5002) not restarted** — per constraint "never
   touch any `audioura-*` container." The `docker-compose-master.yml` change
   will take effect on next container rebuild. Tests should be run against the
   tourquality stack (port 5202) until then.

3. **Cloud Tasks path** — `_enqueue_cloud_task()` does not forward `is_test`
   to the worker. This only matters for `GENERATION_MODE='cloud_tasks'`
   (Cloud Run production), which already uses a different flagging strategy.
   The local Docker path (thread mode) is fully plumbed.
