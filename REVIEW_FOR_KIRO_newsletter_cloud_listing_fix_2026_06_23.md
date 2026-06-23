# REVIEW_FOR_KIRO — Newsletter Cloud Listing Fix v2 (2026-06-23)

**Task:** ClickUp 86aj6k3d7 — "Cloud newsletter listing returns 0 — /newsletters_v2 empty after successful /process_newsletter"
**Status:** ✅ Fixed (round 2), deployed, verified live.
**Addresses:** Claude review `claude_review_newsletter_cloud_fix_2026_06_23.md` — all 3 concerns.

---

## Round 1 Fix (still in place)
- Replaced hardcoded Docker hostname with `NEWS_ORCHESTRATOR_URL` env var
- Added `_get_auth_headers()` OIDC for inter-service calls
- Deployed as `newsletter-processor-00006-5ht` on `audioura:v27`

## Round 2 Fix (this deployment)

### Concern 1 Answer: Where are the missing 6 articles?
Claude was right — processing is fully synchronous. The "missing 6" were **quota-denied** (429). Each article in a newsletter triggered a per-article quota check. A free-plan user with 10/week limit would exhaust quota after ~7 articles (some prior articles already counted). The 7/13 gap was NOT background processing — it was **silent quota exhaustion**.

### Concern 2 Fix: Newsletter quota fan-out
**Decision: one newsletter = one quota unit.** A single newsletter submission counts as one usage against the weekly quota, regardless of how many articles it contains.

**Implementation:**
1. `newsletter_processor_service.py` (~line 969): Added **batch-level quota check** at the start of `process_newsletter()`. If quota is exceeded, returns 429 immediately (before fetching/parsing the newsletter).
2. `newsletter_processor_service.py` (~line 2122): Payload now includes `'source': 'newsletter'` so the orchestrator knows this article is pre-authorized.
3. `news_orchestrator_service.py` (~line 83): When `source == 'newsletter'`, skips per-article quota check but still applies word-budget/narration capping.
4. `newsletter_processor_service.py` (~line 2200): If orchestrator ever returns 429, **breaks** out of the article loop (defense-in-depth, shouldn't happen now).

### Concern 3 Fix: Sibling processors
| File | Fix |
|------|-----|
| `subscription_article_processor.py` (line 15) | `NEWS_ORCHESTRATOR_URL = os.getenv(...)` — was hardcoded `http://news-orchestrator-1:5012` |
| `subscription_article_processor.py` (line 18–37) | Added `_get_auth_headers()` OIDC function |
| `subscription_article_processor.py` (line ~302) | Uses env-var URL + OIDC headers in `requests.post()` |
| `background_article_processor_service.py` (line 12) | Fixed port: `5012` (was `5009`) |
| `background_article_processor_service.py` (line 14–34) | Added `_get_auth_headers()` OIDC function |
| `background_article_processor_service.py` (line ~178) | Added auth headers to `request_audio_generation()` |

### Process fix: Committed to git
All changes committed in `services-migration` branch: `0a0d7a9`.

---

## Deployment

- **Image:** `audioura:v28`
- **Revisions:**
  - `news-orchestrator-00017-dgn` (quota bypass logic)
  - `newsletter-processor-00007-mhx` (batch quota + source flag)
- **Git commit:** `0a0d7a9` — "fix: newsletter quota fan-out + sibling processor cloud routing"

## Live Verification

**Test:** `POST /process_newsletter` with `test_mode=true`, user `USER-281301397` (tester plan)

**Before fix (Round 1, v27):**
```
articles_detected: 13, articles_created: 7, articles_failed: 0
(6 articles silently quota-denied — counted as created but no news_audios row)
```

**After fix (Round 2, v28):**
```
articles_detected: 13, articles_created: 13, articles_failed: 0
/newsletters_v2 → 3 newsletters (7+ articles completing TTS pipeline)
```

All 13 articles now enter the pipeline. Articles appear in `/newsletters_v2` as their TTS processing completes (the 4-table JOIN requires `news_audios` row from Polly TTS). This is expected — the listing grows over ~2–5 minutes as each article's audio is synthesized.

## Quota Design Summary

```
┌─────────────────────────────────────────────────────────────┐
│ App → /process_newsletter (newsletter_processor)             │
│   └─ Batch-level check: check_news_quota(user_id)           │
│      └─ If allowed → loop articles:                          │
│         └─ POST /generate-news { source: 'newsletter' }      │
│            └─ Orchestrator SKIPS per-article quota            │
│               (pre-authorized by batch check)                │
│                                                              │
│ App → /generate-news (direct, single article)                │
│   └─ Per-article check: check_news_quota(user_id)            │
│      └─ Each article counts as 1 quota unit                  │
└─────────────────────────────────────────────────────────────┘
```

Free plan: 10 news/week. A newsletter with 15 articles uses 1 of those 10 slots.
Direct single-article requests each consume 1 slot.
