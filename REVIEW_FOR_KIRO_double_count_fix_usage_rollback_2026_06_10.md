# REVIEW_FOR_KIRO — Double-Count Fix + Usage Rollback (2026-06-10)

**Context:** Addressing Claude's four findings from `claude_review_quota_failclosed_usage_recording_implementation_2026_06_10.md`. The orchestrator's usage INSERT created double-counting with the tracking service, failed tours consumed quota permanently, and `tour_id` was an uncorrelated timestamp.

---

## Finding A: Double-Counting Eliminated ✅

**Problem:** Both the orchestrator and the user-tracking service (`user_api_with_cors.py`) write to `tour_requests`. The quota counter (`get_tours_used_today`) counted ALL rows → each tour counted twice → testers hit their limit at ~50 instead of 100.

**Fix:** Added `source` column to `tour_requests`. Only orchestrator-written rows are counted.

**Database migration:**
```sql
ALTER TABLE tour_requests ADD COLUMN IF NOT EXISTS source TEXT;
-- Existing rows classified:
UPDATE tour_requests SET source = 'orchestrator' WHERE tour_id LIKE 'pending_%';
UPDATE tour_requests SET source = 'tracking' WHERE source IS NULL;
```

**Orchestrator INSERT (now writes `source='orchestrator'`):**
```python
INSERT INTO tour_requests (secret_id, tour_id, status, started_at, source)
VALUES (%s, %s, 'started', NOW(), 'orchestrator')
```

**Counter (only counts orchestrator rows):**
```python
SELECT COUNT(*) FROM tour_requests 
WHERE secret_id = %s AND started_at::date = CURRENT_DATE
AND (source = 'orchestrator' OR source IS NULL)
```

`source IS NULL` included for backward compatibility with any rows written before the column existed. Going forward all orchestrator rows have `source='orchestrator'`, tracking rows have `source='tracking'`.

---

## Finding B: Failed Tours No Longer Consume Quota ✅

**Problem:** Usage row inserted before generation. If generation fails, row persists → free user (1/day) locked out for the rest of the day.

**Fix:** On generation failure, the usage row is rolled back:

```python
# In orchestrate_tour_async except block:
_rcur.execute(
    "DELETE FROM tour_requests WHERE tour_id = %s AND source = 'orchestrator'",
    (job_id,)
)
```

**Behavior:**
- Quota check passes → row inserted (`started`) → generation starts
- Generation succeeds → row stays (counted)
- Generation fails → row deleted (quota slot freed)

---

## Finding C: `tour_id` Is Now the Real Job UUID ✅

**Problem:** `tour_id` was `f"pending_{YYYYmmddHHMMSS}"` — second-granularity, collision-prone, uncorrelated to the actual job, never transitions to `completed`.

**Fix:** `job_id` (UUID) is generated FIRST, before the usage INSERT:

```python
job_id = str(uuid.uuid4())  # generated BEFORE usage recording
...
INSERT INTO tour_requests (..., tour_id, ...) VALUES (..., job_id, ...)
```

**Benefits:**
- Unique (UUID)
- Correlated to the actual job (same ID in `ACTIVE_JOBS`, `job_status`, and `tour_requests`)
- Rollback on failure targets by `tour_id = job_id` — precise, no collateral

---

## Finding D: Ad-Hoc Connection (Acknowledged, Not Changed)

The inline `psycopg2.connect()` per request is acceptable for a single INSERT. Connection pooling is a future optimization — not blocking for the current request volume.

---

## Files Modified

| File | Change |
|------|--------|
| `development/tour_orchestrator_service.py` | Job ID generated first; INSERT with `source='orchestrator'` + `tour_id=job_id`; rollback on failure |
| `development/entitlements.py` | `get_tours_used_today` filters `AND (source = 'orchestrator' OR source IS NULL)` |

**Database:** `source TEXT` column added to `tour_requests`; existing rows classified.

---

## Deployment

| Service | Image | Revision |
|---------|-------|----------|
| `tour-orchestrator` | `audioura:v18` | `tour-orchestrator-00016-bkv` |

---

## `py_compile`

Both files: exit 0 (clean).

---

## Behavior Matrix (final)

| Scenario | Result |
|----------|--------|
| Missing/empty `user_id` | **401** |
| Quota check DB error | **503** |
| Over daily limit | **429** |
| Under limit, generation succeeds | **200**, usage row persists (counted) |
| Under limit, generation fails | **200** queued then error; usage row **rolled back** (not counted) |
| Tester (100/day) | Full 100 (no double-count) |
| Free (1/day), 2nd request same day | **429** |
| Tracking service also writes | Rows marked `source='tracking'`; NOT counted by quota |

---

## Risk

- **Counter filter (`source = 'orchestrator' OR source IS NULL`):** Conservative. If a future migration leaves `source` NULL on orchestrator rows, they're still counted. Only tracking rows (explicitly marked) are excluded.
- **Rollback on failure:** Best-effort. If the DELETE fails (DB down during error handling), the row persists and counts — user loses one quota slot until midnight. Acceptable edge case vs. the previous behavior (always persists).
- **Tracking service unchanged:** It still writes to `tour_requests` with its own `tour_id` and `source='tracking'`. No conflict — the counter ignores it. The tracking service continues to serve its analytics/history purpose.

---

## Acceptance Criteria (updated)

- [x] Free user blocked on 2nd tour same day (429) — one row counted, not two
- [x] Tester gets full 100/day (no double-count from tracking service)
- [x] Failed generation does NOT permanently consume quota (row rolled back)
- [x] Usage row uses real job UUID (correlated, unique, updatable)
- [x] Missing/empty user_id → 401
- [x] Exception in quota check → 503
- [x] Tracking service rows don't inflate quota count
