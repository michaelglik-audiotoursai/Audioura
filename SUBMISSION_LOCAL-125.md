##### READY FOR REVIEW

# SUBMISSION_LOCAL-125: App Port Map vs Running Services

**Task:** LOCAL-125 — The app points at 5002 for a route that may not be there  
**Branch:** `kiro/local125-app-port-map`  
**Author:** Mac Mini Kiro  
**Date:** 2026-08-02  

---

## Commit

```
commit: 2a32170
git rev-list --count subscribed..HEAD: 1
```

## Files Changed

| File | Lines | Purpose |
|------|-------|---------|
| `APP_PORT_MAP.md` | 168 (new) | Full port map, route audit with curl evidence, blocker analysis |
| `SUBMISSION_LOCAL-125.md` | this file | Submission artifact |

---

## Evidence

### Method

Every route called by the Flutter app (found via `grep -r 'Endpoints\.(get|post|url|base)'` in `audio_tour_app/lib/`) was curled against the live container on the Mac. Routes were classified as:

- **LIVE**: Route registered and functional (200, or 400 with app-level validation error, or JSON 404 like `{"error":"Job not found"}`)
- **WOULD-404**: Either Flask HTML 404 (route not registered in running image) or connection refused (no container on port)

### Key Findings

**11 services in `_localPorts`. 8 have running containers. 3 ports have no container at all.**

| Port | Service | Container exists? |
|------|---------|-------------------|
| 5002 | orchestrator | ✅ Yes — but missing 5 routes |
| 5003 | userDb | ✅ Yes — fully functional |
| 5005 | mapDelivery | ✅ Yes — fully functional |
| 5007 | treats | ✅ Yes — fully functional |
| 5008 | voice | ✅ Yes — fully functional |
| 5012 | news | ✅ Yes — fully functional |
| 5017 | newsletter | ❌ No container |
| 5022 | tourEditing | ❌ No container |
| 5023 | customAudio | ❌ No container |
| 5025 | tourIdResolution | ✅ Yes — fully functional |
| 5030 | translation | ✅ Yes — fully functional |

### Verbatim curl evidence — Port 5002 Would-404s

```
$ curl -s -X POST http://localhost:5002/user/test/stop-feedback \
    -H "Content-Type: application/json" \
    -d '{"swipe":1,"stop_index":0,"class_details":0.5,"class_historic":0.5,"class_social":0.5,"i_con":0.5}'

<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">
<title>404 Not Found</title>
<h1>Not Found</h1>
<p>The requested URL was not found on the server.</p>
```

```
$ curl -s http://localhost:5002/wallet/test

<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">
<title>404 Not Found</title>
...
```

```
$ curl -s http://localhost:5002/plans/available

<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">
<title>404 Not Found</title>
...
```

### Verbatim curl evidence — Port 5002 LIVE routes (for contrast)

```
$ curl -s -X POST http://localhost:5002/generate-complete-tour \
    -H "Content-Type: application/json" -d '{}'
{"error":"location and tour_type are required"}     ← 400, route exists

$ curl -s http://localhost:5002/status/test
{"error":"Job not found"}                           ← 404 JSON, route exists

$ curl -s -X DELETE http://localhost:5002/delete-account/test
{"deleted":true,"rows_removed":0}                   ← 200, route exists
```

### Container file listing — orchestrator missing route modules

```
$ docker exec audioura-tour-orchestrator-1 find /app -name "*.py" -type f
/app/cost_rates.py
/app/cost_meter.py
/app/cost_ceiling_monitor.py
/app/entitlements.py
/app/tour_orchestrator_service.py
```

`swipe_preference_service.py` and `wallet_api.py` do not exist in the running container.
The source in `storied` has both files and calls `register_preference_routes(app)` +
`app.register_blueprint(wallet_bp)`, but the image was built before those were added.

### Verbatim curl evidence — Port 5017 (no container)

```
$ curl -s -o /dev/null -w "%{http_code}" http://localhost:5017/newsletters_v2
000                                                  ← connection refused
```

### 12 Total Would-404 Routes

1. `POST /user/<id>/stop-feedback` (5002) — swipe preferences
2. `GET /wallet/<id>` (5002) — wallet balance
3. `GET /wallet/<id>/transactions` (5002) — transaction history
4. `GET /plans/available` (5002) — plan selection
5. `POST /wallet/<id>/topup` (5002) — top-up purchase
6. `GET /newsletters_v2` (5017) — newsletter list
7. `POST /process_newsletter` (5017) — newsletter processing
8. `POST /get_articles_by_newsletter_id` (5017) — newsletter articles
9. `POST /submit_credentials` (5017) — subscription credentials
10. `POST /key_exchange` (5017) — subscription key exchange
11. All routes on port 5022 — tour editing
12. All routes on port 5023 — custom audio

### Blockers per group

| Feature | Blocker | Resolution |
|---------|---------|------------|
| Swipe | Route on `subscribed`, LEAD added to `storied` but image not rebuilt | Rebuild orchestrator from `storied` (Docker build) |
| Wallet/Plans | `wallet_api.py` only on `subscribed`, D24 keeps shared on `storied` | Merge `subscribed` → `storied` + rebuild (Michael's call) |
| Newsletter | No container ever deployed on port 5017 | Docker build + compose entry |
| Tour Editing | No container ever deployed on port 5022 | Docker build |
| Custom Audio | No container ever deployed on port 5023 | Docker build |

---

## Constraints Verified

- `git diff --stat` shows only `APP_PORT_MAP.md` and this submission
- `audio_tours` row count: 88 before, 88 after
- Zero code changes
- No Docker builds attempted
- No containers touched

---

## Limitations

1. **Cannot prove what routes the rebuilt orchestrator will have** — the claim that LEAD added stop-feedback to `storied` is taken from the task description; the running image has not been verified against current `storied` source (would require a Docker build).
2. **Newsletter, tour editing, custom audio** — no source inspection done for what routes these services expose, because no container exists to curl against. The app calls them, and they will connection-refuse.
3. **WalletService has a `_useMock()` gate** — in practice, if mock mode is enabled, wallet routes never hit the network. The 404 only matters when mock is disabled.
4. **`mapDelivery` /download-tour returns Flask 404 for non-numeric IDs** — the route only matches `<int:id>`. App always sends numeric IDs so this is not a production issue.
5. **`voice` /parse_voice_search returns 400 with test input** — route is registered but the exact parameter name the container expects was not determined. Route is confirmed live (not a Flask 404).
