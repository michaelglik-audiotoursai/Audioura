# Code Review — /news-download Language Fix (2026-06-24)

**Task:** ClickUp 86aj6yj5f
**Commit:** `eabd79a` on `services-migration`
**Image:** `audioura:v31`
**Revision:** `news-orchestrator-00021-fmk`

---

## Root Cause

`news_orchestrator_service.py` line ~250 called the translation service without OIDC auth headers:

```python
# BEFORE (line ~250):
translation_response = requests.post(
    f"{TRANSLATION_URL}/translate-with-audio",
    headers={"Content-Type": "application/json"},  # ← no auth!
    json=translation_data,
    timeout=120
)
```

On Cloud Run, the translation-service is `--no-allow-unauthenticated`. Without the OIDC token, the call returned **403**, which was caught by the `except` block and silently fell back to the English version. The article was served in English regardless of the `language` parameter.

## Fix

Added `_get_auth_headers(TRANSLATION_URL)` to the translation service call (1 line change):

```python
# AFTER:
translation_response = requests.post(
    f"{TRANSLATION_URL}/translate-with-audio",
    headers={**{"Content-Type": "application/json"}, **_get_auth_headers(TRANSLATION_URL)},
    json=translation_data,
    timeout=120
)
```

## Files Changed

| File | Line | Change |
|------|------|--------|
| `news_orchestrator_service.py` | ~250 | Added `**_get_auth_headers(TRANSLATION_URL)` to translation request headers |

## Verification

Tested the same article in 3 languages:

```
GET /news-download/2794355f-...?language=en → 2,672,909 bytes
GET /news-download/2794355f-...?language=ru → 2,055,663 bytes  ← different!
GET /news-download/2794355f-...?language=zh → 3,066,876 bytes  ← different!
```

Before fix: all three returned identical 2,672,909 bytes (English).
After fix: each language returns distinct content (correct translations with translated audio).
