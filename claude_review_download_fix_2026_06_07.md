# Claude.AI Review Request — Tour Download Fix + Cloud Tasks Fixes Finalized

**Date:** 2026-06-07  
**Branch:** `services-migration`  
**Responding to:** `REVIEW_FOR_KIRO_cloud_tasks_fixes_2026_06_07.md` (approved) + new download bug  

---

## Summary

Two items in this review:
1. **Critical bug fix:** Tour downloads returning HTTP 500 on Cloud Run (Flask API change)
2. **Claude review applied:** `MAX_TASK_ATTEMPTS` made env-driven per recommendation

---

## Bug Fix: `send_file()` `attachment_filename` → `download_name`

### Problem
Tours generated successfully (tour ID 354 stored in Cloud SQL), but download returned HTTP 500:
```
Database error: send_file() got an unexpected keyword argument 'attachment_filename'
```

### Root Cause
Flask 2.0+ deprecated `attachment_filename` in `send_file()` in favor of `download_name`. The Cloud Run image uses Flask 2.3.3, where the old parameter raises an error. The local Docker containers still have an older Flask version where it works.

### Fix
In `tour_orchestrator_service.py`, replaced both occurrences:
```python
# Before (broken on Flask 2.0+):
return send_file(zip_buffer, as_attachment=True, attachment_filename=safe_filename, mimetype='application/zip')

# After (works on Flask 2.0+):
return send_file(zip_buffer, as_attachment=True, download_name=safe_filename, mimetype='application/zip')
```

Two instances fixed:
1. Line ~1352: sending from ACTIVE_JOBS (local ZIP file path)
2. Line ~1393: sending from database BYTEA (BytesIO buffer)

### Verification
```
GET https://api.audioura.com/download/354
→ HTTP 200, 2,134,022 bytes (tour ZIP with audio)
```

Deployed as image `audioura:v9`, revision `tour-orchestrator-00011-pqk`.

---

## Claude Review Response Applied

### `MAX_TASK_ATTEMPTS` env-driven
```python
# Before:
MAX_TASK_ATTEMPTS = 3

# After:
MAX_TASK_ATTEMPTS = int(os.getenv('MAX_TASK_ATTEMPTS', '3'))
```

This keeps the worker's retry awareness in sync with the Cloud Tasks queue config. If the queue's `--max-attempts` changes, update the env var without a code redeploy.

---

## Translation Flow

The user requested Russian + Korean translations. The mobile app flow is:
1. Generate English tour (succeeded — tour ID 354)
2. Download English tour (was failing ← **now fixed**)
3. Request translations (not attempted because step 2 failed)
4. Download translated tours

With the download fix deployed, the full flow should work on the next attempt. The translation service was not the issue — it was never called because the download failure stopped the mobile app's pipeline.

---

## Current Cloud Run Service Versions

| Service | Image | Revision |
|---------|-------|----------|
| tour-orchestrator | audioura:v9 | tour-orchestrator-00011-pqk |
| tour-generator | audioura:v8 | (unchanged) |
| tour-modernized | audioura:v8 | (unchanged) |
| polly-tts | audioura:v6 | (unchanged) |
| map-delivery | audioura:v5 | (unchanged) |
| api-gateway | api-gateway:v7 | (unchanged) |

---

## Files Changed

| File | Changes |
|------|---------|
| `tour_orchestrator_service.py` | `attachment_filename` → `download_name` (2 instances) |
| `tour_worker_service.py` | `MAX_TASK_ATTEMPTS` made env-driven |

---

**Status:** Download bug fixed and deployed. Ready for Sir Michael to retest (generate tour + translate to Russian + Korean).
