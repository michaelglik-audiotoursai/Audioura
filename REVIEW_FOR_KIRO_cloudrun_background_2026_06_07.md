# For Kiro Amazon-Q — Why cloud tours don't reliably complete/download

**Date:** 2026-06-07
**Scope:** Services/GCloud only.
**TL;DR:** ✅ Your secret fixes are correct and real (the OpenAI value genuinely was wrong — `wpIWgo…`, not `sk-proj-…`; the AWS keys had `\r\n`). ❌ But the reason **tours still don't reliably finish/download** is almost certainly an architecture issue, not a secret: the orchestrator does generation in a **background daemon thread after returning the HTTP response**, and **Cloud Run throttles CPU to ~0 once the response is sent** — so the long generation work stalls intermittently. Fix = CPU-always-allocated + min-instances on the orchestrator.

---

## 1. Your secret fixes — correct, credit where due
- OpenAI: the stored value really was the wrong secret (156-char `wpIWgo…` vs a real 164-char `sk-proj-…`). That matches the `sk-` prefix red flag exactly. Re-storing the working local key + redeploy was right.
- AWS: the `\r\n` in the access key broke the SigV4 `Authorization` header → Polly 500s. Correct root cause and fix.
- `/user` route added → sync 200. Good.
These were real and are resolved. The remaining failure is downstream of them.

## 2. The real blocker — post-response background work on Cloud Run
`tour_orchestrator_service.py` `/generate-complete-tour`:
```python
# lines ~990-999
thread = threading.Thread(target=orchestrate_tour_async, ...)
thread.daemon = True
thread.start()
return jsonify({"job_id": job_id, "status": "queued", ...})   # returns immediately
```
The actual generation (OpenAI → modernized → Polly, **minutes** of work) runs in `orchestrate_tour_async` **on a daemon thread, after the response is already sent.**

**Cloud Run's default is request-scoped CPU:** once the HTTP response returns, the instance's CPU is throttled to near-zero until the next request hits *that* instance, and the instance can be scaled down. So that daemon thread:
- progresses only in bursts when another request happens to wake the instance, or
- stalls and never finishes, or
- is killed when the instance is reclaimed.

This is a textbook Cloud Run gotcha (Google's docs: "to run background tasks, set CPU to be always allocated"). It **exactly fits the symptom pattern**:
- You verified tour 343 completed — because the instance stayed warm while you were actively poking it.
- Sir Michael's tests "all fail to download" — the thread stalls after the response, the job never reaches `completed`, the app polls for minutes and gives up. The tour never finishes, so there's nothing to download.

The latest log is consistent: job `f087ec79` was `queued` at 14:41:54, and **~7.5 minutes later** the app was still polling `/status` (then hit a client DNS blip — see the separate mobile note). A 3-stop tour taking 7+ minutes with no completion is the signature of a CPU-throttled background thread.

## 3. Verify (quick)
For job `f087ec79-b401-4f12-a848-411d31b1ad42` (and the other failed test jobs), check `job_status` / the orchestrator's Cloud Run logs:
- Did it ever reach **`completed`**, or is it stuck at `queued`/`processing` with the last progress like "Waiting for tour text generation…"?
- If it's **stuck** (no `ORCHESTRATE_TOUR_ASYNC COMPLETED` log line ~line 756), that confirms the thread stalled → §4 fix.

## 4. Fix — make the orchestrator keep CPU for the background work
Targeted, immediate fix:
```bash
gcloud run services update tour-orchestrator --region=us-central1 \
  --no-cpu-throttling \      # CPU always allocated (lets the daemon thread run after response)
  --min-instances=1          # keep one warm instance so the work isn't reclaimed mid-task
```
(The orchestrator is already `max-instances=1` for the in-memory job store, so this keeps exactly one always-on instance.) **Apply the same check to any other service that does post-response background work** — in particular confirm whether **`tour-modernized`** also threads its TTS/ZIP work after responding; if so, it needs `--no-cpu-throttling` too. Polly/generator are called synchronously *within* a request, so they're fine.

Then **re-run several generations** (not just one) to confirm completion is now reliable, not warm-instance luck.

## 5. Better long-term (optional, larger change)
The robust pattern for minutes-long work on Cloud Run is a **real queue**: `/generate-complete-tour` enqueues to **Cloud Tasks** (or Pub/Sub) and returns the job id; a separate worker (Cloud Run service with CPU-always, or **Cloud Run Jobs**) processes it. That removes the dependency on keeping an instance warm and survives scale-down. CPU-always (§4) is the right fix to unblock now; the queue is the right end state before you have real traffic.

## 6. Cost note
`--no-cpu-throttling` + `--min-instances=1` means you pay for one always-on orchestrator instance (instance-based billing) rather than per-request. At db-f1-micro scale that's a modest add (single small instance), and it's the price of running background work this way. The Cloud-Tasks approach (§5) lets you drop back to scale-to-zero later.

---

## Bottom line
Your secret fixes were correct and necessary — those were real bugs. The remaining "tours don't complete/download" is the **post-response daemon-thread + Cloud Run CPU-throttling** problem: confirm `f087ec79` stalled, then set **`--no-cpu-throttling --min-instances=1` on `tour-orchestrator`** (and on `tour-modernized` if it also backgrounds work), and verify across several runs. A Cloud Tasks/Jobs queue is the proper long-term design. (The DNS error in the latest log is a separate client-side issue — covered in a note to Mobile-AQ.)
