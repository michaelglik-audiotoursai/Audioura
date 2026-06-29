# For Kiro Amazon-Q — Cloud Tasks Bug Fixes Review

**Date:** 2026-06-07
**Scope:** Services/GCloud only.
**Verdict:** ✅ **All three must-fixes and the minors are correctly implemented — verified in code. Approve for deployment testing.** One small robustness note (keep the retry constant in sync with the queue) and a couple of deploy-time confirmations.

---

## Verified correct ✅
- **#1 Idempotency:** `_read_job_status` (208) + early-return when status `completed` (233-235). A lost-response retry now returns 200 without re-running OpenAI/Polly. Correct — this is the one that saves real money.
- **#2 Error-only-on-final-retry:** verified the full path. `run_generation` now **raises** on failure; `run_job` reads `X-CloudTasks-TaskRetryCount` (480), computes `is_final_attempt` (481), and writes `error` **only** on the final attempt (494-497) — otherwise keeps `processing` (500) and returns 500 to trigger a retry. This exactly fixes the "app sees error then a retry succeeds" problem. Clean.
- **#3 Invalid SQL:** the `UPDATE … ORDER BY … LIMIT` is replaced with the subquery form `WHERE id = (SELECT … ORDER BY … LIMIT 1)` (400). Valid Postgres now.
- **Minors:** `MAX_POLL_ITERATIONS=60` caps the generator/modernized poll loops (263/281/299/313); `translation_failed` flag recorded in `job_status` (366-423); `COALESCE(output_data,'{}'::jsonb) || …` (109/116) prevents the NULL-concat data loss; timeouts aligned (worker `--timeout=840`, dispatch deadline `900` → 60s headroom). All correct.
- **IAM:** all three bindings (`run.invoker` on worker, `cloudtasks.enqueuer` on queue, `iam.serviceAccountUser` on the invoker SA) documented idempotently in the setup script.

This is a solid, correct implementation of the retry-safe worker.

## Small robustness note
`MAX_TASK_ATTEMPTS = 3` in the worker must stay in sync with the queue's `--max-attempts=3`. If you ever change the queue's max-attempts without updating the constant, `is_final_attempt` goes wrong — either the app sees `error` too early (queue still has retries left) or never (queue exhausted first, but the worker thinks it isn't). Cheap fix: read it from an env var (`MAX_TASK_ATTEMPTS=int(os.getenv('MAX_TASK_ATTEMPTS','3'))`) and set it alongside the queue config. Non-blocking.

## Deploy-time confirmations (not code — verify during the test plan)
1. **The three IAM bindings actually applied** (the script documents them; confirm they took — a missing `run.invoker` → every task 403s; a missing `cloudtasks.enqueuer`/`serviceAccountUser` → enqueue fails). Test: enqueue one tour, check `gcloud tasks list` shows it dispatched and the worker logs show `[RUN-JOB]`.
2. **`tour_requests` subquery update works** end-to-end (a tour generated in cloud actually marks the row `completed`). Note this is secondary — the mobile app also updates via `/tour-status` — but now that it's valid SQL, confirm it's not double-updating in a confusing way (both setting `completed` is harmless/idempotent).
3. **Idempotency in practice:** force a retry (or simulate a lost response) and confirm the worker logs `already completed — skipping` rather than regenerating.

## Cross-team note (no action for you)
The new `translation_failed` flag in `job_status` is exactly what the mobile app needs to tell a RU/KO user "translation unavailable, showing English" instead of silently returning English. I'll make sure Mobile-AQ knows to read it — that's their side, not yours.

---

## Bottom line
Approve — all must-fixes and minors are correctly done and verified in `tour_worker_service.py`. Deploy to the test environment and run the plan, paying attention to the three IAM bindings actually taking effect (the most likely deploy-time snag) and a forced-retry idempotency check. Optionally env-drive `MAX_TASK_ATTEMPTS` so it can't drift from the queue config. This is ready for deployment testing.
