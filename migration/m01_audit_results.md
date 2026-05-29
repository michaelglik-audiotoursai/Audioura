# M01 — Pre-Migration Audit Results

**Date:** 2026-05-28  
**Auditor:** Kiro (services-migration branch)  
**Status:** Complete

---

## 1. Service Inventory (22 running containers)

The actual running container count (22) exceeds the migration doc's estimate of 13. Here's the full inventory:

| # | Container | Port | Dockerfile | Base Image | Key Dependencies | Cloud Run? |
|---|---|---|---|---|---|---|
| 1 | development-postgres-2-1 | 5433→5432 | postgres:15-alpine (image) | postgres:15-alpine | — | **No — Cloud SQL** |
| 2 | development-tour-generator-1 | 5000 | Dockerfile.generator | python:3.9-slim | flask, openai, requests | Yes |
| 3 | development-tour-processor-1 | 5001 | Dockerfile.tour-processor | python:3.10-slim | flask, gtts, pydub, **ffmpeg, espeak** | Yes (needs ffmpeg) |
| 4 | development-tour-orchestrator-1 | 5002 | Dockerfile.orchestrator | python:3.9-slim | flask, flask-cors, requests, psycopg2 | Yes |
| 5 | development-user-api-2-1 | 5003→5000 | Dockerfile (generic) | python:3.9-slim | flask, flask-cors, psycopg2 | Yes |
| 6 | development-tour-update-1 | 5004→5001 | Dockerfile (generic) | python:3.9-slim | flask, psycopg2 | Yes |
| 7 | development-map-delivery-1 | 5005 | Dockerfile (generic) | python:3.9-slim | flask, flask-cors, psycopg2 | Yes |
| 8 | development-coordinates-fromai-1 | 5006→5004 | Dockerfile (generic) | python:3.9-slim | flask, openai, psycopg2 | Yes |
| 9 | development-treats-1 | 5007→5006 | Dockerfile.treats | python:3.9-slim | flask, flask-cors, psycopg2 | Yes |
| 10 | development-voice-control-1 | 5008 | Dockerfile.voice-nlp | python:3.9-slim | flask, requests | Yes |
| 11 | news-generator-1 | 5010 | Dockerfile.news-generator | python:3.9-slim | flask, psycopg2, gTTS, pydub | Yes |
| 12 | news-processor-1 | 5011 | Dockerfile.news-processor | python:3.9-slim | flask, psycopg2, gTTS, pydub, **ffmpeg** | Yes (needs ffmpeg) |
| 13 | news-orchestrator-1 | 5012 | Dockerfile.news-orchestrator | python:3.9-slim | flask, psycopg2, requests | Yes |
| 14 | background-article-processor-1 | 5015 | Dockerfile.background-article-processor | python:3.9-slim | flask, requests, beautifulsoup4, psycopg2 | Yes |
| 15 | simple-news-search-1 | 5016 | Dockerfile.simple-news-search | python:3.9-slim | flask, requests, beautifulsoup4, psycopg2 | Yes |
| 16 | newsletter-processor-1 | 5017 | Dockerfile.newsletter-processor | python:3.9-slim | flask, psycopg2, requests, beautifulsoup4 | Yes (**heavy**) |
| 17 | polly-tts-1 | 5018 | Dockerfile.polly-tts | python:3.9-slim | flask, boto3 | Yes |
| 18 | tour-editing-1 | 5020 | Dockerfile (generic) | python:3.9-slim | flask, psycopg2 | Yes |
| 19 | tour-generation-modernized-1 | 5021 | Dockerfile (generic) | python:3.9-slim | flask, boto3, psycopg2 | Yes |
| 20 | tour-editing-phase2-1 | 5022 | Dockerfile (generic) | python:3.9-slim | flask, boto3, psycopg2 | Yes |
| 21 | tour-id-resolution-1 | 5025 | Dockerfile.tour-id-resolution | python:3.11-slim | flask, flask-cors, psycopg2 | Yes |
| 22 | translation-service-1 | 5030 | translation-service/Dockerfile | python:3.9-slim | flask, boto3, psycopg2 | Yes |

**Total Cloud Run services needed: 21** (everything except postgres)

### Services NOT in the original migration doc (need to be added):

- `development-user-api-2-1` (port 5003) — user tracking API
- `development-tour-update-1` (port 5004) — tour update service
- `development-voice-control-1` (port 5008) — voice NLP
- `background-article-processor-1` (port 5015) — background article processing
- `simple-news-search-1` (port 5016) — news search
- `tour-editing-1` (port 5020) — tour editing v1
- `tour-generation-modernized-1` (port 5021) — modernized tour generation (MP3 via Polly)
- `tour-editing-phase2-1` (port 5022) — tour editing v2 (language-aware)
- `tour-id-resolution-1` (port 5025) — tour ID resolution

---

## 2. Database Analysis

### 2.1 Tables (19 total)

| Table | Rows | Total Size | Has Blobs? |
|---|---|---|---|
| news_audios | 745 | **1,680 MB** | ✅ `news_article` bytea — avg 2.2 MB, max 12 MB |
| audio_tours | 228 | **979 MB** | ✅ `audio_tour` bytea — avg 4.1 MB, max 19 MB |
| article_requests | 896 | 18 MB | ✅ `article_text` bytea (small — article text) |
| treats | 2 | 744 KB | ✅ `ad_image` bytea — avg 170 KB, max 280 KB |
| newsletters_article_link | — | 144 KB | No |
| newsletters | 117 | 136 KB | No |
| tour_requests | — | 88 KB | No |
| All other tables (12) | — | <80 KB each | No |

### 2.2 Total database size: ~2.7 GB

- **Blobs account for ~99% of database size** (2.66 GB of 2.7 GB)
- Without blobs, the relational data is ~40 MB

### 2.3 Blob Migration Recommendation: **CRITICAL — Move to R2**

| Table | Blob Column | Count | Total Size | Recommendation |
|---|---|---|---|---|
| `news_audios` | `news_article` | 745 | ~1.65 GB | **Move to R2** — these are ZIP files with MP3 audio |
| `audio_tours` | `audio_tour` | 228 | ~936 MB | **Move to R2** — these are ZIP files with tour audio + HTML |
| `article_requests` | `article_text` | 896 | ~16 MB | Keep in DB — small text blobs, not worth extracting |
| `treats` | `ad_image` | 2 | ~340 KB | Keep in DB — tiny, only 2 rows |

**Impact of moving blobs to R2:**
- DB size drops from 2.7 GB → ~40 MB
- Cloud SQL `db-f1-micro` ($10/month) becomes viable for production (10 GB storage included)
- Backup/restore time drops from minutes to seconds
- R2 storage for 2.6 GB = $0.04/month (vs paying for oversized DB instance)

---

## 3. Shared Volume Analysis

### 3.1 The `./tours` volume

- **Mounted by:** tour-orchestrator, tour-processor, map-delivery, tour-editing, tour-generation-modernized, tour-editing-phase2, tour-id-resolution
- **Contents:** 976 ZIP files, 2.3 GB total
- **Purpose:** Intermediate storage during tour generation (text file → MP3 processing → ZIP packaging) + serving tours for download
- **Lifecycle:** Files are created during tour generation, then the ZIP is stored in the database (`audio_tours.audio_tour`). The volume acts as both working directory AND a cache.

### 3.2 Migration Impact: **HIGH**

Cloud Run containers are **stateless** — no shared filesystem. This volume must be replaced with:

1. **R2 object storage** for the final ZIP files (already planned for blob migration)
2. **In-memory or temp-dir processing** for intermediate files during tour generation (each Cloud Run instance gets a writable `/tmp` with up to 2 GB)
3. **Service-to-service communication** changes: instead of writing a file to a shared path and another service reading it, services must pass data via HTTP or R2 URLs

This is the **single biggest code change** in the migration. The tour generation pipeline currently works like:
```
orchestrator writes text → shared volume → processor reads text
processor writes MP3s → shared volume → orchestrator reads ZIP
```

In cloud, it needs to become:
```
orchestrator sends text → HTTP POST to processor
processor returns ZIP → HTTP response (or R2 URL)
```

---

## 4. Inter-Service Communication (Service Mesh)

Services call each other using Docker container names as hostnames. These are hardcoded in the deployed code:

| Caller | Calls | URL Pattern |
|---|---|---|
| tour-orchestrator | tour-generator | `http://development-tour-generator-1:5000/generate` |
| tour-orchestrator | tour-generation-modernized | `http://tour-generation-modernized-1:5021/process` |
| tour-orchestrator | translation-service | `http://translation-service-1:5030/translate-with-audio` |
| tour-orchestrator | tour-update | `http://development-tour-update-1:5001/update` |
| tour-orchestrator | user-api | `http://user-api-2:5000/user/{id}` |
| tour-orchestrator | coordinates | `http://coordinates-fromai:5004/coordinates/{loc}` |
| news-orchestrator | news-generator | (similar pattern) |
| news-orchestrator | news-processor | (similar pattern) |

### Migration Impact: **MEDIUM**

All inter-service URLs must become environment-variable-driven:
```python
# Before (hardcoded Docker hostname)
url = "http://development-tour-generator-1:5000/generate"

# After (env-var-driven)
url = f"{os.getenv('TOUR_GENERATOR_URL', 'http://development-tour-generator-1:5000')}/generate"
```

In Cloud Run, each service gets a URL like `https://tour-generator-abc123.us-central1.run.app`. These URLs are injected as env vars during deployment.

---

## 5. Environment Variables & Secrets

### 5.1 Secrets that need Secret Manager

| Secret | Used By | Current Location |
|---|---|---|
| `OPENAI_API_KEY` | tour-generator, newsletter-processor | `.env` / docker-compose env |
| `AWS_ACCESS_KEY_ID` | polly-tts, tour-editing-phase2, translation-service | `.env` / hardcoded in docker-compose |
| `AWS_SECRET_ACCESS_KEY` | polly-tts, tour-editing-phase2, translation-service | `.env` / hardcoded in docker-compose |
| `DB_PASSWORD` | All services with DB access | Hardcoded `password123` in docker-compose |

### 5.2 Configuration env vars (not secrets)

| Var | Current Default | Cloud Value |
|---|---|---|
| `DB_HOST` | `localhost` or container name | Cloud SQL private IP or socket |
| `DB_NAME` | `audiotours` | `audiotours` (unchanged) |
| `DB_USER` | `admin` | `admin` (unchanged) |
| `DB_PORT` | `5432` | `5432` (unchanged) |
| `AWS_REGION` / `AWS_DEFAULT_REGION` | `us-east-1` | `us-east-1` (unchanged) |
| Inter-service URLs | Docker hostnames | Cloud Run service URLs |

### 5.3 Good news: DB connections already use env vars

Most services already use `os.getenv('DB_HOST', 'localhost')` pattern. This means the DB connection code works as-is — just inject the Cloud SQL host at deploy time.

---

## 6. External Dependencies (Outbound Network)

| Service | External Dependency | Protocol | Notes |
|---|---|---|---|
| tour-generator | api.openai.com | HTTPS | GPT-4o-mini for tour text |
| newsletter-processor | Various websites | HTTP/HTTPS | Web scraping (requests + beautifulsoup) |
| newsletter-processor | podcasts.apple.com, open.spotify.com | HTTPS | Podcast metadata extraction |
| polly-tts | polly.us-east-1.amazonaws.com | HTTPS | AWS Polly TTS |
| translation-service | polly.us-east-1.amazonaws.com | HTTPS | AWS Polly for translated audio |
| tour-editing-phase2 | polly.us-east-1.amazonaws.com | HTTPS | AWS Polly for edited stops |
| tour-generation-modernized | polly.us-east-1.amazonaws.com | HTTPS | AWS Polly for tour audio |
| news-processor | Google TTS (gTTS) | HTTPS | Google Translate TTS (free, may be deprecated) |
| news-generator | Google TTS (gTTS) | HTTPS | Same |

**Note:** `gTTS` (Google Translate TTS) is used by news-processor and news-generator. This is a free but unofficial API that could break. Consider migrating these to Polly as well during Phase B.

---

## 7. Health Check Readiness

| Service | Has `/health` endpoint? | Notes |
|---|---|---|
| tour-orchestrator | ✅ Yes | docker-compose-complete.yml has healthcheck |
| tour-generator | ✅ Yes | docker-compose-complete.yml has healthcheck |
| tour-processor | ✅ Yes | docker-compose-complete.yml has healthcheck |
| map-delivery | Likely yes | Shows "unhealthy" in docker ps (config issue) |
| Others | Unknown | Need to verify during Phase B |

**Phase B task:** Ensure ALL 21 services respond to `GET /health` with 200 in <1 second.

---

## 8. System Dependencies (apt packages)

| Service | System Packages | Image Size Impact |
|---|---|---|
| tour-processor | gcc, espeak, espeak-data, libespeak1, libespeak-dev, **ffmpeg** | +200 MB |
| news-processor | **ffmpeg** | +100 MB |
| newsletter-browser (not currently running) | chromium, google-chrome-stable, chromedriver | +500 MB |
| All others | gcc only (for psycopg2 build) or none | Minimal |

**Note:** The `newsletter-processor` Dockerfile is minimal (just pip installs). The heavy `Dockerfile.newsletter-browser` with Chrome is a separate image that's NOT currently running. If browser automation is needed in cloud, it would use the newsletter-browser image.

---

## 9. Migration Complexity Summary

| Category | Effort | Blocking? |
|---|---|---|
| Shared volume (`./tours`) → R2 + temp storage | **HIGH** (biggest code change) | Yes — must be done in Phase B |
| Inter-service URLs → env vars | MEDIUM (mechanical, ~21 services) | Yes — must be done in Phase B |
| DB connection strings | LOW (already env-var-driven) | No — works as-is |
| Secrets → Secret Manager | LOW (6 secrets) | Phase C |
| Blob migration (DB → R2) | MEDIUM (schema change + code) | Can be Phase D |
| Health endpoints | LOW (add to services missing them) | Phase B |
| Dockerfile cleanup (EXPOSE, CMD, PORT env) | LOW (mechanical) | Phase B |

---

## 10. Recommendations

1. **Reduce Cloud Run service count.** 21 services is a lot. Consider consolidating:
   - `tour-editing-1` (v1) is likely superseded by `tour-editing-phase2-1` (v2) — can we retire v1?
   - `development-voice-control-1` — is this used by the mobile app or only for dev testing?
   - `simple-news-search-1` and `background-article-processor-1` — are these actively used?
   
   Fewer services = simpler deployment, fewer env vars to manage, lower cognitive overhead.

2. **Tackle the shared volume first** (Phase B). This is the hardest part. Everything else is mechanical.

3. **Move blobs to R2 early** (Phase B or C). This dramatically simplifies the DB migration (40 MB vs 2.7 GB) and makes Cloud SQL `db-f1-micro` viable for prod ($10/month instead of $25/month).

4. **Standardize Dockerfiles.** Currently there's a mix of:
   - Generic `Dockerfile` (shared by many services via different `command:` in docker-compose)
   - Service-specific `Dockerfile.<name>`
   - Subdirectory with own Dockerfile (`translation-service/`)
   
   For Cloud Run, each service needs its own self-contained Dockerfile. Phase B should create `deploy/<service>/Dockerfile` for each.

5. **Replace gTTS with Polly** in news-processor and news-generator. gTTS is an unofficial Google API that could break anytime. You already have Polly infrastructure.

---

## 11. Decision Points for Sir Michael

### Decisions captured (2026-05-28):

1. **`tour-editing-1` (port 5020):** KEEP — news_processor_service.py uses voice-control container for short title generation via this pipeline path.
2. **`voice-control` (port 5008):** KEEP for now — `news_processor_service.py` calls `5008/generate_short_title` to shorten article titles for the news/newsletter audio pipeline. The other two endpoints (`/parse_voice_search`, `/process-voice-command`) are unused server-side. `news_generator_service.py` has a duplicate inline `generate_short_title()` that doesn't use the service. Unclear which path is active; not worth the risk of dropping.
3. **`simple-news-search-1` (5016) + `background-article-processor-1` (5015):** LIKELY DEAD — prototype containers superseded by `newsletter-processor-1:5017`. **Action:** Turn off locally, have Services Amazon-Q run full newsletter pipeline tests to verify nothing breaks. If confirmed dead, exclude from cloud deployment (saves 2 services).
4. **Database tier:** `db-f1-micro` ($10/month) for prod — confirmed. Blobs move to R2.
5. **gTTS → Polly:** Already done. All 4 main voices are Polly Neural. No migration needed.

### Revised Cloud Run service count: 19 (if dead services confirmed)

- 21 total containers minus postgres (Cloud SQL) = 20 Cloud Run candidates
- Minus 2 dead services (simple-news-search, background-article-processor) = **18-19 Cloud Run services**
- Minus newsletter-browser (not currently running, only needed if browser automation required) = **18 active services**
