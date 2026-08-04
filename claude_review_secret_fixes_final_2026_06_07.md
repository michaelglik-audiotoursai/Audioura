# Claude.AI Review — Secret Key Fixes (OpenAI + AWS)

**Date:** 2026-06-07  
**Branch:** `services-migration`  
**Status:** Tour generation with real audio verified working on cloud

---

## Issues Fixed

### 1. OpenAI API Key — wrong value in Secret Manager

**Problem:** Cloud generator returned "no stops could be generated" for every request. Same request succeeded locally.

**Root cause:** The value stored in Secret Manager `openai-api-key` was NOT an OpenAI key — it started with `wpIWgo` (156 chars). Real OpenAI keys start with `sk-proj-` (164 chars). The wrong value was stored during initial Secret Manager setup.

**Fix:** Extracted the working key from the local Docker container (`docker exec ... printenv OPENAI_API_KEY`) and stored it in Secret Manager using `[IO.File]::WriteAllText` (no newline) + `--data-file`. Redeployed `tour-generator` to pick up version 4.

**Verified:** PHASE 3A now succeeds, tour text generation completes, tour ID 343 generated with 3 stops.

### 2. AWS Keys — trailing `\r\n` in Secret Manager

**Problem:** Polly TTS returned 500 for every synthesis request. All MP3 files were 16-byte placeholders.

**Root cause:** Cloud Run logs showed `Invalid header value b'AWS4-HMAC-SHA256 Credential=AKIA[REDACTED-see-D81]\r\n/20260607/...'` — the AWS access key had a trailing carriage-return + newline. This made the HTTP Authorization header invalid, so boto3 couldn't authenticate to AWS Polly.

**Fix:** Same pattern — extracted from working local container, stored with `[IO.File]::WriteAllText` (no newline). Redeployed `polly-tts` and `tour-modernized`.

**Verified:** Tour 343 now has real MP3 audio files (700+ KB each, 2 MB total ZIP).

### 3. Gateway `/user` route missing

**Problem:** Mobile app `POST /user` returned 404. Gateway had `/user/<path:subpath>` but NOT `/user` alone.

**Fix:** Added `@app.route('/user', methods=['GET', 'POST', 'PUT'])` stub.

**Verified:** User sync returns 200.

---

## Verification Results

```
Tour generation:     ✅ Completed (ID 343, 3 stops, Harvard Square)
Audio (Polly TTS):   ✅ Real MP3 files (729KB + 732KB + 701KB)
Tour download:       ✅ 2,081,755 bytes (full ZIP with audio)
User sync:           ✅ POST /user → 200 {"status":"success"}
```

---

## Root Cause Pattern

All three Secret Manager issues (DB password, R2 keys, OpenAI key, AWS keys) had the same root cause: **trailing `\r\n` from Windows/PowerShell when piping to `gcloud secrets`**. The fix is always:

```powershell
# WRONG (adds newline):
echo "value" | gcloud secrets versions add secret-name --data-file=-

# RIGHT (no newline):
[System.IO.File]::WriteAllText("$env:TEMP\val.txt", "value")
gcloud secrets versions add secret-name --data-file="$env:TEMP\val.txt"
```

Or use the Google Cloud Console web UI (paste directly, no newline added).

---

## Services Image Versions (Current)

| Service | Image | Notes |
|---------|-------|-------|
| api-gateway | api-gateway:v7 | /user route, auth proxy |
| tour-orchestrator | audioura:v8 | All inter-service auth |
| tour-generator | audioura:v8 | PYTHONUNBUFFERED=1, correct OpenAI key |
| tour-modernized | audioura:v8 | Auth token for polly-tts |
| polly-tts | audioura:v6 | Correct AWS keys (v3 in Secret Manager) |
| map-delivery | audioura:v5 | R2 dual-read |
| translation-service | audioura:v5 | AWS keys via Secret Manager |
| coordinates | audioura:v5 | OpenAI key via Secret Manager |

---

## Cloud Tour Generation Pipeline — Fully Working

```
Mobile App → api.audioura.com (Cloudflare + LB)
  → api-gateway (API key check) 
    → tour-orchestrator (quota check + workflow)
      → tour-generator (OpenAI text) ✅
      → tour-modernized (polly-tts audio) ✅
        → polly-tts (AWS Polly synthesis) ✅
    → Cloud SQL (store tour) ✅
  → map-delivery (download from DB) ✅
```
