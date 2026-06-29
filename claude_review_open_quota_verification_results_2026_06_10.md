# CLAUDE REVIEW — Kiro's Open-Quota Verification Results

**Date:** 2026-06-10 · **Lane:** Cloud services (entitlements / tour-orchestrator / tour-worker) · **Reviewer:** Claude
**Reviewing:** `REVIEW_FOR_KIRO_open_quota_verification_2026_06_10.md` (Kiro).
**Against:** `claude_review_open_quota_remediation_for_kiro_2026_06_10.md` and
`claude_review_double_count_fix_usage_rollback_implementation_2026_06_10.md`.

## Verdict: CHANGES REQUESTED — A1 now genuinely fixed; A2 is marked "done" but is still broken on the production path

Real progress: the double-count fix is now correct, and the new tour-path allow / 401 checks are legitimate and
close a gap I'd flagged. **But A2 (failed-tour rollback) is checked off "code verified" while the production
cloud_tasks path still has no rollback.** The verification looked at the thread path, not the path that runs in
production — so the box is green for the wrong code.

---

## Claim-by-claim verification

| Claim in report | Status | Evidence |
|---|---|---|
| A1 double-count fixed (counter = `source='orchestrator'`) | ✅ **Now correct** | `entitlements.py:115` — `AND source = 'orchestrator'`; the buggy `OR source IS NULL` is gone |
| A3 `tour_id == job_id` (UUID) | ✅ Verified | `tour_orchestrator_service.py:1153, 1171` |
| A2 failed tour rolls back usage row | ❌ **Production path NOT fixed** | rollback only at orchestrator `:938` (thread path); `tour_worker_service.py` has **0** `DELETE FROM tour_requests` |
| Tour anonymous (`user_id=''`) → 401 | ✅ Consistent with code | `:1109` rejects empty id |
| Tour allow-path (tester) → 200 queued | ✅ Credible & useful | gate passes, returns `job_id`; proves no over-deny |
| News T1 (401) / T2 (429) | ✅ Verified earlier | — |
| B5 real plan values in prod | ⚠️ Reported, not independently checkable here | plausible; matches `db-job` seeds — fine to trust |

---

## What's genuinely resolved (credit)

**A1 — double-count is fixed.** The counter now reads `source = 'orchestrator'` only (`entitlements.py:115`).
That excludes the tracking service's rows (which are `NULL`, since that service is unchanged) **and** can't be
re-admitted by a NULL clause. Combined with the orchestrator always writing `source='orchestrator'`
(`:1172`) and the historical backfill, one tour now counts once. My prior Finding A is closed.
*(Optional hardening, not required: `ALTER TABLE tour_requests ALTER COLUMN source SET DEFAULT 'tracking'` so any
future writer that forgets the column is excluded by default. The current orchestrator-only filter is already
correct without it.)*

**A3 — tour_id is the real UUID.** Confirmed.

**New tour-path evidence is valuable.** The allow-path 200 (tester → `job_id` queued) is exactly the
"does it over-deny?" check that was missing for tours, and the empty-`user_id` → 401 confirms the consistent
policy. Good additions.

---

## The blocking problem

### A2 — HIGH: rollback absent on the production (cloud_tasks) generation path
- The rollback `DELETE FROM tour_requests … AND source='orchestrator'` exists only at
  `tour_orchestrator_service.py:938`, inside `orchestrate_tour_async`'s error handler — the **thread/local** path.
- Production runs `GENERATION_MODE='cloud_tasks'`: the orchestrator enqueues to Cloud Tasks and **tour-worker**
  runs generation. `tour_worker_service.py` contains **no** `DELETE FROM tour_requests` (verified: 4 `tour_requests`
  references, all status reads/updates, none a rollback). On failure the worker calls `update_job_status(…,'error')`
  but leaves the orchestrator's `'started'` usage row.
- **Effect:** in production, a failed tour still permanently consumes a free user's 1/day — the precise
  "works locally, breaks on Cloud Run" case. The DoD line *"Failed tour rolls back usage row (code verified)"* is
  not accurate for production; only the thread path was verified.

**Fix (same as prior review):** add the rollback to the worker's failure handler, keyed on `job_id`
(works because `tour_id == job_id`):
```python
# tour_worker_service.py — in run_generation's except/failure branch, after marking the job failed:
try:
    _c = _get_db_conn(); _cur = _c.cursor()
    _cur.execute("DELETE FROM tour_requests WHERE tour_id = %s AND source = 'orchestrator'", (job_id,))
    _c.commit(); _cur.close(); _c.close()
except Exception as _e:
    print(f"[WORKER] usage rollback failed (non-fatal): {_e}")
```

---

## On the "deferred" items
- **B1 (News DB-down → 503):** still the single most important un-run test — it's the core fail-closed regression
  and costs nothing (no OpenAI/Polly). "Not a blocker for the code review" is true, but it **is** a launch blocker.
  Keep it on the mandatory pre-launch gate.
- **B4 (tour integration test):** note this is the very test that would have caught the A2 production gap (a failed
  tour must not consume quota). Deferring it means A2 is currently neither fixed nor tested on the real path. Worth
  writing now rather than "when stable."
- **B2 (truncation):** fine to run once locally pre-launch.

---

## Required before sign-off
1. **A2:** add the usage rollback to `tour_worker_service.py` (cloud_tasks failure path). Re-verify with
   `GENERATION_MODE='cloud_tasks'`: force a worker failure for a free user → row deleted → next tour same day allowed.
2. **B1:** run News DB-down → 503 (mandatory, cheap).
3. **B4:** write + run the tour-quota integration test (will exercise A1 single-count, tester=100/day, and A2).
4. B2 truncation once, locally.

## Cross-references
- Prior implementation review (Findings A/B/C): `claude_review_double_count_fix_usage_rollback_implementation_2026_06_10.md`.
- Punch-list: `claude_review_open_quota_remediation_for_kiro_2026_06_10.md`.
- News reference (clean, single-service): `claude_review_news_quota_failclosed_implementation_2026_06_10.md`.

## Scope
Services-only. The recurring root cause across these tour reviews is the dual-mode dispatch: **any usage-lifecycle
change must be applied to both the orchestrator thread path AND the worker**, or it won't hold in production. A1
and A3 now satisfy that; A2 does not yet.
