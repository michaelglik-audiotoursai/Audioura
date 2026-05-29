# M02 — Phase B Design: Cloud-Ready Refactoring

**Date:** 2026-05-28  
**Author:** Kiro (services-migration branch)  
**Purpose:** Design document for Claude.AI review before implementation begins  
**Status:** DRAFT — awaiting Claude review

---

## 1. Problem Statement

The Audioura backend has 21 services that need to run on Google Cloud Run (stateless containers). Three issues block this:

1. **Shared volume (`/app/tours/`)** — 7 services share a Docker volume for intermediate file passing during tour generation. Cloud Run containers are stateless with no shared filesystem.
2. **Hardcoded inter-service URLs** — Services call each other using Docker container names (e.g., `http://development-tour-generator-1:5000/generate`). Cloud Run services have dynamic URLs.
3. **Large blobs in PostgreSQL** — 2.7 GB of ZIP files stored as BYTEA. This makes the DB expensive and slow to backup/restore.

This document proposes solutions for all three, prioritized by migration-blocking severity.

---

## 2. Current Tour Generation Pipeline (File I/O Flow)

```
Mobile App
  → POST tour_orchestrator:5002/generate-complete-tour
      → POST tour_generator:5000/generate
          → Writes .txt file to /app/tours/
          → Returns filename
      → POST tour_generation_modernized:5021/process {tour_file: "filename.txt"}
          → Reads .txt from /app/tours/
          → Calls polly-tts:5018/synthesize for each stop
          → Writes .zip to /app/tours/
          → Returns job_id
      → GET tour_generation_modernized:5021/download/{job_id}
          → Returns ZIP bytes
      → Orchestrator saves ZIP to /app/tours/ (redundant copy)
      → Orchestrator extracts ZIP to /app/tours/{dir}/ (temporary)
      → Orchestrator reads ZIP bytes → stores in DB as BYTEA
      → Orchestrator cleans up extracted directory
      → Returns tour_id to mobile app

Mobile App
  → GET map_delivery:5005/download-tour/{id}
      → Reads BYTEA from DB → serves as ZIP (NEVER touches volume)
```

### Key Insight

**`map_delivery` (the service that serves tours to end users) already reads exclusively from the database.** It never touches the shared volume. This means the volume is only needed during the *generation* pipeline — not for serving.

---

## 3. Proposed Solution: Eliminate Shared Volume

### Strategy: Pass data via HTTP responses instead of shared filesystem

The shared volume currently acts as a message bus between services. We replace it with direct HTTP data transfer:

#### Current flow (file-based):
```
generator writes .txt to disk → modernized reads .txt from disk
modernized writes .zip to disk → orchestrator downloads .zip via HTTP (already!)
```

#### Proposed flow (HTTP-based):
```
generator returns .txt content in HTTP response → orchestrator passes it to modernized via HTTP POST body
modernized returns .zip in HTTP response → orchestrator receives it directly (already works this way!)
```

### 3.1 Changes Required

**Service: `generate_tour_text_service.py` (port 5000)**

Current behavior:
- Writes `.txt` file to `/app/tours/`
- Returns filename in status response
- Orchestrator never reads this file directly — it passes the filename to modernized service

Proposed change:
- Still write to local `/tmp/` (Cloud Run gives each instance 2 GB writable temp)
- Return the **file content** in the status response (add `tour_content` field)
- Keep the filename-based flow as fallback for local dev compatibility

```python
# Current status response:
{"status": "completed", "output_file": "boston_walking_tour_20240115.txt", "coordinates": [...]}

# New status response (additive, backwards-compatible):
{"status": "completed", "output_file": "boston_walking_tour_20240115.txt", "tour_content": "Stop 1: ...", "coordinates": [...]}
```

**Service: `tour_generation_modernized.py` (port 5021)**

Current behavior:
- Receives `{"tour_file": "filename.txt"}` 
- Reads `/app/tours/{tour_file}`
- Writes ZIP to `/app/tours/`
- Serves ZIP via `/download/{job_id}`

Proposed change:
- Accept **either** `tour_file` (filename, for local dev) **or** `tour_content` (text body, for cloud)
- If `tour_content` provided, use it directly instead of reading from disk
- Write ZIP to `/tmp/` instead of `/app/tours/` (Cloud Run temp storage)
- Serve ZIP from `/tmp/` (already works — `send_file` doesn't care about the path)

```python
# New /process endpoint accepts both:
{"tour_file": "filename.txt"}           # Local dev (reads from volume)
{"tour_content": "Stop 1: Boston..."}   # Cloud (content passed directly)
```

**Service: `tour_orchestrator_service.py` (port 5002)**

Current behavior:
- Calls generator, gets filename
- Passes filename to modernized service
- Downloads ZIP from modernized service (already HTTP!)
- Saves ZIP to `/app/tours/` (redundant — also stores in DB)
- Extracts ZIP to `/app/tours/{dir}/` (temporary, cleaned up)
- Stores ZIP bytes in DB

Proposed change:
- After generator completes, get `tour_content` from status response
- Pass `tour_content` to modernized service (instead of `tour_file`)
- Download ZIP from modernized service (unchanged — already HTTP)
- Store ZIP bytes directly in DB (skip saving to disk)
- Use `/tmp/` for any temporary extraction needed

```python
# Current:
status_data = check_generator_status(job_id)
tour_file = status_data["output_file"]
modernized_response = requests.post(modernized_url + "/process", json={"tour_file": tour_file})

# New:
status_data = check_generator_status(job_id)
tour_content = status_data["tour_content"]  # Get content directly
modernized_response = requests.post(modernized_url + "/process", json={"tour_content": tour_content})
```

**Service: `tour_editing_phase2.py` (port 5022)**

Current behavior:
- Reads tour directories from `/app/tours/` for editing
- Creates new directories with modified stops
- Creates ZIP from directory
- Promote endpoint receives base64 ZIP from mobile and stores in DB

Proposed change:
- For editing, extract the tour from **database BYTEA** into `/tmp/` (not shared volume)
- `resolve_tour_to_directory()` → `resolve_tour_from_db()` that extracts to temp dir
- Create new tour in `/tmp/`, ZIP it, store in DB
- Promote endpoint already works without the volume (receives ZIP from mobile)

This is the most complex change because editing currently assumes persistent directories on disk. But the key insight is: **the database already has the complete ZIP**. We just need to extract it to a temp dir when editing starts, and re-ZIP when done.

### 3.2 What about `tour_id_resolution` and `tour_editing_1`?

- `tour_id_resolution` (port 5025): Reads from volume to resolve tour IDs. Change to read from DB.
- `tour_editing_1` (port 5020): Used for short title generation only (per Sir Michael). Likely doesn't need the volume for that function. Verify during implementation.

### 3.3 Local Dev Compatibility

The refactored code must work in BOTH environments:
- **Local Docker Compose**: Volume still mounted, services can use it as before (fallback path)
- **Cloud Run**: No volume, services use HTTP content passing + temp dirs

Strategy: **Feature flag via environment variable**

```python
STORAGE_MODE = os.getenv('STORAGE_MODE', 'volume')  # 'volume' (local) or 'cloud' (Cloud Run)
```

When `STORAGE_MODE=volume`: existing behavior (read/write shared volume)  
When `STORAGE_MODE=cloud`: new behavior (HTTP content passing + /tmp/ + DB)

This means we can test cloud behavior locally by setting the env var, without breaking the existing Docker Compose workflow.

---

## 4. Proposed Solution: Environment-Variable-Driven Service URLs

### Current (hardcoded Docker hostnames):
```python
response = requests.post("http://development-tour-generator-1:5000/generate", ...)
url = f"http://coordinates-fromai:5004/coordinates/{location}"
response = requests.post("http://tour-generation-modernized-1:5021/process", ...)
```

### Proposed (env-var with local defaults):
```python
TOUR_GENERATOR_URL = os.getenv('TOUR_GENERATOR_URL', 'http://development-tour-generator-1:5000')
COORDINATES_URL = os.getenv('COORDINATES_URL', 'http://coordinates-fromai:5004')
MODERNIZED_URL = os.getenv('MODERNIZED_URL', 'http://tour-generation-modernized-1:5021')

response = requests.post(f"{TOUR_GENERATOR_URL}/generate", ...)
url = f"{COORDINATES_URL}/coordinates/{location}"
response = requests.post(f"{MODERNIZED_URL}/process", ...)
```

**Default values = current Docker hostnames**, so local dev works unchanged without setting any env vars.

### Service URL Map (all inter-service calls):

| Env Var | Default (Docker) | Cloud Run Value |
|---|---|---|
| `TOUR_GENERATOR_URL` | `http://development-tour-generator-1:5000` | `https://tour-generator-abc.us-central1.run.app` |
| `MODERNIZED_URL` | `http://tour-generation-modernized-1:5021` | `https://tour-generation-modernized-xyz.us-central1.run.app` |
| `TRANSLATION_URL` | `http://translation-service-1:5030` | `https://translation-service-xyz.us-central1.run.app` |
| `TOUR_UPDATE_URL` | `http://development-tour-update-1:5001` | `https://tour-update-xyz.us-central1.run.app` |
| `USER_API_URL` | `http://user-api-2:5000` | `https://user-api-xyz.us-central1.run.app` |
| `COORDINATES_URL` | `http://coordinates-fromai:5004` | `https://coordinates-xyz.us-central1.run.app` |
| `POLLY_TTS_URL` | `http://polly-tts-1:5018` | `https://polly-tts-xyz.us-central1.run.app` |
| `NEWSLETTER_PROCESSOR_URL` | `http://newsletter-processor-1:5017` | `https://newsletter-processor-xyz.us-central1.run.app` |

---

## 5. Proposed Solution: Blob Migration (DB → R2)

### Phase 1 (Phase B): Add R2 support behind feature flag

```python
BLOB_STORAGE = os.getenv('BLOB_STORAGE', 'database')  # 'database' or 'r2'
R2_ENDPOINT = os.getenv('R2_ENDPOINT', '')
R2_BUCKET = os.getenv('R2_BUCKET', 'audioura-tours')
R2_ACCESS_KEY = os.getenv('R2_ACCESS_KEY', '')
R2_SECRET_KEY = os.getenv('R2_SECRET_KEY', '')
```

When `BLOB_STORAGE=database`: current behavior (store/read BYTEA)  
When `BLOB_STORAGE=r2`: store ZIP in R2, store R2 key in DB column

### Phase 2 (Phase D): Migrate existing blobs

- Add `r2_key` column to `audio_tours` and `news_audios` tables
- Script to upload existing BYTEA blobs to R2 and populate `r2_key`
- `map_delivery` reads from R2 when `r2_key` is set, falls back to BYTEA when NULL
- After all blobs migrated, BYTEA columns can be NULLed to reclaim space

### Why defer full blob migration to Phase D?

- Phase B goal is "make code cloud-ready locally" — no cloud accounts needed yet
- R2 requires Cloudflare account (being set up in parallel)
- We can test locally with MinIO (S3-compatible) as R2 stand-in
- The feature flag approach means we can ship Phase B without R2 being ready

---

## 6. Implementation Order

| Step | What | Risk | Effort |
|---|---|---|---|
| 1 | Add env-var-driven service URLs to `tour_orchestrator_service.py` | LOW — additive, defaults preserve current behavior | 1 hour |
| 2 | Add `tour_content` field to generator status response | LOW — additive field | 30 min |
| 3 | Add `tour_content` parameter to modernized service `/process` | LOW — alternative input path | 1 hour |
| 4 | Refactor orchestrator to pass content instead of filename (when `STORAGE_MODE=cloud`) | MEDIUM — core pipeline change | 2 hours |
| 5 | Refactor `tour_editing_phase2` to extract from DB instead of volume (when `STORAGE_MODE=cloud`) | MEDIUM-HIGH — most complex change | 3-4 hours |
| 6 | Add `/health` endpoints to all services missing them | LOW — mechanical | 1 hour |
| 7 | Add R2 storage abstraction behind feature flag | MEDIUM — new code path | 2 hours |
| 8 | Test full pipeline locally with `STORAGE_MODE=cloud` | — | 2 hours |

**Total estimated effort: 12-15 hours**

---

## 7. Questions for Claude Review

1. **Is the feature-flag approach (`STORAGE_MODE=volume|cloud`) the right pattern?** Alternative: always use HTTP content passing even locally (simpler code, but changes local dev behavior).

2. **Should the orchestrator store the ZIP in R2 immediately after generation, or keep storing in DB BYTEA for now?** The migration doc suggests R2 in Phase D, but doing it in Phase B means less code to change later.

3. **For tour_editing_phase2: is extracting from DB to /tmp/ on every edit request acceptable?** A 19 MB ZIP (max observed) takes ~1 second to extract. Cloud Run instances can cache in memory if the same tour is edited repeatedly within one instance's lifetime. Is this good enough, or should we add a caching layer?

4. **The `tour_id_resolution` service reads the volume to find tours by name/UUID. Should it be refactored to query the DB instead?** This seems like the right move (DB is the source of truth), but it's a behavior change.

5. **Should we consolidate `tour_editing_1` (port 5020) and `tour_editing_phase2` (port 5022) into one service?** They share the same volume and similar functionality. Fewer services = simpler deployment. But Sir Michael said keep both for now.

6. **Is there a risk that passing full tour content via HTTP (instead of filename) hits request size limits?** A typical tour text file is 5-50 KB. Cloud Run's max request size is 32 MB. Should be fine, but worth confirming.

---

## 8. What This Document Does NOT Cover

- GCP project setup (Phase C — separate assignment)
- Actual R2 bucket creation and data migration (Phase D)
- Production cutover (Phase E)
- Mobile app config changes (separate track)
- CI/CD pipeline (out of scope per migration doc)

---

## 9. Success Criteria for Phase B

After Phase B is complete:

1. All 21 services can run locally with `STORAGE_MODE=cloud` set
2. Tour generation pipeline works end-to-end without the shared volume
3. Tour editing works by extracting from DB instead of reading volume directories
4. All services have `/health` endpoints returning 200
5. All inter-service URLs are env-var-driven (with Docker hostname defaults)
6. R2 storage abstraction exists behind feature flag (tested with MinIO locally)
7. Existing Docker Compose workflow is UNCHANGED when env vars are not set
