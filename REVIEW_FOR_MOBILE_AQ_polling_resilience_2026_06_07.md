# For Mobile Amazon-Q — Make status polling resilient to transient network errors

**Date:** 2026-06-07
**Scope:** Flutter/Dart app code only.
**Context:** In `log_android_06072026_1454.txt`, a cloud generation was queued, then ~7.5 min later the status poll failed and the tour was marked failed — but the failure was a **transient client-side DNS error**, not a server failure.

---

## What the log shows
```
14:41:54  TOUR_REQUEST 200 → job f087ec79 queued
14:41:55  TOUR_TRACK 200
14:49:25  TOUR_STATUS error: Failed host lookup: 'api.audioura.com'
          (No address associated with hostname, errno = 7)  → /tour-status and /status
14:50:20  Connectivity to api.audioura.com/health → OK
```
The phone **temporarily couldn't resolve `api.audioura.com`** at 14:49 (DNS hiccup / network transition / doze during the long wait), then resolved it fine one minute later. A **single transient lookup failure during polling caused the whole tour to be marked `failed`.**

## The problem
Cloud generation takes minutes (the server side is being fixed separately). During that long poll, any one-off network/DNS blip currently aborts the flow and marks the tour failed — even though the server may still finish and the tour become downloadable. That makes generations look like they "all failed to download" when the real cause is a momentary network drop, not a missing tour.

## Recommended changes (status-poll resilience)
1. **Don't mark the tour `failed` on a transient network/DNS error.** Catch `SocketException` / `ClientException` (host-lookup failures, timeouts) separately from an actual server "error" status. On a transient error: log it, **keep polling** (with backoff), don't write `failed`.
2. **Retry with backoff** across the long generation window — e.g. keep polling for up to N minutes, tolerating intermittent failures, rather than giving up on the first one.
3. **On give-up, leave the job recoverable** — keep the `tour_id_$jobId` mapping and show "still generating — check My Tours shortly" instead of a hard failure, so a tour that completes server-side after the blip can still be picked up.
4. **(Optional) Re-check on app resume** — when the app returns to foreground, re-poll any in-flight job so a tour that finished while the phone was asleep/offline gets downloaded.

## Note
This is **not** the root cause of the broader "tours don't complete" issue — that's a server-side Cloud Run background-work problem being handled by Kiro. But even after that's fixed, generation will still take minutes, so making the poll survive transient network blips is needed for a reliable experience. The `/tour-status` `rows_affected: 0` concern is now resolved (Kiro added the `/user` route, and `TOUR_TRACK` returned 200 in this log).

## iOS correlation
Shared Dart — iOS inherits this once it lands; no separate change.

---

**Bottom line:** treat a transient `Failed host lookup` / `SocketException` during polling as "keep waiting," not "tour failed." Retry with backoff, keep the job recoverable, and re-check on resume.
