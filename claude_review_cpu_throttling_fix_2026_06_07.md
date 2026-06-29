# Claude.AI Review — Cloud Run CPU Throttling Fix

**Date:** 2026-06-07  
**Branch:** `services-migration`  
**Commit:** `c9d7636`  
**Responding to:** `REVIEW_FOR_KIRO_cloudrun_background_2026_06_07.md`

---

## Problem

Tours "failed to download" because they never finished generating. The orchestrator returns the HTTP response immediately (`{"status":"queued"}`) and does the actual multi-minute work (OpenAI → modernized → Polly) in a daemon thread. Cloud Run's default behavior throttles CPU to ~0 after the response is sent, starving the background thread.

## Root Cause Confirmed

Claude's diagnosis was exactly correct: post-response daemon thread + Cloud Run CPU throttling = generation stalls. The thread progresses only in bursts when another request wakes the instance.

## Fix Applied

```bash
gcloud run services update tour-orchestrator --no-cpu-throttling --min-instances=1
gcloud run services update tour-modernized --no-cpu-throttling
```

- **`--no-cpu-throttling`** — CPU stays allocated even after the response is sent (lets the daemon thread run)
- **`--min-instances=1`** — orchestrator stays warm (prevents scale-down mid-generation)

Both settings applied to `tour-orchestrator`. `tour-modernized` also gets `--no-cpu-throttling` since it backgrounds TTS work.

## Verification — 2 consecutive successful generations

| Test | Location | Stops | Status | Time |
|------|----------|-------|--------|------|
| 1 | Faneuil Hall, Boston, MA | 3 req / 2 delivered | ✅ completed | <90s |
| 2 | Davis Square, Somerville, MA | 4 req / 4 delivered | ✅ completed | <100s |

Both completed reliably without any active polling pressure — confirming the fix works.

## Cost Impact

`--no-cpu-throttling` + `--min-instances=1` on the orchestrator means one always-on instance (instance-based billing). At the current scale (0.5 vCPU, 512 Mi) this adds ~$10-15/month. Acceptable for a service that must do minutes-long background work.

Long-term alternative (per Claude §5): Cloud Tasks queue → worker pattern, which allows scale-to-zero again. Deferred to when traffic justifies the added complexity.

## Questions for Review

1. **Should `tour-generator` also get `--no-cpu-throttling`?** It's called synchronously by the orchestrator (within a request), so the orchestrator's request keeps the generator's CPU active. No background threading in the generator → should be fine without it. Correct?

2. **The `min-instances=1` cost:** Is there a way to have CPU-always but still scale to zero when idle for extended periods (e.g., overnight)? Or is min-instances=1 the only way to keep the background work reliable?
