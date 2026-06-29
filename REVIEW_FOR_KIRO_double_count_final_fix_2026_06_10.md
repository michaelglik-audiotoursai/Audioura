# REVIEW_FOR_KIRO — Double-Count Final Fix (2026-06-10)

**Context:** Addressing Claude's two remaining HIGH findings from `claude_review_double_count_fix_usage_rollback_implementation_2026_06_10.md`.

---

## Finding A Fixed: `OR source IS NULL` removed + column default set

**Problem:** The counter had `AND (source = 'orchestrator' OR source IS NULL)`. The tracking service doesn't set `source`, so its new rows were NULL → still counted → double-counting persisted.

**Fix (three-part):**

1. **Counter** (`entitlements.py`): Changed to strict `AND source = 'orchestrator'` — no more `OR source IS NULL`:
```python
SELECT COUNT(*) FROM tour_requests 
WHERE secret_id = %s AND started_at::date = CURRENT_DATE
AND source = 'orchestrator'
```

2. **Column default** (DB): `ALTER TABLE tour_requests ALTER COLUMN source SET DEFAULT 'tracking'` — new tracking-service rows automatically get `source='tracking'` (excluded from count), no code change to the tracking service needed.

3. **Backfill**: `UPDATE tour_requests SET source = 'tracking' WHERE source IS NULL` — 0 remaining (previous backfill already caught them). Verified: 2 orchestrator rows, 163 tracking rows.

**Result:** Counter now counts ONLY `source='orchestrator'` rows. One tour = one counted row. Tester gets full 100/day.

---

## Finding B Fixed: Rollback added to tour-worker (cloud_tasks path)

**Problem:** Rollback only existed in `orchestrate_tour_async` (thread/local mode). In production (`GENERATION_MODE='cloud_tasks'`), the worker handles generation. On permanent failure (final retry), the `tour_requests` row stayed → free user locked out.

**Fix:** Added rollback to `tour_worker_service.py` in the `run_job` exception handler, on the **final attempt** only:

```python
# In run_job except block, when is_final_attempt:
if is_final_attempt:
    update_job_status(job_id, 'error', error_msg, error=error_msg)
    # Rollback usage row
    _rcur.execute("DELETE FROM tour_requests WHERE tour_id = %s AND source = 'orchestrator'", (job_id,))
```

**Why only on final attempt:** On earlier retries, the job may still succeed. The usage row should stay to prevent racing a parallel request. Only when the job is permanently failed (all retries exhausted) is the quota slot freed.

---

## Deployment

| Service | Image | Revision |
|---------|-------|----------|
| `tour-orchestrator` | `audioura:v19` | `tour-orchestrator-00017-5zb` |
| `tour-worker` | `audioura:v19` | `tour-worker-00003-w59` |

Database: `source` column default set to `'tracking'`.

---

## Files Modified

| File | Change |
|------|--------|
| `development/entitlements.py` | Counter: `source = 'orchestrator'` only (removed `OR source IS NULL`) |
| `development/tour_worker_service.py` | Added rollback DELETE on final-attempt failure |

---

## Verification (from DB)

```
Source breakdown:
  orchestrator: 2 rows
  tracking: 163 rows
  (NULL: 0)
```

No NULL rows remain. Counter will only ever see `orchestrator` rows.

---

## Final Behavior (complete)

| Path | Usage recorded | Failure rollback | Counter sees |
|------|---------------|-----------------|--------------|
| Thread mode (local) | Orchestrator INSERTs | Orchestrator DELETEs on exception | ✅ orchestrator rows only |
| Cloud Tasks (prod) | Orchestrator INSERTs | Worker DELETEs on final failure | ✅ orchestrator rows only |
| Tracking service | Auto-tagged `'tracking'` (default) | N/A | ❌ excluded from count |

---

## `py_compile`

All three files: exit 0 (clean).
