# REVIEW_FOR_KIRO — News Processor → Polly TTS Auth Fix (2026-06-12)

**Context:** The news-processor's call to polly-tts was returning 403 — same missing OIDC token pattern as the orchestrator → generator fix. Applied the same `_get_auth_headers` pattern. News pipeline now works end-to-end on cloud.

---

## Problem

`news_processor_service.py` called the polly-tts Cloud Run service with bare `requests.post()` — no OIDC identity token. Cloud Run's IAM layer rejected it with 403 before the request ever reached the polly-tts application code.

Same root cause as the news-orchestrator fix (previous review), just one hop further down the chain.

---

## Fix

Added `_get_auth_headers(target_url)` to `news_processor_service.py` (identical helper to the one in news-orchestrator). Applied to both inter-service calls:

1. **Polly TTS call** (`POLLY_TTS_URL/synthesize`) — the blocking issue
2. **Voice Control call** (`VOICE_CONTROL_URL/generate_short_title`) — preemptive fix (same pattern)

```python
response = requests.post(
    f'{POLLY_TTS_URL}/synthesize',
    json={'text': clean_text, 'voice_id': 'Joanna', 'output_format': 'mp3'},
    headers=_get_auth_headers(POLLY_TTS_URL),  # ← added
    timeout=300
)
```

Local Docker compatibility preserved: `http://` URLs get no auth (empty dict).

---

## Live Verification

```
200: {"article_id":"f90f47f9-22b8-44ef-93b3-065385f6ad0c",
      "message":"News article processed successfully",
      "status":"success"}
```

Full pipeline confirmed working end-to-end:
- Gateway → news-orchestrator (quota check ✅)
- → news-generator (OIDC ✅, article processed)
- → news-processor (OIDC ✅)
- → polly-tts (OIDC ✅, TTS audio generated)
- → Result stored, 200 returned to client ✅

---

## Deployment

| Service | Revision | Image |
|---------|----------|-------|
| `news-processor` | `news-processor-00003-9c5` | `audioura:v24` |

---

## File Modified

| File | Change |
|------|--------|
| `development/news_processor_service.py` | Added `_get_auth_headers` + applied to polly-tts and voice-control calls |

---

## The Full News Inter-Service Auth Chain (now complete)

```
api-gateway (public, OIDC tokens minted via metadata server)
  → news-orchestrator (OIDC ✅)
    → news-generator (OIDC ✅, v23)
    → news-processor (OIDC ✅, v23)
      → polly-tts (OIDC ✅, v24)  ← this fix
      → voice-control (OIDC ✅, v24)
```

Every hop in the news pipeline now authenticates correctly on Cloud Run.
