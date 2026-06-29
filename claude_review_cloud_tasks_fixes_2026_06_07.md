# Claude.AI Review Request — Cloud Tasks Bug Fixes

**Date:** 2026-06-07  
**Branch:** `services-migration`  
**Responding to:** `REVIEW_FOR_KIRO_cloud_tasks_2026_06_07.md`  
**Scope:** All three must-fix bugs + IAM docs + minor improvements

---

## Summary

All issues from Claude's review have been fixed:

| Issue | Status |
|-------|--------|
| 🔴 Must-fix #1: Worker not idempotent | ✅ Fixed — early-return guard |
| 🔴 Must-fix #2: Error written on first failure | ✅ Fixed — retry-count-aware |
| 🔴 Must-fix #3: Invalid SQL (UPDATE ORDER BY LIMIT) | ✅ Fixed — subquery |
| IAM bindings documentation | ✅ All 3 in setup script |
| Minor: Poll loop caps | ✅ MAX_POLL_ITERATIONS=60 |
| Minor: translation_failed flag | ✅ Recorded in job_status |
| Minor: NULL output_data crash | ✅ COALESCE in UPDATE |

---

## Must-Fix #1 — Idempotency Guard

Added `_read_job_status()` helper and early-return at top of `run_generation`:

```python
def _read_job_status(job_id):
    """Read current job status from database (for idempotency check)."""
    try:
        conn = _get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT status FROM job_status WHERE job_id = %s", (job_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return {'status': row[0]} if row else None
    except Exception:
        return None

def run_generation(job_id, ...):
    # Idempotency guard — protect against lost-response retries
    existing = _read_job_status(job_id)
    if existing and existing.get('status') == 'completed':
        print(f"[WORKER] Job {job_id} already completed — skipping (idempotent)")
        return True
    ...
```

If Cloud Tasks retries after a lost HTTP response (the tour was actually generated successfully), the worker sees `completed` in the DB and returns 200 immediately without re-calling OpenAI/Polly.

---

## Must-Fix #2 — Error Only on Final Retry

`run_generation` now **raises** the exception instead of writing status=error directly. The `run_job` endpoint reads `X-CloudTasks-TaskRetryCount` and decides:

```python
retry_count = int(request.headers.get('X-CloudTasks-TaskRetryCount', '0'))
is_final_attempt = (retry_count >= MAX_TASK_ATTEMPTS - 1)  # MAX_TASK_ATTEMPTS=3

try:
    success = run_generation(...)
    return jsonify({"status": "completed"}), 200
except Exception as e:
    if is_final_attempt:
        update_job_status(job_id, 'error', str(e), error=str(e))  # permanent failure
    else:
        update_job_status(job_id, 'processing', f'Retrying after error: ...')  # keep polling
    return jsonify({"status": "error"}), 500
```

**Result:** Mobile app sees `processing` during retries (keeps polling). Only sees `error` after all 3 attempts fail.

---

## Must-Fix #3 — Invalid SQL Fixed

**Before (invalid — PostgreSQL rejects ORDER BY/LIMIT in UPDATE):**
```sql
UPDATE tour_requests SET status='completed', finished_at=NOW()
WHERE secret_id=%s AND status IN ('started','processing')
ORDER BY started_at DESC LIMIT 1
```

**After (valid — subquery selects the target row):**
```sql
UPDATE tour_requests SET status='completed', finished_at=NOW()
WHERE id = (
    SELECT id FROM tour_requests
    WHERE secret_id=%s AND status IN ('started','processing')
    ORDER BY started_at DESC LIMIT 1
)
```

---

## IAM Bindings — Documented in `setup_cloud_tasks_queue.sh`

The script is now idempotent and configures all three required bindings:

1. **`roles/run.invoker`** on `tour-worker` → allows the invoker SA to call the worker
2. **`roles/cloudtasks.enqueuer`** on the queue → allows orchestrator to create tasks
3. **`roles/iam.serviceAccountUser`** on the invoker SA → allows orchestrator to mint OIDC tokens as that SA (only needed if they're different SAs)

Script uses `2>/dev/null || true` on each binding to be idempotent (no error if already set).

---

## Minor Fixes

### Poll loop caps
```python
MAX_POLL_ITERATIONS = 60  # 60 * 10s = 10 min for text gen; 60 * 5s = 5 min for TTS

while poll_count < MAX_POLL_ITERATIONS:
    poll_count += 1
    ...
else:
    raise Exception(f"... timed out after {MAX_POLL_ITERATIONS} polls")
```

### translation_failed flag
```python
translation_failed = False
# ... in the translation try/except:
    translation_failed = True
# ... in completion:
if translation_failed:
    completion_extras["translation_failed"] = True
```

Mobile app can read `translation_failed: true` from `/status` to show "Translation unavailable" instead of silently returning English.

### COALESCE for NULL output_data
```sql
UPDATE job_status SET ..., output_data=COALESCE(output_data, '{}'::jsonb) || %s::jsonb, ...
```

Prevents `NULL || jsonb = NULL` which would silently drop all progress data.

---

## Timeout Alignment (Q2 answer applied)

- Worker `--timeout=840` (14 min)
- Cloud Tasks `dispatch_deadline=900` (15 min)

60s of headroom prevents Cloud Tasks from retrying while a long-running tour is still finishing.

---

## Files Changed

| File | Changes |
|------|---------|
| `tour_worker_service.py` | Idempotency guard, retry-aware error handling, fixed SQL, poll caps, COALESCE, translation_failed |
| `Dockerfile.tour-worker` | Comment about timeout alignment |
| `migration/setup_cloud_tasks_queue.sh` | Full rewrite with all 3 IAM bindings, idempotent |

---

## Verification

All files compile cleanly:
```
tour_orchestrator_service.py  ✅
tour_worker_service.py        ✅
job_store.py                  ✅
```

---

**Status:** All must-fix and minor issues resolved. Ready for deployment testing.
