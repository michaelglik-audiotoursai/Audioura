##### READY FOR REVIEW

# SUBMISSION_LOCAL-107: Register Preference Routes, Prove the Loop Over HTTP

**Task:** LOCAL-107 — Register the preference routes, then prove the loop over HTTP  
**Branch:** `kiro/local107-register-preference-routes`  
**Author:** Mac Mini Kiro  
**Date:** 2026-08-01  

---

## Commit

```
commit: d327366
git rev-list --count subscribed..HEAD: 1
```

## Files Changed

| File | Lines | Purpose |
|------|-------|---------|
| `tour_orchestrator_service.py` | +8 | Call `register_preference_routes(app)` after wallet blueprint |
| `Dockerfile.orchestrator` | +2 | Include `swipe_preference_service.py` and `tests/db_connection.py` in container image |
| `tests/test_local107_register_preference_routes.py` | 418 (new) | HTTP-level proof that routes work end-to-end |
| `SUBMISSION_LOCAL-107.md` | this file | Submission artifact |

---

## The Fix

```python
# --- Swipe Preference Routes (LOCAL-107) ---
try:
    from swipe_preference_service import register_preference_routes
    register_preference_routes(app)
    print("[ORCHESTRATOR] Preference routes registered (LOCAL-107)")
except ImportError as e:
    print(f"[ORCHESTRATOR] Preference routes not available: {e}")
```

Added at line 120 of `tour_orchestrator_service.py`, directly after the wallet blueprint
registration. Same try/except pattern as the wallet blueprint for consistency.

---

## Evidence

### POST /user/<id>/stop-feedback returns 200

```
  POST /user/test_local107_a_8f35bed8/stop-feedback
  Body: {
    "stop_index": 4,
    "swipe": -1,
    "class_details": 0.26,
    "class_historic": 0.48,
    "class_social": 0.26,
    "i_con": 5.0
  }
  Response: 200 {"prefs":{"confidence":{"details":0.26,"historic":0.48,"social":0.26},"pref_details":0.4425,"pref_historic":0.4032,"pref_social":0.4425,"swipe_count":1,"user_id":"test_local107_a_8f35bed8"},"status":"ok"}
  ✓ PASS — Route exists and responds 200
```

### Full LOCAL-106 scenario over HTTP

```
  Recording swipes via HTTP:
    DISLIKE: Place Rossetti (h=0.48) → 200
    DISLIKE: Castle Hill (Colline du Château) (h=0.47) → 200
    LIKE:    Lascaris Palace (s=0.33) → 200
    LIKE:    Promenade des Anglais (s=0.32) → 200

  GET /user/test_local107_a_8f35bed8/preferences → 200
    pref_details:  0.4818
    pref_historic: 0.414
    pref_social:   0.4867
    swipe_count:   5
    interpretation: neutral on social (0.49); neutral on details (0.48); neutral on historic (0.41)
  ✓ pref_historic=0.4140 < 0.5 (historic disliked)

  POST /stops/biased-order → 200
    personalized: True
    Biased stop order (top 5):
      1. Castle Hill                                   combined=0.8368
      2. Cours Saleya Market                           combined=0.8368
      3. Old Town (Vieux Nice)                         combined=0.8368
      4. Place Masséna                                 combined=0.8368
      5. Place Rossetti                                combined=0.8352

    Positions changed vs baseline: 8/16
  ✓ PASS — Biased order differs from quality-only order
    Historic-heavy stops in biased order: 15
  ✓ Disliked class still present — bias, not filter
```

### Undo moves vector back (over HTTP)

```
  Reversal swipe (+1) on: Place Rossetti → 200
  pref_historic BEFORE undo: 0.4140
  pref_historic AFTER undo:  0.4756
  Delta: +0.0616
  ✓ PASS — Vector moved back (Δ = +0.0616)
```

### Isolation — User B (untouched) gets unbiased order (over HTTP)

```
  GET /user/test_local107_b_8f35bed8/preferences → 200
    cold_start: True
  ✓ User B is cold start (no preferences)
    User B rank_changes: 0
    User B top 3: ['Castle Hill', 'Cours Saleya Market', 'Old Town (Vieux Nice)']
  ✓ PASS — User B order is unbiased (all rank_change = 0)
  ✓ User A (personalized) ≠ User B (unbiased) — isolation confirmed
```

### Test fails when registration is commented out

**With registration commented out:**
```
  POST /user/test_local107_a_fc342dbb/stop-feedback
  Response: 404 <!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">
  <title>404 Not Found</title>
  ✗ FAIL — Expected 200, got 404
    This means register_preference_routes() was NOT called!
```

**With registration restored:**
```
  Response: 200 {"prefs":{...},"status":"ok"}
  ✓ PASS — Route exists and responds 200
```

### Row count before and after

```
  audio_tours row count BEFORE: 88
  audio_tours row count AFTER:  88
  ✓ audio_tours unchanged (88 → 88)
```

### tours-near constraint

```
  tours-near/43.7009358/7.2683912?radius=50 = [1, 12, 14, 17, 21, 24, 27, 28, 29]
  ✓ tours-near matches expected
```

---

## Scope Item 4: Other Registration Functions

Searched the entire codebase:

```
grep -rn "^def register_.*_routes\|^def register_.*\(app\)" *.py
```

**Result:** Only `swipe_preference_service.py:302` defines `register_preference_routes(app)`.
No other `register_*_routes` siblings exist. No other unregistered route-registration
functions were found.

---

## Design Decisions

### 1. Why the orchestrator (not a separate service or user-api)

The Dart client (`stop_feedback_service.dart:258`) posts to `Service.orchestrator` (port 5002).
Changing the host would require modifying the Flutter app, rebuilding the APK, and
deploying to devices — a much larger change. The orchestrator is the natural host because
it already has DB access and the preference engine has no external dependencies beyond
psycopg2 (already in `requirements_orchestrator.txt`).

### 2. Why try/except around the import

Matches the existing wallet blueprint pattern. If `swipe_preference_service.py` is somehow
missing from the container (build error, partial deploy), the orchestrator still starts
and serves all other endpoints. The failure is logged, not silent.

### 3. Why Dockerfile.orchestrator needs the file

The Dockerfile uses explicit `COPY` of named files (not `COPY *.py`). Without adding
`swipe_preference_service.py` and its dependency `tests/db_connection.py`, the import
would fail inside the container even though it works locally.

### 4. Test runs against subscribed stack (port 5102)

The constraint says "Never touch any `audioura-*` container." The subscribed stack
(`docker-compose-subscribed.yml`) runs on port 5102 and is a separate container.
The test defaults to `http://localhost:5102` via env var `ORCHESTRATOR_URL`.

---

## Limitations

1. **The `audioura-tour-orchestrator-1` container (port 5002) is NOT patched.** It runs
   from the previous image build and does NOT have this fix. Only the subscribed-orchestrator
   container on port 5102 demonstrates the fix. To apply to the audioura container, its
   compose stack would need to be rebuilt — which the constraint forbids.

2. **`swipe_preference_service.py` imports `db_connection` via `sys.path` manipulation.**
   This is inherited from LOCAL-101. A cleaner pattern would be to make `db_connection.py`
   a proper package or to inline the connection logic. Not in scope for this fix.

3. **The test uses existing `stop_metrics` data** (16 Nice stops from prior generations).
   No new tour generation was performed, so no cost was incurred and no rows were added.

4. **No Dart-side changes.** The client code (`stop_feedback_service.dart`) already
   targets the correct endpoint. It will work without any changes once the updated
   orchestrator container is deployed.

5. **Cost: $0.00.** No LLM calls, no generation, no API keys used.
