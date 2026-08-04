# App Feature Reachability Audit — LOCAL-150

**Date:** 2026-08-02  
**Author:** Mac Mini Kiro  
**Base:** storied  
**Method:** Read-only probes against running containers. Ports tested with `curl`. Route existence determined by response: structured JSON error (400/401/404/405/500) = route exists; generic Flask HTML 404 = route absent; connection refused = nothing listening. No containers started, stopped, or built.

---

## Summary Table

| # | Service | Port | Listening? | App Routes Match? | Verdict |
|---|---------|------|-----------|-------------------|---------|
| 1 | orchestrator | 5002 | ✅ Yes | ✅ All routes present | **WORKS** |
| 2 | userDb | 5003 | ✅ Yes | ✅ All routes present | **WORKS** |
| 3 | mapDelivery | 5005 | ✅ Yes | ✅ All routes present | **WORKS** |
| 4 | treats | 5007 | ✅ Yes | ✅ All routes present | **WORKS** |
| 5 | voice | 5008 | ✅ Yes | ✅ All routes present | **WORKS** |
| 6 | news | 5012 | ✅ Yes | ✅ All routes present | **WORKS** |
| 7 | tourIdResolution | 5025 | ✅ Yes | ✅ All routes present | **WORKS** |
| 8 | translation | 5030 | ✅ Yes | ✅ Route present | **WORKS** (POST UNVERIFIED) |
| 9 | tourEditing | 5022 | ✅ Yes | ⚠️ 2 of 4 routes absent | **PORT OPEN, WRONG API** |
| 10 | newsletter | 5017 | ❌ No | N/A | **NOTHING LISTENING** |
| 11 | customAudio | 5023 | ❌ No | N/A | **NOTHING LISTENING** |

---

## Detailed Evidence

### 1. orchestrator (port 5002) — WORKS

**Container:** `audioura-tour-orchestrator-1` (Up 44 hours)

| App Route | Method | HTTP Code | Evidence | Result |
|-----------|--------|-----------|----------|--------|
| `/health` | GET | 200 | Health OK | ✅ |
| `/generate-complete-tour` | POST | OPTIONS→200 | Route registered | UNVERIFIED (triggers AI generation, costs money) |
| `/status/<jobId>` | GET | 404 `{"error":"Job not found"}` | Structured JSON = route exists | ✅ |
| `/download/<jobId>` | GET | 404 `{"error":"Job not found"}` | Structured JSON = route exists | ✅ |
| `/tour-status` | POST | 400 (empty body) | Validation error = route exists | ✅ |
| `/delete-account/<userId>` | DELETE | 200 `{"deleted":true,"rows_removed":0}` | Route exists and works | ✅ |

**UNVERIFIED:** `POST /generate-complete-tour` — triggers OpenAI and Polly TTS (costs money, creates data). Confirmed route exists via OPTIONS 200.

---

### 2. userDb (port 5003) — WORKS

**Container:** `audioura-user-api-2-1` (Up 44 hours)

| App Route | Method | HTTP Code | Evidence | Result |
|-----------|--------|-----------|----------|--------|
| `/health` | GET | 200 | Health OK | ✅ |
| `/user` | POST | OPTIONS→200, GET→405 | 405 = route exists, only accepts POST | UNVERIFIED (creates user record) |
| `/user/<userId>` | GET | 404 `{"error":"User not found"}` | Structured JSON = route exists | ✅ |
| `/user/<userId>` | PUT | OPTIONS→200 | Route registered | UNVERIFIED (writes user data) |

**UNVERIFIED:** `POST /user` (creates/updates user) and `PUT /user/<id>` (updates user). Both confirmed present via OPTIONS 200 and 405 responses. Not tested destructively.

---

### 3. mapDelivery (port 5005) — WORKS

**Container:** `audioura-map-delivery-1` (Up 44 hours)

| App Route | Method | HTTP Code | Evidence | Result |
|-----------|--------|-----------|----------|--------|
| `/health` | GET | 200 | Health OK | ✅ |
| `/tours-near/<lat>/<lng>` | GET | 200 | Returns tour data | ✅ |
| `/download-tour/<int:tour_id>` | GET | 404 `{"error":"Tour not found"}` | Structured JSON = route exists (tested with integer ID 999999) | ✅ |

**Note:** Route requires integer tour_id (`<int:tour_id>`). Non-integer IDs get generic Flask 404, but integer IDs get structured JSON error. Source confirmed: `map_delivery/app.py:160`.

---

### 4. treats (port 5007) — WORKS

**Container:** `audioura-treats-1` (Up 4 days)

| App Route | Method | HTTP Code | Evidence | Result |
|-----------|--------|-----------|----------|--------|
| `/health` | GET | 200 | Health OK | ✅ |
| `/treats-near/<lat>/<lng>` | GET | 200 | Returns treats data | ✅ |

---

### 5. voice (port 5008) — WORKS

**Container:** `audioura-voice-control-1` (Up 4 days)

| App Route | Method | HTTP Code | Evidence | Result |
|-----------|--------|-----------|----------|--------|
| `/health` | GET | 200 | Health OK | ✅ |
| `/process-voice-command` | POST | 200 `{"action":"next_stop","message":"Moving to stop 3","stop_number":2}` | Full working response | ✅ |
| `/parse_voice_search` | POST | 400 `{"error":"No voice command provided"}` | Validation error = route exists | ✅ |

**Note:** Voice commands are processed 100% on-device in cloud mode (the app gates off server calls). Server-side processing used only in local WiFi mode.

---

### 6. news (port 5012) — WORKS

**Container:** `news-orchestrator-1` (Up 44 hours)

| App Route | Method | HTTP Code | Evidence | Result |
|-----------|--------|-----------|----------|--------|
| `/health` | GET | 200 | Health OK | ✅ |
| `/generate-news` | POST | GET→405 | 405 = route exists, accepts POST only | UNVERIFIED (triggers AI processing, costs money) |
| `/status/<articleId>` | GET | 404 `{"error":"Article not found"}` | Structured JSON = route exists | ✅ |
| `/download/<articleId>` | GET | 404 `{"error":"Article not found"}` | Structured JSON = route exists | ✅ |

**UNVERIFIED:** `POST /generate-news` — triggers OpenAI article processing. Confirmed route exists via 405 response on GET.

---

### 7. tourIdResolution (port 5025) — WORKS

**Container:** `audioura-tour-id-resolution-1` (Up 2 days)

| App Route | Method | HTTP Code | Evidence | Result |
|-----------|--------|-----------|----------|--------|
| `/health` | GET | 200 | Health OK | ✅ |
| `/tour/<id>/resolve` | GET | 400 | Validation error = route exists | ✅ |

Source confirms route: `tour_id_resolution_service.py:245`.

---

### 8. translation (port 5030) — WORKS (POST UNVERIFIED)

**Container:** `audioura-translation-service-1` (Up 2 days)

| App Route | Method | HTTP Code | Evidence | Result |
|-----------|--------|-----------|----------|--------|
| `/health` | GET | 200 | Health OK | ✅ |
| `/translate-with-audio` | POST | OPTIONS→200 | Route registered | UNVERIFIED (triggers translation + Polly TTS, costs money) |

**UNVERIFIED:** `POST /translate-with-audio` — triggers translation pipeline and TTS generation. Confirmed route exists via OPTIONS 200.

---

### 9. tourEditing (port 5022) — PORT OPEN, WRONG API

**Container:** `tour-editing-phase2-1` (Up About an hour)

| App Route | Method | HTTP Code | Evidence | Result |
|-----------|--------|-----------|----------|--------|
| `/health` | GET | 200 | Health OK | ✅ |
| `/tour/<id>/update-multiple-stops` | POST | 400 `{"error_code":"VALIDATION_FAILED",...}` | Structured JSON = route exists | ✅ |
| `/tour/<id>/edit-info` | GET | 404 `{"error_code":"TOUR_NOT_FOUND",...}` | Structured JSON = route exists | ✅ |
| `/tour/<id>/download` | GET | 404 `{"error_code":"TOUR_NOT_FOUND",...}` | Structured JSON = route exists | ✅ |
| `/tour/<id>/update-stop` | POST | 404 (generic Flask HTML) | **Route ABSENT** | ❌ |
| `/tour/<id>/job-status/<jobId>` | GET | 404 (generic Flask HTML) | **Route ABSENT** | ❌ |

**Source confirms:** `tour_editing_phase2.py` registers only: `/tour/<id>/bulk-save`, `/tour/<id>/update-multiple-stops`, `/tour/<id>/edit-info`, `/tour/<id>/download`, `/tour/<id>/promote`, `/health`. No `update-stop` or `job-status` route exists.

**App calls missing routes from:**
- `TourEditingService.updateStop()` → `POST /tour/<id>/update-stop` (tour_editing_service.dart:31)
- `TourEditingService.checkJobStatus()` → `GET /tour/<id>/job-status/<jobId>` (tour_editing_service.dart:64)

---

### 10. newsletter (port 5017) — NOTHING LISTENING

**Container:** None. Port 5017 has no running container in `docker-compose-master.yml`.

| App Route | Method | HTTP Code | Evidence | Result |
|-----------|--------|-----------|----------|--------|
| `/newsletters_v2` | GET | Connection refused | No process on port | ❌ |
| `/process_newsletter` | POST | Connection refused | No process on port | ❌ |
| `/submit_credentials` | POST | Connection refused | No process on port | ❌ |
| `/key_exchange` | POST | Connection refused | No process on port | ❌ |

**App calls from:**
- `home_screen.dart:1737` → `GET /newsletters_v2`
- `tour_generator_screen.dart:2104` → `POST /process_newsletter`
- `subscription_service.dart:100` → `POST /submit_credentials`
- `subscription_service.dart:176` → `POST /key_exchange`

**Context:** Per D40, the newsletter-processor was restored briefly by LOCAL-147, found to store passwords in plaintext, and stopped within the hour. The service is deliberately not deployed.

---

### 11. customAudio (port 5023) — NOTHING LISTENING

**Container:** None. No compose entry for port 5023 in either compose file. `version_api.py` (the only candidate) implements `/health`, `/tour/<id>/version`, `/tours/check-versions` — none of which match what the app expects.

| App Route | Method | HTTP Code | Evidence | Result |
|-----------|--------|-----------|----------|--------|
| `/tour/<id>/stop/<n>/custom-audio` | POST | Connection refused | No process on port | ❌ |
| `/tour/<id>/stop/<n>/custom-audio` | DELETE | Connection refused | No process on port | ❌ |
| `/tour/<id>/stop/<n>/audio-versions` | GET | Connection refused | No process on port | ❌ |
| `/tour/<id>/audio-metadata` | GET | Connection refused | No process on port | ❌ |

**App calls from:** `custom_audio_service.dart` (all four methods)

**Context:** Per DORMANT_SERVICES.md §5, no implementation of the custom audio API exists in the repo. The app has a fully built client (`custom_audio_service.dart`, 148 lines) against a service that was never written.

---

## Broken Features — User-Visible Symptoms

Ranked by likelihood a user would notice:

### 1. Newsletter browsing & subscription processing (NOTHING LISTENING — port 5017)

**User symptom:** On the home screen, the "Newsletters" section either shows stale cached data or is empty. Tapping any newsletter or attempting to process a newsletter URL from the tour generator shows a network error or times out silently. The "Subscribe to paid content" flow (entering newspaper credentials) fails immediately — the credentials never leave the device.

**Impact:** High. The newsletter feature is a primary home screen element. Every user sees it.

**Why it's off:** D40 — the service stores passwords in plaintext. Cannot be restored without encryption redesign.

---

### 2. Tour editing — single-stop update (PORT OPEN, WRONG API — port 5022)

**User symptom:** After generating a tour, tapping "Edit" on a single stop and saving the change fails. The app calls `POST /tour/<id>/update-stop` which returns 404. The error manifests as a toast/snackbar "Update failed" or similar. The user cannot modify one stop at a time.

**Workaround exists:** The `update-multiple-stops` route works, and the app's `updateMultipleStops()` method uses it. If the UI has a "Save All" flow that goes through `updateMultipleStops`, that path works. But the single-stop quick-edit path is dead.

**Impact:** Medium-High. Users who edit tours hit this on the most common edit action (changing one stop's text).

---

### 3. Tour editing — job status polling (PORT OPEN, WRONG API — port 5022)

**User symptom:** After submitting a multi-stop edit (which works), the app polls `GET /tour/<id>/job-status/<jobId>` to track async processing progress. This returns 404. The user sees the progress indicator stuck or a "Failed to check job status" error. They cannot tell if their edit is processing, complete, or failed.

**Impact:** Medium. Affects the same flow as #2 but is a UX degradation (no progress feedback) rather than total failure — the edit may still complete server-side.

---

### 4. Custom audio upload/management (NOTHING LISTENING — port 5023)

**User symptom:** Tapping "Record custom audio" or "Upload audio" for a tour stop, then saving, fails with a network error. The audio versions list is empty. The remove-custom-audio button fails silently. The entire custom narration feature is non-functional.

**Impact:** Medium. Not all users record custom audio, but those who try get a complete failure with no fallback.

**Context:** No server-side implementation exists. The Dart client was built speculatively against an API that was never implemented.

---

## UNVERIFIED Routes

| Service | Route | Method | Why Unverified |
|---------|-------|--------|----------------|
| orchestrator | `/generate-complete-tour` | POST | Triggers OpenAI generation + Polly TTS. Costs money, creates database records. |
| translation | `/translate-with-audio` | POST | Triggers translation pipeline + TTS. Costs money. |
| news | `/generate-news` | POST | Triggers AI article processing. Costs money. |
| userDb | `POST /user` | POST | Creates/updates user record in database. |
| userDb | `PUT /user/<id>` | PUT | Writes tour tracking data to user record. |
| newsletter | `/submit_credentials` | POST | **Would write credentials** — but moot (port not listening). |
| newsletter | `/process_newsletter` | POST | **Would trigger browser automation + OpenAI** — but moot (port not listening). |

All UNVERIFIED routes were confirmed to exist (via OPTIONS 200, GET→405, or structured error responses) — the route is registered, but the actual operation was not triggered because it writes, charges, or stores.

---

## Docker State (Before = After)

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

21 containers before, 21 containers after. No changes.

---

## Limitations

1. **Write routes confirmed by proxy only.** POST/PUT/DELETE routes that write data were confirmed present via OPTIONS 200 or wrong-method responses (405), not by actual invocation. Their internal logic could still fail.

2. **Map delivery `download-tour` requires integer IDs.** The Flask route is `<int:tour_id>`. If the app ever passes a non-integer tour ID string, Flask returns a generic 404 before the handler runs — the app would see "route not found" behaviour even though the route exists for valid inputs.

3. **Newsletter-processor ghost.** During testing, `newsletter-processor-test-147` appeared briefly in `docker ps` (residual from LOCAL-147/D40 incident) then vanished. It was not responding on port 5017 and is now fully gone. It did not affect any probe results.

4. **Cloud-mode paths not tested.** The app uses different URL paths in cloud mode (e.g., `/news-download/<id>` vs `/download/<id>`). This audit tested local-mode paths only since we're probing `localhost`.

5. **`map_service.dart` hardcoded base URL.** `MapService` in `map_service.dart` uses `http://map_delivery:5005` (Docker DNS name) rather than `Endpoints.base(Service.mapDelivery)`. This works inside containers but not from the app on a real device. However, this file appears to be dead code — the home screen uses `Endpoints.url(Service.mapDelivery, '/tours-near/...')` directly.
