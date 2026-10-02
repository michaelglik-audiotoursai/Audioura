# APP_PORT_MAP.md — Client Port Map vs Running Services

**Date:** 2026-08-02  
**Branch:** `kiro/local125-app-port-map`  
**Context:** D24 (shared containers stay on `storied`); Docker builds hung.

---

## 1. Port Map: `Endpoints._localPorts` vs Running Containers

| Service enum | Port | Container | Image | Status |
|---|---|---|---|---|
| `orchestrator` | 5002 | audioura-tour-orchestrator-1 | audioura-tour-orchestrator | Up 29h |
| `userDb` | 5003 | audioura-user-api-2-1 | audioura-user-api-2 | Up 29h |
| `mapDelivery` | 5005 | audioura-map-delivery-1 | audioura-map-delivery | Up 29h (unhealthy) |
| `treats` | 5007 | audioura-treats-1 | audioura-treats | Up 3d |
| `voice` | 5008 | audioura-voice-control-1 | audioura-voice-control | Up 3d (unhealthy) |
| `news` | 5012 | news-orchestrator-1 | 0a60127c5ee1 | Up 29h |
| `newsletter` | 5017 | **NONE** | — | **No container** |
| `tourEditing` | 5022 | **NONE** | — | **No container** |
| `customAudio` | 5023 | **NONE** | — | **No container** |
| `tourIdResolution` | 5025 | audioura-tour-id-resolution-1 | audioura-tour-id-resolution | Up 40h |
| `translation` | 5030 | audioura-translation-service-1 | audioura-translation-service | Up 40h |

### Why 5002 is missing routes — container source listing

```
$ docker exec audioura-tour-orchestrator-1 find /app -name "*.py" -type f
/app/cost_rates.py
/app/cost_meter.py
/app/cost_ceiling_monitor.py
/app/entitlements.py
/app/tour_orchestrator_service.py
```

`swipe_preference_service.py` and `wallet_api.py` do **not** exist in the running
container. The `storied` source in this worktree has both files and calls
`register_preference_routes(app)` + `app.register_blueprint(wallet_bp)`, but the
image predates those additions. Per D24, rebuilding is deferred until Michael returns.

### Registered routes in running orchestrator (from Flask url_map)

```
DELETE /delete-account/<secret_id>
GET    /download/<job_id>
POST   /generate-complete-tour
GET    /health
GET    /jobs
GET    /serve/<job_id>
GET    /status/<job_id>
POST   /tour-status
```

No `/user/*/stop-feedback`, no `/wallet/*`, no `/plans/*`.

---

## 2. Route Audit: Every Client-Called Route

### Port 5002 — Orchestrator

| Route | Caller | curl result | Verdict |
|---|---|---|---|
| `POST /generate-complete-tour` | tour_generator_screen.dart | 400 `{"error":"location and tour_type are required"}` | **LIVE** — route exists, rejects empty body correctly |
| `GET /status/<id>` | tour_generator_screen, background_service, background_tour_monitor | 404 `{"error":"Job not found"}` | **LIVE** — route exists, JSON error = app-level "not found" |
| `GET /download/<id>` | tour_generator_screen, background_service, background_tour_monitor | 404 `{"error":"Job not found"}` | **LIVE** — route exists, JSON error = app-level "not found" |
| `POST /tour-status` | tour_status_service.dart | 400 `{"message":"tour_id and status are required"}` | **LIVE** — route exists |
| `DELETE /delete-account/<id>` | about_screen.dart | 200 `{"deleted":true,"rows_removed":0}` | **LIVE** |
| `POST /user/<id>/stop-feedback` | stop_feedback_service.dart | **Flask HTML 404** | **WOULD-404** — route not registered |
| `GET /wallet/<id>` | wallet_service.dart | **Flask HTML 404** | **WOULD-404** — route not registered |
| `GET /wallet/<id>/transactions` | wallet_service.dart | **Flask HTML 404** | **WOULD-404** — route not registered |
| `GET /plans/available` | wallet_service.dart | **Flask HTML 404** | **WOULD-404** — route not registered |
| `POST /wallet/<id>/topup` | wallet_service.dart | **Flask HTML 404** | **WOULD-404** — route not registered |

### Port 5003 — User DB

| Route | Caller | curl result | Verdict |
|---|---|---|---|
| `POST /user` | about_screen.dart | 500 (server error, but route exists) | **LIVE** — route registered |
| `GET /user/<id>` | tour_status_service.dart | 404 `{"error":"User not found"}` | **LIVE** — app-level "not found" |
| `GET /health` | about_screen.dart | 200 | **LIVE** |

### Port 5005 — Map Delivery

| Route | Caller | curl result | Verdict |
|---|---|---|---|
| `GET /tours-near/<lat>/<lng>` | home_screen.dart | 200 | **LIVE** |
| `GET /download-tour/<id>` | home_screen, tour_generator_screen, tour_translation_helper | 200 (binary tour data, numeric ID) | **LIVE** |
| `GET /search-tours?pattern=...&lat=...&lng=...` | home_screen.dart | 200 | **LIVE** |

### Port 5007 — Treats

| Route | Caller | curl result | Verdict |
|---|---|---|---|
| `GET /treats-near/<lat>/<lng>` | treats_screen.dart | 200 | **LIVE** |

### Port 5008 — Voice

| Route | Caller | curl result | Verdict |
|---|---|---|---|
| `POST /process-voice-command` | voice_control_service.dart | 200 | **LIVE** |
| `POST /parse_voice_search` | my_tours_screen.dart | 400 `{"error":"No voice command provided"}` | **LIVE** — route exists, rejects on param validation |

### Port 5012 — News

| Route | Caller | curl result | Verdict |
|---|---|---|---|
| `POST /generate-news` | tour_generator_screen.dart | 400 (route exists, rejects empty body) | **LIVE** |
| `GET /download/<id>` | newsDownloadUrl() | 404 `{"error":"Article not found"}` | **LIVE** — app-level "not found" |
| `GET /status/<id>` | newsStatusUrl() | 404 `{"error":"Article not found"}` | **LIVE** — app-level "not found" |

### Port 5017 — Newsletter (**NO CONTAINER**)

| Route | Caller | curl result | Verdict |
|---|---|---|---|
| `GET /newsletters_v2` | home_screen.dart | **Connection refused** | **WOULD-404** — no service listening |
| `POST /process_newsletter` | home_screen, tour_generator_screen | **Connection refused** | **WOULD-404** — no service listening |
| `POST /get_articles_by_newsletter_id` | home_screen.dart | **Connection refused** | **WOULD-404** — no service listening |
| `POST /submit_credentials` | subscription_service.dart | **Connection refused** | **WOULD-404** — no service listening |
| `POST /key_exchange` | subscription_service.dart | **Connection refused** | **WOULD-404** — no service listening |

### Port 5022 — Tour Editing (**NO CONTAINER**)

| Route | Caller | curl result | Verdict |
|---|---|---|---|
| `base(Service.tourEditing)` | tour_editing_service.dart | **Connection refused** | **WOULD-404** — no service listening |

### Port 5023 — Custom Audio (**NO CONTAINER**)

| Route | Caller | curl result | Verdict |
|---|---|---|---|
| `base(Service.customAudio)` | custom_audio_service.dart | **Connection refused** | **WOULD-404** — no service listening |

### Port 5025 — Tour ID Resolution

| Route | Caller | curl result | Verdict |
|---|---|---|---|
| `GET /tour/<id>/resolve` | home_screen.dart | 200 (returns resolution JSON) | **LIVE** |

### Port 5030 — Translation

| Route | Caller | curl result | Verdict |
|---|---|---|---|
| `POST /translate-with-audio` | translation_service.dart | 200 | **LIVE** |

---

## 3. Summary: Would-404 Routes

| # | Route | Port | Feature affected | Blocker |
|---|---|---|---|---|
| 1 | `POST /user/<id>/stop-feedback` | 5002 | **Swipe preferences** | Route exists on `subscribed` branch only. Needs orchestrator rebuild from current `storied` (which LEAD has merged the registration into). **Blocked on Docker build.** |
| 2 | `GET /wallet/<id>` | 5002 | **Wallet balance display** | `wallet_api.py` only on `subscribed`. Needs orchestrator rebuild from `subscribed` merge → `storied`, then container rebuild. **Blocked on D24 + Docker build.** |
| 3 | `GET /wallet/<id>/transactions` | 5002 | **Transaction history** | Same as #2. |
| 4 | `GET /plans/available` | 5002 | **Plan selection UI** | Same as #2. |
| 5 | `POST /wallet/<id>/topup` | 5002 | **Top-up purchase** | Same as #2. |
| 6 | `GET /newsletters_v2` | 5017 | **Newsletter list** | No container on port 5017. Service never deployed to this Mac. Needs container created and started. **Blocked on Docker build.** |
| 7 | `POST /process_newsletter` | 5017 | **Newsletter processing** | Same as #6. |
| 8 | `POST /get_articles_by_newsletter_id` | 5017 | **Newsletter articles** | Same as #6. |
| 9 | `POST /submit_credentials` | 5017 | **Subscription credentials** | Same as #6. |
| 10 | `POST /key_exchange` | 5017 | **Subscription key exchange** | Same as #6. |
| 11 | all routes | 5022 | **Tour editing** | No container on port 5022. **Blocked on Docker build.** |
| 12 | all routes | 5023 | **Custom audio** | No container on port 5023. **Blocked on Docker build.** |

---

## 4. What Unblocks Each

| Group | Routes | What's needed | Who decides |
|---|---|---|---|
| **Swipe (stop-feedback)** | #1 | LEAD already added route registration to `storied`'s `tour_orchestrator_service.py`. Rebuild orchestrator container from current `storied`. | LEAD (Michael) — Docker build required |
| **Wallet/Plans** | #2–#5 | `wallet_api.py` lives only on `subscribed`. Merge `subscribed` → `storied`, then rebuild orchestrator. D24 explicitly defers this to Michael's return. | LEAD (Michael) — merge + Docker build |
| **Newsletter** | #6–#10 | Newsletter service never had a container deployed to port 5017 on this Mac. Needs a compose entry or standalone container. | LEAD — Docker build + compose config |
| **Tour Editing** | #11 | Port 5022 never had a container deployed. | LEAD — Docker build |
| **Custom Audio** | #12 | Port 5023 never had a container deployed. | LEAD — Docker build |

---

## 5. What IS Live Today

All core tour features work on the Mac today:

- ✅ Tour generation (`/generate-complete-tour`, `/status`, `/download`)
- ✅ Tour browsing & discovery (`/tours-near`, `/search-tours`, `/download-tour`)
- ✅ Tour ID resolution (`/tour/<id>/resolve`)
- ✅ Voice commands (`/process-voice-command`, `/parse_voice_search`)
- ✅ Treats discovery (`/treats-near`)
- ✅ News generation & download (`/generate-news`, `/download`, `/status`)
- ✅ Translation (`/translate-with-audio`)
- ✅ User DB & health (`/user`, `/health`)
- ✅ Account deletion (`/delete-account`)
- ✅ Tour status updates (`/tour-status`)

**Features waiting on rebuild:**
- ❌ Swipe preferences (1 route, blocked on Docker)
- ❌ Wallet/subscriptions (4 routes, blocked on D24 + Docker)
- ❌ Newsletter (5 routes, no container exists)
- ❌ Tour editing (no container exists)
- ❌ Custom audio (no container exists)
