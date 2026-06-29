# REVIEW_FOR_KIRO — Integration Test Results (2026-06-10)

**Context:** Ran `test_news_quota_integration.py` against the live cloud deployment to verify the fail-closed quota enforcement.

---

## Test Execution

**T1 ran from local machine** against `https://api.audioura.com` (no DB access needed — pure HTTP assertions).

**T2 ran from Cloud Run job** (inside the cluster — has DB access via Cloud SQL unix socket + the `GATEWAY_API_KEY` secret to authenticate with the gateway).

---

## Results

| Test | Status | Method | Evidence |
|------|--------|--------|----------|
| **T1a**: missing `secret_id` → 401 | ✅ PASS | Local → gateway | HTTP 401 returned |
| **T1b**: `secret_id='anonymous'` → 401 | ✅ PASS | Local → gateway | HTTP 401 returned |
| **T2**: over quota → 429 | ✅ PASS | Cloud Run job → gateway | Response: `{"allowed": false, "error": "quota_exceeded", "limit": "news_per_period", "max": 1, "used": 1, "news_max_minutes": 10, "period": "week", "plan": "itest", "upgrade": true}` |
| T3: under quota → gate passes | ⬜ Skipped | Requires `--run-generate` (costs money) | — |
| T4: DB down → 503 | ⬜ Skipped | Requires operator to break DB | — |
| T5: long article truncated | ⬜ Skipped | Requires `--test-truncation` (costs money) | — |

---

## What Each Test Proves

**T1 (anonymous rejection):** The fail-closed guard at the top of `/generate-news` correctly rejects requests without a valid `secret_id`. No article is created, no downstream services are called. This prevents anonymous users from consuming resources.

**T2 (over-quota denial):** With a test plan limited to 1 news/week and 1 usage row seeded, the second request is correctly blocked with 429. The response includes `news_max_minutes: 10` (Change 2 from the spec), confirming the entitlement field is exposed. The gate returns BEFORE generation — no OpenAI/Polly costs are incurred.

---

## Test Infrastructure

The T2 test runs entirely inside GCP:
1. Cloud Run job connects to Cloud SQL (same as the services)
2. Seeds a test plan (`itest`, `news_per_period=1`) and test user (`ITEST-NEWS-QUOTA`)
3. Inserts 1 usage row to fill the quota
4. Calls the gateway (with API key from Secret Manager) to trigger the deny path
5. Asserts 429
6. Tears down all test data (plan, user, usage rows)

No test data persists after execution.

---

## Skipped Tests — Risk Assessment

| Test | Risk of not running | Mitigation |
|------|--------------------:|------------|
| T3 (under quota passes) | Low | T1+T2 prove the gate blocks correctly; if it blocks when it shouldn't, normal app usage would immediately fail — self-evidencing |
| T4 (DB down → 503) | Medium | Code inspection confirms the exception path returns 503 (same pattern as verified news path); manual test deferred to pre-launch checklist |
| T5 (truncation) | Low | `truncate_to_word_budget` is a pure function; unit-testable without cost. Integration proof deferred |

---

## How to Re-run

**T1 (from any machine with internet):**
```bash
python test_news_quota_integration.py --base-url https://api.audioura.com
```

**T2 (from Cloud Run job with DB+secrets):**
Already automated in `db-job/run.py` — rebuild and execute the Cloud Run job with `GATEWAY_API_KEY` secret attached.

**Full suite (local Docker, all tests):**
```bash
python test_news_quota_integration.py --local --run-generate --test-truncation
```
