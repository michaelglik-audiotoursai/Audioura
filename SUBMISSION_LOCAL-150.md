##### READY FOR REVIEW

## LOCAL-150 Submission

**Commit:** c5de376  
**Branch:** kiro/local150-app-feature-reachability  
**Commits ahead of storied:** 1

---

## Per-File Changes

| File | Action | Lines |
|------|--------|-------|
| `APP_FEATURE_REACHABILITY.md` | Created | +299 |

---

## Verbatim Evidence

### Method
All 11 services in `endpoints.dart` were probed via HTTP on localhost. The 404-vs-4xx distinction was applied throughout:
- **Structured JSON error** (e.g., `{"error":"Job not found"}`, `{"error_code":"VALIDATION_FAILED",...}`) → route exists, resource missing or validation failed
- **Generic Flask HTML 404** (`<title>404 Not Found</title>`) → route ABSENT from the service
- **Connection refused** (curl exit 7, HTTP 000) → nothing listening on port
- **405 Method Not Allowed** → route exists, tested with wrong HTTP method
- **OPTIONS 200** → route registered (for write routes we couldn't exercise)

### Key Probes

```
# Treats (5007) - WORKS
GET /treats-near/42.3601/-71.0589 → 200

# Orchestrator (5002) - WORKS
GET /status/test123 → 404 {"error":"Job not found"}       (route exists)
GET /download/test123 → 404 {"error":"Job not found"}     (route exists)
POST /tour-status {} → 400                                (validation = exists)
DELETE /delete-account/testuser123 → 200                   (works)

# News (5012) - WORKS
GET /status/testnews123 → 404 {"error":"Article not found"} (route exists)
GET /download/testnews123 → 404 {"error":"Article not found"} (route exists)
GET /generate-news → 405                                    (POST only = exists)

# Voice (5008) - WORKS
POST /process-voice-command → 200 {"action":"next_stop",...}
POST /parse_voice_search → 400 {"error":"No voice command provided"}

# Map Delivery (5005) - WORKS
GET /tours-near/42.36/-71.06?radius=50 → 200
GET /download-tour/999999 → 404 {"error":"Tour not found"} (route exists)

# UserDb (5003) - WORKS
GET /user → 405 (POST only = exists)
GET /user/testuser123 → 404 {"error":"User not found"} (route exists)
OPTIONS /user/test123 → 200 (PUT route registered)

# Tour ID Resolution (5025) - WORKS
GET /tour/test123/resolve → 400 (validation = route exists)

# Translation (5030) - WORKS
OPTIONS /translate-with-audio → 200 (route registered)

# Tour Editing (5022) - PORT OPEN, WRONG API
POST /tour/test123/update-multiple-stops {} → 400 {"error_code":"VALIDATION_FAILED"} (EXISTS)
GET /tour/test123/edit-info → 404 {"error_code":"TOUR_NOT_FOUND"}              (EXISTS)
GET /tour/test123/download → 404 {"error_code":"TOUR_NOT_FOUND"}               (EXISTS)
POST /tour/test123/update-stop {} → 404 <title>404 Not Found</title>           (ABSENT)
GET /tour/test123/job-status/job456 → 404 <title>404 Not Found</title>         (ABSENT)

# Newsletter (5017) - NOTHING LISTENING
GET /health → connection refused (curl exit 7)
GET /newsletters_v2 → connection refused

# Custom Audio (5023) - NOTHING LISTENING
GET /health → connection refused (curl exit 7)
```

### Docker State Unchanged
```
$ docker ps --format "{{.Names}}" | sort | wc -l
21   (before)
21   (after — identical list)
```

---

## Summary of Findings

| Verdict | Count | Services |
|---------|-------|----------|
| WORKS | 8 | orchestrator, userDb, mapDelivery, treats, voice, news, tourIdResolution, translation |
| PORT OPEN, WRONG API | 1 | tourEditing (2 of 4 app routes absent: `update-stop`, `job-status`) |
| NOTHING LISTENING | 2 | newsletter (5017), customAudio (5023) |

### Broken features ranked by user visibility:
1. **Newsletter browsing & credential submission** — home screen element, every user sees it
2. **Tour editing single-stop update** — most common edit action fails
3. **Tour editing job-status polling** — no progress feedback on async edits
4. **Custom audio upload/management** — entire custom narration feature dead

---

## Limitations

1. Write/cost routes (generate-complete-tour, translate-with-audio, generate-news, POST /user, PUT /user/<id>) confirmed present via OPTIONS/405 but not exercised. Internal logic could still fail at runtime.
2. Cloud-mode URL paths not tested (local-mode only since probing localhost).
3. `map_service.dart` uses hardcoded Docker DNS (`http://map_delivery:5005`) not `Endpoints.base()` — appears to be dead code (home_screen.dart uses Endpoints directly).
4. Map delivery's `/download-tour/<int:tour_id>` rejects non-integer IDs at the Flask routing layer (generic 404). App must pass integers.
5. A ghost container `newsletter-processor-test-147` appeared briefly during probing (D40 residual) then vanished. Did not affect results — port 5017 never responded.
