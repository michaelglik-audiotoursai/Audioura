# For Kiro Amazon-Q — Cloud Tasks Restructure Review

**Date:** 2026-06-07
**Scope:** Services/GCloud only.
**Verdict:** ✅ **The architecture is implemented correctly and matches the design** — job row created before enqueue, OIDC token attached, dispatch deadline set, thread-mode fallback, dual-mode, `/status` reads memory→DB. **But three real bugs need fixing before you rely on it** (one is invalid SQL that errors every run), plus the IAM that, if missing, makes every task 403. Part A fixes are good.

---

## Verified correct ✅
- Part A: join timeout 240s (< grace), `Retry-After: 5` on the 503. Good.
- Dispatch (`tour_orchestrator_service.py:1155-1170`): **creates the `job_status` row first** (1158), then enqueues (1159), with a **thread-mode fallback** if enqueue fails (1160-1170). Correct ordering — the worker's `UPDATE job_status` will find the row.
- Enqueue (`_enqueue_cloud_task`): attaches an **OIDC token** with `audience=TOUR_WORKER_URL` (198-201) and `dispatch_deadline=900s` (204). Correct.
- Worker (`tour_worker_service.py`): fully synchronous generation, progress written to `job_status`, returns 200/500 for Tasks retry. Clean. Dual-mode keeps local Docker unchanged.

---

## 🔴 Must-fix #1 — Worker is not idempotent; retries re-spend money
Cloud Tasks retries on 500 **and** when a task's HTTP response is lost (even after a *successful* run). `run_generation` re-executes the **entire** OpenAI + Polly pipeline on every retry. `store_audio_tour` dedups the row (UPDATE vs INSERT), so you won't get duplicate tour rows — but you **will pay for generation again** (~$0.30–1.10 wasted per retry), and overwrite a good tour.

**Fix:** guard at the top of `run_generation` — if the job is already `completed` in `job_status`, return success without re-running:
```python
def run_generation(job_id, ...):
    existing = _read_job_status(job_id)   # reuse the orchestrator's reader pattern
    if existing and existing.get('status') == 'completed':
        print(f"[WORKER] job {job_id} already completed — skipping (idempotent)")
        return True
    ...
```
This protects against the lost-response retry, which is the common case.

## 🔴 Must-fix #2 — Don't write `status=error` until the FINAL retry (your Q3)
Today the worker writes `status='error'` on *any* failure (line 381) and returns 500 → Cloud Tasks retries → a later attempt writes `completed`. But the **mobile app polls `/status`, sees `error` first, marks the tour failed and stops** — then the retry succeeds and the tour is actually fine. The user sees a failure that didn't happen.

**Fix:** read the retry count Cloud Tasks sends and only mark `error` on the last attempt; otherwise keep `processing` so the app keeps waiting:
```python
retry_count = int(request.headers.get('X-CloudTasks-TaskRetryCount', '0'))
MAX_ATTEMPTS = 3
...
# in the failure path:
if retry_count >= MAX_ATTEMPTS - 1:
    update_job_status(job_id, 'error', str(e), error=str(e))   # final attempt → real error
else:
    update_job_status(job_id, 'processing', f'Retrying after error: {e}')  # let Tasks retry
return jsonify({"status": "error"}), 500
```
This directly answers your Q3: **mark error only on retry exhaustion**, not on the first failure.

## 🔴 Must-fix #3 — Invalid SQL in the worker's Step 8 (silently fails every time)
`tour_worker_service.py:347-351`:
```sql
UPDATE tour_requests SET status='completed', finished_at=NOW()
WHERE secret_id=%s AND status IN ('started','processing')
ORDER BY started_at DESC LIMIT 1
```
**PostgreSQL `UPDATE` does not support `ORDER BY` / `LIMIT`.** This raises a syntax error on every call — it's swallowed by the surrounding `try/except`, so it *silently does nothing*. Use a subquery if you want "the most recent matching row":
```sql
UPDATE tour_requests SET status='completed', finished_at=NOW()
WHERE id = (SELECT id FROM tour_requests
            WHERE secret_id=%s AND status IN ('started','processing')
            ORDER BY started_at DESC LIMIT 1)
```
Or **remove this block entirely** — the mobile app already updates `tour_requests` via `POST /tour-status` (keyed on `tour_id`), so this worker-side update is redundant *and* currently broken.

---

## IAM — verify all three bindings or tasks fail (your Q5)
Document these in `setup_cloud_tasks_queue.sh`; if any is missing, enqueue or dispatch breaks:
1. **Worker accepts the task:** `WORKER_SERVICE_ACCOUNT` needs `roles/run.invoker` on `tour-worker`. *(Missing → worker 403s every task.)*
2. **Orchestrator can enqueue:** the orchestrator's runtime SA needs `roles/cloudtasks.enqueuer` on the queue. *(Missing → `create_task` permission-denied.)*
3. **Orchestrator can mint the OIDC token as that SA:** the orchestrator's runtime SA needs `roles/iam.serviceAccountUser` **on** `WORKER_SERVICE_ACCOUNT`. *(Missing → `create_task` fails when setting `oidc_token`.)*

(Yes — document all three in the script; the script + comments is sufficient, no `queue.yaml` needed — that's legacy App Engine. Make the script idempotent.)

---

## Answers to your other questions
- **Q1 (worker timeout 900s):** Reasonable for worst-case multi-language. One refinement (see Q2): set the worker `--timeout` **slightly below** the dispatch deadline.
- **Q2 (dispatch deadline = worker timeout):** You matched both at 900s — good direction, but make them **not exactly equal**: set worker `--timeout=840` and `dispatch_deadline=900`. If they're equal and a tour legitimately takes ~900s, Cloud Tasks may consider the dispatch expired and **retry while the worker is still finishing** → duplicate work. Give the deadline ~60s of headroom over the worker timeout.
- **Q4 (queue.yaml vs CLI):** The committed setup script is the right choice (version-controlled, idempotent); document the IAM in it. No `queue.yaml`.
- **Q5 (IAM):** Yes — see the three bindings above.

## Minor (non-blocking)
- The worker's `while True` poll loops (generator/modernized) have **no max-iteration cap** — they rely on the 900s request timeout as the only backstop. Add a `poll_count` ceiling so a hung sub-service fails fast instead of burning CPU to the deadline.
- **Translation failure is silent** (line 339-340): a user who requested RU/KO but whose translation fails gets the English tour with no notice. Acceptable for resilience, but consider recording it in `job_status` (e.g., `translation_failed: true`) so the app can tell the user.
- Confirm `_create_job_in_db` writes `output_data = '{}'` (non-null) — the `output_data || %s::jsonb` concat yields NULL if the column is NULL, which would drop all the worker's progress/extra fields.

---

## Bottom line
The restructure is well-built and the wiring (job-row-before-enqueue, OIDC, deadline, fallback, DB-backed status) is correct. **Before deploying to real use, fix the three bugs** — idempotency guard (#1, saves money on retries), error-only-on-final-retry (#2, your Q3, prevents false failures in the app), and the invalid `UPDATE … ORDER BY … LIMIT` (#3, fix or remove) — and **confirm the three IAM bindings** or every task 403s. Then run your test plan (enqueue → worker → DB status). This is the right launch architecture; these fixes make it correct under retries and concurrency.
