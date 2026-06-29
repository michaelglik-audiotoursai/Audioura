# For Kiro Amazon-Q — CPU-Throttling/Shutdown Review + Cloud Tasks Restructure

**Date:** 2026-06-07
**Scope:** Services/GCloud only.
Two parts: (A) review of the CPU-throttling + graceful-shutdown changes (commit on `services-migration`), and (B) the **Cloud Tasks restructure** — which removes the ~$30/mo idle cost **and** is the only way to handle many concurrent customers without job-id confusion.

---

# PART A — CPU-throttling + graceful shutdown: ✅ correct interim, ship it

### Verified in code
- `--no-cpu-throttling --min-instances=1` on orchestrator (and `--no-cpu-throttling` on modernized) — correct; two consecutive generations completing in <100s confirms the throttling was the cause.
- Graceful-shutdown handler (`tour_orchestrator_service.py:130-149`): SIGTERM sets `_SHUTTING_DOWN`, joins live generation threads (≤300s), exits. Thread tracking at 1025-1027; new-request rejection (503) at 959. The logic is sound.

### Answers to your 3 questions
**Q1 — 300s join timeout too generous?** Set it **just under** the instance termination grace period, not equal to it. With `--no-cpu-throttling` Cloud Run grants ~300s grace; if your `join(timeout=300)` runs the full 300s, SIGKILL may fire before `sys.exit(0)` returns. Use **~240–270s** (or confirm `terminationGracePeriodSeconds` is >300). 180s is fine too given generations are reliably <100s — the only downside of a lower value is force-killing a genuinely stuck generation, which is acceptable. Not critical, just don't set join == grace.

**Q2 — cleanup only on new requests?** Fine as-is. The handler already re-filters live threads (`[t for t in … if t.is_alive()]`), so a stale list doesn't cause incorrect waits. The list can only grow between requests, and it's cleared on each new request — bounded. No periodic cleanup needed.

**Q3 — 503 + `Retry-After`?** Yes, add `Retry-After: 5` (or similar) to the shutdown 503. It's correct HTTP semantics and gives clients a back-off hint. (Heads-up for cross-team alignment: a 503 is an HTTP response, not a socket error, so the mobile poll-resilience won't auto-retry it unless it's taught to — that's a mobile item, noted separately. Adding `Retry-After` is still the right server-side move.)

### Two caveats on this interim fix
1. **Cost is higher than stated.** `--no-cpu-throttling --min-instances=1` bills a full always-on instance. For **0.5 vCPU / 512 MiB** that's ≈ **$30/month** (not $10–15); at 1 vCPU it's ≈ $60. It's a fixed cost regardless of tour volume.
2. **It does NOT scale to concurrent customers.** The orchestrator is pinned `max-instances=1` (for the in-memory `ACTIVE_JOBS` dict), and generations run as threads on that one small instance. Several customers generating at once would **contend for 0.5 vCPU** and serialize. You cannot raise `max-instances` while `ACTIVE_JOBS` is in memory (a `/status` poll could hit an instance that never saw the job → 404). So this is correct for **single-user testing**, but it is **not the launch architecture.**

Both caveats are solved by Part B.

---

# PART B — Restructure to Cloud Tasks + a worker service (the real fix)

**Goal:** scale-to-zero (no $30/mo idle) **and** true parallel multi-customer generation, with every job tracked by its unique `job_id` in the shared DB so the right result always goes to the right client.

### Why this also fixes the "job-id confusion across many customers" concern
The confusion risk is **not** that job_ids collide — each is a unique UUID returned to its own client. The risk is that job **state lives in one instance's memory**, so you can't run more than one instance. Move job state to the **shared DB (`DatabaseJobStore` / `job_status` table)** and *any* instance can answer *any* client's `/status/<job_id>` poll. Then you can run many workers in parallel, each generating a different customer's tour, with zero cross-talk.

### Target design
```
Mobile → api-gateway → tour-orchestrator (THIN, scale-to-zero)
   1. validate + quota check (entitlements)
   2. create job row in Cloud SQL (job_status) with job_id, status=queued
   3. enqueue a Cloud Task (payload = job_id + request) to the worker
   4. return {job_id, status:"queued"}     ← returns in ms

Cloud Tasks  ──HTTP push──►  tour-worker (Cloud Run service, scale 0→N)
   - does the FULL generation INSIDE the task's HTTP request
     (CPU is allocated during a request → no throttling, no min-instances)
   - writes progress/status to job_status as it goes
   - on success: stores tour, sets status=completed
   - Cloud Tasks auto-retries on failure (configurable)

Mobile → api-gateway → tour-orchestrator /status/<job_id>
   - reads job_status from Cloud SQL (DatabaseJobStore)
   - ANY instance can answer → safe to scale out
```

### Why this is faster *and* cheaper
- **Cheaper:** the worker only runs (and bills) while generating; it scales to zero between tours. The orchestrator can drop `--no-cpu-throttling`/`--min-instances=1` → the ~$30/mo idle cost goes away.
- **Faster under load:** Cloud Tasks dispatches concurrent tasks to multiple worker instances, so 10 customers generate on 10 workers in parallel instead of contending on one. Each worker gets full CPU for its request.
- **More reliable:** Tasks gives built-in retries and a dispatch deadline; a redeploy mid-task doesn't strand a job (it's re-dispatched), which also makes the graceful-shutdown handler less critical.

### Implementation steps
1. **Switch to `JOB_STORE_MODE=database`** on orchestrator + worker. The `DatabaseJobStore` you built (and we fixed to write through `.update()`) already supports this — this is the linchpin that makes multi-instance safe.
2. **Create a `tour-worker` Cloud Run service** that exposes `POST /run-job` (or reuse the existing generation code path), does the generation synchronously within the request, and updates `job_status`. Set `--timeout=900`, normal CPU (allocated during request), `--min-instances=0`, `--max-instances=N` (your desired concurrency), `--concurrency=1` (one tour per instance so they don't share CPU).
3. **Create a Cloud Tasks queue** (e.g. `tour-generation`) with rate/concurrency limits (e.g. max-dispatches-per-second + max-concurrent-dispatches) sized to your **OpenAI/Polly** rate limits so a burst of customers can't trip those APIs. The worker target is the `tour-worker` URL, authenticated with an OIDC token (Tasks supports adding an identity token — same IAM pattern you already use).
4. **Thin the orchestrator:** `/generate-complete-tour` does validate → quota → create job row → enqueue task → return `job_id`. Remove the daemon-thread generation. Then remove `--no-cpu-throttling`/`--min-instances=1` and let it scale to zero; you can raise `max-instances` since state is now in the DB.
5. **`/status/<job_id>`** reads from `DatabaseJobStore` (already does, once `JOB_STORE_MODE=database`).
6. **Entitlements stay in the orchestrator** at enqueue time (reject over-quota before spending a task), keyed on `user_id` — unchanged.

### Effort / sequencing
This is a moderate change (new worker service + Tasks queue + flip job store), maybe a day of work. It's not needed for your current single-user testing — the Part A band-aid is fine for that. But do it **before** you invite real/concurrent users, because the single-instance design can't serve them and you'd otherwise pay the $30/mo idle cost indefinitely. Recommended order: keep Part A now → build Part B before launch → then drop the always-on flags.

---

## Bottom line
**Part A is correct — ship it** (use a join timeout below the grace period; add `Retry-After` to the 503). It's the right fix for testing today. But it's a single always-on instance (~$30/mo, not $10–15) that **can't handle concurrent customers**. **Part B (Cloud Tasks → worker + `DatabaseJobStore`)** is the launch architecture: scale-to-zero (kills the idle cost), parallel multi-customer generation, and job state in the shared DB so the right tour always returns to the right client. Build it before opening to real users.
