# Claude.AI Code Review — Phase B Cloud-Ready Refactoring (Complete)

**Date:** 2026-06-02  
**Branch:** `services-migration`  
**Commits:** `399e335` through `459e887` (15 commits in this session)  
**Scope:** All Phase B infrastructure changes to make 21 Docker services Cloud-Run-ready  
**Status:** Phase B functionally complete — core architectural changes deployed and tested

---

## Overview of Changes

Phase B makes the Audioura backend capable of running on Google Cloud Run (stateless, multi-instance) while preserving the existing local Docker workflow unchanged.

Three problems solved:
1. **Shared volume dependency** → HTTP content passing between services
2. **Hardcoded URLs/credentials** → Environment-variable-driven configuration
3. **In-memory job state** → Database-backed job store (multi-instance safe)

Plus three tour-quality fixes discovered during testing.

---

## Files Created (New Modules)

| File | Purpose |
|------|---------|
| `blobstorage.py` | Abstract interface for tour ZIP storage (DatabaseBlobStorage + R2BlobStorage). Feature flag: `BLOB_STORAGE_TYPE=database\|r2` |
| `job_store.py` | Database-backed replacement for `ACTIVE_JOBS` dict. Feature flag: `JOB_STORE_MODE=memory\|database` |
| `service_config.py` | Centralized env-var config for all services (DB, URLs, AWS, feature flags) |
| `.env.example` | Template for environment variables (no secrets, safe to commit) |
| `migration/sql/002_phase_b_cloud_readiness.sql` | Schema: `draft` column, `tour_blob_uri`, `news_blob_uri`, `job_status` table |

---

## Files Modified (Service Refactoring)

### Credential Externalization (7 services)

All hardcoded `password="password123"` and DB host references replaced with `os.getenv()`:

| Service | Change |
|---------|--------|
| `map_delivery_service.py` | `get_db_connection()` → env vars |
| `tour_id_resolution_service.py` | `get_db_connection()` → env vars |
| `treats_service.py` | `get_db_connection()` → env vars |
| `tour_editing_phase2.py` | `get_db_connection()` → env vars |
| `tour_orchestrator_service.py` | 3 inline `psycopg2.connect()` calls → env vars |
| `translation_service.py` | `get_db_connection()` → env vars |
| `background_article_processor_service.py` | Multiple connection sites → env vars |

### Inter-Service URL Externalization (6 services)

All hardcoded Docker container hostnames replaced with `os.getenv('SERVICE_URL', 'default')`:

| Service | URLs Externalized |
|---------|-------------------|
| `tour_orchestrator_service.py` | TOUR_GENERATOR_URL, MODERNIZED_URL, TRANSLATION_URL, TOUR_UPDATE_URL, USER_API_URL, COORDINATES_URL |
| `news_orchestrator_service.py` | NEWS_GENERATOR_URL, NEWS_PROCESSOR_URL, TRANSLATION_URL |
| `tour_generation_modernized.py` | POLLY_TTS_URL |
| `tour_editing_phase2.py` | POLLY_TTS_URL |
| `news_processor_service.py` | POLLY_TTS_URL, VOICE_CONTROL_URL |
| `background_article_processor_service.py` | NEWS_ORCHESTRATOR_URL |

### HTTP Content Passing (Core Pipeline Change)

| Service | Change |
|---------|--------|
| `generate_tour_text_service.py` | Now stores `tour_content` in job status + returns it in `/status` response |
| `tour_generation_modernized.py` | `/process` endpoint now accepts `tour_content` (inline text) OR `tour_file` (filename) |
| `tour_orchestrator_service.py` | Prefers `tour_content` from generator status, passes it to modernized service via HTTP body |

**Result:** Tour generation pipeline works without the shared `/app/tours/` volume. The orchestrator sends content directly via HTTP instead of relying on both services reading/writing the same filesystem.

### Cloud-Mode Editing

| Service | Change |
|---------|--------|
| `tour_editing_phase2.py` | Added `_resolve_tour_from_db()` — extracts tour ZIP from database to `/tmp/` when `TOUR_STORAGE_MODE=cloud`. `resolve_tour_to_directory()` now branches on storage mode. |

### Health Endpoints (4 services added)

| Service | Port |
|---------|------|
| `tour_editing_phase2.py` | 5022 |
| `background_article_processor_service.py` | 5015 |
| `simple_news_search_service.py` | 5016 |
| `tour_editing_simple.py` | 5020 |

All 21 services now respond to `GET /health` with 200.

### Translation Service Dockerfile Fix

| File | Change |
|------|--------|
| `translation-service/translation_service.py` | Replaced stale 8 KB file with the real 76 KB version (prevents catastrophic regression on first Cloud Build) |

### Newsletter Processor Fix (Item 3)

| File | Change |
|------|--------|
| `newsletter_processor_service.py` | Response no longer exposes `articles_found` as top-level user-facing field. Only `articles_created` (deliverable count) is returned. `_diagnostic` object holds internal detection/failure counts. |

---

## Tour Quality Fixes (Found During Testing)

### 1. Museum Icon on Walking Tours (`generate_tour_text.py`)

**Problem:** "walking tour in Portsmouth with a stop at Strawbery Banke Museum" got museum icons (🏛️) because "museum" in `tour_type` triggered museum classification.

**Fix:** Added explicit walking-tour phrase detection with highest priority in `_classify_tour_category()`. "walking tour", "walk tour", "walking in" now override museum/restaurant keywords.

### 2. Exhibit Verification Gap (`generate_tour_text.py`)

**Problem:** "Thoreau's Bedroom" (at Concord Museum) was accepted as inside The Old Manse because the pre-filter only checked stops with institution marker words in their names.

**Fix:** For single-venue museum tours ≤12 stops, ALL stops are now verified (not just institution-named ones). Cost guard at 12 stops prevents pathological cases.

### 3. Venue Containment Prompt (`generate_tour_text.py`)

**Problem:** PHASE 5 description prompt didn't tell OpenAI to stay inside the venue.

**Fix:** Added explicit constraint: "Every stop MUST be physically located INSIDE '{venue_name}'. Do NOT include artifacts housed at any other institution."

### 4. PHASE 5.6 Scope Containment (`generate_tour_text.py`)

**Problem:** S17 scope constraint was injected as a prompt hint but never enforced. GPT ignored it for Robbins House and generated city-wide landmarks.

**Fix:** New `_validate_stops_within_scope()` function — post-generation check verifying each stop is inside the named scope. Removes out-of-scope landmarks. Only fires when museum guard (5.5b) didn't run.

### 5. Venue Promotion (`generate_tour_text.py`)

**Problem:** "tour in Robbins House and Monument Square museum" → intent returned `venue_name: null` because "and" confused it into thinking it's two places.

**Fix:** Deterministic promotion: when venue_name is null but request uses interior preposition ("in/inside/within/of") and scope ends in institutional building noun (museum/house/gallery/etc.), promote scope to venue_name.

### 6. Next-Stop Naming in Directions (`generate_tour_text.py`)

**Problem:** Directions said "Please resume the tour at the next stop" instead of naming it.

**Fix:** Now says "Please resume the tour at {next_poi['name']}" (e.g., "Please resume the tour at Portland Museum of Art").

---

## Feature Flags (Backwards Compatible)

All changes default to current behavior. Cloud paths only activate when explicitly set:

| Env Var | Default | Cloud Value | Effect |
|---------|---------|-------------|--------|
| `TOUR_STORAGE_MODE` | `volume` | `cloud` | HTTP content passing instead of shared volume |
| `BLOB_STORAGE_TYPE` | `database` | `r2` | R2 object storage instead of PostgreSQL BYTEA |
| `JOB_STORE_MODE` | `memory` | `database` | DB-backed job tracking instead of in-memory dict |

---

## Schema Migration Applied

```sql
-- audio_tours
ALTER TABLE audio_tours ADD COLUMN draft BOOLEAN DEFAULT FALSE;
ALTER TABLE audio_tours ADD COLUMN tour_blob_uri VARCHAR(512);

-- news_audios
ALTER TABLE news_audios ADD COLUMN news_blob_uri VARCHAR(512);

-- New table for multi-instance job tracking
CREATE TABLE job_status (
    job_id VARCHAR(64) PRIMARY KEY,
    service_name VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    progress TEXT,
    location TEXT, tour_type VARCHAR(50), total_stops INTEGER,
    output_data JSONB, error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Test Results

| Test | Result |
|------|--------|
| Tour generation (walking) | ✅ Completed end-to-end with HTTP content passing |
| Tour generation (museum) | ✅ Correct icons, exhibit verification working |
| Translation (Russian) | ✅ Dockerfile fix confirmed working |
| Newsletter processing | ✅ Blog homepage pattern, deliverable-only response |
| Health endpoints (all 21 ports) | ✅ All return 200 |
| Orchestrator logs | ✅ "Using tour_content for modernized service (7332 chars)" |
| Robbins House scope containment | ✅ 3 correct stops instead of 8 wrong city landmarks |

---

## Questions for Review

1. **Is the feature-flag approach sound?** Three independent flags control three independent behaviors. Local dev never sees the cloud path unless explicitly opted in. Is there a simpler way?

2. **The `job_store.py` DatabaseJobStore is created but not yet wired into the actual services** (they still use in-memory `ACTIVE_JOBS`). Wiring it in requires touching every async service. Should this happen before Phase C (GCP setup) or can it wait until the first multi-instance deploy?

3. **PHASE 5.6 adds 3-7 GPT calls per tightly-scoped tour.** At $0.0001 per call, the cost is negligible. But it adds ~5-10 seconds to generation time for these tours. Acceptable?

4. **The `_resolve_tour_from_db` function in tour_editing_phase2 extracts to `/tmp/`.** Cloud Run instances have 2 GB writable `/tmp/` but it's ephemeral. For a 19 MB ZIP (max observed), extraction takes <1 second. Is there a concern about `/tmp/` disk pressure under load?

5. **Should we add a cleanup step** that removes `/tmp/tour_*` directories after each edit request completes? Currently they persist until the container recycles.

---

## What's Next (Phases C-E)

| Phase | What | Effort | Prerequisite |
|-------|------|--------|-------------|
| **C** | GCP project setup (2 projects, Cloud SQL, Secret Manager, Artifact Registry) | 3 hours | GCloud account (Sir Michael setting up) |
| **D** | Migrate 2.7 GB blobs from DB BYTEA to Cloudflare R2, flip `BLOB_STORAGE_TYPE=r2` | 4-6 hours | Cloudflare account (Sir Michael setting up) |
| **E** | Deploy all services to Cloud Run, DNS cutover, mobile app config | 4-6 hours | Phases C+D complete |

Phase B is the largest and hardest phase. C/D/E are mostly mechanical deployment work.
