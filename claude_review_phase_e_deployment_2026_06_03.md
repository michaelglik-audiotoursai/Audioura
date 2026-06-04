# Claude.AI Code Review — Phase E Cloud Run Deployment

**Date:** 2026-06-03  
**Branch:** `services-migration`  
**Commits:** `91ef406` through `deebad3`  
**Scope:** Docker image build, Artifact Registry push, Cloud Run deployment of 4 core services  
**Status:** All 4 services live and healthy on Cloud Run

---

## What was deployed

| Service | Cloud Run URL | Image | Port | Memory/CPU |
|---|---|---|---|---|
| tour-orchestrator | `https://tour-orchestrator-60899077572.us-central1.run.app` | audioura:v3 | 5002 | 512Mi / 1 CPU |
| tour-generator | `https://tour-generator-60899077572.us-central1.run.app` | audioura:v3 | 8080 | 512Mi / 1 CPU |
| tour-modernized | `https://tour-modernized-60899077572.us-central1.run.app` | audioura:v3 | 8080 | 1Gi / 2 CPU |
| map-delivery | `https://map-delivery-60899077572.us-central1.run.app` | audioura:v3 | 5005 | 256Mi / 1 CPU |

All services respond to `/health` with 200.

---

## Code Changes

### 1. `Dockerfile.cloudrun` (new file)

Universal Docker image containing all Python service files. Single image, multiple CMD args per Cloud Run service:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc curl ffmpeg
RUN pip install --no-cache-dir flask flask-cors requests psycopg2-binary boto3 openai beautifulsoup4 pydub python-dotenv lxml
COPY *.py /app/
RUN mkdir -p /app/tours
EXPOSE 8080
```

Each Cloud Run service uses `--command="python" --args="<service_file.py>"` to select which service runs.

### 2. `.dockerignore` (new file)

Filters out test files, one-off scripts, backups, and non-Python assets to keep the image clean (~50 active .py files included vs ~500 total in the directory).

### 3. `app.run()` PORT fix (11 service files)

All active services changed from:
```python
app.run(host='0.0.0.0', port=5002, debug=True)
```
to:
```python
app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5002')), debug=False)
```

Cloud Run injects `PORT` env var automatically. `debug=True` caused Flask's reloader to delay port binding past Cloud Run's startup timeout.

### 4. `map_delivery_service.py` — R2 read path wired

Added dual-read logic for tour downloads:
```python
# Query now also fetches tour_blob_uri
SELECT tour_name, audio_tour, request_string, tour_blob_uri
FROM audio_tours 
WHERE id = %s AND (audio_tour IS NOT NULL OR tour_blob_uri IS NOT NULL)

# If R2 key available and BLOB_STORAGE_TYPE=r2, read from R2
if tour_blob_uri and _get_blob_storage():
    audio_tour_data = _get_blob_storage().download(tour_blob_uri)
```

Falls back to BYTEA if R2 read fails.

### 5. Recovered missing modules from container

9 Python files that existed in the running Docker container but were never committed to git:
- `api_call_logger.py` — logging utility for API calls
- `coordinate_requirements.py` — coordinate validation rules
- `enhanced_prompt_generator.py` — enhanced AI prompt builder
- `enhanced_tour_templates.py` — tour template definitions
- `poi_inclusion_exceptions.py` — POI filtering rules
- `tour_type_detector.py` — tour type classification helpers
- `debug_openai_request.py`, `debug_phase3c.py`, `debug_step_count_tracer.py` — debug utilities

These were docker-cp'd into the container during development but never committed. Cloud Build (unlike docker-compose) starts from the repo, so these had to be recovered and committed.

---

## Deployment Configuration

### Secret Manager bindings:
- `DB_PASSWORD` → `db-password:latest`
- `OPENAI_API_KEY` → `openai-api-key:latest`
- `AWS_ACCESS_KEY_ID` → `aws-access-key-id:latest`
- `AWS_SECRET_ACCESS_KEY` → `aws-secret-access-key:latest`
- `R2_ACCESS_KEY_ID` → `r2-access-key-id:latest`
- `R2_SECRET_ACCESS_KEY` → `r2-secret-access-key:latest`

### Environment variables:
- `DB_HOST=34.27.121.203` (Cloud SQL public IP)
- `DB_NAME=audiotours`, `DB_USER=admin`, `DB_PORT=5432`
- `TOUR_STORAGE_MODE=cloud` (HTTP content passing, no shared volume)
- `BLOB_STORAGE_TYPE=r2` (read tours from Cloudflare R2)
- `JOB_STORE_MODE=memory` (single instance, pinned max=1)
- `TOUR_GENERATOR_URL` / `MODERNIZED_URL` → Cloud Run URLs of sibling services

### IAM:
- `60899077572-compute@developer.gserviceaccount.com` granted `roles/secretmanager.secretAccessor`

---

## Process Issues Encountered + Fixes

| Issue | Root Cause | Fix |
|---|---|---|
| Secret Manager permission denied | Service account lacked accessor role | `gcloud projects add-iam-policy-binding --role=roles/secretmanager.secretAccessor` |
| tour-generator failed to start | `debug=True` delayed port binding; Cloud Run timed out | Changed to `debug=False` + `PORT` env var |
| tour-generator import error | `COPY *.py` included stale files that broke imports | Created `.dockerignore` to exclude test/utility scripts |
| Still missing modules | 9 .py files existed only in container (docker-cp'd, never committed) | Recovered from container, committed to git |
| `PORT` env var rejected | Cloud Run reserves PORT — can't set it in `--set-env-vars` | Removed from env vars; service reads `os.getenv('PORT')` which Cloud Run sets automatically |

---

## What's NOT yet deployed (remaining Phase E work)

| Service | Why | Priority |
|---|---|---|
| polly-tts | Needed for new tour audio generation | HIGH — deploy next |
| translation-service | Needed for multi-language tours | HIGH |
| news-orchestrator / news-generator / news-processor | Newsletter pipeline | MEDIUM |
| newsletter-processor | Newsletter crawling | MEDIUM |
| treats / coordinates / user-api / tour-editing | Supporting services | LOW (can test without) |

### For mobile app testing off local network:
The mobile app needs two changes:
1. Use HTTPS instead of HTTP
2. Point to the Cloud Run URL (`tour-orchestrator-60899077572.us-central1.run.app`) instead of LAN IP

---

## Questions for Review

1. **Single image for all services** — is this acceptable, or should each service have its own minimal image? The single-image approach is simpler to build/push but larger (~400 MB) and includes dependencies not needed by every service.

2. **The `debug_*.py` files were recovered from the container and committed.** Should they be excluded from the Cloud Run image (they're not runtime dependencies, just debugging tools that happen to be in the same directory)?

3. **Cloud SQL is publicly accessible** (`0.0.0.0/0`). For this initial test deployment it works, but production needs either:
   - (a) VPC connector + private IP (no public exposure)
   - (b) Cloud SQL Auth Proxy sidecar
   - (c) Restricted authorized networks (Cloud Run egress IPs are dynamic, making this impractical)
   
   Recommendation?

4. **The orchestrator has `max-instances=1`** (for the ACTIVE_JOBS in-memory dict reason). Is this acceptable for initial testing, or should we wire the DatabaseJobStore before increasing?

5. **Polly-tts is not yet deployed** — the orchestrator's tour generation will fail at the audio step because the modernized service calls polly-tts (currently pointing to the Docker hostname default). Should I deploy polly-tts next, or is the map-delivery + tour-download path sufficient for initial mobile testing?
