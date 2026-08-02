##### READY FOR REVIEW

## LOCAL-145 — Restore Tour Editing Service

### Commit
See `git log --oneline storied..HEAD` for hash after push.

### Summary
The app's edit screens call `Service.tourEditing` on port 5022 (`endpoints.dart:30`).
The backend service `tour_editing_phase2.py` was absent from `docker-compose-master.yml`
(the active stack). Started it from the existing `audioura-tour-generator:latest` image
which already contains the file.

### What was done

1. **Identified the target service**: The app points at port 5022 → `tour_editing_phase2.py`.
   The old `docker-compose.yml` defined both `tour-editing` (5020, `tour_editing_simple.py`)
   and `tour-editing-phase2` (5022, `tour_editing_phase2.py`). Only the phase2 service
   is needed for the app.

2. **Confirmed the image contains the code**:
   ```
   docker run --rm --entrypoint ls audioura-tour-generator:latest \
     /app/tour_editing_phase2.py /app/tour_editing_simple.py /app/tour_editing_service.py
   ```
   All three present.

3. **Started the service** via `docker run` (not compose `up`, which risked recreating
   the running stack since it's managed from a different worktree path):
   ```
   docker run -d \
     --name tour-editing-phase2-1 \
     --network development_default \
     -p 5022:5022 \
     -v /Users/micha/Audioura/tours:/app/tours \
     -e DB_HOST=postgres-2 \
     -e DB_NAME=audiotours \
     -e DB_USER=admin \
     -e DB_PASSWORD=password123 \
     -e DB_PORT=5432 \
     -e AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID} \
     -e AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY} \
     -e AWS_DEFAULT_REGION=us-east-1 \
     -e POLLY_TTS_URL=http://polly-tts-1:5018 \
     --restart unless-stopped \
     audioura-tour-generator:latest \
     sh -c "pip install boto3 --quiet && python tour_editing_phase2.py"
   ```

4. **Added compose entry** to `docker-compose-master.yml` for reproducibility,
   using `image:` not `build:`.

### About `tour-editing` (port 5020)
Not started. The app does not reference port 5020. `tour_editing_simple.py` is a
bare `http.server`-based service with a much smaller API surface — it was the
prototype before phase2 replaced it. The app's `endpoints.dart` only maps
`Service.tourEditing: 5022`.

### Rollback command
```bash
docker stop tour-editing-phase2-1 && docker rm tour-editing-phase2-1
```

### Evidence

#### Health endpoint (not 404):
```
$ curl -s http://localhost:5022/health
{"service":"tour_editing_phase2","status":"healthy","version":"1.2.6.234"}
```

#### App route — GET /tour/<id>/edit-info (200, real data):
```
$ curl -s http://localhost:5022/tour/palais_lascaris_nice_france_museum_4988cdcc/edit-info | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(f'status=200, stops={len(d[\"stops\"])}, tour_id={d[\"tour_id\"]}')"
status=200, stops=5, tour_id=palais_lascaris_nice_france_museum_4988cdcc
```

#### App route — POST /tour/<id>/bulk-save (validation error, not 404):
```
$ curl -s -X POST http://localhost:5022/tour/palais_lascaris_nice_france_museum_4988cdcc/bulk-save \
  -H "Content-Type: application/json" -d '{"stops": []}'
{"error_code":"VALIDATION_FAILED","message":"Tour stops data is required for saving","recoverable":true,"status":"error","suggested_action":"Please ensure tour has at least one stop and try again"}
```

#### Container uptimes — no existing containers recreated:
BEFORE (pre-change):
```
audioura-coordinates-fromai-1             Up 42 hours (healthy)
audioura-map-delivery-1                   Up 43 hours (unhealthy)
audioura-polly-tts-1-1                    Up 44 hours
audioura-tour-generation-modernized-1-1   Up 42 hours
audioura-tour-generator-1                 Up 35 hours (unhealthy)
audioura-tour-id-resolution-1             Up 2 days
audioura-tour-orchestrator-1              Up 42 hours
audioura-tour-processor-1                 Up 44 hours (unhealthy)
audioura-tour-update-1                    Up 4 days
audioura-translation-service-1            Up 2 days
audioura-treats-1                         Up 4 days
audioura-user-api-2-1                     Up 42 hours
audioura-voice-control-1                  Up 4 days (unhealthy)
background-article-processor-1            Up 4 days
development-postgres-2-1                  Up 4 days
news-generator-1                          Up 2 days
news-orchestrator-1                       Up 42 hours
news-processor-1                          Up 4 days
newsletter-link-extractor-1               Up 4 days
simple-news-search-1                      Up 4 days
```

AFTER:
```
[All identical uptimes — no change]
tour-editing-phase2-1                     Up 54 seconds  (NEW)
```

#### Row counts (unchanged):
```
audio_tours: 106
stop_metrics: 1011
```

### Per-file changes
| File | Change |
|------|--------|
| `docker-compose-master.yml` | Added `tour-editing-phase2` service definition (image-based, no build) |
| `SUBMISSION_LOCAL-145.md` | This file |

### Limitations

1. **boto3 installed at startup**: The `audioura-tour-generator:latest` image lacks
   `boto3`. The command installs it on each container start (`pip install boto3 --quiet`).
   This adds ~15s to cold-start but avoids needing a Docker build. A proper fix is to
   add `boto3` to the image's requirements and rebuild (blocked by hung builder).

2. **AWS credentials**: Language detection (Comprehend) and TTS (Polly) require valid
   AWS credentials passed via environment. If `$AWS_ACCESS_KEY_ID` is not set in the
   shell that started the container, those features will fail at runtime (the service
   still starts, but `/tour/<id>/bulk-save` with text changes will error on language
   detection).

3. **`tour-editing` (5020) not started**: Only the phase2 service was needed. If future
   work needs the simple editing service, it can be started similarly.
