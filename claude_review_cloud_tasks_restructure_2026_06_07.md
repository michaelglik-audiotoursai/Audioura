# Claude.AI Review Request — Cloud Tasks Restructure (Part A fixes + Part B implementation)

**Date:** 2026-06-07  
**Branch:** `services-migration`  
**Responding to:** `REVIEW_FOR_KIRO_throttling_and_restructure_2026_06_07.md`  
**Scope:** Tour orchestrator + new tour-worker service

---

## Summary

Implemented ALL recommendations from Claude's review:
- **Part A:** Three fixes to the graceful shutdown (join timeout, Retry-After header, cost note)
- **Part B:** Full Cloud Tasks restructure with dual-mode operation

---

## Part A — Fixes Applied

### 1. Join timeout reduced: 300s → 240s
```python
t.join(timeout=240)  # Below Cloud Run's 300s grace period to allow clean exit
```
Rationale: Ensures `sys.exit(0)` has time to return before SIGKILL arrives.

### 2. Retry-After header added to 503 shutdown response
```python
if _SHUTTING_DOWN:
    response = jsonify({"error": "Service is shutting down. Please retry in a few seconds."})
    response.headers['Retry-After'] = '5'
    return response, 503
```

### 3. Cost note acknowledged
$30/month for the always-on instance (not $10-15). Part B eliminates this cost.

---

## Part B — Cloud Tasks Restructure

### Architecture

```
Mobile → api-gateway → tour-orchestrator (THIN, scale-to-zero capable)
   1. Validate input + quota check (entitlements)
   2. Create job row in Cloud SQL (job_status table)
   3. Enqueue Cloud Task (payload = job_id + params)
   4. Return {job_id, status:"queued"} immediately

Cloud Tasks ──HTTP POST──► tour-worker (Cloud Run, scale 0→N)
   - Full generation pipeline INSIDE the request (no background thread)
   - Updates job_status table with progress as it goes
   - Returns 200 on success / 500 for Cloud Tasks to retry

Mobile → api-gateway → tour-orchestrator /status/<job_id>
   - Reads job_status from Cloud SQL (ANY instance can answer)
```

### New Files

| File | Purpose |
|------|---------|
| `tour_worker_service.py` | Cloud Tasks target — runs generation synchronously |
| `Dockerfile.tour-worker` | Docker image for the worker service |
| `migration/setup_cloud_tasks_queue.sh` | One-time queue setup script |

### Modified Files

| File | Changes |
|------|---------|
| `tour_orchestrator_service.py` | Part A fixes + dual-mode dispatch (thread vs cloud_tasks) + DB-backed /status |
| `.env.example` | Added GENERATION_MODE, JOB_STORE_MODE, Cloud Tasks vars |
| `requirements.txt` | Added `google-cloud-tasks==2.16.0` |

---

## Key Design Decisions

### 1. Dual-mode operation (GENERATION_MODE env var)
- `thread` (default): Original daemon-thread approach. Local Docker. Backwards compatible.
- `cloud_tasks`: Enqueues to Cloud Tasks. Worker handles generation. Production.

This means **local Docker development is completely unchanged** — just don't set `GENERATION_MODE=cloud_tasks`.

### 2. Fallback on enqueue failure
If Cloud Tasks enqueue fails (network issue, queue misconfigured), the orchestrator falls back to thread mode rather than failing the request. This prevents a configuration issue from blocking generation entirely.

### 3. /status reads memory first, then DB
The status endpoint tries the in-memory dict first (fast path, covers local Docker), then falls back to the database (covers Cloud Tasks mode where a different worker wrote the status).

### 4. Worker does NOT re-check entitlements
Quota is checked at enqueue time in the orchestrator. The worker trusts the payload — it shouldn't reject a task that already passed quota.

### 5. Cloud Tasks retry policy
- 3 max attempts, 30s→300s exponential backoff
- Worker returns 500 on failure → Cloud Tasks auto-retries
- Worker returns 200 on success → task completed

### 6. Worker concurrency=1
Each worker instance handles exactly one tour at a time (`--concurrency=1`). This ensures full CPU is dedicated to the generation pipeline, no contention.

---

## Environment Variables (New)

| Variable | Default | Cloud Run Value |
|----------|---------|-----------------|
| `GENERATION_MODE` | `thread` | `cloud_tasks` |
| `JOB_STORE_MODE` | `memory` | `database` |
| `GCP_PROJECT_ID` | `audiotours-migration` | `audiotours-migration` |
| `CLOUD_TASKS_QUEUE` | `tour-generation` | `tour-generation` |
| `CLOUD_TASKS_LOCATION` | `us-central1` | `us-central1` |
| `TOUR_WORKER_URL` | (none) | `https://tour-worker-XXXX.us-central1.run.app` |
| `WORKER_SERVICE_ACCOUNT` | (none) | `<sa>@audiotours-migration.iam.gserviceaccount.com` |

---

## Deployment Sequence

1. **Deploy tour-worker** to Cloud Run:
   ```bash
   gcloud run deploy tour-worker \
     --source=. --dockerfile=Dockerfile.tour-worker \
     --timeout=900 --min-instances=0 --max-instances=5 --concurrency=1 \
     --no-allow-unauthenticated \
     --set-secrets=DB_PASSWORD=db-password:latest,OPENAI_API_KEY=openai-api-key:latest,...
   ```

2. **Create Cloud Tasks queue:**
   ```bash
   gcloud tasks queues create tour-generation \
     --location=us-central1 \
     --max-dispatches-per-second=2 \
     --max-concurrent-dispatches=3 \
     --max-attempts=3
   ```

3. **Redeploy tour-orchestrator** with new env vars:
   ```bash
   gcloud run services update tour-orchestrator \
     --set-env-vars="GENERATION_MODE=cloud_tasks,JOB_STORE_MODE=database,GCP_PROJECT_ID=audiotours-migration,TOUR_WORKER_URL=https://tour-worker-XXXX.us-central1.run.app,WORKER_SERVICE_ACCOUNT=<sa>"
   ```

4. **Remove always-on settings** from orchestrator:
   ```bash
   gcloud run services update tour-orchestrator \
     --cpu-throttling --min-instances=0
   ```

5. **Test:** Generate a tour from mobile → verify task dispatched → worker completes → /status returns completed.

---

## Cost Comparison

| Architecture | Monthly Cost (idle) | Monthly Cost (10 tours/day) |
|---|---|---|
| Current (always-on) | ~$30 | ~$30 |
| Cloud Tasks (Part B) | ~$0 | ~$2-5 (pay only during generation) |

---

## Questions for Claude

1. **Worker timeout:** Set to 900s (15 min) to handle worst-case tours with translations. Is that reasonable, or should it be lower (e.g., 600s)?

2. **Cloud Tasks dispatch deadline:** Set to 900s in the task payload. Should this match the worker timeout?

3. **Retry behavior:** On worker failure (500), Cloud Tasks retries up to 3 times with 30s→300s backoff. Should the mobile app see the job as "error" immediately on first failure, or should it stay in "processing" until all retries are exhausted? Current implementation: worker writes `status=error` on failure, so mobile sees it immediately. Cloud Tasks may retry and overwrite with `status=completed` on success.

4. **queue.yaml vs gcloud CLI:** Should the queue configuration live in a `queue.yaml` file (deployable via `gcloud tasks queues update`) or is the one-time CLI setup script sufficient?

5. **IAM:** The worker needs `roles/run.invoker` granted to the Cloud Tasks service agent (`service-PROJECTNUM@gcp-sa-cloudtasks.iam.gserviceaccount.com`). Should I document this in the setup script?

---

## Testing Plan

### Local Docker (no changes needed)
```bash
docker-compose up -d
# GENERATION_MODE defaults to 'thread' — original behavior preserved
curl -X POST localhost:5002/generate-complete-tour -H "Content-Type: application/json" \
  -d '{"location":"Boston Common","tour_type":"walking","total_stops":3}'
# Verify: works exactly as before
```

### Cloud Run (after deployment)
```bash
# 1. Generate tour
curl -X POST https://api.audioura.com/generate-complete-tour \
  -H "Content-Type: application/json" -H "X-API-Key: <key>" \
  -d '{"location":"Davis Square, Somerville, MA","tour_type":"walking","total_stops":4}'

# 2. Check Cloud Tasks queue (should show pending task)
gcloud tasks list --queue=tour-generation --location=us-central1

# 3. Poll status (reads from Cloud SQL)
curl https://api.audioura.com/status/<job_id>

# 4. Verify worker logs
gcloud run services logs read tour-worker --limit=50
```

---

**Status:** Code complete. Ready for Claude.AI review before deployment.
