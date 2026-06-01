# Phase B Implementation Guide for Kiro + Amazon Q

**Prepared for:** Kiro (implementation lead)  
**Tool:** Amazon Q (code generation + refactoring)  
**Date:** May 29, 2026  
**Status:** Ready for implementation  
**Previous phases:** Phase A (assessment) complete  
**Related docs:** `AUDIOURA_SERVICES_MAP_POI_HISTORY.md`, `CLOUDFLARE_R2_SETUP_PHASE_D.md`

---

## Executive Summary

**Goal:** Make all 21 Docker services cloud-ready (stateless, no shared volumes, no hardcoded URLs/credentials) for Google Cloud Run deployment.

**Key constraint:** Services must work identically in local Docker Compose (`TOUR_STORAGE_MODE=volume`) and cloud (`TOUR_STORAGE_MODE=cloud`), with only environment variable changes between environments.

**Estimated scope:** 4–5 weeks (including decisions, refactoring, testing, sign-off)

**Blocking nothing:** Phase B is independent; Phase C (GCP setup) can start in parallel after decisions are locked.

---

## Phase B Breakdown: The Three Problems to Solve

From `AUDIOURA_SERVICES_MAP_POI_HISTORY.md` §2:

### 1. Shared Volume `/app/tours/` → HTTP Content Passing
- **Problem:** 7 services use `/app/tours/` as a message bus during tour generation. Cloud Run is stateless—no shared FS.
- **Solution:** Pass tour content (text, then ZIP) between services via HTTP instead of disk; orchestrator stores final ZIP in blob store (abstraction layer).

### 2. Hardcoded Inter-Service URLs → Env-Var-Driven
- **Problem:** Services call each other by Docker container names (`http://development-tour-generator-1:5000`). Cloud Run URLs are dynamic.
- **Solution:** Env-var-driven URLs with Docker names as local defaults. Cloud Run injects actual URLs at deploy time.

### 3. 2.7 GB ZIPs in PostgreSQL BYTEA → BlobStorage Abstraction
- **Problem:** Expensive backups, slow restores.
- **Solution:** Abstraction layer in Phase B (MinIO-backed local test); flip to R2 in Phase D.

---

## Task Breakdown (17 Tasks, Sequenced)

### **STAGE 1: DECISIONS** (Unlock implementation)

#### Task 1: Decision 3.1 — Edit-Session State Across Cloud Run Instances

**What:** Decide how to persist draft tour state between `bulk-save` and `promote` calls across multi-instance Cloud Run.

**Options:**
- Collapse `bulk-save` + `promote` into one call (loses naming-conflict UX)
- **[RECOMMENDED]** Add `draft=true` row in `audio_tours` table (preserves UX)
- Cloud Run session affinity (fragile across deploys/recycles)

**Action:** Confirm the `draft=true` approach with Kiro. Once approved, proceed to Task 15 (schema migration).

**Deliverable:** Decision documented; schema plan ready.

---

#### Task 2: Decision 3.2 — ACTIVE_JOBS Shared Store for Async Services

**What:** Resolve per-instance `ACTIVE_JOBS = {}` dict breaking when Cloud Run scales past 1 replica.

**Options:**
- **[RECOMMENDED]** Redis Memorystore (production-ready; GCP Memorystore for production)
- DB table (simpler, slower)
- Pin services to `min=max=1` (temporary workaround)

**Action:** Confirm Redis approach. For Phase B: add Redis service to docker-compose.yml for local testing. For production: GCP Memorystore endpoint injected at Cloud Run deploy time.

**Services affected:** `tour-generator`, `tour-generation-modernized`, `tour-editing-phase2`

**Deliverable:** Redis connection pattern documented; docker-compose.yml updated with Redis service.

---

#### Task 3: Decision 3.3 — Fix translation_service.py Dockerfile/Runtime Divergence

**What:** Dockerfile copies 8 KB old file; actual logic is in root 76 KB file (docker cp'd in). Plain `docker compose build` silently reverts to old file. Cloud Build will too.

**Action:**
- Audit: Which file is actually running in docker-compose.yml?
- Update Dockerfile to copy the correct file (root `translation_service.py`, not the 8 KB stub)
- Add smoke test: generate tour → translate to Russian → verify audio is Russian

**Deliverable:** Dockerfile corrected; smoke test added to Phase B test suite.

---

#### Task 4: Decision 3.4 — Externalize Hardcoded Credentials

**What:** Remove all hardcoded credentials (e.g., `tour_editing_phase2.py:97 password="password123"`). Cloud Run images cannot ship credentials.

**Action:**
```bash
# Find all hardcoded creds
grep -rn 'password=' --include='*.py' .
grep -rn 'api_key=' --include='*.py' .
grep -rn 'secret=' --include='*.py' .
```

Move all to environment variables:
- Local Compose: `.env` file (added to `.gitignore`)
- Cloud Run: GCP Secret Manager (injected at deploy)

**Deliverable:** Zero hardcoded credentials in code; `.env.example` template with all required keys (no values); docker-compose.yml reads from `.env`.

---

### **STAGE 2: INFRASTRUCTURE** (Implement abstraction layers)

#### Task 5: Implement BlobStorage Abstraction Layer

**What:** Create interface + implementations for tour ZIP storage (local MinIO, future R2).

**Files to create:**

```python
# blobstorage.py (abstract interface)
class BlobStorage:
    async def upload(self, tour_id: str, zip_bytes: bytes) -> str:
        """Upload ZIP; return object URI."""
        pass
    
    async def download(self, tour_id: str) -> bytes:
        """Download ZIP by tour ID."""
        pass
    
    async def delete(self, tour_id: str) -> None:
        """Delete ZIP by tour ID."""
        pass

# miniostorage.py (local testing backend)
class MinioBlobStorage(BlobStorage):
    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str):
        self.client = minio.Minio(endpoint, access_key, secret_key)
        self.bucket = bucket
    # ... implement upload/download/delete

# r2storage.py (R2 backend — stub for now, implemented in Phase D)
class R2BlobStorage(BlobStorage):
    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str):
        # boto3 S3 client pointing to R2
        pass
```

**Feature flag:** `TOUR_STORAGE_MODE=volume|cloud`
- `volume`: Use `/app/tours/` (local Docker Compose, backward-compatible)
- `cloud`: Use BlobStorage abstraction (production, stateless)

**Docker-compose integration:**
```yaml
services:
  minio:
    image: minio/minio:latest
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      - "9000:9000"
      - "9001:9001"
    command: server /data --console-address ":9001"

  tour-orchestrator:
    environment:
      TOUR_STORAGE_MODE: ${TOUR_STORAGE_MODE:-cloud}
      BLOB_STORAGE_TYPE: ${BLOB_STORAGE_TYPE:-minio}
      MINIO_ENDPOINT: ${MINIO_ENDPOINT:-minio:9000}
      MINIO_ACCESS_KEY: ${MINIO_ACCESS_KEY:-minioadmin}
      MINIO_SECRET_KEY: ${MINIO_SECRET_KEY:-minioadmin}
```

**Deliverable:** blobstorage.py + miniostorage.py + r2storage.py (stub); docker-compose.yml with MinIO service; services instantiate correct backend based on `TOUR_STORAGE_MODE`.

---

#### Task 6: Refactor Service URLs to Environment Variables

**What:** Replace hardcoded inter-service URLs with env-var-driven configuration.

**Current pattern (WRONG):**
```python
# tour_orchestrator.py
generator_url = 'http://development-tour-generator-1:5000'
modernized_url = 'http://tour-generation-modernized-1:5021'
```

**Target pattern (RIGHT):**
```python
# tour_orchestrator.py
generator_url = os.getenv('TOUR_GENERATOR_URL', 'http://development-tour-generator-1:5000')
modernized_url = os.getenv('TOUR_MODERNIZED_URL', 'http://tour-generation-modernized-1:5021')
```

**Services to audit (grep for all `http://` calls):**
- `tour-orchestrator` (calls generator, modernized, editing, translation)
- `tour-generation-modernized` (calls TTS/Polly, translation)
- `tour-editing-phase2` (calls orchestrator)
- Any other inter-service calls

**Docker-compose template:**
```yaml
services:
  tour-orchestrator:
    environment:
      TOUR_GENERATOR_URL: ${TOUR_GENERATOR_URL:-http://development-tour-generator-1:5000}
      TOUR_MODERNIZED_URL: ${TOUR_MODERNIZED_URL:-http://tour-generation-modernized-1:5021}
      TOUR_EDITING_URL: ${TOUR_EDITING_URL:-http://tour-editing-phase2-1:5022}
      TRANSLATION_SERVICE_URL: ${TRANSLATION_SERVICE_URL:-http://translation-service-1:5030}
      POLLY_TTS_URL: ${POLLY_TTS_URL:-http://polly-tts-1:5018}
```

**Verification:**
```bash
grep -rn 'http://[a-z0-9.-]*:' --include='*.py' .
# Should return ONLY env-var reads, zero raw container names
```

**Deliverable:** All inter-service URLs env-var-driven; defaults to Docker container names; grep audit clean.

---

#### Task 7: Update docker-compose.yml with Full Env-Var Structure

**What:** Consolidate all environment variable definitions in docker-compose.yml for Phase B.

**Template (all services need this pattern):**
```yaml
version: '3.9'

services:
  redis:  # NEW: for ACTIVE_JOBS
    image: redis:7-alpine
    ports:
      - "6379:6379"

  minio:  # NEW: for BlobStorage (local testing)
    image: minio/minio:latest
    # ... (see Task 5)

  tour-generator:
    environment:
      # Service URLs
      ORCHESTRATOR_URL: ${ORCHESTRATOR_URL:-http://development-tour-orchestrator-1:5002}
      
      # Database
      DB_HOST: ${DB_HOST:-postgres-2}
      DB_NAME: ${DB_NAME:-audiotours}
      DB_USER: ${DB_USER:-postgres}
      DB_PASSWORD: ${DB_PASSWORD}  # From .env
      
      # Redis (for ACTIVE_JOBS if needed)
      REDIS_URL: ${REDIS_URL:-redis://redis:6379}
      
      # Feature flags
      TOUR_STORAGE_MODE: ${TOUR_STORAGE_MODE:-volume}
      
      # Health checks
      LOG_LEVEL: ${LOG_LEVEL:-INFO}

  # ... (repeat for all 21 services)
```

**Create `.env.example` (commit to repo, no secrets):**
```bash
# Service URLs (defaults work in Docker Compose)
TOUR_GENERATOR_URL=http://development-tour-generator-1:5000
TOUR_MODERNIZED_URL=http://tour-generation-modernized-1:5021
# ... (all service URLs)

# Database (MUST be populated in local .env)
DB_HOST=postgres-2
DB_NAME=audiotours
DB_USER=postgres
DB_PASSWORD=<SET_THIS_IN_.env>

# MinIO (local testing)
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# Redis
REDIS_URL=redis://redis:6379

# Feature flags
TOUR_STORAGE_MODE=cloud
BLOB_STORAGE_TYPE=minio

# AWS (from current setup; externalize from code)
AWS_ACCESS_KEY_ID=<SET_THIS_IN_.env>
AWS_SECRET_ACCESS_KEY=<SET_THIS_IN_.env>
AWS_REGION=us-east-1
```

**Test:**
```bash
cp .env.example .env
# Populate DB_PASSWORD, AWS keys
docker-compose up
# All services should start with env vars
```

**Deliverable:** docker-compose.yml with all env vars; `.env.example` template; local `.env` works with docker-compose up.

---

### **STAGE 3: SERVICE REFACTORING** (Make services stateless)

#### Task 8: Refactor tour-orchestrator

**Current:** Coordinates pipeline; writes/reads `/app/tours/`; stores ZIP in DB.

**Target:**
- Accept tour content (text ZIP) via HTTP from `tour-generation-modernized`
- Remove all `/app/tours/` I/O
- Upload final ZIP via BlobStorage abstraction (when `TOUR_STORAGE_MODE=cloud`)
- Env vars for all downstream service URLs

**Changes:**
```python
# tour_orchestrator_service.py

class TourOrchestrator:
    def __init__(self, blob_storage: BlobStorage, service_urls: dict):
        self.blob_storage = blob_storage
        self.service_urls = service_urls
    
    async def generate_tour(self, location, poi_list):
        # 1. Call generator service
        text_zip = await self.call_service(self.service_urls['generator'], ...)
        
        # 2. Call modernized (gets back final ZIP)
        final_zip = await self.call_service(self.service_urls['modernized'], text_zip)
        
        # 3. Store ZIP via abstraction (respects TOUR_STORAGE_MODE)
        blob_uri = await self.blob_storage.upload(tour_id, final_zip)
        
        # 4. Write row to audio_tours with URI
        db.insert_tour(tour_id, blob_uri, ...)
        
        return tour_id

@app.get('/health')
async def health():
    # Check DB connection works
    await db.query("SELECT 1")
    return {"status": "healthy"}

@app.get('/health/deep')
async def health_deep():
    # Check all dependencies
    await db.query("SELECT 1")
    await blob_storage.health_check()
    return {"status": "healthy"}
```

**Files affected:**
- `tour_orchestrator_service.py` (main refactor)
- `docker-compose.yml` (add BLOB_STORAGE_MODE, MINIO env vars)

**Tests:**
- End-to-end generation with `TOUR_STORAGE_MODE=cloud`
- `/health` and `/health/deep` endpoints return 200
- ZIP appears in blob store (not in `/app/tours/`)

**Deliverable:** stateless orchestrator; no shared volume; abstracted blob storage; health endpoints.

---

#### Task 9: Refactor tour-generation-modernized

**Current:** Reads from `/app/tours/` (from generator); builds ZIP; writes to `/app/tours/`.

**Target:**
- Remove `/app/tours/` writes
- Stream/return final ZIP to orchestrator (or upload via BlobStorage)
- Use `/tmp` for staging
- Update TTS service URL (env var)

**Changes:**
```python
# tour_generation_modernized.py

class ModernizedGenerator:
    def __init__(self, tts_url: str, blob_storage: BlobStorage):
        self.tts_url = tts_url
        self.blob_storage = blob_storage
    
    async def build_tour(self, text_zip_bytes):
        # 1. Decompress text ZIP
        text_tour = unzip(text_zip_bytes)
        
        # 2. Build HTML, call TTS (via env var URL)
        for stop in text_tour.stops:
            audio = await self.http_post(self.tts_url + '/synthesize', ...)
        
        # 3. Build final ZIP in /tmp (temp staging only)
        final_zip = build_zip(...)
        
        # 4. Return to orchestrator (or upload if this service owns blob storage)
        return final_zip  # orchestrator uploads via blob_storage
```

**Files affected:**
- `tour_generation_modernized.py` (main refactor)
- `docker-compose.yml` (add POLLY_TTS_URL env var)

**Tests:**
- Multi-instance scaling (no shared state)
- ZIP generation without `/app/tours/` writes
- `/health` checks TTS service connectivity

**Deliverable:** stateless modernized generator; `/tmp` only; TTS URL env-var-driven.

---

#### Task 10: Refactor tour-editing-phase2 (Complex)

**Current:** 
- Per-instance `ACTIVE_JOBS` dict (breaks on scale)
- Reads/writes `/app/tours/`
- Hardcoded DB password
- `bulk-save` and `promote` are separate calls; state lost across instances

**Target:**
- Replace `ACTIVE_JOBS` dict with Redis
- Remove `/app/tours/` I/O; use `draft=true` flag in DB
- All credentials from env vars
- HTTP-based content passing; ensure `tour_content` is populated

**Changes:**
```python
# tour_editing_phase2.py

class TourEditingService:
    def __init__(self, redis_client, db, blob_storage, orchestrator_url):
        self.redis = redis_client
        self.db = db
        self.blob_storage = blob_storage
        self.orchestrator_url = orchestrator_url

@app.post('/bulk-save/<tour_id>')
async def bulk_save(tour_id, edit_data):
    # 1. Save draft in DB (draft=TRUE)
    db.update(f"UPDATE audio_tours SET draft=TRUE, tour_content=%s WHERE id=%s", 
              edit_data.content, tour_id)
    
    # 2. Store job in Redis (not in-process dict)
    await redis.set(f"job:{uuid}", {"status": "saving", "tour_id": tour_id})
    
    # 3. Return job ID
    return {"job_id": uuid}

@app.post('/promote/<tour_id>')
async def promote(tour_id, user_name):
    # 1. Read draft from DB (no disk read!)
    tour = db.query(f"SELECT * FROM audio_tours WHERE id=%s AND draft=TRUE", tour_id)
    
    # 2. Build final ZIP
    final_zip = build_zip(tour.tour_content)
    
    # 3. Upload via blob storage
    blob_uri = await blob_storage.upload(tour_id, final_zip)
    
    # 4. Flip draft flag, set user name, update blob URI
    db.update(f"UPDATE audio_tours SET draft=FALSE, user_name=%s, tour_blob_uri=%s WHERE id=%s",
              user_name, blob_uri, tour_id)
    
    return {"status": "promoted"}

@app.get('/status/<job_id>')
async def status(job_id):
    # Query Redis (works across instances!)
    job = await redis.get(f"job:{job_id}")
    return job

@app.get('/health/deep')
async def health_deep():
    await db.query("SELECT 1")
    await redis.ping()
    return {"status": "healthy"}
```

**Files affected:**
- `tour_editing_phase2.py` (major refactor)
- `docker-compose.yml` (add REDIS_URL, ORCHESTRATOR_URL, DB_PASSWORD, BLOB_STORAGE vars)

**Tests:**
- Multi-instance scaling: `bulk-save` on instance A, `promote` on instance B (works via DB)
- Job status queries across instances (works via Redis)
- `tour_content` populated (required by translation service)
- No hardcoded credentials
- No `/app/tours/` reads/writes

**Deliverable:** stateless editing service; Redis-backed job tracking; DB-backed draft state; credentials externalized.

---

#### Task 11: Update Other Services

**translation-service:**
- Fix Dockerfile (Task 3.3)
- Update orchestrator URL (env var)
- Verify it can read `tour_content` from DB (required for translation)
- `/health` checks orchestrator connectivity

**tour-generator** (generate_tour_text.py):
- Ensure no shared volume writes
- Clean up stale sibling files (`generate_tour_text_*.py`)

**map-delivery:**
- Prepare to read ZIPs from `BlobStorage` (instead of DB BYTEA) — will happen in Phase D
- For Phase B: still reads from DB BYTEA, but abstraction ready

**polly-tts:**
- Ensure `/health` checks AWS Polly connectivity
- No hardcoded AWS credentials (all env vars)

**newsletter-processor:**
- Ensure `/health/deep` works
- No hardcoded credentials

**tour-id-resolution:**
- Refactor to read from DB (currently reads from `/app/tours/` volume)

**General for all 21 services:**
- `/health` endpoint returns 200 and checks one dependency
- `/health/deep` endpoint checks all dependencies
- All credentials from env vars
- All service URLs from env vars
- No `/app/tours/` writes (except `/tmp` for staging)

**Files affected:** One by one; see docker-compose.yml and service files

**Deliverable:** All 21 services have health endpoints, externalized credentials, env-var URLs.

---

#### Task 12: Audit and Clean Stale Service Files

**Problem (critical):** 9+ stale sibling files in `development/`:
- `tour_editing_phase2_*.py` (×9)
- Multiple `tour_orchestrator_service*.py`
- Multiple `tour_editing*.py`

Docker Compose runs the file in its `command:` line. Cloud Build will copy whatever Dockerfile says. **Stale files create confusion and runtime drift.**

**Action:**
```bash
# For EACH service, audit:
ls -la development/tour_*.py | sort
# Determine which file is "canonical" (runs in docker-compose.yml command:)
# Update Dockerfile to COPY canonical file
# Delete stale siblings
# Document canonical file in README
```

**Example:**
```yaml
# docker-compose.yml (current)
tour-editing-phase2:
  build: .
  command: python /app/tour_editing_phase2.py  # CANONICAL FILE

# But files exist:
# tour_editing_phase2.py (8 KB, CANONICAL)
# tour_editing_phase2_v1.py (6 KB, STALE)
# tour_editing_phase2_v2.py (7 KB, STALE)
# tour_editing_phase2_backup.py (8 KB, STALE)

# Action:
rm tour_editing_phase2_v*.py tour_editing_phase2_backup.py
# Verify Dockerfile copies tour_editing_phase2.py
```

**Deliverable:** Audit report + deleted stale files; Dockerfiles updated; docker-compose.yml matches Dockerfile.

---

### **STAGE 4: SCHEMA & DATABASE**

#### Task 13: Schema Migration — Add draft Flag + tour_blob_uri

**What:** Add two columns to `audio_tours` table for Phase B + Phase D.

**Phase B (required for Decision 3.1):**
```sql
ALTER TABLE audio_tours
ADD COLUMN draft BOOLEAN DEFAULT FALSE;

-- Backfill existing tours
UPDATE audio_tours SET draft = FALSE WHERE draft IS NULL;
```

**Phase D prep (required for R2 migration):**
```sql
ALTER TABLE audio_tours
ADD COLUMN tour_blob_uri VARCHAR(512);

-- tour_blob_uri will store the R2 object URI when ZIPs are moved out of BYTEA
```

**Migration file:** Create in `migrations/` or `db/migrations/`:
```bash
migrations/002_phase_b_cloud_readiness.sql
```

**Test locally:**
```bash
psql -U postgres -d audiotours -f migrations/002_phase_b_cloud_readiness.sql
# Verify columns exist
\d audio_tours
```

**Deliverable:** Schema migration file; columns added to audio_tours; backfill complete.

---

### **STAGE 5: TESTING & DOCUMENTATION**

#### Task 14: Phase B Smoke Tests (Local Verification)

**Run all tests with `TOUR_STORAGE_MODE=cloud`.**

**Test 1: End-to-end tour generation without shared volume**
```bash
TOUR_STORAGE_MODE=cloud docker-compose up -d
# Generate a tour via mobile app / API
# Verify: ZIP appears in MinIO (not in /app/tours/)
# Verify: audio_tours row has blob_uri set
docker-compose down
```

**Test 2: Multi-instance scaling**
```bash
TOUR_STORAGE_MODE=cloud docker-compose up --scale tour-generator=2 --scale tour-generation-modernized=2 --scale tour-editing-phase2=2 -d
# Generate tour
# Edit tour: bulk-save on one instance
# Promote on different instance (should work!)
# Verify job tracking works across instances (Redis)
docker-compose down
```

**Test 3: Health endpoints**
```bash
curl http://localhost:5002/health  # orchestrator
curl http://localhost:5002/health/deep
# All should return 200 + dependency checks
```

**Test 4: No hardcoded credentials**
```bash
grep -rn 'password=' --include='*.py' .
grep -rn 'api_key=' --include='*.py' .
# Should return ZERO non-test hits
```

**Test 5: Service URL audit**
```bash
grep -rn 'http://[a-z0-9.-]*:' --include='*.py' .
# Should return ONLY env-var reads (os.getenv), zero hardcoded URLs
```

**Test 6: Translation regression**
```bash
TOUR_STORAGE_MODE=cloud docker-compose up -d
# Generate a tour to a location with POIs
# Call /translate endpoint with Russian as target language
# Download tour ZIP
# Play audio: verify it's Russian (not English)
# Catches translation_service.py Dockerfile divergence
docker-compose down
```

**Deliverable:** All 6 tests pass; documented in PHASE_B_SMOKE_TESTS.md

---

#### Task 15: Document Phase B Implementation Guide

**Create:** `PHASE_B_IMPLEMENTATION_GUIDE.md` (for Amazon Q, in development/)

**Sections:**
1. Phase B overview + goals
2. The 3 problems + solutions (shared volume, service URLs, blob storage)
3. The 4 pre-implementation decisions (with rationale)
4. Task breakdown (ordered)
5. BlobStorage abstraction pattern (code examples)
6. Service refactoring checklist
7. Environment variable naming conventions
8. Health endpoint requirements
9. Smoke test scripts
10. Common pitfalls (stale files, docker cp drift, translation regression)
11. Sign-off checklist

**Audience:** Kiro + Amazon Q should be able to execute this independently.

**Deliverable:** PHASE_B_IMPLEMENTATION_GUIDE.md (complete, ready for Amazon Q).

---

### **STAGE 6: SIGN-OFF**

#### Task 16: Phase B Sign-Off — Verify & Merge to services-migration Branch

**Verification checklist:**
- [ ] All 4 decisions finalized (3.1–3.4)
- [ ] Code review: BlobStorage abstraction + all service refactoring
- [ ] All 6 smoke tests pass (local with `TOUR_STORAGE_MODE=cloud`)
- [ ] Stale files deleted; Dockerfile/compose.yml aligned
- [ ] Schema migrations applied to local DB; columns verified
- [ ] No hardcoded URLs or credentials in code (grep clean)
- [ ] docker-compose.yml with env vars tested
- [ ] PHASE_B_IMPLEMENTATION_GUIDE.md complete
- [ ] All PRs reviewed and approved
- [ ] Merged to `services-migration` branch

**Once signed off:** Phase B complete. Phase C (GCP setup) can proceed.

**Deliverable:** Phase B complete; services-migration branch ready for Phase C.

---

## Implementation Sequence (Recommended)

1. **Decisions (Day 1):** Lock Tasks 1–4 with Kiro
2. **Infrastructure (Days 2–4):** Implement Tasks 5–7 (BlobStorage, env vars, docker-compose)
3. **Service Refactoring (Days 5–10):** Implement Tasks 8–11 (one service at a time, test as you go)
4. **Database (Day 11):** Task 13 (schema migration)
5. **Testing (Day 12):** Task 14 (smoke tests)
6. **Documentation (Day 13):** Task 15 (guide for next phases)
7. **Sign-Off (Day 14):** Task 16 (final verification)

**Parallelization:** Tasks 5–7 (infrastructure) can happen in parallel; services (Tasks 8–11) should be sequential to catch issues early.

---

## Dependencies & Blocking

**No blocking external dependencies.** Phase B is self-contained:
- ✅ Cloudflare R2 setup complete (separate task; Phase D will use)
- ✅ GCP project can start in parallel (Phase C)
- ✅ No customer-facing changes required

---

## Deliverables Checklist (for sign-off)

- [ ] All services accept `TOUR_STORAGE_MODE=cloud` env var
- [ ] All services read credentials from env vars (no hardcoding)
- [ ] All services read service URLs from env vars
- [ ] BlobStorage abstraction implemented (MinIO + R2 stub)
- [ ] All services have `/health` + `/health/deep` endpoints
- [ ] Audio_tours table has `draft` and `tour_blob_uri` columns
- [ ] docker-compose.yml passes all env vars
- [ ] All 6 smoke tests pass
- [ ] Stale files deleted; git repo clean
- [ ] PHASE_B_IMPLEMENTATION_GUIDE.md complete (ready for Phase C team)
- [ ] services-migration branch merged to main (or held for Phase C)

---

## Key Files to Create/Modify

| File | Action | Status |
|---|---|---|
| `blobstorage.py` | Create (abstract interface) | Task 5 |
| `miniostorage.py` | Create (MinIO implementation) | Task 5 |
| `r2storage.py` | Create (R2 stub for Phase D) | Task 5 |
| `tour_orchestrator_service.py` | Refactor (remove /app/tours/, use BlobStorage) | Task 8 |
| `tour_generation_modernized.py` | Refactor (remove /app/tours/, use /tmp) | Task 9 |
| `tour_editing_phase2.py` | Refactor (Redis ACTIVE_JOBS, DB draft flag) | Task 10 |
| `docker-compose.yml` | Update (env vars, MinIO, Redis services) | Task 7 |
| `.env.example` | Create (template, no secrets) | Task 7 |
| `migrations/002_phase_b_cloud_readiness.sql` | Create (schema: draft, tour_blob_uri) | Task 13 |
| `PHASE_B_SMOKE_TESTS.md` | Create (test scripts) | Task 14 |
| `PHASE_B_IMPLEMENTATION_GUIDE.md` | Create (Amazon Q guide) | Task 15 |
| (delete stale files) | Delete (`tour_editing_phase2_*.py`, etc.) | Task 12 |

---

## Success Criteria

Phase B is complete when:
1. **All services are stateless:** No shared volumes, no in-process state, no hardcoded URLs/credentials
2. **Local dev unchanged:** `TOUR_STORAGE_MODE=volume` (default) works exactly as before with Docker Compose
3. **Cloud-ready:** `TOUR_STORAGE_MODE=cloud` passes all smoke tests
4. **Health checks:** Every service has `/health` + `/health/deep` + dependency checks
5. **Documentation:** Kiro can hand off to Phase C team with confidence

---

## Questions for Kiro

Before starting, confirm:
1. ✅ **Decision 3.1:** Use `draft=true` approach for edit-session state?
2. ✅ **Decision 3.2:** Use Redis Memorystore for ACTIVE_JOBS?
3. ✅ **Decision 3.3:** Which file is canonical for `translation_service.py`?
4. ✅ **Decision 3.4:** Have you identified all hardcoded credentials? (grep check)
5. ✅ **Timeline:** 2 weeks feasible for Phase B with Amazon Q support?
6. ✅ **Amazon Q:** Is Amazon Q ready for multi-file refactoring (blobstorage integration across 21 services)?

---

## Post-Phase B (Phase C & Beyond)

Once Phase B is complete:
- **Phase C:** Set up GCP project + Cloud Run
- **Phase D:** Migrate 2.7 GB ZIPs from DB BYTEA to Cloudflare R2 (R2 setup already done)
- **Phase E:** Production cutover

---

**Status:** Ready for Kiro + Amazon Q implementation.

**Next step:** Share this doc with Kiro; confirm decisions 1–4; begin Phase B.
