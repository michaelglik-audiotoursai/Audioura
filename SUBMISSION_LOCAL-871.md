# SUBMISSION LOCAL-871 — keep the orchestrator instance alive while a job runs

Branch `LOCAL-871-keepalive` (base subscribed 2d1ec67e). Code only; nothing deployed.

## GCloud action: env vars for the ORCHESTRATOR service
| var | value |
|---|---|
| `SELF_URL` | the orchestrator's own public URL (e.g. `https://orchestrator-subscribed-<hash>.<region>.run.app`) — **required**, without it no keepalive runs |
| `K_SERVICE` | set automatically by Cloud Run (the keepalive refuses to run without it) |
| `KEEPALIVE_INTERVAL_SECONDS` | optional, default 45 |

The ping uses the existing `_authenticated_request`, so it sends an identity token when SELF_URL is https. If the service requires IAM auth, its own service account needs `run.invoker` on itself (same as for orchestrator→generator calls). Pre-existing `ORCH_RESUME_ENABLED=true` is still needed for LOCAL-821 resume.

## What changed (tour_orchestrator_service.py)
1. **Self keep-alive.** `orchestrate_tour_async` is now a thin wrapper around `_orchestrate_tour_async_impl` that registers the job in `_ACTIVE_RUNS` (try/finally, so errors also unregister; covers fresh jobs AND LOCAL-821 resumes). While ≥1 job is active a daemon thread GETs `$SELF_URL/health?keepalive=1` every 45 s and logs `[LOCAL-871] keepalive <n> jobs`; it exits (decided under the lock) when no jobs remain. Never starts without `K_SERVICE` + `SELF_URL`. `/health?keepalive=1` returns a trivial body (no ceiling/DB work).
2. **Generator stays busy.** Orchestrator polls generator status every 10 s (worst case 30 s timeout + 10 s sleep = 40 s) for the job's whole life, PHASE 5 included; modernized (audio) is polled every 5 s. Poller hardened: any `requests.RequestException` (not only Timeout/ConnectionError) and any HTTP 5xx is now a counted transient failure instead of killing the loop (same 30-failure / stall / 40 min caps). The generator does no work after the orchestrator's last poll (poll ends on `completed`), so no generator-side keepalive was added.
3. **SIGTERM.** Logs `[LOCAL-871] SIGTERM with N active jobs`, re-persists each job's generator_job_id to `orchestrator_jobs`, waits (existing 240 s), then releases the leases of unfinished jobs so the next instance resumes immediately rather than waiting out the 900 s lease.

### Is the checkpoint enough to resume without regenerating paid phases?
- **Text generation (the paid phase): yes.** `orchestrator_jobs` already holds the request params + `generator_job_id` (written right after /generate; re-written at SIGTERM). Resume re-attaches to the generator job (LOCAL-775 persisted result), no /generate.
- **Missing: the modernized/audio phase.** `modernized_job_id` is not persisted. A kill during audio makes the resume POST `/process` again (TTS re-spent). Fixing needs a new column on `orchestrator_jobs` (schema change) — deliberately not done here; suggest a follow-up ticket.

## Tests
`tests/test_local871_keepalive.py` (14, no DB/HTTP): starts/stops with jobs, stays while any job active, 45 s interval, no keepalive without K_SERVICE / SELF_URL, log line, ping URL + never raises, wrapper (incl. exception) unregisters, cheap health, SIGTERM log/checkpoint/lease release, poller survives ReadTimeout/ChunkedEncodingError/503 and still completes. LOCAL-821/829/833 suites still pass (32).

## Live (own containers, project `local871`, fake generator, $0 spend, K_SERVICE set, SELF_URL=http://tour-orchestrator:5002)
Job start 03:47:03; fake generator "processing" 100 s; modernized deliberately unreachable so the job ends in error. Orchestrator log:
```
[LOCAL-871] keepalive started (every 45s)
==== ORCHESTRATE_TOUR_ASYNC STARTED: 2026-11-06T03:47:03 ====
[LOCAL-871] keepalive 1 jobs
... "GET /health?keepalive=1 HTTP/1.1" 200   (03:47:48)
[LOCAL-871] keepalive 1 jobs
... "GET /health?keepalive=1 HTTP/1.1" 200   (03:48:33)
[LOCAL-871] keepalive stopped (no active jobs)     <- after the job ended; no lines afterwards
```
SIGTERM during a second job:
```
[LOCAL-871] SIGTERM with 1 active jobs
[LOCAL-871] checkpoint job 37863be6-...: generator_job_id=8acd1f00-...
[SHUTDOWN] SIGTERM received. Waiting for 1 in-flight generation(s) to complete (max 240s)...
```
Containers/volumes removed. TASK_BUDGET_ID=LOCAL-871, TASK_BUDGET_USD=0.20 set; actual spend $0 (no paid generator used). Not verified: real Cloud Run scale-in behaviour (needs GCloud wave).
