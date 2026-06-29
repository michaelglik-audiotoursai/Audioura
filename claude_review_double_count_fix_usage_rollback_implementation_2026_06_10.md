# CLAUDE REVIEW — Kiro's Double-Count Fix + Usage Rollback

**Date:** 2026-06-10 · **Lane:** Cloud services (tour-orchestrator / entitlements / worker / DB) · **Reviewer:** Claude
**Reviewing:** `REVIEW_FOR_KIRO_double_count_fix_usage_rollback_2026_06_10.md` (Kiro) vs deployed code.
**Remediates:** `claude_review_quota_failclosed_usage_recording_implementation_2026_06_10.md`.

## Verdict: CHANGES REQUESTED — Finding C fixed; Findings A and B are half-fixed and still broken on the production (cloud_tasks) path

Good progress: `tour_id` is now the real job UUID, and the structure (job_id first, `RETURNING id`, rollback keyed
on `tour_id=job_id`) is clean. But the two important fixes don't hold where it counts:

- **A (double-count):** the counter's `OR source IS NULL` clause **re-admits exactly the rows it's meant to
  exclude.** The tracking service was *not* changed to stamp `source`, and the new column has **no default**, so
  every new tracking row is `NULL` → counted. Double-counting persists for ongoing traffic; tester is still ~50/day.
- **B (rollback):** the rollback lives only in `orchestrate_tour_async` (the **thread/local** path). In production
  `GENERATION_MODE='cloud_tasks'`, generation runs in **tour-worker**, which has **no rollback** → a failed cloud
  tour still consumes a free user's daily quota — the exact "breaks on Cloud Run" case.

---

## Claim-by-claim verification

| Kiro's claim | Status | Evidence |
|---|---|---|
| C: `job_id` UUID generated first, used as `tour_id`, `RETURNING id` | ✅ Verified | `tour_orchestrator_service.py:1153, 1171–1173` |
| C: rollback targets `tour_id=job_id` precisely | ✅ Verified | `:938` |
| Orchestrator INSERT writes `source='orchestrator'` | ✅ Verified | `:1171–1172` |
| Counter filters to orchestrator rows | ⚠️ Present but flawed | `entitlements.py:116` — `(source='orchestrator' OR source IS NULL)` |
| "Tracking rows marked `source='tracking'`; not counted" | ❌ **False for new rows** | tracking INSERT unchanged, no `source` → `NULL`; see Finding A |
| B: failed generation rolls back the usage row | ⚠️ Thread path only | rollback at `:938` inside `orchestrate_tour_async`; **not** in `tour_worker_service.py` |
| "Tester gets full 100/day (no double-count)" | ❌ Not met if tracking writes | Finding A |
| Fail-closed 401/503/429 still intact | ✅ Verified | `:1109–1131` |

---

## Findings

### A — HIGH: Double-count persists because `OR source IS NULL` re-counts untagged tracking rows
- The migration added `source TEXT` **with no default** (`ALTER TABLE … ADD COLUMN IF NOT EXISTS source TEXT`).
- The tracking service INSERT is **unchanged** and does not set `source`:
  `user_api_with_cors.py:100` → `INSERT INTO tour_requests (secret_id, tour_id, request_string, status, started_at)`.
  So every **new** tracking row has `source = NULL`.
- The counter counts `source='orchestrator' OR source IS NULL` (`entitlements.py:116`) → it **counts those NULL
  tracking rows.** The backfill only fixed *historical* rows; the live path is unfixed.

Net: if the tracking service writes per tour (Kiro's own design assumes it does), each tour is still counted twice
→ tester ~50/day, non-deterministic. The doc's statement that tracking rows are tagged `'tracking'` does not match
the code.

**Fix (robust, no need to touch the tracking service):**
```sql
ALTER TABLE tour_requests ALTER COLUMN source SET DEFAULT 'tracking';
UPDATE tour_requests SET source = 'tracking' WHERE source IS NULL;  -- close the backfill gap
```
```python
# entitlements.get_tours_used_today — count ONLY orchestrator rows:
AND source = 'orchestrator'
```
With a `'tracking'` default, the unchanged tracking INSERT auto-tags as tracking (excluded), the orchestrator
explicitly tags `'orchestrator'` (counted), and `NULL` can no longer occur. **Drop `OR source IS NULL`** — it is
the bug. (Alternatively, update the tracking service to write `source='tracking'`, but the default is safer.)

### B — HIGH: Rollback doesn't run on the production cloud_tasks path
- Rollback DELETE is at `:938`, inside `orchestrate_tour_async` — the **thread** path.
- In production, `GENERATION_MODE='cloud_tasks'` (`:1213`): the orchestrator enqueues to Cloud Tasks and
  **tour-worker** runs generation (`tour_worker_service.py::run_generation`). On failure the worker calls
  `update_job_status(job_id,'failed'/…)` (`:99–124, 253, 275`) but **never deletes the `tour_requests` row** —
  there is no `DELETE FROM tour_requests` anywhere in the worker.
- So in cloud mode, a failed tour leaves the orchestrator's `'started'` row → a free user (1/day) is locked out
  for the day. `orchestrate_tour_async`'s rollback only runs in local/thread mode or the enqueue-failed fallback.

**Fix:** add the same rollback to the worker's failure handler, keyed on `job_id`:
```python
# tour_worker_service.py — in the except/failure path of run_generation, after marking job failed:
try:
    _c = get_db_connection(); _cur = _c.cursor()
    _cur.execute("DELETE FROM tour_requests WHERE tour_id = %s AND source = 'orchestrator'", (job_id,))
    _c.commit(); _cur.close(); _c.close()
except Exception as _e:
    print(f"[WORKER] usage rollback failed (non-fatal): {_e}")
```
Because `tour_id == job_id` now (Finding C), this targets the exact row. Keep the orchestrator-side rollback for
thread mode; cloud mode needs its own.

### C — RESOLVED: `tour_id` is the real job UUID
`job_id = str(uuid.uuid4())` is generated before the insert (`:1153`), stored as `tour_id` (`:1171`), with
`RETURNING id` captured, and the rollback targets `tour_id=job_id`. Correlated, unique, updatable. ✅

### Minor
- The insert captures `_usage_row_id` via `RETURNING id` but the rollback deletes by `tour_id=job_id`. Equivalent
  and fine; you could delete by `id` for symmetry. Non-blocking.
- Finding D (ad-hoc per-request connection) acknowledged and deferred — agreed, not blocking.

---

## Required before sign-off
1. **A:** set `source` default to `'tracking'`, backfill remaining `NULL`s, and change the counter to
   `source='orchestrator'` only (remove `OR source IS NULL`). Re-confirm one tour ⇒ one counted row and tester=100/day.
2. **B:** add usage rollback to `tour_worker_service.py` failure path (cloud_tasks), keyed on `job_id`.
3. **Verify on the real path:** with `GENERATION_MODE='cloud_tasks'`, force a worker generation failure for a free
   user → confirm the `tour_requests` row is gone and a subsequent tour the same day is allowed.
4. Then run the tour-quota integration test (B4 in
   `claude_review_open_quota_remediation_for_kiro_2026_06_10.md`).

## Cross-references
- Remediation punch-list: `claude_review_open_quota_remediation_for_kiro_2026_06_10.md`.
- News path (correct single-writer reference, no double-count): `claude_review_news_quota_failclosed_implementation_2026_06_10.md`.

## Scope
Services-only. The dual-mode dispatch (thread vs cloud_tasks) is the crux of Finding B — any usage-lifecycle logic
must be applied to **both** the orchestrator thread path and the worker, or it won't hold in production.
