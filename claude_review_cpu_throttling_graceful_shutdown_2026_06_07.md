# Claude.AI Review Request — CPU Throttling Fix + Graceful Shutdown

**Date:** 2026-06-07  
**Branch:** `services-migration`  
**Previous review:** `REVIEW_FOR_KIRO_cloudrun_background_2026_06_07.md`  
**Scope:** Tour orchestrator reliability on Cloud Run

---

## Summary

This review covers two changes:
1. **Infrastructure fix (already applied):** `--no-cpu-throttling --min-instances=1` on Cloud Run services
2. **Code improvement (new):** Graceful shutdown signal handler for in-flight tour generations

---

## 1. CPU Throttling Fix — Infrastructure (Applied)

### Problem (confirmed)
Tour generation uses a background daemon thread (`orchestrate_tour_async`) that runs after the HTTP response returns `{"status":"queued"}`. Cloud Run's default CPU throttling starves this thread, causing tours to stall indefinitely.

### Fix Applied
```bash
gcloud run services update tour-orchestrator --no-cpu-throttling --min-instances=1
gcloud run services update tour-modernized --no-cpu-throttling
```

### Verification
Two consecutive generations completed successfully:
- Faneuil Hall, Boston, MA: 3 stops, <90s ✅
- Davis Square, Somerville, MA: 4 stops, <100s ✅

### Questions from Previous Review (Answered)

**Q1: Should `tour-generator` also get `--no-cpu-throttling`?**  
No. The generator is called synchronously within the orchestrator's background thread via `_authenticated_request("POST", ...)` with a 60s timeout. The orchestrator's request keeps the generator's CPU active for the duration of that call. No background threading in the generator → no throttling issue.

**Q2: Is there a way to have CPU-always but still scale to zero when idle?**  
No. `--no-cpu-throttling` only matters when there's an instance running — it controls what happens *after* a response is sent. `--min-instances=1` is required separately to prevent the instance from being reclaimed while a background thread is running. Together they mean "always one instance with full CPU." The orchestrator already has `max-instances=1` (for ACTIVE_JOBS dict safety), so this results in exactly one always-on instance.

Cost: ~$10-15/month for a single 0.5 vCPU / 512 MiB instance. Acceptable for a service that runs multi-minute background tasks.

---

## 2. Graceful Shutdown Handler — Code Change (New)

### Problem
Cloud Run sends SIGTERM before shutting down an instance (e.g., during redeployment). Default grace period is 10 seconds. A tour generation takes 60-100+ seconds. Without handling SIGTERM, a redeploy during active generation would kill the thread, leaving the job stuck in `processing` forever.

### Fix
Added to `tour_orchestrator_service.py`:

```python
import signal

_ACTIVE_GENERATION_THREADS = []  # Track in-flight generation threads
_SHUTTING_DOWN = False  # Signal that shutdown is in progress


def _graceful_shutdown(signum, frame):
    """Handle SIGTERM by waiting for in-flight generations to complete."""
    global _SHUTTING_DOWN
    _SHUTTING_DOWN = True
    active = [t for t in _ACTIVE_GENERATION_THREADS if t.is_alive()]
    if active:
        print(f"[SHUTDOWN] SIGTERM received. Waiting for {len(active)} generation(s) (max 300s)...")
        for t in active:
            t.join(timeout=300)
        still_active = [t for t in active if t.is_alive()]
        if still_active:
            print(f"[SHUTDOWN] WARNING: {len(still_active)} generation(s) did not finish.")
        else:
            print(f"[SHUTDOWN] All in-flight generations completed cleanly.")
    else:
        print(f"[SHUTDOWN] No in-flight generations. Exiting cleanly.")
    sys.exit(0)


signal.signal(signal.SIGTERM, _graceful_shutdown)
```

Thread tracking in `generate_complete_tour`:
```python
thread.start()
_ACTIVE_GENERATION_THREADS.append(thread)
# Clean up completed threads
_ACTIVE_GENERATION_THREADS[:] = [t for t in _ACTIVE_GENERATION_THREADS if t.is_alive()]
```

New requests rejected during shutdown:
```python
if _SHUTTING_DOWN:
    return jsonify({"error": "Service is shutting down. Please retry in a few seconds."}), 503
```

### Cloud Run Configuration Required
For this to work effectively, the Cloud Run termination grace period must be set longer than a typical generation:

```bash
gcloud run services update tour-orchestrator --timeout=600
```

Cloud Run's default container termination timeout is 10 seconds. With `--timeout=600` (or setting via Cloud Console), the instance gets up to 10 minutes to complete after SIGTERM.

**Note:** This is a Cloud Run service-level setting (`--timeout` controls *request* timeout). The *instance shutdown* grace period is set via the `terminationGracePeriodSeconds` field in the YAML spec (default 300s for CPU-always instances). With `--no-cpu-throttling`, Cloud Run already grants a 300s grace period on SIGTERM, which should be sufficient for most generations.

### Design Rationale
- **Why track threads?** So the shutdown handler knows what to wait for.
- **Why `_SHUTTING_DOWN` flag?** Prevents new generations from starting during drain, which would extend shutdown indefinitely.
- **Why 300s per-thread timeout?** Matches Cloud Run's default grace period for always-allocated instances. If a generation hasn't finished in 5 minutes during shutdown, it's likely stuck and the instance should exit.
- **Why keep `daemon=True`?** If the signal handler fails or is bypassed (SIGKILL), the process exits immediately rather than hanging. The signal handler provides graceful behavior; daemon=True provides the safety net.

---

## 3. Remaining Architecture Notes

### Current State (Acceptable for Now)
- `ACTIVE_JOBS = {}` in-memory dict — safe with `min=max=1` (single instance)
- `job_store.py` exists with `DatabaseJobStore` but orchestrator hasn't switched yet
- Background daemon thread pattern — works with `--no-cpu-throttling`

### Long-Term Improvements (Deferred)
1. **Cloud Tasks queue** — `/generate-complete-tour` enqueues to Cloud Tasks, separate worker processes. Enables scale-to-zero + multi-instance.
2. **Switch to `DatabaseJobStore`** — Makes `/status/<job_id>` work across instance replacement (deploy/crash). Currently if the instance restarts, in-memory jobs are lost.
3. **Request-scoped timeout** — Add a maximum generation time (e.g., 600s) after which the orchestrator marks the job as `error` and stops polling sub-services.

These are nice-to-haves for current scale (single user, <10 tours/day). The current fix is correct and sufficient.

---

## 4. Files Changed

| File | Change |
|------|--------|
| `tour_orchestrator_service.py` | Added `signal` import, `_graceful_shutdown()` handler, `_ACTIVE_GENERATION_THREADS` tracking, `_SHUTTING_DOWN` request rejection |

---

## 5. Questions for Claude

1. **300s timeout in the signal handler:** Is 300s per-thread too generous? A typical generation is <100s. Should this be 180s (3 min) to prevent the instance from lingering too long during a failed generation?

2. **Thread tracking cleanup:** The list cleanup (`_ACTIVE_GENERATION_THREADS[:] = [t for t in ... if t.is_alive()]`) happens only on new requests. Should it also run periodically (e.g., in the shutdown handler pre-check)?

3. **503 during shutdown:** The mobile app currently retries on network errors. Should the 503 response include a `Retry-After` header to guide client behavior?

---

## Verification Plan

1. Deploy updated `tour_orchestrator_service.py` to Cloud Run
2. Start a tour generation
3. While it's processing, redeploy the service (`gcloud run deploy ...`)
4. Confirm in logs: `[SHUTDOWN] SIGTERM received. Waiting for 1 generation(s)...`
5. Confirm the generation completes and the job reaches `completed` status
6. After deploy finishes, new requests hit the new revision successfully

---

**Status:** Ready for Claude.AI review.
