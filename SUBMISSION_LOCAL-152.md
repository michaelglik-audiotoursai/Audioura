##### READY FOR REVIEW

**Task:** LOCAL-152 — Do the Subscribed wallet routes actually answer?  
**Branch:** `kiro/local152-wallet-routes-reachability`  
**Date:** 2026-08-02  
**Method:** LOCAL-150's HTTP reachability test (generic Flask HTML 404 vs structured JSON 404)

---

## Summary

The SUBSCRIBED_STATUS.md note that "five app routes would 404 until a container
rebuild" was correct but tested for the first time here. All five wallet/swipe
routes return **generic Flask HTML 404** on the shared orchestrator (port 5002)
— meaning the routes are not registered in the running image, not just that
resources are absent. The subscribed stack (port 5102) is not running at all.

**The app cannot reach the wallet today.** No code path exists.

---

## Per-route reachability table

| # | Route | Stack | Port | Listening? | Response | Body type | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | `GET /wallet/<id>` | shared | 5002 | ✅ | 404 | Generic Flask HTML (`<!DOCTYPE HTML ...>`) | **NOT REGISTERED** |
| 2 | `GET /wallet/<id>/transactions` | shared | 5002 | ✅ | 404 | Generic Flask HTML | **NOT REGISTERED** |
| 3 | `GET /plans/available` | shared | 5002 | ✅ | 404 | Generic Flask HTML | **NOT REGISTERED** |
| 4 | `POST /wallet/<id>/topup` | shared | 5002 | ✅ | 404 | Generic Flask HTML | **NOT REGISTERED** |
| 5 | `POST /user/<id>/stop-feedback` | shared | 5002 | ✅ | 404 | Generic Flask HTML | **NOT REGISTERED** |
| 6 | `GET /wallet/<id>` | subscribed | 5102 | ❌ | — | Connection refused | **NOT RUNNING** |
| 7 | `GET /wallet/<id>/transactions` | subscribed | 5102 | ❌ | — | Connection refused | **NOT RUNNING** |
| 8 | `GET /plans/available` | subscribed | 5102 | ❌ | — | Connection refused | **NOT RUNNING** |
| 9 | `POST /wallet/<id>/topup` | subscribed | 5102 | ❌ | — | Connection refused | **NOT RUNNING** |
| 10 | `POST /user/<id>/stop-feedback` | subscribed | 5102 | ❌ | — | Connection refused | **NOT RUNNING** |

---

## Can the app reach the wallet today?

**No.** The app hardcodes `Service.orchestrator` → port 5002. Port 5002 does
not have the wallet Blueprint registered. Port 5102 (subscribed stack) has
no running container. There is no reachable wallet endpoint from the app.

---

## POST /topup — UNVERIFIED

**Reason:** The route does not exist on either stack (confirmed via Flask
`url_map` inspection and HTTP 404). There is nothing to call. Even if it
existed, any body with a valid `product_id` string would succeed and credit
a wallet — no "malformed body" test is possible that wouldn't move money on
a registered route. The route's absence from `url_map` is itself definitive
proof it is not registered; no HTTP exercise was needed beyond the 404.

---

## Wallet balances unchanged

```
wallet_ledger row count BEFORE: 163
wallet_ledger row count AFTER:  163
```

No rows created, modified, or deleted. All HTTP calls either 404'd at the
Flask routing layer (before reaching any application code) or failed at TCP
connection (port 5102 not listening).

---

## Docker state unchanged

Container list identical before and after (21 containers, none started/stopped):

```
audioura-coordinates-fromai-1
audioura-map-delivery-1
audioura-polly-tts-1-1
audioura-tour-generation-modernized-1-1
audioura-tour-generator-1
audioura-tour-id-resolution-1
audioura-tour-orchestrator-1
audioura-tour-processor-1
audioura-tour-update-1
audioura-translation-service-1
audioura-treats-1
audioura-user-api-2-1
audioura-voice-control-1
background-article-processor-1
development-postgres-2-1
news-generator-1
news-orchestrator-1
news-processor-1
newsletter-link-extractor-1
simple-news-search-1
tour-editing-phase2-1
```

---

## Verbatim evidence

### Shared orchestrator health (proves connectivity):
```
$ curl http://localhost:5002/health
{"cost_ceiling":{"hard_limit_aborts":0,"last_abort_cost":null,"last_abort_job_id":null,"target_warnings":0},"service":"tour_orchestrator","status":"healthy"}
```

### Wallet route (generic Flask 404):
```
$ curl http://localhost:5002/wallet/test-user-999
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">
<title>404 Not Found</title>
<h1>Not Found</h1>
<p>The requested URL was not found on the server. If you entered the URL manually please check your spelling and try again.</p>
```

### Plans route (generic Flask 404):
```
$ curl http://localhost:5002/plans/available
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">
<title>404 Not Found</title>
<h1>Not Found</h1>
<p>The requested URL was not found on the server. ...</p>
```

### Topup route (generic Flask 404):
```
$ curl -X POST http://localhost:5002/wallet/test-user-999/topup -H "Content-Type: application/json" -d '{}'
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">
<title>404 Not Found</title>
...
```

### Subscribed stack (connection refused):
```
$ curl http://localhost:5102/health
curl: (7) Failed to connect to localhost port 5102: Connection refused
```

### Flask url_map (container inspection):
```
$ docker exec audioura-tour-orchestrator-1 python3 -c "..."
DELETE /delete-account/<secret_id>
GET    /download/<job_id>
POST   /generate-complete-tour
GET    /health
GET    /jobs
GET    /serve/<job_id>
GET    /status/<job_id>
POST   /tour-status
```

### Files in running container:
```
$ docker exec audioura-tour-orchestrator-1 find /app -name "*.py" -type f
/app/cost_ceiling_monitor.py
/app/cost_meter.py
/app/cost_rates.py
/app/entitlements.py
/app/tour_orchestrator_service.py
```

No `wallet_api.py`, `wallet_ledger.py`, `pricing.py`, `swipe_preference_service.py`.

---

## Per-file changes

| File | Change |
|---|---|
| `SUBSCRIBED_STATUS.md` | Replaced inferred "Port map mismatch" section with tested per-route evidence; updated §7 Known Gap from inference to measured fact |
| `SUBMISSION_LOCAL-152.md` | Created (this file) |

---

## Limitations

1. **POST /topup not functionally exercised.** Route doesn't exist on either
   stack — cannot test application-level 400 rejection since Flask rejects at
   the routing layer. Marked UNVERIFIED.

2. **Subscribed stack could not be tested for route behavior.** The containers
   are down (connection refused). We can only confirm absence, not what they
   would serve if rebuilt and started.

3. **No Docker builds performed.** Per constraints. The only way to make the
   wallet reachable from the app is to rebuild a container, which is blocked
   by D24 and the hung Docker builder.

4. **APP_FEATURE_REACHABILITY.md does not exist in this worktree.** The method
   was applied from the task description (distinguish generic Flask HTML 404
   from structured JSON 404).

5. **D35 does not exist in DECISIONS.md.** Latest decision is D31. Referenced
   in the task but not present — may be on another branch.
