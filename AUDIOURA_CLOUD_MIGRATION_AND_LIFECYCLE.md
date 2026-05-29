# Audioura — Cloud Migration & Lifecycle Plan

**Drafted by:** Claude (session "Audioura Build and Start #4"), 2026-05-04. This is a SPEC for Amazon-Q to draft phase-by-phase migration assignments. Sir Michael approved the architecture (Cloud Run + Cloud SQL Postgres + Cloudflare R2) in chat 2026-05-04.

**Status:** Architecture decided. Migration not yet started. Service-by-service audit pending.

**Document location policy** (per Sir Michael's directive 2026-05-04):
- `D:\` is the USB stick — for transient files crossing machines, NOT permanent docs.
- Claude-only permanent docs: `C:\Business\audiotours.com\Claude\Audioura development\` (this folder).
- Claude + Amazon-Q shared permanent docs / outputs: `C:\Users\micha\eclipse-workspace\AudioTours\development\` (create subfolder `migration\` for migration-specific outputs).
- This file relocated from `D:\Audioura\assignments\` on 2026-05-04. The old D:\ copy is now obsolete; Sir Michael deletes it.

**Companion docs:**
- `D:\Audioura\assignments\STORE_SUBMISSION_ROADMAP.md` — App Store + Play Store submission roadmap. **TODO:** also relocate to a permanent path; currently on USB.
- `C:\Business\audiotours.com\Claude\Audioura development\Audioura_project_log.md` — running project log.

---

## 1. Goals

1. **Pay-only-for-usage** on the cloud — compute scales to zero between users, you pay per actual request.
2. **Always-on storage** — DB, audio files, newsletter content, ad-targeting data persist 24/7 for reports and ad-sales operations.
3. **No code rewrite** — same Python services, same Docker images, same Postgres schema. Connection strings and hostnames change; logic doesn't.
4. **Continue local development** — the laptop's Docker Compose stack stays the dev environment. Cloud is the production target.
5. **Zero-downtime PreProd → Prod cutover.** Standard cloud-native canary pattern.
6. **Fast rollback** if a catastrophic bug reaches production — minutes, not hours.
7. **Clean PreProd ↔ Prod isolation** — bugs in PreProd don't affect Prod, and PreProd uses non-production data.

---

## 2. Current state inventory (per `remind_Services_ai.md` + `remind_ai.md`)

### 2.1 Services (13 total)

| Service | Port | Role | Notes |
|---|---|---|---|
| tour-processor | 5001 | Tour generation + MP3 creation | Likely heavy CPU (audio synthesis) |
| tour-orchestrator | 5002 | Tour workflow coordination | Calls tour-generator, tour-processor, polly-tts |
| tour-generator | 5000 | AI prompt-based tour text generation | OpenAI API outbound |
| postgres | 5432 | PostgreSQL DB | The single source of truth |
| map-delivery | 5005 | Map + tour delivery to mobile app | Handles `tours-near` queries |
| coordinates | 5006 | Location services | |
| treats | 5007 | Local treats / POIs | Has image_base64 in DB |
| news-orchestrator | 5012 | News workflow coordination | |
| news-generator | 5010 | News content processing | |
| news-processor | 5011 | News audio generation | |
| newsletter-processor | 5017 | Newsletter crawling + Spotify/Apple Podcasts scraping | **Heavy** — browser automation, needs Chrome runtime |
| polly-tts | 5018 | Amazon Polly TTS wrapper | **AWS dependency** — calls AWS API |
| translation-service | 5030 | Multi-language translation | |

### 2.2 External dependencies

- **OpenAI API** (tour-generator, possibly news-generator) — outbound HTTPS to api.openai.com.
- **AWS Polly** (polly-tts) — AWS account + IAM credentials needed regardless of compute platform.
- **Spotify / Apple Podcasts public pages** (newsletter-processor) — outbound web scraping via headless browser.

### 2.3 Database schema (per remind_ai.md)

```sql
tour_requests(id, tour_id, request_string, status, finished_at, coordinates)
audio_tours(id, tour_name, tour_data, coordinates)
treats(id, name, description, lat, lng, image_base64)
article_requests(article_id, article_text, request_string, status, major_points)
news_audios(article_id, article_name, news_article)
newsletters(id, url, name, created_at)
newsletters_article_link(newsletter_id, article_requests_id)
```

**Storage size question to answer during audit:** are large blobs stored in Postgres (`tour_data`, `news_article`, `image_base64`)? If yes, migrating those blobs to R2 cuts DB cost and improves scaling. If they're already references (URLs/keys), good as-is.

### 2.4 Current dev workflow

1. Edit Python file in `c:\Users\micha\eclipse-workspace\AudioTours\development\`.
2. `docker cp <file> <container>:/app/<file>`
3. `docker restart <container>`
4. Test from mobile app or curl.
5. Commit + push to GitHub `Newsletters` branch (or `main`).

This loop is fast — under a minute end-to-end. **The migration must preserve this.** Cloud deployment is a separate path from local dev iteration.

---

## 3. Target architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Mobile App (iOS / Android)                                             │
│  - Calls https://api.audioura.com                                        │
│  - Downloads audio from https://media.audioura.com (Cloudflare R2)       │
└────────────────────────┬────────────────────────────────────────────────┘
                         │ HTTPS
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Cloudflare DNS + Edge                                                  │
│  - api.audioura.com → Google Cloud Load Balancer / Cloud Run             │
│  - media.audioura.com → Cloudflare R2 bucket (audio files)               │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Google Cloud Project: audioura-prod (and audioura-preprod)             │
│                                                                         │
│  Cloud Run services (one per Docker service, 13 total):                 │
│    tour-orchestrator, tour-generator, tour-processor, map-delivery,    │
│    coordinates, treats, news-orchestrator, news-generator,              │
│    news-processor, newsletter-processor (heavier sizing),               │
│    polly-tts, translation-service                                       │
│                                                                         │
│  Each scales 0 → N concurrent based on load. Idle = $0/service.         │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Cloud SQL Postgres (always-on, db-g1-small)                    │    │
│  │  Single instance for relational data, ~$10–25/month             │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Secret Manager (OpenAI key, Polly creds, R2 keys, DB password) │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Artifact Registry (Docker images, one repo per service)        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└────────────────────────┬────────────────────────────────────────────────┘
                         │ outbound
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  External APIs                                                          │
│  - api.openai.com (tour generation, news processing)                    │
│  - polly.us-east-1.amazonaws.com (TTS)                                  │
│  - Spotify / Apple Podcasts public pages (newsletter scraping)          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.1 Why this shape

- **Cloud Run per service** instead of one giant service: matches current Docker Compose structure exactly. Each service scales independently (newsletter-processor, which does browser automation, can be sized at 2 vCPU + 4 GB without paying that for tour-orchestrator which is mostly I/O bound).
- **Cloud SQL Postgres** instead of Aurora Serverless v2: simpler, predictable cost, no cold-start, plenty of capacity for the next 12 months at $10-25/month tier. Migrate to a larger instance only when monitoring data justifies it.
- **Cloudflare R2 for audio files** instead of GCS: zero egress fees. Audio playback = lots of egress. R2's $0/GB egress vs GCS's $0.12/GB egress is 100% savings on the dominant cost line for an audio-tour app at scale.
- **AWS Polly stays** because the polly-tts service already wraps it. Migrating off Polly is a separate decision (could move to GCP Text-to-Speech to consolidate clouds; not blocking for migration).
- **Two GCP projects** (`audioura-preprod` and `audioura-prod`): hard isolation — IAM, billing, networking all separated. PreProd outage cannot touch Prod. Easy to give Amazon-Q access to PreProd without granting Prod permissions.

### 3.2 What does NOT change

- The Flask service code.
- The Docker images (built the same way, just pushed to a remote registry).
- The Postgres schema (migrated via `pg_dump | pg_restore`).
- The mobile app's API contract.
- The dev workflow on the laptop (still `docker compose up`).
- The OpenAI / AWS Polly / scraping integrations.

### 3.3 Special handling: newsletter-processor

Browser automation (`browser_automation.py`) needs:
- Chromium runtime (~200 MB image overhead).
- 2 vCPU, 2-4 GB RAM (browser launch is RAM-hungry).
- Long timeout — Cloud Run default is 5 minutes; newsletter scraping with anti-bot retries can hit that. Configure with `--timeout=900` (15 min, the Cloud Run max).
- Concurrency = 1 (one browser per instance) so heavy requests don't block each other.
- This service runs at higher cost-per-invocation than the others. May be worth investigating moving newsletter scraping to Cloud Run Jobs (background tasks) if real-time response isn't needed for newsletter ingestion.

### 3.4 Special handling: tour-processor + polly-tts

Audio synthesis is bursty. A single tour generates 5+ MP3 files (one per stop). Each Polly call is fast but the workflow can take 30-60 seconds total. Configure Cloud Run for these two services with:
- 2 vCPU, 1-2 GB RAM.
- Concurrency = 5-10 (multiple tours can be processed in parallel by one instance).
- Timeout = 300 seconds (5 min) — generous but fits within Cloud Run limits.

---

## 4. Migration plan (one-time, ~20-30 hours of focused work)

Broken into 5 phases. Each phase is a separable Amazon-Q assignment that Claude reviews before execution.

**Output directory for migration phase result files:** `C:\Users\micha\eclipse-workspace\AudioTours\development\migration\` (Claude + Amazon-Q shared, NOT on USB). Create the subfolder during Phase A.

### Phase A — Pre-migration audit (Assignment M01, ~2 hours)

**Goal:** Confirm the architecture matches reality. No deployments yet.

**Tasks for Amazon-Q:**

1. List every Dockerfile in the dev directory; capture base image + dependencies for each service.
2. Inspect each `docker-compose.yml` — list volumes (which services have persistent local volumes? those become R2 / Cloud SQL targets), networks (any non-trivial internal routing?), env vars (which need to become Secret Manager entries?).
3. For each service, identify "stateful interactions": writing files to disk that survive across requests, holding in-memory caches, etc.
4. `docker exec development-postgres-2-1 psql -U admin -d audiotours -c "\dt"` — actual table list.
5. For each table, get row count + average row size + total table size. Pay specific attention to `audio_tours.tour_data`, `news_audios.news_article`, `treats.image_base64` — if these contain blobs > 100 KB, plan to migrate them to R2 and replace with R2 keys.
6. List outbound external dependencies per service (pip packages that hit the network, hardcoded URLs).

**Output:** `C:\Users\micha\eclipse-workspace\AudioTours\development\migration\m01_audit_results.md` with a table of all 13 services + their migration considerations.

**Why this matters:** if a service writes uploaded files to a local volume, that volume migrates to R2 with a code change. We need to know about it before deploying, not during.

### Phase B — Local "cloud-ready" rehearsal (Assignment M02, ~3 hours)

**Goal:** Make sure each service runs the same way it will in Cloud Run, *while still on the laptop*. Catches "works on my Docker Compose" issues before they cost real money.

**Tasks for Amazon-Q:**

1. For each service, ensure the Dockerfile has an explicit `EXPOSE <port>` and a `CMD` that starts the server bound to `0.0.0.0:$PORT` (Cloud Run injects `PORT` env var).
2. Replace any `localhost:5432` / `host.docker.internal:5432` Postgres references with an env-var-driven `DATABASE_URL`.
3. Replace any local file writes (audio files, etc.) with object-storage calls behind a feature flag — file → R2 path. Test locally with a MinIO container (S3-compatible local) so R2 doesn't cost anything yet.
4. Each service should respond to `GET /health` with a 200 in under 1s. Cloud Run uses this for liveness.
5. Run all 13 services locally with the new config; smoke-test the mobile app against them.

**Validation:** mobile app talks to local services via env-var-driven config; tour generation + news + newsletter all work.

**Why this matters:** a Cloud Run deployment that fails due to a hardcoded `localhost` reference burns ~10 min per debug cycle. Catching them locally is free.

### Phase C — GCP project setup (Assignment M03, ~3 hours)

**Goal:** Both GCP projects exist with all infrastructure but zero services deployed yet.

**⚠️ Phase C is when GCP billing starts.** See §9.5 for the detailed breakdown of what costs money the moment you complete this phase vs what stays free until you actually deploy.

**Tasks for Amazon-Q (PowerShell on the laptop, since Amazon-Q has access there):**

1. Create two GCP projects: `audioura-preprod`, `audioura-prod`. Different billing accounts if you want strict separation.
2. Enable APIs in each: `run.googleapis.com`, `sqladmin.googleapis.com`, `secretmanager.googleapis.com`, `artifactregistry.googleapis.com`, `compute.googleapis.com` (for VPC if needed).
3. Create Artifact Registry Docker repos in each project (e.g. `us-central1-docker.pkg.dev/audioura-preprod/services/`).
4. Provision **Cloud SQL Postgres**: `db-g1-small` in `audioura-preprod`, same tier in `audioura-prod`. Postgres 15 (matches current dev). Private IP only (Cloud Run connects via Cloud SQL Auth Proxy). **This is the primary cost driver — meter starts now.**
5. Set up **Secret Manager** entries: `openai-api-key`, `polly-aws-access-key`, `polly-aws-secret`, `r2-access-key`, `r2-secret-key`, `db-password`. Per-project secrets.
6. Create the Cloudflare R2 bucket (one for prod, one for preprod). Get S3-compatible access keys.
7. Reserve the production hostname `api.audioura.com` in Cloudflare DNS, but don't point it anywhere yet. Same for `media.audioura.com`.

**Validation:** `gcloud run services list --project audioura-preprod` returns empty (good — nothing deployed yet); Cloud SQL is up; Secret Manager has all entries.

### Phase D — Service-by-service migration to PreProd (Assignment M04, ~10-15 hours)

**Goal:** All 13 services running in `audioura-preprod`, callable via Cloud Run URLs, talking to Cloud SQL preprod and R2 preprod buckets.

**Pattern per service** (Amazon-Q drafts a script that does this for all 13):

1. `docker build` the service image, tag as `us-central1-docker.pkg.dev/audioura-preprod/services/<service-name>:v1`.
2. `docker push` to Artifact Registry.
3. `gcloud run deploy <service-name>` with appropriate `--memory`, `--cpu`, `--timeout`, `--concurrency`, `--set-env-vars`, `--set-secrets`, `--add-cloudsql-instances` flags.
4. Get the service URL: `gcloud run services describe <service-name> --format="value(status.url)"`.
5. Verify the service health: `curl <service-url>/health`.
6. Move to the next service.

**Service-specific config table (Amazon-Q to use this as the deployment matrix):**

| Service | Memory | CPU | Concurrency | Timeout | Special |
|---|---|---|---|---|---|
| tour-orchestrator | 512 Mi | 1 | 80 | 300 | — |
| tour-generator | 512 Mi | 1 | 40 | 300 | OpenAI calls |
| tour-processor | 1 Gi | 2 | 5 | 300 | Audio synthesis |
| map-delivery | 256 Mi | 1 | 80 | 60 | — |
| coordinates | 256 Mi | 1 | 80 | 60 | — |
| treats | 256 Mi | 1 | 80 | 60 | — |
| news-orchestrator | 512 Mi | 1 | 40 | 300 | — |
| news-generator | 512 Mi | 1 | 40 | 300 | — |
| news-processor | 1 Gi | 2 | 5 | 300 | Audio synthesis |
| newsletter-processor | 4 Gi | 2 | 1 | 900 | **Browser automation; 1 concurrency only** |
| polly-tts | 512 Mi | 1 | 20 | 60 | AWS Polly outbound |
| translation-service | 512 Mi | 1 | 40 | 60 | — |
| postgres | — | — | — | — | **Not Cloud Run — Cloud SQL handles this** |

**Database migration sub-task:**

7. `docker exec development-postgres-2-1 pg_dump -U admin audiotours > audiotours_dump.sql` on the laptop.
8. Connect to Cloud SQL preprod via Cloud SQL Auth Proxy: `cloud_sql_proxy -instances=audioura-preprod:us-central1:audioura=tcp:5432`.
9. `psql -h localhost -U postgres -d audiotours -f audiotours_dump.sql`.
10. Verify table counts match the dev DB.

**Validation:**

- All 13 services return 200 from `/health` via their Cloud Run URLs.
- A test tour-generation request through tour-orchestrator's Cloud Run URL completes successfully end-to-end (calls tour-generator → AI → tour-processor → Polly → R2 upload → DB insert → returns tour ID).
- The mobile app, with its `BACKEND_BASE_URL` temporarily pointed at the preprod orchestrator URL, can list tours and play audio.

### Phase E — Production cutover (Assignment M05, ~2-4 hours)

**Goal:** `audioura-prod` is live; `api.audioura.com` resolves to it; mobile app release builds use it.

**Tasks for Amazon-Q:**

1. Repeat Phase D's build + deploy pattern, but pushing to `audioura-prod` registry and deploying to `audioura-prod` Cloud Run.
2. Migrate prod database: `pg_dump` from preprod (which has been validated), `pg_restore` into prod Cloud SQL. Or for the very first prod cutover, pg_dump from the laptop dev DB to prod.
3. Set up subdomain mappings (option (b) from §9.1) OR Cloud Load Balancer (option (a)) — chosen by Sir Michael's decision in §10.
4. Cloudflare DNS: point chosen domains at the prod backend.
5. Point `media.audioura.com` at the prod R2 bucket.
6. Update mobile app config: release builds use `https://api.audioura.com` and `https://media.audioura.com`.

**Validation:**

- `curl https://api.audioura.com/health` returns 200.
- Mobile app, rebuilt with prod config, generates tours end-to-end.
- All Cloud Run services have valid revisions; traffic is at 100% on the latest revision.

---

## 5. Continuing development + bug fixes (after migration)

The dev workflow on the laptop **does not change**. Cloud is added as a deploy target, not a development environment.

### 5.1 Daily dev cycle (laptop, unchanged)

```bash
# Edit a file
vim tour_orchestrator_service.py

# Hot-deploy to local container (existing pattern)
docker cp tour_orchestrator_service.py development-tour-orchestrator-1:/app/
docker restart development-tour-orchestrator-1

# Test from mobile app pointing at local backend (192.168.x.y:5002)
# OR via curl
curl -X POST http://localhost:5002/generate-complete-tour ...

# Commit when working
git add tour_orchestrator_service.py
git commit -m "Fix tour stop count edge case"
git push origin Newsletters
```

This is the existing workflow. After migration, it stays exactly the same. The laptop's Docker Compose talks to the laptop's Postgres. No cloud involved.

### 5.1.1 Disaster recovery (if the laptop dies)

Today the laptop is a single point of failure for the dev environment. After migration the cloud is fine, but local dev still depends on the laptop. Mitigations:

- **Source code:** already on GitHub (`Audioura` repo, branches `main` + `Newsletters`). Survives laptop death.
- **Local Postgres:** add a daily `pg_dump` to a Google Cloud Storage bucket (or any other off-machine target). One-line cron job. Restoring is `pg_restore` on a fresh laptop — 10 minutes.
- **Local audio files:** if any are on the local filesystem (not in DB), back up to the same GCS bucket.
- **`.env` files + secrets:** copy to a password manager (1Password, Bitwarden, Apple Keychain). NEVER commit to GitHub.
- **Configuration files** (Docker Compose, build scripts, etc.): they're in GitHub. Commit any local modifications.
- **Mac Mini state:** Xcode signing identities and provisioning profiles live in the keychain. Export them to encrypted files in GCS or a USB key kept off-machine. Apple Developer Program membership and bundle ID survive — only the local keychain copy is at risk.

A laptop death recovery run-book lives in §12.5 for explicit steps.

### 5.2 Pushing a fix to PreProd cloud (new workflow, simple)

When a fix is ready for cloud testing:

```bash
# Build production image
cd c:\Users\micha\eclipse-workspace\AudioTours\development
./scripts/build_and_push.sh tour-orchestrator preprod
# This script does:
#   docker build -t us-central1-docker.pkg.dev/audioura-preprod/services/tour-orchestrator:v26 .
#   docker push us-central1-docker.pkg.dev/audioura-preprod/services/tour-orchestrator:v26
#   gcloud run deploy tour-orchestrator --image=...:v26 --region=us-central1 --project=audioura-preprod

# That's it. Cloud Run provisions the new revision, shifts 100% traffic to it (default).
# If the build is broken, you can roll back instantly (see §8).
```

Amazon-Q drafts `build_and_push.sh` once during Phase D. Re-used forever.

### 5.2.1 What `build_and_push.sh` does in detail

```bash
#!/bin/bash
# Usage: ./build_and_push.sh <service-name> <env>
# <env> is "preprod" or "prod"
# Reads the active git tag/version for image tagging.

SERVICE="$1"
ENV="$2"
PROJECT="audioura-${ENV}"
REGION="us-central1"
VERSION=$(git describe --tags --always)   # e.g. "1.2.10-3-g4abc"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/services/${SERVICE}:${VERSION}"

# 1. Build the Docker image from this service's directory (per-service Dockerfile).
docker build -t "${IMAGE}" "./${SERVICE}/"

# 2. Push to Artifact Registry (the project-specific Docker registry).
docker push "${IMAGE}"

# 3. Deploy to Cloud Run.
#    - Reads service-specific config from a YAML manifest (memory, cpu, concurrency, timeout, env, secrets).
#    - Default behavior: shift 100% traffic to the new revision. Override with --no-traffic for canary.
gcloud run deploy "${SERVICE}" \
    --image="${IMAGE}" \
    --region="${REGION}" \
    --project="${PROJECT}" \
    --config-from-file="./deploy/${SERVICE}.yaml"
```

The per-service YAML manifests are checked into the repo and version-controlled, so the deployment config is reproducible. Amazon-Q drafts these in Phase D.

### 5.3 Local dev testing against cloud services (occasional)

If you need to test the mobile app against the cloud while still iterating on a service:

```bash
# Mobile app config: BACKEND_BASE_URL = https://preprod-api.audioura.com
# Build + install on physical device
flutter build ios --release
# Install via the existing build_install_launch_a28.sh on Mac Mini
```

The mobile app on the device hits the cloud preprod endpoint. The laptop's local Docker stack is bypassed (or used in parallel for backend dev).

### 5.4 Bug fix workflow (recommended)

1. Reproduce locally first. Local dev cycle is faster than cloud.
2. Fix in local Docker Compose, test there.
3. Commit to GitHub `Newsletters` branch.
4. Push to PreProd via `build_and_push.sh <service> preprod`. Test there.
5. After PreProd validation (1+ days of testing), promote to Prod via traffic shift (see §7).

---

## 6. PreProd release + testing

PreProd is identical to Prod in every way except: separate GCP project, separate database, separate R2 bucket, separate hostname (`preprod-api.audioura.com`).

### 6.0 Why preprod gets its own database (and not "shared")

Sharing one database across preprod and prod looks tempting (saves money) but breaks the entire purpose of preprod:

- **Schema migrations.** Testing a migration against shared DB risks corrupting prod data. Separate DB lets you destructively test.
- **Test data.** Preprod tests need fixtures, edge-case rows, and may delete data. None of that should touch prod records.
- **Performance isolation.** A runaway test query on shared DB slows prod for real users.
- **Ad-sale & report integrity.** Prod data feeds revenue-critical reports and ad-targeting. Mixed test rows poison those.
- **Compliance.** GDPR / CCPA require clear data boundaries — test data should not commingle with real user PII.

Cost is small ($10-25/month for the small preprod instance). The isolation guarantee is what you're paying for. Shared DB across dev + preprod + prod is a class of mistake that causes outages later.

### 6.1 What runs in PreProd

- All 13 Cloud Run services, latest builds.
- Cloud SQL preprod instance, populated with full schema (must match prod exactly so migrations transfer cleanly) but only test/sample data — NOT a copy of prod records.
- R2 preprod bucket.
- Distinct domain: `preprod-api.audioura.com` and `preprod-media.audioura.com`.

### 6.1.1 Distinct domain — what it buys you

- **Mobile app build separation.** Debug iOS builds + TestFlight internal builds point at preprod hostname; release builds point at prod hostname. Both compiled into different `BACKEND_BASE_URL` constants by build flag.
- **TLS certificate isolation.** Preprod cert is separate from prod cert. Cert errors in preprod don't affect prod users.
- **Audit logs make environment obvious.** Cloudflare/Cloud Run logs show which hostname was hit; you instantly know if a request came from a tester or from production.
- **Public access control.** You can require Cloudflare Access (free, single-sign-on auth) on `preprod-api.audioura.com` so only known testers reach it; prod stays open to the public.
- **DNS sanity check.** A bug pointing the prod app at preprod hostname would be caught in code review; a bug pointing it at the same hostname as dev would not.

Cost is zero — adding a subdomain to a Cloudflare-hosted domain is free.

### 6.2 PreProd lifecycle — always-on or spin up/down?

Two options:

- **Always-on PreProd** (recommended). Cloud SQL preprod = ~$10/month for the small instance. Cloud Run services scale to zero when idle (no per-service cost). Total preprod overhead: about $10/month. You can start a test session at any time without 30-minute setup overhead.
- **Spin up/down PreProd.** Stop the Cloud SQL instance between testing sessions (saves the $10/month). To resume: start the instance (~5 min), maybe restore a snapshot (~5-10 min). 30 minutes total per session. Reasonable if you test once a month, not if you test weekly.

For active development, always-on saves time at small cost. Once Audioura is stable and releases are infrequent (say, one release per quarter), switch to spin up/down to save the small monthly fee. Cloud SQL has a "stop/start" API that takes ~5 minutes — worth scripting.

### 6.3 Who has access

- Sir Michael (full).
- Internal TestFlight testers (their builds point at preprod).
- Amazon-Q (deploy + view logs, no DB write outside dev tasks).
- NOT external testers, NOT Apple's App Review, NOT real users — those all hit Prod.

### 6.4 Testing checklist before promoting a build to Prod

For each significant release (e.g. `1.2.9+25` → `1.2.10+0` if you bump minor version):

1. Mobile app smoke test on PreProd: tour generation, news playback, newsletter ingestion, language switch, voice control.
2. Server-side functional tests: curl-based tests of each major endpoint via the preprod Cloud Run URLs.
3. Performance check: a tour generation completes in <60s end-to-end (close to local dev performance).
4. Database health: row counts increment as expected; no errors in Cloud Run logs.
5. R2 bucket: new audio files appear; signed URLs work from the mobile app.
6. Cost sanity: GCP billing dashboard for the preprod project — no unexpected spend.

If all green for 1-3 days of soak time, promote to Prod.

---

## 7. PreProd → Prod cutover with zero downtime

Cloud Run does this natively via **revisions and traffic splitting**. No extra tooling needed.

### 7.1 The mechanism

Every `gcloud run deploy` creates a new immutable revision (e.g. `tour-orchestrator-00026-abc`). By default, the new revision serves 100% of traffic immediately. But you can override that:

```bash
# Deploy without traffic
gcloud run deploy tour-orchestrator \
    --image=...:v26 \
    --no-traffic \
    --project=audioura-prod

# Now revision -00026-abc exists but serves 0% of traffic.
# Test it directly via its revision-specific URL:
gcloud run services describe tour-orchestrator \
    --format="value(status.traffic[0].url)" \
    --project=audioura-prod

# Shift traffic gradually:
gcloud run services update-traffic tour-orchestrator \
    --to-revisions=tour-orchestrator-00026-abc=10 \
    --project=audioura-prod
# 10% of traffic now hits the new revision.

# Watch logs/metrics for ~10 minutes. If healthy:
gcloud run services update-traffic tour-orchestrator \
    --to-revisions=tour-orchestrator-00026-abc=50

# Watch ~10 more min. If still healthy:
gcloud run services update-traffic tour-orchestrator \
    --to-revisions=tour-orchestrator-00026-abc=100

# Done. The previous revision is still there, ready for instant rollback.
```

### 7.1.1 "Where do the other 90% go?" — clarified

When traffic is split 10/90 between revision N+1 and revision N: **Cloud Run keeps BOTH revisions running simultaneously.** Each request is routed to one revision based on the configured percentages. There is briefly "two production environments" running side by side, but they share the same Cloud SQL database, the same R2 bucket, the same Secret Manager entries, the same domain — only the running container code differs.

This is normal and intentional. The same machine could serve a tour from N+1 to user A while serving the very next tour from N to user B. Both write to the same DB rows. Both look the same to users. The point is to find out if N+1 is broken on a small fraction of real traffic before exposing all users to it.

When you settle at 100% on N+1, the N revision keeps existing in Cloud Run's revision history for instant rollback (see §8) but receives 0% traffic — so it costs nothing, just sits in Artifact Registry as an image. After several successful releases, you can prune older revisions if storage matters.

### 7.2 Cutover script

Amazon-Q drafts `promote_to_prod.sh <service> <preprod-revision-tag>` that:

1. Pulls the validated PreProd image.
2. Re-tags it as a Prod image.
3. Pushes to Prod Artifact Registry.
4. Deploys to Prod Cloud Run with `--no-traffic`.
5. Echoes the revision-specific test URL for manual smoke testing.
6. Awaits human input ("OK to proceed to 10%?") before each traffic shift.
7. Shifts 0 → 10% → 50% → 100% with monitoring pauses.

### 7.3 Database schema changes — what's safe and what isn't

You said: "I assume I would change database schema only by adding tables and fields and triggers and cursors without breaking the existing contracts from release to release."

**That is the right discipline and it covers the vast majority of cases.** Everything below works without breaking anything:

- Adding a new table.
- Adding a new column with a default value (or NULL allowed).
- Adding an index (including unique if the data already has no duplicates).
- Adding a trigger that doesn't change existing rows' visible state.
- Adding a stored function / procedure / cursor.
- Adding a new view.
- Adding a new constraint that all existing rows already satisfy.
- Increasing a column's max length (e.g. VARCHAR(50) → VARCHAR(100)).
- Backfilling values into a new column with a separate, idempotent script.

Cases that **cannot** be done with pure additive changes (these need maintenance windows or expand/contract patterns):

1. **Renaming a column.** Old code reads `tour_name`; new code reads `title`. Old code crashes if you rename. Solution: add `title` as a new column, update writes to populate both, update reads to prefer `title` and fall back to `tour_name`, then in a later release drop the old column.
2. **Changing a column's type** in an incompatible way (e.g. INT → UUID). Same expand/contract pattern.
3. **Adding NOT NULL to an existing column** when some rows have NULL. Backfill first, then add the constraint.
4. **Splitting one column into multiple** (e.g. `full_name` → `first_name` + `last_name`). Add new columns, populate, switch reads, drop old.
5. **Removing a column** that old code still reads. Stop reading first, deploy several releases without reads, then drop.
6. **Changing primary key** or foreign key relationships. This is genuinely hard and usually needs a maintenance window.
7. **Renaming a table.** Same as renaming a column but bigger.
8. **Reordering columns** in a way that affects `SELECT *` callers. Avoid `SELECT *` in service code; use explicit column lists.

Practical advice: 95% of schema changes during normal feature development are additive and safe. The disciplined cases above only come up during major refactors. When they do, plan a single 5-minute maintenance window — far simpler than expand/contract for a small project.

### 7.4 Mobile app coordination

Mobile app releases are independent of backend releases (the mobile app is in user-controlled stores; backend is yours). The contract:

- New backend = old mobile clients still work (backwards-compatible API).
- New mobile clients = old backend still works (additive features, version-flagged).

Mobile app version checking: include `App-Version: 1.2.9+25` header on every request. If you ever need to force-upgrade, the orchestrator can return 426 "Upgrade Required" for known-broken versions.

### 7.5 Mobile app environment configuration

The current dev mobile app talks to `http://192.168.0.218:5005` — modifiable IP, fixed port, plain HTTP. After migration, three changes are needed:

1. **HTTPS only** for prod and preprod. Apple ATS requires it; both preprod and prod will use Cloudflare-fronted certs.
2. **DNS hostnames instead of raw IPs.** `https://api.audioura.com` (prod), `https://preprod-api.audioura.com` (preprod). The home network IP becomes a *dev-only* fallback.
3. **Compile-time environment selection,** not runtime. Release builds must NEVER include the home-network IP — that's a security and reliability risk.

Recommended mobile-app code structure:

```dart
// lib/config/api_config.dart
class ApiConfig {
  // Build flags injected via --dart-define, default to prod.
  static const String env = String.fromEnvironment(
    'AUDIOURA_ENV',
    defaultValue: 'prod',
  );

  static const _backendUrls = {
    'dev':     'http://192.168.0.218:5005',     // home network only
    'preprod': 'https://preprod-api.audioura.com',
    'prod':    'https://api.audioura.com',
  };

  static const _mediaUrls = {
    'dev':     'http://192.168.0.218:5005',
    'preprod': 'https://preprod-media.audioura.com',
    'prod':    'https://media.audioura.com',
  };

  static String get backendBaseUrl => _backendUrls[env]!;
  static String get mediaBaseUrl    => _mediaUrls[env]!;
}
```

Build commands for each environment:

```bash
# Local dev build (talks to home network)
flutter build apk --debug --dart-define=AUDIOURA_ENV=dev

# Internal TestFlight build (talks to preprod)
flutter build ios --release --dart-define=AUDIOURA_ENV=preprod

# App Store / Play Store build (talks to prod)
flutter build ios --release --dart-define=AUDIOURA_ENV=prod
flutter build appbundle --release --dart-define=AUDIOURA_ENV=prod
```

This eliminates a whole class of bugs (release build pointing at dev backend, dev build pointing at prod, etc.). The backend URLs and the choice of HTTP vs HTTPS are baked into each binary.

`Info.plist` ATS lock-down (planned in the Store Submission Roadmap A31) goes well with this — release builds disallow plain HTTP, dev builds keep an exception for the local IP. Two `Info.plist` variants per build flavor, generated from the build flag.

---

## 8. Production rollback if catastrophic bug found by users

### 8.1 Instant rollback (Cloud Run revision shift)

```bash
# Find the previous good revision:
gcloud run revisions list \
    --service=tour-orchestrator \
    --project=audioura-prod \
    --format="value(name,status.conditions[0].lastTransitionTime)"

# Shift 100% traffic back:
gcloud run services update-traffic tour-orchestrator \
    --to-revisions=tour-orchestrator-00025-prev=100 \
    --project=audioura-prod
```

This takes effect in seconds. Everyone hitting `api.audioura.com` is now served by the old revision.

Amazon-Q drafts `rollback_prod.sh <service>` that lists recent revisions, prompts for which one to roll back to, and executes the traffic shift.

### 8.2 What "catastrophic" means

Rollback is appropriate when:
- New revision has a fatal bug (crashes, returns 500s, corrupts data).
- New revision has a regression that affects a meaningful fraction of users.
- New revision causes unexpected spike in OpenAI / Polly costs.

Rollback is NOT the right tool when:
- Bug is fixable with a hot-fix faster than rollback discipline (e.g. typo in a string).
- Schema migration in the new revision is non-trivial to reverse.

### 8.3 Database considerations during rollback

If the bad revision wrote bad data to the DB:

1. Roll back Cloud Run first (stops the bleeding).
2. Identify what the bad revision wrote — typically by `created_at` filter for the affected window.
3. Decide: roll back DB to a backup (Cloud SQL has automatic point-in-time recovery up to 7 days), OR write a corrective migration that fixes the bad rows.

Cloud SQL automated backups: enabled by default, 7-day PITR window. Restore to a NEW instance to inspect, then either swap or migrate good rows back.

### 8.4 Communicating with users during a rollback

For your scale (testers + early users), in-app banner or push notification ("We've rolled back a recent update due to issues. Please update the app when prompted.") is sufficient. Larger user bases need status pages, email, etc. — out of scope for v1.

### 8.5 Post-mortem after every rollback

For each rollback event, record:
- What broke (symptom).
- Which revision introduced it.
- How it was caught (user report? monitoring alert? manual smoke test?).
- What was missing in PreProd testing that let it through.
- Rollback time (how many minutes from "user reports broken" to "100% on old revision").

This drives PreProd test improvements and shortens future MTTR.

---

## 9. Cost model

### 9.1 Floor (zero users)

| Item | Cost/month |
|---|---|
| Cloud Run (all 13 services idle) | $0 |
| Cloud SQL Postgres (db-g1-small, prod) | ~$25 |
| Cloud SQL Postgres (db-f1-micro, preprod) | ~$10 |
| R2 storage (10 GB combined) | $0.15 |
| Cloud Storage (operational, 1 GB) | $0.02 |
| Secret Manager | $0.06 (6 secrets × 2 projects) |
| Artifact Registry (5 GB combined) | $0.50 |
| Cloud Load Balancer (forwarding rule) | $18 |
| **Floor total** | **~$54/month** |

### 9.1.1 Subdomain strategy — what option (b) is and why $18 matters

Cloud Run services have built-in URLs (e.g. `tour-orchestrator-abc123.us-central1.run.app`) that work out of the box but aren't memorable or stable. To use a custom domain like `api.audioura.com`, you have two options:

- **Option (a): Cloud Load Balancer.** One IP, path-based routing (`/tour/*`, `/news/*`, etc.) routed to the right Cloud Run service. **Costs $18/month** for the forwarding rule plus a few cents for traffic. Pro: one hostname for the mobile app to talk to. Con: $18 baseline whether you use it or not.
- **Option (b): Cloud Run Domain Mappings.** Each Cloud Run service gets its own subdomain (e.g. `tours.audioura.com` → tour-orchestrator, `news.audioura.com` → news-orchestrator, etc.). **Costs $0/month.** Cloud Run handles its own TLS cert per subdomain. Pro: free. Con: mobile app needs to know multiple hostnames, and you have ~13 subdomains to manage.

The $18/month savings is for the load balancer's forwarding-rule fee — the main cost line of option (a). Option (b) is fine for v1: the mobile app can have a config map (`tour: tours.audioura.com`, `news: news.audioura.com`, etc.) and pick the right hostname per call.

When to switch from (b) to (a): when you have to reason about more than ~13 subdomains, want unified WAF/auth in front of all services, or when you need traffic-based routing rules that DNS can't express. Probably not for at least a year.

The tour orchestrator is the primary entry point — most mobile-app calls go through it — so even with option (b) the most commonly used hostname is just `tours.audioura.com` or similar.

Revised floor with (b): **~$36/month**, of which $25 is the prod DB (which Sir Michael accepts as always-on storage cost).

### 9.2 Per-user marginal cost

Negligible until thousands of DAU. Cloud Run free tier is 2M requests + 360K vCPU-seconds + 180K GiB-seconds per month. Even with 100 DAU generating 5 tours/day each, you're inside the free tier on compute. Database load is the bottleneck and `db-g1-small` handles ~50 concurrent connections fine.

### 9.3 OpenAI + Polly variable costs

These are usage-based and unrelated to backend hosting. Roughly:

- OpenAI gpt-4o-mini: $0.15 per 1M input tokens + $0.60 per 1M output tokens. A tour generation with detailed prompt is maybe 2-5K tokens total = ~$0.001-0.003 per tour.
- AWS Polly Standard voices: $4 per 1M characters. A 10-stop tour with ~500 chars per stop = ~$0.02 per tour. Neural voices are 4x more expensive.

So a complete tour costs roughly $0.025 in third-party API calls. 100 tours/day = $75/month variable cost. This dwarfs infrastructure cost and would dwarf it on any architecture.

### 9.4 Per-content cost approximations

Sir Michael's specific examples — exact math.

#### One tour: 10 POIs × 3 minutes audio = 30 min audio per language

A 30-minute audio recording at typical narration speed (150 wpm × 5 chars/word average) = ~22,500 characters of script per language.

| Component | Per-tour-per-language | At Standard Polly | At Neural Polly |
|---|---|---|---|
| OpenAI text generation (gpt-4o-mini, ~2K input + ~5K output tokens) | $0.0033 | — | — |
| Polly TTS (22.5K chars) | — | $0.090 | $0.360 |
| R2 storage (30 min mp3 ≈ 14 MB) | $0.0002/month | — | — |
| Cloud Run compute (~30s of work) | ~$0.0001 | — | — |
| **Total per tour, 1 language** | | **~$0.10** | **~$0.37** |
| **Total per tour, 5 languages** | | **~$0.40 + $0.013 OpenAI = ~$0.41** | **~$1.65 + $0.013 = ~$1.66** |

Notes:
- OpenAI cost is paid once per tour regardless of languages — the text is generated once, then translated.
- If the translation step uses OpenAI as well: add ~$0.005 per language for translation, total ~$0.04 for 5 languages of translation. Negligible.
- Storage is ongoing cost (per month), not per-tour. 100 tours × 30 min × 5 languages = 7 GB. R2 storage = ~$0.10/month.
- Egress when users download tours = $0.00 on R2 (zero egress fee). On S3 / GCS it'd be $0.09/GB and at scale this dominates.

#### One news article: 60K chars input, translated to 3 languages, audio for each

60K characters of article text = roughly 10K-12K words = roughly 70-80 minutes of audio per language.

| Component | Per-article | At Standard Polly | At Neural Polly |
|---|---|---|---|
| Translation (OpenAI for 3 languages, ~60K chars × 3 = 180K chars ≈ 45K tokens) | $0.025 | — | — |
| Polly TTS (60K chars × 3 languages = 180K chars total) | — | $0.72 | $2.88 |
| R2 storage (3 × ~35 MB per language ≈ 105 MB per article) | $0.002/month | — | — |
| Cloud Run compute (~3-5 min of work spread across services) | ~$0.001 | — | — |
| **Total per article (3 languages, including original)** | | **~$0.75** | **~$2.91** |

Notes:
- News articles are ~7-30× more expensive than tours per delivery, because of the much larger character volume (60K vs ~22.5K and audio length is proportional).
- This argues strongly for **caching translated audio**: if 100 users listen to the same translated article, you generate it once and serve 100 R2 downloads (zero egress) — cost stays at $0.75 total, not 100 × $0.75.
- Polly Neural is 4× more expensive than Standard for the same text. For news articles (which testers will compare to existing podcast quality), Neural is probably worth it. For tours, Standard is fine.

#### Combined break-even thinking

If you charge users $X per article or per tour, you need:
- $X > Polly cost (the only true variable cost) for unit economics to work.
- Plus a margin to cover OpenAI, fixed infra, and your time.

Round numbers: news articles in 3 languages cost you ~$0.75 (Standard) or ~$2.91 (Neural). For sustainable per-article billing, charge at least $1-3 per article-pack or a subscription that covers 10-50 articles/month.

### 9.5 When does GCP billing start, and on what?

Concrete answer:

| GCP resource | Costs money the moment it's created? | Per-use only? |
|---|---|---|
| GCP project (the project itself) | No | — |
| Enabling APIs (`run.googleapis.com`, etc.) | No | — |
| Artifact Registry (Docker repo) | Free until you push images | Per-GB stored after first 0.5 GB free |
| Cloud Run service (no traffic, no min-instances) | No | Per-request only |
| Cloud Run service with `--min-instances=1` | YES | — (always-on) |
| **Cloud SQL Postgres instance (db-g1-small)** | **YES — $25/month from creation** | — |
| **Cloud SQL preprod (db-f1-micro)** | **YES — $10/month from creation** | — |
| Secret Manager (first 6 secrets × 10K accesses) | No (free tier) | After free tier |
| Cloud Load Balancer forwarding rule | YES, $18/month from creation | — |
| Cloud Storage (GCS bucket, no objects) | No | Per GB stored + per egress GB |
| Cloudflare R2 bucket (no objects) | No | Per GB stored, zero egress |
| Cloudflare DNS / Pages / Workers (free tiers) | No | — |
| Domain registration | Yes (~$15/year at registrar) | — |

**The meter starts** when Phase C (M03) provisions Cloud SQL. Until then everything is free. This means:

- **Phase A (audit), Phase B (local rehearsal):** $0 GCP cost.
- **Phase C (project setup):** ~$35/month begins (preprod DB ~$10 + prod DB ~$25). Even before deploying any services.
- **Phase D (preprod deploys):** Cloud Run free until traffic exists; first audio uploads to R2 start storage costs (~pennies).
- **Phase E (prod cutover):** Mobile app traffic begins; OpenAI/Polly variable costs begin.

To keep costs minimal during the long tail of a hobby pace:

- **Don't provision prod Cloud SQL until Phase E** (saves $25/month during M04).
- **Stop preprod Cloud SQL when not actively testing** (Cloud SQL has stop/start; saves $10/month).
- **Use db-f1-micro for preprod permanently** unless tests need more.

These optimizations save $25-35/month if the migration takes weeks; not worth optimizing for if the migration takes days.

### 9.6 Total expected monthly cost trajectory

| Stage | Floor | API costs | Total |
|---|---|---|---|
| 0 testers | $36 | $0 | ~$36/month |
| 5-20 testers, light use | $36 | $5-15 | ~$40-50 |
| 100 DAU | $36 | $50-100 | ~$85-135 |
| 1,000 DAU | $50 (DB upgrade) | $300-500 | ~$350-550 |

OpenAI + Polly are the dominant cost line at any non-trivial scale. Optimization there (caching common tours, using Polly Standard instead of Neural, prompt engineering for shorter outputs) has way more leverage than infrastructure choice.

---

## 10. Outstanding decisions — Sir Michael's responses captured

1. **GCP project structure**: Sir Michael — shared billing, separate projects, accounting via Wave. ✅ Locked in.
2. **Domain registrar + DNS**: Sir Michael — `audioura.com` registered, empty. Open question: what other domains, and how to fill them with email + marketing.
   - Recommended additional registrations: `audioura.com` (developer-feel TLD), `audiotours.com` (typo defense), maybe `audioura.app` (gives Apple Universal Links a nice fit).
   - Email: Google Workspace ($6/user/month) on `@audioura.com` — this is the simplest professional option. Alternatives: Fastmail ($3/month), Zoho Mail (free for 5 users on custom domain).
   - Marketing site: Cloudflare Pages (free, hosts a static site you build with any framework), Vercel (free tier), or a one-page site at `audioura.com/` describing the app + linking to App Store / Play Store. Doesn't need to be built before launch — even a placeholder is fine. Worth doing before App Review since reviewers may visit your marketing URL.
3. **Subdomain strategy**: see §9.1.1 above. Recommend (b) — subdomain-per-service. Saves $18/month at the cost of slightly more mobile-app config.
4. **AWS account for Polly**: Sir Michael — use existing account, may switch later. ✅ Provision IAM credentials with Polly-only permissions for Cloud Run during Phase C.
5. **Cloudflare account**: Sir Michael asks if Amazon-Q can set this up. **Yes** — Cloudflare account creation is in Phase C task list; Amazon-Q will instruct or handle. Free tier covers everything Audioura needs (DNS, R2 with zero egress, Pages for marketing site, free TLS, Cloudflare Access for preprod auth).
6. **Postgres data**: Sir Michael — start preprod fresh. ✅ Locked in. On the question of "one DB vs many": for the same cost as one db-g1-small instance you can host all of Audioura's data — the alternative of multiple smaller instances doesn't save money and adds complexity (multiple connection pools, multiple credentials, no joins across DBs). Single Cloud SQL instance with multiple logical databases inside it (`audiotours`, `analytics`, `ads_targeting`) is the clean shape. Free tier on Cloud SQL is small (limited db-f1-micro hours); not worth chasing for production data.
7. **Mobile app build pipeline**: Sir Michael — manual. ✅ Out of scope for this doc.

---

## 11. Working agreement for the migration

- **Amazon-Q drafts each phase's scripts and assignments.**
- **Claude reviews each before execution.** V2 discipline — review-before-execute for every script.
- **Sir Michael executes** — Amazon-Q runs `gcloud` from the laptop with appropriate permissions; Sir Michael authorizes destructive operations.
- **All migration result files in `C:\Users\micha\eclipse-workspace\AudioTours\development\migration\`** (NOT on USB). Naming `m##_<description>_<timestamp>.txt`.
- **Project log gets updated** at the end of each phase (`C:\Business\audiotours.com\Claude\Audioura development\Audioura_project_log.md`).
- **Rollback strategy in place before deploy:** every Cloud Run deploy assignment must include the corresponding rollback command in its assignment doc.

---

## 12. Risks and explicit non-goals

### 12.1 Risks

1. **GCP API quota gotchas** — Cloud Run, Artifact Registry, Cloud SQL all have per-project quotas. Adequate for our scale but not infinite. Worth checking during Phase C.
2. **Data migration corruption** — `pg_dump | pg_restore` between Postgres versions is normally clean but not guaranteed. Compare row counts after every migration; have a rollback to local DB ready until prod is verified.
3. **R2 vs S3 SDK quirks** — most S3 SDKs work against R2 unchanged but signed URL generation has subtle differences. Test signed-URL audio playback from the mobile app early in Phase D.
4. **AWS Polly cross-cloud latency** — adds ~50-100ms per call. Probably not noticeable; if it is, switch to Google Cloud TTS later.
5. **Newsletter-processor Chrome reliability** — headless Chrome under Cloud Run has historically been finicky. Have a fallback to invoke this service less frequently or run it as a Cloud Run Job (background) if it doesn't fit a request-response pattern.

### 12.2 Explicit non-goals (NOT part of this migration)

- Multi-region deployment. v1 is single-region (us-central1). Multi-region is a 2027 problem.
- Auto-scaling Cloud SQL. Manual instance-size bumps for v1.
- CI/CD for mobile app. Stays manual via the existing assignment scripts.
- Replacing AWS Polly. Stays as-is.
- Writing an admin panel. Stays manual via gcloud + DB queries.
- Implementing user accounts. Out of scope.
- Real-time analytics dashboard. Use GCP's built-in Cloud Run + Cloud SQL dashboards for v1.

### 12.5 Disaster recovery run-book (laptop dies)

If the laptop fails, here's how to recover:

1. New laptop, install: Git, Docker Desktop, Flutter SDK, Python 3.x, Node, AWS CLI, gcloud CLI.
2. `git clone` the Audioura repo (latest `Newsletters` branch).
3. Restore `.env` files from password manager (1Password / Bitwarden).
4. Restore Postgres dev DB from the latest GCS backup (assumed daily backups in place — see §5.1.1).
5. `docker compose up -d` — local dev stack rebuilds.
6. Verify mobile app's local backend connection works.

Everything cloud-hosted (preprod, prod, audio in R2, prod DB in Cloud SQL) is unaffected by laptop death. A tester wouldn't notice.

Recovery time: ~1-2 hours given pre-prepared backups. Without backups: significant data loss of dev DB content + .env secrets.

---

## 13. Migration timeline summary

| Phase | Assignment | Effort | Cumulative |
|---|---|---|---|
| A — Pre-migration audit | M01 | 2 hours | 2 |
| B — Local cloud-ready rehearsal | M02 | 3 hours | 5 |
| C — GCP project setup (billing starts) | M03 | 3 hours | 8 |
| D — Service-by-service to PreProd | M04 | 10-15 hours | 18-23 |
| E — Production cutover | M05 | 2-4 hours | 20-27 |

Realistic calendar duration: 2-3 weeks elapsed if working 1-2 hours/day, with 2-3 days each between phases for review + rest.

---

**Last Updated:** 2026-05-04 by Claude (session "Audioura Build and Start #4")
**Status:** SPEC ready for Amazon-Q to draft Phase A audit (Assignment M01) for review.
**Next step:** Amazon-Q drafts M01; Claude reviews; Sir Michael executes the audit on the laptop.
**File location:** `C:\Business\audiotours.com\Claude\Audioura development\AUDIOURA_CLOUD_MIGRATION_AND_LIFECYCLE.md` (Claude-only permanent doc). Old D:\ copy is obsolete; Sir Michael deletes.
