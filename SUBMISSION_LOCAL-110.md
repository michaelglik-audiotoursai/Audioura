##### READY FOR REVIEW

# LOCAL-110: Wire Sharing — POST /tour/share + GET /tour/<id> Now Reachable

**Branch:** `kiro/local110-wire-sharing`  
**Commit:** `342ae29`  
**Agent:** Mac Mini Kiro  
**Date:** 2026-08-01

---

## Summary

`sharing_endpoints.py` defines a `sharing_bp` Blueprint with `POST /tour/share`
and `GET /tour/<tour_id>`. The blueprint was fully implemented (S49/S50) but
never registered on any service. One line added to `generate_tour_text_service.py`
makes both routes reachable. Sharing is confirmed free — no cost_meter or
wallet_ledger reference anywhere on this code path.

---

## Architecture Decision: Where POST /tour/share Lives

**Decision: tour-generator service (`generate_tour_text_service.py`, port 5000).**

Rationale:
1. `Dockerfile.generator` already copies `*.py` — both `sharing_endpoints.py` and
   `tour_sharing.py` are in the image. Zero Dockerfile changes needed.
2. The mobile app already talks to this service for tour operations.
3. `DATABASE_URL` is already configured (required by `tour_sharing.py`).
4. The auth pattern (`GATEWAY_API_KEY` / `X-API-Key` header) matches what the
   mobile client already sends to this service.

**Why not tour-id-resolution?** The GET path for deep links (`/resolve/tour/<id>`)
is already there via `deeplink_resolution_endpoint.py`. But POST (creating shares)
belongs with the service that has the tour data and the auth gate. Splitting
write and read across services because "the code happens to sit there" is not
a reason — the mobile client should talk to one service for the share lifecycle.

**Finding: /resolve/tour/<id> has a pre-existing DATABASE_URL bug.**
`deeplink_resolution_endpoint.py` defaults to `postgresql://admin:admin@localhost:5432/audiotours`
when `DATABASE_URL` is unset. Inside Docker, postgres is at `postgres-2:5432` with
password `password123`. The audioura-tour-id-resolution container has `DB_HOST`/`DB_PASSWORD`
set but NOT `DATABASE_URL`, so the deeplink endpoint silently fails with a connection
error. This is a pre-existing bug — not fixed here per constraint "never touch
audioura containers."

---

## Per-File Changes

| File | Change |
|------|--------|
| `generate_tour_text_service.py` | +3 lines: import `sharing_bp` + `app.register_blueprint(sharing_bp)` |
| `docker-compose-subscribed.yml` | New — subscribed stack for this worktree with `GATEWAY_API_KEY=test-api-key` |
| `tests/test_local110_sharing_wiring_guard.py` | New — 3-part guard test (AST + live HTTP + no-charge) |

---

## Acceptance Evidence

### AC1: Before/After for Every Sharing Route

| Method | Path | Service (port) | BEFORE | AFTER |
|--------|------|----------------|--------|-------|
| POST | /tour/share | subscribed-generator (5100) | 404 (Flask) | **200** |
| GET | /tour/\<id\> | subscribed-generator (5100) | 404 (Flask) | **200** |
| GET | /resolve/tour/\<id\> | tour-id-resolution (5025) | 404 (JSON: "shared tour not found") | 404 (same — pre-existing DATABASE_URL bug, not touched) |

### AC2: Round Trip — Create Then Fetch

```
POST http://localhost:5100/tour/share
Headers: X-API-Key: test-api-key
Body: {"location":"Nice France old town","tour_type":"walking","total_stops":5,"tour_text":"Stop 1: Place Rossetti..."}
→ 200 {"share_id":"Gz0tZmkV","share_url":"http://localhost:5000/tour/Gz0tZmkV"}

GET http://localhost:5100/tour/Gz0tZmkV
→ 200 {"location":"Nice France old town","share_count":1,"total_stops":5,"tour_text":"Stop 1: Place Rossetti...","tour_type":"walking"}
```

Tour text matches input. share_count = 1 (incremented on retrieval). Idempotent:
second POST with same inputs returns same share_id without re-storing.

### AC3: Guard Test Fails When Registration Removed

```
# With registration present:
$ python3 tests/test_local110_sharing_wiring_guard.py
Results: 14 PASS, 0 FAIL → exit 0

# With registration commented out:
$ python3 tests/test_local110_sharing_wiring_guard.py
  FAIL: AST confirms register_blueprint(sharing_bp) is live code — Call exists in text but not in AST — possibly commented out or in a string
Results: 13 PASS, 1 FAIL → exit 1
```

The AST guard catches removal without requiring a running container.

### AC4: No Charge — cost_ledger and wallet_ledger Unchanged

| Table | BEFORE (pre-share) | AFTER (post-share) | Delta |
|-------|--------------------|--------------------|-------|
| cost_ledger | 148 | 148 | **0** |
| wallet_ledger | 163 | 163 | **0** |
| audio_tours | 88 | 88 | **0** |
| shared_tours | 0 | 2 | +2 (guard test data) |

Static verification: `sharing_endpoints.py` and `tour_sharing.py` contain zero
references to `cost_meter`, `wallet_ledger`, or `record_operation`.

### AC5: Row Count Verification

```
audio_tours: 88 (unchanged)
```

### AC6: tours-near Constraint

```
GET http://localhost:5005/tours-near/43.7009358/7.2683912?radius=50
IDs (sorted): [1, 12, 14, 17, 21, 24, 27, 28, 29] ✓
```

---

## Verbatim Evidence

### Evidence: POST /tour/share — before (404)

```
$ curl -s -o /dev/null -w "HTTP %{http_code}" -X POST http://localhost:5100/tour/share \
  -H "Content-Type: application/json" -H "X-API-Key: test-api-key" \
  -d '{"location":"test","tour_type":"walking","total_stops":3,"tour_text":"hello"}'
HTTP 404
```

### Evidence: POST /tour/share — after (200)

```
$ curl -s -X POST http://localhost:5100/tour/share \
  -H "Content-Type: application/json" -H "X-API-Key: test-api-key" \
  -d '{"location":"Nice France old town","tour_type":"walking","total_stops":5,"tour_text":"Stop 1: Place Rossetti..."}'
{"share_id":"Gz0tZmkV","share_url":"http://localhost:5000/tour/Gz0tZmkV"}
```

### Evidence: GET /tour/Gz0tZmkV — after (200)

```
$ curl -s http://localhost:5100/tour/Gz0tZmkV
{"location":"Nice France old town","share_count":1,"total_stops":5,"tour_text":"Stop 1: Place Rossetti. A beautiful baroque cathedral dominates this charming square.\n\nStop 2: Cours Saleya. The famous flower and food market.\n\nStop 3: Palais Lascaris. A stunning 17th-century palace.\n\nStop 4: Place Garibaldi. Named after the Italian revolutionary.\n\nStop 5: Colline du Chateau. Ancient ruins with panoramic views.","tour_type":"walking"}
```

### Evidence: Guard test with registration commented out — exit 1

```
$ python3 tests/test_local110_sharing_wiring_guard.py; echo "Exit: $?"
  FAIL: AST confirms register_blueprint(sharing_bp) is live code — Call exists in text but not in AST — possibly commented out or in a string
Results: 13 PASS, 1 FAIL
Exit: 1
```

### Evidence: Guard test with registration present — exit 0

```
$ python3 tests/test_local110_sharing_wiring_guard.py; echo "Exit: $?"
Results: 14 PASS, 0 FAIL
ALL TESTS PASSED
Exit: 0
```

---

## Finding: /resolve/tour/<id> Pre-Existing Bug

The `audioura-tour-id-resolution-1` container has `deeplink_resolution_endpoint.py`
registered (`GET /resolve/tour/<share_id>`), but it uses `DATABASE_URL` env var
which is NOT set in the container. It falls back to
`postgresql://admin:admin@localhost:5432/audiotours` — wrong host (localhost vs
postgres-2) and wrong password (admin vs password123). Connection fails silently
and returns `{"error": "shared tour not found"}` for all queries.

This means **no deeplink resolution has ever worked in the Docker stack**.
The route exists but can never reach the database. Fix: add
`DATABASE_URL=postgresql://admin:password123@postgres-2:5432/audiotours`
to the tour-id-resolution service in `docker-compose-master.yml`. Not fixed
here per constraint (audioura containers not touched).

---

## Limitations

1. **audioura-tour-id-resolution not rebuilt** — per constraint "never touch any
   audioura-* container." The `/resolve/tour/<id>` deeplink path remains broken
   (pre-existing bug). Only the subscribed-generator was rebuilt.

2. **GATEWAY_API_KEY hardcoded as `test-api-key`** — production deployment should
   use a proper secret. The subscribed stack is dev-only; this is acceptable for
   testing.

3. **shared_tours table created on first use** — `_ensure_shared_tours_table(conn)`
   in `tour_sharing.py` creates the table with CREATE TABLE IF NOT EXISTS. No
   migration file needed, but production should use a proper migration.

4. **share_url uses BASE_URL=http://localhost:5000** — the container's BASE_URL
   env var defaults to localhost. In production, this would need to be
   `https://audioura.io`. The share_id (the actual identifier) is correct
   regardless.
