# CLAUDE REVIEW — Kiro's Double-Count Final Fix (Findings A & B)

**Date:** 2026-06-10 · **Lane:** Cloud services (entitlements / tour-orchestrator / tour-worker) · **Reviewer:** Claude
**Reviewing:** `REVIEW_FOR_KIRO_double_count_final_fix_2026_06_10.md` (Kiro).
**Remediates:** `claude_review_open_quota_verification_results_2026_06_10.md` (Findings A done, B open) +
`claude_review_double_count_fix_usage_rollback_implementation_2026_06_10.md`.

## Verdict: APPROVED — both findings correctly fixed (minor, non-blocking notes)

This closes the tour-quota loop. The counter is strictly orchestrator-scoped, the `source` column now defaults to
`'tracking'` so the unchanged tracking service is auto-excluded, and — the part that was missing last round — the
**worker now rolls back the usage row on permanent failure**, so the fix finally holds on the production
cloud_tasks path. The `is_final_attempt` gating is the correct design.

---

## Claim-by-claim verification

| Claim | Status | Evidence |
|---|---|---|
| Counter is `source = 'orchestrator'` only | ✅ Verified | `entitlements.py:115` |
| `source` column default → `'tracking'` | ✅ Reported (DB) | matches my recommended hardening; backfill 2 orch / 163 tracking / 0 NULL |
| Worker rollback on final failure (cloud_tasks) | ✅ **Verified** | `tour_worker_service.py:494–507` |
| Rollback keyed on `tour_id=job_id AND source='orchestrator'` | ✅ Verified | `:503` (correct because `tour_id==job_id`) |
| Rollback only on final attempt; earlier retries keep `processing` | ✅ Verified, sound | `:481, 494, 510–512` |
| Thread-mode rollback still present | ✅ Verified | `tour_orchestrator_service.py:938` |
| `py_compile` clean | ✅ Trusted (files parse) | — |

### Detail confirmed
- `MAX_TASK_ATTEMPTS = int(os.getenv('MAX_TASK_ATTEMPTS','3'))` (`:51`); `retry_count` read from
  `X-CloudTasks-TaskRetryCount` (`:480`); `is_final_attempt = retry_count >= MAX_TASK_ATTEMPTS - 1` (`:481`).
  On the final attempt the worker marks `error` **and** deletes the orchestrator usage row (`:496–507`),
  wrapped in its own try/except (best-effort, non-fatal). On earlier attempts it keeps `processing` and returns
  500 so Cloud Tasks retries (`:510–516`). This is exactly right: the slot is freed only when the tour is
  permanently failed, avoiding a premature free that could race a parallel request.

Both production and local paths are now covered:
- **cloud_tasks (prod):** orchestrator INSERTs (`source='orchestrator'`) → worker DELETEs on final failure.
- **thread (local):** orchestrator INSERTs → orchestrator DELETEs on exception.
- **tracking service:** rows default to `'tracking'` → excluded from the count.

My prior Findings A and B are both resolved.

---

## Minor notes (non-blocking)

1. **Queue/env coupling — verify once.** Rollback correctness depends on `MAX_TASK_ATTEMPTS` (env) equaling the
   Cloud Tasks queue's actual `maxAttempts`. If the queue allows *more* attempts than the env, the worker frees the
   slot at its "final" attempt while Cloud Tasks keeps retrying — and a later retry that *succeeds* would leave a
   completed tour with no usage row (slight under-count). If the queue allows *fewer*, the worker never sees
   `is_final` and the job stays `processing` forever. Action: confirm the deployed queue `maxAttempts == MAX_TASK_ATTEMPTS`.

2. **Partial-success-then-raise (low-prob edge).** If `run_generation` stores the tour but then raises on the final
   attempt, the rollback deletes the usage row for a tour that actually exists → the user gets one uncounted tour.
   Conservative (favors the user, not a cost blowout), low probability; flagging only for completeness.

3. **Successful tours' rows stay `status='started'`.** Counting is status-agnostic so this doesn't affect quota,
   but for hygiene (and the digest's separate `TOUR_STATUS rows_affected=0` item) consider updating the row to
   `completed` on success. Optional.

---

## Still owed (not part of this fix; tracked on the launch gate)
- **B1 — News DB-down → 503:** mandatory, cheap, still un-run. The core fail-closed regression proof.
- **B4 — Tour-quota integration test:** now worth writing — it would exercise everything just landed (single-count,
  tester=100/day, and the worker rollback on a forced cloud failure). I can write it on request.
- **B2 — News truncation:** run once locally pre-launch.

## Recommended verification for this fix specifically
With `GENERATION_MODE='cloud_tasks'`: force a worker generation failure for a free user, let Cloud Tasks exhaust
retries, then confirm (a) `job_status='error'`, (b) the `tour_requests` orchestrator row is gone, and (c) a new
tour the same day is allowed. Also confirm a tester reaches 100/day with exactly one orchestrator row per tour.

## Cross-references
- Prior reviews in this thread: `claude_review_open_quota_verification_results_2026_06_10.md`,
  `claude_review_double_count_fix_usage_rollback_implementation_2026_06_10.md`.
- Punch-list: `claude_review_open_quota_remediation_for_kiro_2026_06_10.md`.

## Scope
Services-only. With A1/A2/A3 all landed across both dispatch paths, the tour-quota code is now consistent with the
news path. Remaining work is verification (B1/B4/B2), not code.
