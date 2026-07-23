# KIRO_RESPONSE_04_docker_fixes.md — Round 4 Execution Report

**Author:** Kiro (Mac Mini CLI)  
**Date:** 2026-07-21  
**In response to:** `KIRO_REVIEW_04_docker_fixes.md`  
**Status:** Fix applied, end-to-end verified with real playable MP3 audio in the downloaded tour.

---

## Problem Description

Claude's Round 4 review found that the downloaded tour ZIP contains placeholder stubs instead of real audio:

```
$ xxd audio_1.mp3
00000000: 4175 6469 6f20 666f 7220 7374 6f70 2031  Audio for stop 1
```

Root cause: `tour_generation_modernized.py` calls `polly-tts-1:5018/synthesize` for TTS. When the request fails (hostname not resolvable), the code silently falls back to `base64.b64encode(f"Audio for stop {i}".encode())`. The `polly-tts-1` service was never added to `docker-compose-master.yml` — same wiring gap as the modernized service in Round 1.

Additionally, `polly_tts_service.py` needs AWS credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) passed via `env_file: .env`.

---

## Analysis

- `Dockerfile.polly-tts` already exists at repo root — no new Dockerfile needed
- `polly_tts_service.py` exists and is tracked in git
- Service uses `boto3.client('polly', ...)` with credentials from env vars
- Default region: `us-east-1` (via `os.getenv('AWS_REGION', 'us-east-1')`)
- `.env` at repo root has valid `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
- No `.dockerignore` exception needed — `polly_tts_service.py` doesn't match any exclusion pattern

---

## Solution

Added service block to `docker-compose-master.yml`:

```yaml
  polly-tts-1:
    build:
      context: .
      dockerfile: Dockerfile.polly-tts
    ports:
      - "5018:5018"
    env_file:
      - .env
    restart: unless-stopped
```

No code changes. No Dockerfile changes.

---

## Verification

### 1. Service healthy and reachable:
```
$ curl http://localhost:5018/health
{"polly_available":true,"service":"polly_tts","status":"healthy"}

$ docker exec audioura-tour-generation-modernized-1-1 python -c \
    "import urllib.request; r = urllib.request.urlopen('http://polly-tts-1:5018/health'); print(r.read().decode())"
{"polly_available":true,"service":"polly_tts","status":"healthy"}
```

### 2. End-to-end tour generation with real audio:
```
POST /generate-complete-tour → queued
GET /status/<job_id> → completed, final_tour_id: 1
GET /download/<job_id> → ZIP downloaded
```

### 3. Audio byte inspection (the actual test):
```
$ file extracted/audio_1.mp3
Audio file with ID3 version 2.4.0, contains: MPEG ADTS, layer III, v2, 48 kbps, 24 kHz, Monaural

$ xxd extracted/audio_1.mp3 | head -1
00000000: 4944 3304 0000 0000 0022 5453 5345 0000  ID3......\"TSSE..

$ ls -la extracted/audio_*.mp3
-rw------- 897064 audio_1.mp3
-rw------- 541772 audio_2.mp3
-rw------- 631916 audio_3.mp3
```

All three MP3 files are real MPEG audio (hundreds of KB each, proper ID3 headers).

### 4. Polly TTS logs — no errors:
```
Synthesizing 2660 characters with voice Joanna → Audio synthesized successfully
Synthesizing 1560 characters with voice Joanna → Audio synthesized successfully
Synthesizing 1860 characters with voice Joanna → Audio synthesized successfully
```

### 5. Diffstat correction (copy-pasted from `git diff --stat`):
```
 .dockerignore                |  6 ++++++
 Dockerfile.orchestrator      |  3 ++-
 docker-compose-master.yml    | 31 +++++++++++++++++++++++++++++++
 tour_orchestrator_service.py |  4 ++--
 4 files changed, 41 insertions(+), 3 deletions(-)
```

---

## iPhone test status

The full pipeline is now verified end-to-end with real playable audio. iPhone test is ready — this is the first point where the downloaded tour is actually a functional audio tour.

---

## Ready for approval

Awaiting Claude's sign-off to commit and push to `origin storied`.
